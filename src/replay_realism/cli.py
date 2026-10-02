from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from decimal import Decimal, DecimalException, InvalidOperation
from pathlib import Path

import yaml

from replay_realism.assumptions import load_assumption_profile
from replay_realism.comparison import (
    compare_scenarios,
    load_scenarios,
    write_comparison_csv,
    write_comparison_markdown,
)
from replay_realism.events import load_events
from replay_realism.gates import gate_exit_code, validate_replay_report
from replay_realism.reports import write_json_report, write_markdown_report
from replay_realism.simulation import ReplaySimulationConfig, simulate_replay


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="replay-realism")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-events", help="Validate and sort local CSV or JSONL events")
    validate.add_argument("--events", required=True)
    simulate = sub.add_parser(
        "simulate", help="Replay independent decisions with causal market evidence"
    )
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
    simulate.add_argument("--maker-lifetime-ms", type=_non_negative_int, default=1000)
    simulate.add_argument("--markout-max-delay-ms", type=_non_negative_int, default=1000)
    compare = sub.add_parser("compare", help="Compare named profiles and bounded scenario sweeps")
    compare.add_argument("--events", required=True)
    compare.add_argument("--scenarios", required=True)
    compare.add_argument("--json-out", required=True)
    compare.add_argument("--csv-out")
    compare.add_argument("--md-out")
    gate = sub.add_parser("gate", help="Gate a JSON replay report")
    gate.add_argument("--report", required=True)
    gate.add_argument("--md-out")
    init = sub.add_parser("init-example", help="Copy a bundled synthetic example")
    init.add_argument("name", choices=["synthetic-book", "execution-stress"])
    init.add_argument("--out-dir", default="examples")
    return parser


def _non_negative_decimal(raw: str) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"expected a decimal, got {raw!r}") from exc
    if not value.is_finite() or value < 0:
        raise argparse.ArgumentTypeError("value must be finite and non-negative")
    return value


def _non_negative_int(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected an integer, got {raw!r}") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return value


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except (OSError, ValueError, DecimalException, UnicodeError, yaml.YAMLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _run(args: argparse.Namespace) -> int:
    if args.command == "validate-events":
        events = load_events(args.events)
        print(f"validated {len(events)} events")
        return 0
    if args.command == "simulate":
        _check_paths([args.events, args.assumptions], [args.json_out])
        events = load_events(args.events)
        assumptions = load_assumption_profile(args.assumptions)
        config = ReplaySimulationConfig(
            maker_queue_ahead=args.maker_queue_ahead,
            markout_horizon_ms=args.markout_horizon_ms,
            maker_lifetime_ms=args.maker_lifetime_ms,
            markout_max_delay_ms=args.markout_max_delay_ms,
        )
        report = simulate_replay(events, assumptions, config)
        write_json_report(report, args.json_out)
        print(f"wrote {args.json_out}")
        return 0
    if args.command == "compare":
        _check_paths([args.events, args.scenarios], [args.json_out, args.csv_out, args.md_out])
        events = load_events(args.events)
        study = load_scenarios(args.scenarios)
        report = compare_scenarios(events, study)
        report["events_sha256"] = hashlib.sha256(Path(args.events).read_bytes()).hexdigest()
        write_json_report(report, args.json_out)
        if args.csv_out:
            write_comparison_csv(report, args.csv_out)
        if args.md_out:
            write_comparison_markdown(report, args.md_out)
        print(
            f"compared {report['scenario_count']} scenarios; {report['gate_failure_count']} failed gates"
        )
        return 1 if report["gate_failure_count"] else 0
    if args.command == "gate":
        _check_paths([args.report], [args.md_out])
        report = _load_report(Path(args.report))
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


def _check_paths(inputs: list[str], outputs: list[str | None]) -> None:
    sources = {Path(value).resolve() for value in inputs}
    targets = [Path(value).resolve() for value in outputs if value is not None]
    if len(targets) != len(set(targets)) or sources.intersection(targets):
        raise ValueError("output paths must be distinct and cannot replace input files")


def _load_report(path: Path) -> object:
    def object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate report member: {key!r}")
            result[key] = value
        return result

    def invalid_constant(value: str) -> object:
        raise ValueError(f"non-standard JSON constant: {value}")

    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=object_pairs,
        parse_constant=invalid_constant,
    )


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
