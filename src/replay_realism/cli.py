from __future__ import annotations

import argparse
import json
import shutil
from decimal import Decimal
from pathlib import Path

from replay_realism.assumptions import load_assumption_profile
from replay_realism.events import BookEvent, DecisionEvent, TradeEvent, load_events_csv
from replay_realism.fills import (
    BookSnapshot,
    FillRequest,
    OrderSide,
    OrderType,
    simulate_maker_fill,
    simulate_taker_fill,
)
from replay_realism.gates import gate_exit_code, validate_replay_report
from replay_realism.markout import compute_markout, future_midpoint
from replay_realism.reports import ReplayReport, write_json_report, write_markdown_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="replay-realism")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-events", help="Validate and sort a local events CSV")
    validate.add_argument("--events", required=True)
    simulate = sub.add_parser("simulate", help="Run a deterministic demo replay")
    simulate.add_argument("--events", required=True)
    simulate.add_argument("--assumptions", required=True)
    simulate.add_argument("--json-out", required=True)
    gate = sub.add_parser("gate", help="Gate a JSON replay report")
    gate.add_argument("--report", required=True)
    gate.add_argument("--md-out")
    init = sub.add_parser("init-example", help="Copy the bundled synthetic-book example")
    init.add_argument("name", choices=["synthetic-book"])
    init.add_argument("--out-dir", default="examples")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate-events":
        events = load_events_csv(args.events)
        print(f"validated {len(events)} events")
        return 0
    if args.command == "simulate":
        events = load_events_csv(args.events)
        assumptions = load_assumption_profile(args.assumptions)
        fills = _simulate_decisions(events, assumptions)
        report = ReplayReport(assumptions=assumptions, fills=fills)
        write_json_report(report, args.json_out)
        print(f"wrote {args.json_out}")
        return 0
    if args.command == "gate":
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        gates = validate_replay_report(report)
        if args.md_out:
            write_markdown_report(report, args.md_out, gates)
            print(f"wrote {args.md_out}")
        for gate in gates:
            print(f"{gate.severity.value}: {gate.name}: {gate.reason_code}")
        return gate_exit_code(gates)
    if args.command == "init-example":
        src = Path(__file__).resolve().parents[2] / "examples" / args.name
        dst = Path(args.out_dir) / args.name
        if dst.exists():
            raise SystemExit(f"refusing to overwrite existing example directory: {dst}")
        shutil.copytree(src, dst)
        print(f"copied {dst}")
        return 0
    raise AssertionError(args.command)


def _simulate_decisions(events, assumptions):
    book_events = [event for event in events if isinstance(event, BookEvent)]
    trade_events = [event for event in events if isinstance(event, TradeEvent)]
    decision_events = [event for event in events if isinstance(event, DecisionEvent)]
    outputs = []
    for decision in decision_events:
        request = FillRequest(
            instrument_id=decision.instrument_id,
            side=OrderSide(decision.side),
            order_type=OrderType(decision.order_type),
            size=decision.size,
            limit_price=decision.limit_price,
            decision_timestamp=decision.timestamp,
            queue_ahead=Decimal("1"),
        )
        arrival = decision.timestamp + assumptions.latency_ms
        if request.order_type == OrderType.TAKER:
            eligible_books = [book for book in book_events if book.instrument_id == decision.instrument_id and book.timestamp >= arrival]
            if eligible_books:
                event = min(eligible_books, key=lambda item: item.sort_key)
                book = BookSnapshot(
                    instrument_id=event.instrument_id,
                    timestamp=event.timestamp,
                    sequence=event.sequence,
                    bids=((event.bid_price, event.bid_size),),
                    asks=((event.ask_price, event.ask_size),),
                )
                fill = simulate_taker_fill(request, book, assumptions)
            else:
                fill = simulate_maker_fill(request, [], assumptions)
        else:
            fill = simulate_maker_fill(request, trade_events, assumptions)
        midpoint = future_midpoint(
            events, fill.arrival_timestamp, 100, instrument_id=fill.request.instrument_id
        )
        markout = compute_markout(fill, midpoint, horizon_ms=100)
        outputs.append((fill, markout))
    return outputs


if __name__ == "__main__":
    raise SystemExit(main())
