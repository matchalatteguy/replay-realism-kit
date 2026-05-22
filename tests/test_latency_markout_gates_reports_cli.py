import json
from decimal import Decimal
from pathlib import Path

import pytest

from replay_realism.assumptions import ExecutionAssumptionProfile, load_assumption_profile
from replay_realism.cli import main
from replay_realism.events import BookEvent
from replay_realism.fees import FeeModel
from replay_realism.fills import FillRequest, FillResult, OrderSide, OrderType
from replay_realism.gates import gate_exit_code, validate_replay_report
from replay_realism.latency import FixedLatencyModel, apply_latency
from replay_realism.markout import compute_markout, future_midpoint
from replay_realism.reports import ReplayReport, write_json_report


def test_latency_and_future_only_markout() -> None:
    events = [
        BookEvent(
            timestamp=100,
            sequence=1,
            instrument_id="FOO",
            bid_price=Decimal("99"),
            ask_price=Decimal("101"),
        ),
        BookEvent(
            timestamp=200,
            sequence=2,
            instrument_id="FOO",
            bid_price=Decimal("100"),
            ask_price=Decimal("102"),
        ),
    ]
    assert apply_latency(10, FixedLatencyModel(50)) == 60
    assert future_midpoint(events, 100, 50) == Decimal("101")


def test_future_midpoint_can_be_scoped_to_fill_instrument() -> None:
    events = [
        BookEvent(
            timestamp=150,
            sequence=1,
            instrument_id="BAR",
            bid_price=Decimal("49"),
            ask_price=Decimal("51"),
        ),
        BookEvent(
            timestamp=200,
            sequence=2,
            instrument_id="FOO",
            bid_price=Decimal("99"),
            ask_price=Decimal("101"),
        ),
    ]

    midpoint = future_midpoint(events, 100, 50, instrument_id="FOO")

    assert midpoint == Decimal("100")


def test_reports_and_gates_pass(tmp_path: Path) -> None:
    assumptions = ExecutionAssumptionProfile("demo", 10, 250, FeeModel(Decimal("1"), Decimal("5")))
    request = FillRequest("FOO", OrderSide.BUY, OrderType.TAKER, Decimal("1"), Decimal("100"), 0)
    fill = FillResult(
        request,
        10,
        Decimal("1"),
        Decimal("0"),
        Decimal("100"),
        Decimal("100"),
        Decimal("0.05"),
        Decimal("0"),
        "filled",
        ["depth@100:1"],
    )
    markout = compute_markout(fill, Decimal("101"), 100)
    report = ReplayReport(assumptions, [(fill, markout)])
    path = tmp_path / "report.json"
    write_json_report(report, path)
    data = json.loads(path.read_text())
    assert data["schema_version"] == "replay-realism-report/v1"
    assert data["assumptions"]["description"] == ""
    gates = validate_replay_report(data)
    assert gate_exit_code(gates) == 0


def test_assumption_yaml_rejects_string_booleans(tmp_path: Path) -> None:
    config = tmp_path / "assumptions.yaml"
    config.write_text(
        """
name: bad-bool
latency_ms: 10
stale_book_ms: 250
allow_partial_fills: "false"
require_future_markout: true
fee_model:
  name: explicit
  maker_bps: 1
  taker_bps: 5
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="allow_partial_fills must be a YAML boolean"):
        load_assumption_profile(config)


def test_gate_fails_closed_when_summary_fill_count_exceeds_rows() -> None:
    report = {
        "assumptions": ExecutionAssumptionProfile(
            "demo", 10, 250, FeeModel(Decimal("1"), Decimal("5"))
        ).to_dict(),
        "summary": {"fill_count": 1},
        "fills": [],
    }

    gates = validate_replay_report(report)

    assert gate_exit_code(gates) == 1
    assert any(gate.reason_code == "summary-fill-count-mismatch" for gate in gates)


def test_gate_fails_closed_when_required_markout_field_is_missing() -> None:
    report = {
        "assumptions": ExecutionAssumptionProfile(
            "demo", 10, 250, FeeModel(Decimal("1"), Decimal("5"))
        ).to_dict(),
        "summary": {"fill_count": 1},
        "fills": [{"reason_code": "filled", "markout": None}],
    }

    gates = validate_replay_report(report)

    assert gate_exit_code(gates) == 1
    assert any(gate.reason_code == "missing-future-markout" for gate in gates)


def test_gate_exempts_unfilled_rows_from_required_markout() -> None:
    report = {
        "assumptions": ExecutionAssumptionProfile(
            "demo", 10, 250, FeeModel(Decimal("1"), Decimal("5"))
        ).to_dict(),
        "summary": {"fill_count": 1},
        "fills": [
            {"reason_code": "insufficient-crossable-depth", "filled_size": "0", "markout": None}
        ],
    }

    gates = validate_replay_report(report)

    assert gate_exit_code(gates) == 0


@pytest.mark.parametrize(
    "argv, expected",
    [
        (["--help"], "validate-events"),
        (["validate-events", "--help"], "--events"),
        (["simulate", "--help"], "--markout-horizon-ms"),
        (["gate", "--help"], "--report"),
        (["init-example", "--help"], "synthetic-book"),
    ],
)
def test_cli_help_surfaces_public_commands(
    argv: list[str], expected: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(argv)

    assert exc_info.value.code == 0
    assert expected in capsys.readouterr().out


def test_cli_example_runs(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    report = tmp_path / "replay.json"
    md = tmp_path / "review.md"
    assert (
        main(["validate-events", "--events", str(root / "examples/synthetic-book/events.csv")]) == 0
    )
    assert (
        main(
            [
                "simulate",
                "--events",
                str(root / "examples/synthetic-book/events.csv"),
                "--assumptions",
                str(root / "examples/synthetic-book/assumptions.yaml"),
                "--json-out",
                str(report),
                "--maker-queue-ahead",
                "0",
                "--markout-horizon-ms",
                "100",
            ]
        )
        == 0
    )
    assert main(["gate", "--report", str(report), "--md-out", str(md)]) == 0
    assert md.exists()


def test_cli_rejects_invalid_simulation_knobs(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "simulate",
                "--events",
                str(root / "examples/synthetic-book/events.csv"),
                "--assumptions",
                str(root / "examples/synthetic-book/assumptions.yaml"),
                "--json-out",
                str(tmp_path / "replay.json"),
                "--maker-queue-ahead",
                "-1",
            ]
        )

    assert exc_info.value.code == 2


def test_init_example_copies_fixture_and_refuses_overwrite(tmp_path: Path) -> None:
    out_dir = tmp_path / "starter"

    assert main(["init-example", "synthetic-book", "--out-dir", str(out_dir)]) == 0

    copied = out_dir / "synthetic-book"
    assert (copied / "events.csv").exists()
    assert (copied / "assumptions.yaml").exists()
    assert (copied / "README.md").exists()
    assert main(["validate-events", "--events", str(copied / "events.csv")]) == 0
    try:
        main(["init-example", "synthetic-book", "--out-dir", str(out_dir)])
    except SystemExit as exc:
        assert "refusing to overwrite" in str(exc)
    else:  # pragma: no cover - defensive clarity for the assertion above
        raise AssertionError("init-example overwrote an existing fixture")
