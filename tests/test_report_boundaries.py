"""Report gates must reject malformed or mislabeled inputs without crashing."""

import copy
import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest

from replay_realism.assumptions import ExecutionAssumptionProfile, load_assumption_profile
from replay_realism.cli import main
from replay_realism.events import BookEvent, DecisionEvent, TradeEvent, load_events_csv
from replay_realism.fees import FeeModel
from replay_realism.fills import FillPolicy, FillRequest, OrderSide, OrderType, simulate_maker_fill
from replay_realism.gates import gate_exit_code, validate_replay_report
from replay_realism.simulation import ReplaySimulationConfig, simulate_replay

ROOT = Path(__file__).parents[1]


def valid_report():
    events = load_events_csv(ROOT / "examples/synthetic-book/events.csv")
    profile = load_assumption_profile(ROOT / "examples/synthetic-book/assumptions.yaml")
    return simulate_replay(events, profile).to_dict()


@pytest.mark.parametrize(
    "report",
    [
        None,
        [],
        1,
        "report",
        {},
        {"assumptions": []},
        {"assumptions": "reviewable", "summary": [1], "fills": [None, "row", 5]},
    ],
)
def test_malformed_report_fails_without_exception(report):
    assert gate_exit_code(validate_replay_report(report)) == 1


@pytest.mark.parametrize("value", [True, "1", 1.2, None, -1, [], {}])
def test_fill_count_requires_an_actual_integer(value):
    report = valid_report()
    report["summary"]["fill_count"] = value
    assert gate_exit_code(validate_replay_report(report)) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("latency_ms", 0),
        ("latency_ms", True),
        ("stale_book_ms", 10_000),
        ("require_future_markout", False),
        ("require_future_markout", "true"),
        ("fee_model", {"name": "only-a-label"}),
        ("tick_size", "NaN"),
    ],
)
def test_serialized_reviewable_label_cannot_bypass_assumption_checks(field, value):
    report = valid_report()
    report["assumptions"][field] = value
    assert report["assumptions"]["safety_level"] == "reviewable"
    gates = validate_replay_report(report)
    assert gate_exit_code(gates) == 1
    assert any(g.reason_code == "optimistic-or-incomplete-assumptions" for g in gates)


@pytest.mark.parametrize(
    "field,value",
    [
        ("filled_size", "NaN"),
        ("filled_size", "Infinity"),
        ("filled_size", "-1"),
        ("filled_size", {}),
        ("side", ["buy"]),
        ("order_type", {}),
        ("evidence", "depth"),
        ("fee", "NaN"),
        ("average_price", "NaN"),
        ("arrival_timestamp", "1060"),
        ("execution_timestamp", 0),
    ],
)
def test_malformed_fill_fails_closed(field, value):
    report = valid_report()
    report["fills"][0][field] = value
    assert gate_exit_code(validate_replay_report(report)) == 1


@pytest.mark.parametrize(
    "markout",
    [
        None,
        "ok",
        {"reason_code": "ok"},
        {"reason_code": "ok", "midpoint": "100", "edge_after_fees": "NaN", "horizon_ms": 100},
        {"reason_code": "ok", "midpoint": "100", "edge_after_fees": "1", "horizon_ms": 0},
    ],
)
def test_reason_label_alone_does_not_validate_markout(markout):
    report = valid_report()
    report["fills"][0]["markout"] = markout
    assert gate_exit_code(validate_replay_report(report)) == 1


def test_summary_fee_and_filled_count_match_rows():
    report = valid_report()
    for field, value in (("fee_total", "999"), ("filled_count", 99)):
        broken = copy.deepcopy(report)
        broken["summary"][field] = value
        assert gate_exit_code(validate_replay_report(broken)) == 1


def test_delayed_maker_markout_follows_actual_execution():
    events = [
        DecisionEvent(
            100,
            1,
            "FOO",
            side="buy",
            size=Decimal("1"),
            limit_price=Decimal("100"),
            order_type="maker",
        ),
        BookEvent(210, 2, "FOO", bid_price=Decimal("99"), ask_price=Decimal("101")),
        TradeEvent(300, 3, "FOO", side="sell", price=Decimal("100"), size=Decimal("1")),
        BookEvent(400, 4, "FOO", bid_price=Decimal("102"), ask_price=Decimal("104")),
    ]
    profile = ExecutionAssumptionProfile("delayed", 10, 250, FeeModel.explicit_zero())
    fill, markout = simulate_replay(
        events, profile, ReplaySimulationConfig(Decimal("0"), 100)
    ).fills[0]
    assert fill.arrival_timestamp == 110
    assert fill.execution_timestamp == 300
    assert markout.midpoint == Decimal("103")


def test_maker_fill_or_kill_does_not_return_partial_fill():
    profile = ExecutionAssumptionProfile("fok", 10, 250, FeeModel.explicit_zero())
    request = FillRequest(
        "FOO",
        OrderSide.BUY,
        OrderType.MAKER,
        Decimal("2"),
        Decimal("100"),
        0,
        policy=FillPolicy.FOK,
    )
    trades = [TradeEvent(20, 1, "FOO", side="sell", price=Decimal("100"), size=Decimal("1"))]
    fill = simulate_maker_fill(request, trades, profile)
    assert fill.reason_code == "fok-not-filled"
    assert fill.filled_size == 0


@pytest.mark.parametrize(
    "yaml",
    [
        "- list\n- not-a-mapping\n",
        "name: nan\nlatency_ms: 5\nfee_model:\n  maker_bps: NaN\n  taker_bps: 1\n",
    ],
)
def test_invalid_yaml_shape_or_nonfinite_fees_are_rejected(tmp_path, yaml):
    path = tmp_path / "assumptions.yaml"
    path.write_text(yaml)
    with pytest.raises(ValueError):
        load_assumption_profile(path)


def test_gate_cli_reports_malformed_shape_and_can_write_review(tmp_path, capsys):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"assumptions": [], "fills": [None]}))
    markdown = tmp_path / "review.md"
    assert main(["gate", "--report", str(path), "--md-out", str(markdown)]) == 1
    assert "FAIL" in markdown.read_text()
    assert "Traceback" not in capsys.readouterr().err


def test_invalid_json_cli_has_clean_error(tmp_path, capsys):
    path = tmp_path / "report.json"
    path.write_text("broken JSON")
    assert main(["gate", "--report", str(path)]) == 2
    assert capsys.readouterr().err.startswith("error:")


def test_comparison_fixture_has_expected_cost_queue_and_latency_effects():
    script = ROOT / "examples/assumption-comparison/compare.py"
    spec = importlib.util.spec_from_file_location("comparison", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = module.comparison_rows()
    assert [row["edge_after_fees"] for row in rows] == ["1.60", "1.47992", "0.98991", "0"]
    assert [row["maker_size"] for row in rows] == ["2", "2", "1", "0"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("notional", "0"),
        ("fee", "0"),
        ("reason_code", "unfilled"),
        ("reason_code", "partial-fill"),
        ("remaining_size", "1"),
    ],
)
def test_gate_rejects_tampered_fill_arithmetic_even_with_matching_summary(field, value):
    report = valid_report()
    report["fills"][0][field] = value
    if field == "fee":
        report["summary"]["fee_total"] = "0"
    gates = validate_replay_report(report)
    assert gate_exit_code(gates) == 1
    assert any(g.reason_code == "fill-arithmetic-mismatch" for g in gates)


def test_gate_rejects_invented_markout_edge():
    report = valid_report()
    report["fills"][0]["markout"]["edge_after_fees"] = "999999999999"
    assert gate_exit_code(validate_replay_report(report)) == 1


def test_extreme_decimal_input_fails_closed_without_overflow():
    report = valid_report()
    report["fills"][0]["notional"] = "1e999999999"
    report["fills"][0]["fee"] = "1e999999999"
    report["summary"]["fee_total"] = "1e999999999"
    assert gate_exit_code(validate_replay_report(report)) == 1


def test_fractional_average_rounding_does_not_reject_valid_multilevel_fill():
    from replay_realism.fills import BookSnapshot, simulate_taker_fill
    from replay_realism.markout import compute_markout
    from replay_realism.reports import ReplayReport

    profile = ExecutionAssumptionProfile("weighted", 10, 250, FeeModel.explicit_zero())
    request = FillRequest("FOO", OrderSide.BUY, OrderType.TAKER, Decimal("3"), Decimal("101"), 0)
    book = BookSnapshot(
        "FOO",
        10,
        1,
        ((Decimal("99"), Decimal("5")),),
        ((Decimal("100"), Decimal("2")), (Decimal("101"), Decimal("1"))),
    )
    fill = simulate_taker_fill(request, book, profile)
    assert str(fill.average_price).startswith("100.333333")
    report = ReplayReport(profile, [(fill, compute_markout(fill, Decimal("102"), 100))]).to_dict()
    assert gate_exit_code(validate_replay_report(report)) == 0


def test_zero_latency_maker_cannot_use_trade_before_decision_sequence():
    events = [
        TradeEvent(100, 1, "FOO", side="sell", price=Decimal("100"), size=Decimal("1")),
        DecisionEvent(
            100,
            2,
            "FOO",
            side="buy",
            size=Decimal("1"),
            limit_price=Decimal("100"),
            order_type="maker",
        ),
    ]
    profile = ExecutionAssumptionProfile("zero-latency-baseline", 0, 250, FeeModel.explicit_zero())
    report = simulate_replay(events, profile, ReplaySimulationConfig(Decimal("0"), 100))
    assert report.fills[0][0].filled_size == 0


@pytest.mark.parametrize("horizon", [-100, 0, True, 1.5])
def test_future_midpoint_rejects_nonfuture_horizons(horizon):
    from replay_realism.markout import future_midpoint

    with pytest.raises(ValueError, match="positive integer"):
        future_midpoint([], 100, horizon)


def test_duplicate_report_members_are_clean_cli_parse_errors(tmp_path, capsys):
    path = tmp_path / "report.json"
    path.write_text('{"summary": {}, "summary": {"fill_count": 1}}')
    assert main(["gate", "--report", str(path)]) == 2
    assert "duplicate report member" in capsys.readouterr().err
