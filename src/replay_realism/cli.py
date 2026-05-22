from __future__ import annotations

import argparse
import json
import shutil
from decimal import Decimal, InvalidOperation
from pathlib import Path

from replay_realism.assumptions import load_assumption_profile
from replay_realism.events import load_events_csv
from replay_realism.gates import gate_exit_code, validate_replay_report
from replay_realism.reports import write_json_report, write_markdown_report
from replay_realism.simulation import ReplaySimulationConfig, simulate_replay


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="replay-realism")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-events", help="Validate and sort a local events CSV")
    validate.add_argument("--events", required=True)
    simulate = sub.add_parser("simulate", help="Run a deterministic demo replay")
    simulate.add_argument("--events", required=True)
    simulate.add_argument("--assumptions", required=True)
    simulate.add_argument("--json-out", required=True)
    simulate.add_argument(
        "--maker-queue-ahead",
        type=_non_negative_decimal,
        default=Decimal("1"),
        help="Synthetic maker queue size ahead of each maker decision (default: 1)",
    )
    simulate.add_argument(
        "--markout-horizon-ms",
        type=_non_negative_int,
        default=100,
        help="Future midpoint horizon used for markouts (default: 100)",
    )
    gate = sub.add_parser("gate", help="Gate a JSON replay report")
    gate.add_argument("--report", required=True)
    gate.add_argument("--md-out")
    init = sub.add_parser("init-example", help="Copy the bundled synthetic-book example")
    init.add_argument("name", choices=["synthetic-book"])
    init.add_argument("--out-dir", default="examples")
    return parser


def _non_negative_decimal(raw: str) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"expected a decimal, got {raw!r}") from exc
    if value < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return value


def _non_negative_int(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected an integer, got {raw!r}") from exc
    if value < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return value


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate-events":
        events = load_events_csv(args.events)
        print(f"validated {len(events)} events")
        return 0
    if args.command == "simulate":
        events = load_events_csv(args.events)
        assumptions = load_assumption_profile(args.assumptions)
        config = ReplaySimulationConfig(
            maker_queue_ahead=args.maker_queue_ahead,
            markout_horizon_ms=args.markout_horizon_ms,
        )
        report = simulate_replay(events, assumptions, config)
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
        src = _example_source_dir(args.name)
        dst = Path(args.out_dir) / args.name
        if dst.exists():
            raise SystemExit(f"refusing to overwrite existing example directory: {dst}")
        shutil.copytree(src, dst)
        print(f"copied {dst}")
        return 0
    raise AssertionError(args.command)


def _example_source_dir(name: str) -> Path:
    """Return the bundled example path in source trees and built wheels."""
    package_example = Path(__file__).resolve().parent / "examples" / name
    if package_example.exists():
        return package_example
    source_tree_example = Path(__file__).resolve().parents[2] / "examples" / name
    if source_tree_example.exists():
        return source_tree_example
    raise SystemExit(f"bundled example is missing from the package: {name}")


if __name__ == "__main__":
    raise SystemExit(main())
