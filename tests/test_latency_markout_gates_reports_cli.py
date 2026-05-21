import json
from decimal import Decimal
from pathlib import Path

from replay_realism.assumptions import ExecutionAssumptionProfile
from replay_realism.cli import main
from replay_realism.events import BookEvent
from replay_realism.fees import FeeModel
from replay_realism.fills import FillRequest, FillResult, OrderSide, OrderType
from replay_realism.gates import gate_exit_code, validate_replay_report
from replay_realism.latency import FixedLatencyModel, apply_latency
from replay_realism.markout import compute_markout, future_midpoint
from replay_realism.reports import ReplayReport, write_json_report


def test_latency_and_future_only_markout() -> None:
    events = [BookEvent(timestamp=100, sequence=1, instrument_id="FOO", bid_price=Decimal("99"), ask_price=Decimal("101")), BookEvent(timestamp=200, sequence=2, instrument_id="FOO", bid_price=Decimal("100"), ask_price=Decimal("102"))]
    assert apply_latency(10, FixedLatencyModel(50)) == 60
    assert future_midpoint(events, 100, 50) == Decimal("101")


def test_reports_and_gates_pass(tmp_path: Path) -> None:
    assumptions = ExecutionAssumptionProfile("demo", 10, 250, FeeModel(Decimal("1"), Decimal("5")))
    request = FillRequest("FOO", OrderSide.BUY, OrderType.TAKER, Decimal("1"), Decimal("100"), 0)
    fill = FillResult(request, 10, Decimal("1"), Decimal("0"), Decimal("100"), Decimal("100"), Decimal("0.05"), Decimal("0"), "filled", ["depth@100:1"])
    markout = compute_markout(fill, Decimal("101"), 100)
    report = ReplayReport(assumptions, [(fill, markout)])
    path = tmp_path / "report.json"
    write_json_report(report, path)
    data = json.loads(path.read_text())
    gates = validate_replay_report(data)
    assert gate_exit_code(gates) == 0


def test_gate_fails_closed_when_required_markout_field_is_missing() -> None:
    report = {
        "assumptions": ExecutionAssumptionProfile("demo", 10, 250, FeeModel(Decimal("1"), Decimal("5"))).to_dict(),
        "summary": {"fill_count": 1},
        "fills": [{"reason_code": "filled", "markout": None}],
    }

    gates = validate_replay_report(report)

    assert gate_exit_code(gates) == 1
    assert any(gate.reason_code == "missing-future-markout" for gate in gates)


def test_cli_example_runs(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    report = tmp_path / "replay.json"
    md = tmp_path / "review.md"
    assert main(["validate-events", "--events", str(root / "examples/synthetic-book/events.csv")]) == 0
    assert main(["simulate", "--events", str(root / "examples/synthetic-book/events.csv"), "--assumptions", str(root / "examples/synthetic-book/assumptions.yaml"), "--json-out", str(report)]) == 0
    assert main(["gate", "--report", str(report), "--md-out", str(md)]) == 0
    assert md.exists()
