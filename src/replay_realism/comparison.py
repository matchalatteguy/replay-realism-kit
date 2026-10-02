"""Deterministic named-profile comparisons and bounded Cartesian sensitivity sweeps."""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import re
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from replay_realism.arithmetic import reference_arithmetic
from replay_realism.assumptions import ExecutionAssumptionProfile, profile_from_mapping
from replay_realism.events import DecisionEvent, ReplayEvent, sort_events
from replay_realism.gates import validate_replay_report
from replay_realism.serialization import load_unique_yaml
from replay_realism.simulation import ReplaySimulationConfig, simulate_replay

MAX_SCENARIOS = 64
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
CSV_FIELDS = (
    "name",
    "decision_count",
    "filled_count",
    "markout_count",
    "markout_coverage",
    "fee_total",
    "edge_after_fees",
    "gate_failure_count",
    "delta_filled_count",
    "delta_fee_total",
    "delta_edge_after_fees",
)


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    assumptions: ExecutionAssumptionProfile
    config: ReplaySimulationConfig

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not NAME.fullmatch(self.name):
            raise ValueError("scenario name must be a short slug")
        if not isinstance(self.assumptions, ExecutionAssumptionProfile) or not isinstance(
            self.config, ReplaySimulationConfig
        ):
            raise ValueError("scenario requires typed assumptions and simulation settings")


@dataclass(frozen=True, slots=True)
class ScenarioStudy:
    baseline: str
    quote_unit: str
    scenarios: tuple[Scenario, ...]

    def __post_init__(self) -> None:
        if not all(isinstance(scenario, Scenario) for scenario in self.scenarios):
            raise ValueError("study requires typed Scenario objects")
        object.__setattr__(self, "scenarios", tuple(self.scenarios))
        names = [scenario.name for scenario in self.scenarios]
        if not names or len(names) > MAX_SCENARIOS or len(set(names)) != len(names):
            raise ValueError(f"study requires 1-{MAX_SCENARIOS} uniquely named scenarios")
        if self.baseline not in names:
            raise ValueError("baseline must name an included profile")
        if not isinstance(self.quote_unit, str) or not self.quote_unit.strip():
            raise ValueError("quote_unit must declare the common unit used for fees and markouts")


def _keys(data: Any, allowed: set[str], name: str) -> dict[str, Any]:
    if not isinstance(data, dict) or set(data).difference(allowed):
        raise ValueError(f"{name} must be an object using only: {', '.join(sorted(allowed))}")
    return data


def _queue(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("maker_queue_ahead must be finite and non-negative")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("maker_queue_ahead must be a decimal") from exc
    if not number.is_finite() or number < 0:
        raise ValueError("maker_queue_ahead must be finite and non-negative")
    return number


def load_scenarios(path: str | Path) -> ScenarioStudy:
    data = load_unique_yaml(Path(path).read_text(encoding="utf-8"))
    data = _keys(data, {"schema_version", "baseline", "quote_unit", "profiles", "sweep"}, "study")
    if data.get("schema_version") != "replay-realism-scenarios/v1":
        raise ValueError("expected scenario schema replay-realism-scenarios/v1")
    profiles = data.get("profiles")
    if not isinstance(profiles, list) or not profiles or len(profiles) > MAX_SCENARIOS:
        raise ValueError("profiles must be a non-empty list")
    scenarios = []
    for profile in profiles:
        profile = _keys(profile, {"name", "assumptions", "simulation"}, "profile")
        name = profile.get("name")
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise ValueError("profile name must be a short slug")
        assumptions = _keys(
            profile.get("assumptions"),
            {
                "latency_ms",
                "stale_book_ms",
                "tick_size",
                "min_size",
                "allow_partial_fills",
                "require_future_markout",
                "fee_model",
                "description",
            },
            "assumptions",
        )
        _keys(
            assumptions.get("fee_model"),
            {"name", "maker_bps", "taker_bps", "explicit_zero_fees"},
            "fee_model",
        )
        typed = profile_from_mapping({**assumptions, "name": name}, require_complete=True)
        settings = _keys(
            profile.get("simulation", {}),
            {
                "maker_queue_ahead",
                "markout_horizon_ms",
                "maker_lifetime_ms",
                "markout_max_delay_ms",
            },
            "simulation",
        )
        config = ReplaySimulationConfig(
            **{**settings, "maker_queue_ahead": _queue(settings.get("maker_queue_ahead", "1"))}
        )
        scenarios.append(Scenario(name, typed, config))
    if len({scenario.name for scenario in scenarios}) != len(scenarios):
        raise ValueError("profile names must be unique")
    if "sweep" in data:
        sweep = _keys(
            data["sweep"],
            {"profile", "latency_ms", "maker_queue_ahead", "maker_lifetime_ms"},
            "sweep",
        )
        base = next(
            (scenario for scenario in scenarios if scenario.name == sweep.get("profile")), None
        )
        if base is None:
            raise ValueError("sweep.profile must name a base profile")
        if len(sweep) == 1:
            raise ValueError("sweep must declare at least one sensitivity axis")
        axes = []
        for name, default in (
            ("latency_ms", base.assumptions.latency_ms),
            ("maker_queue_ahead", base.config.maker_queue_ahead),
            ("maker_lifetime_ms", base.config.maker_lifetime_ms),
        ):
            values = sweep.get(name, [default])
            if not isinstance(values, list) or not values:
                raise ValueError(f"sweep.{name} must be a non-empty list")
            if name == "maker_queue_ahead":
                values = [_queue(value) for value in values]
            elif any(
                type(value) is not int or value < (0 if name == "latency_ms" else 1)
                for value in values
            ):
                raise ValueError(f"sweep.{name} contains invalid integer values")
            if len(set(values)) != len(values):
                raise ValueError(f"sweep.{name} contains duplicate values")
            axes.append(values)
        if len(scenarios) + len(axes[0]) * len(axes[1]) * len(axes[2]) > MAX_SCENARIOS:
            raise ValueError(f"sweep exceeds the {MAX_SCENARIOS}-scenario limit")
        for latency, queue, lifetime in itertools.product(*axes):
            name = f"{base.name}.latency-{latency}.queue-{queue}.lifetime-{lifetime}"
            scenarios.append(
                Scenario(
                    name,
                    replace(base.assumptions, name=name, latency_ms=latency),
                    replace(base.config, maker_queue_ahead=queue, maker_lifetime_ms=lifetime),
                )
            )
    return ScenarioStudy(data.get("baseline"), data.get("quote_unit"), tuple(scenarios))


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    fills = report["fills"]
    filled = [row for row in fills if Decimal(row["filled_size"]) > 0]
    marked = [
        row
        for row in filled
        if row["markout"] is not None and row["markout"]["reason_code"] == "ok"
    ]
    # Never turn missing evidence into a zero markout or label a partial sum as a total.
    edge = (
        str(sum((Decimal(row["markout"]["edge_after_fees"]) for row in marked), Decimal("0")))
        if len(marked) == len(filled) and filled
        else None
    )
    markets = {}
    for row in fills:
        key = (row["instrument_id"], row["venue_id"])
        values = markets.setdefault(
            key, {"requested_size": Decimal("0"), "filled_size": Decimal("0")}
        )
        values["requested_size"] += Decimal(row["requested_size"])
        values["filled_size"] += Decimal(row["filled_size"])
    return {
        "decision_count": len(fills),
        "filled_count": len(filled),
        "markout_count": len(marked),
        "markout_coverage": str(Decimal(len(marked)) / len(filled)) if filled else None,
        "fee_total": report["summary"]["fee_total"],
        "edge_after_fees": edge,
        "rejection_counts": report["summary"]["rejection_counts"],
        "instruments": [
            {
                "instrument_id": instrument,
                "venue_id": venue,
                "requested_size": str(values["requested_size"]),
                "filled_size": str(values["filled_size"]),
                "fill_ratio": str(values["filled_size"] / values["requested_size"]),
            }
            for (instrument, venue), values in sorted(markets.items())
        ],
    }


@reference_arithmetic
def compare_scenarios(events: list[ReplayEvent], study: ScenarioStudy) -> dict[str, Any]:
    ordered = sort_events(list(events))
    results = []
    for scenario in study.scenarios:
        report = simulate_replay(ordered, scenario.assumptions, scenario.config).to_dict()
        gates = validate_replay_report(report)
        results.append(
            {
                "name": scenario.name,
                "assumptions": report["assumptions"],
                "config": scenario.config.to_dict(),
                "summary": _summary(report),
                "gates": [
                    {
                        "name": gate.name,
                        "severity": gate.severity.value,
                        "reason_code": gate.reason_code,
                        "message": gate.message,
                    }
                    for gate in gates
                ],
                "gate_failure_count": sum(not gate.passed for gate in gates),
                "report": report,
            }
        )
    baseline = next(result["summary"] for result in results if result["name"] == study.baseline)
    for result in results:
        summary = result["summary"]
        result["delta_from_baseline"] = {
            "filled_count": summary["filled_count"] - baseline["filled_count"],
            "fee_total": str(Decimal(summary["fee_total"]) - Decimal(baseline["fee_total"])),
            "edge_after_fees": str(
                Decimal(summary["edge_after_fees"]) - Decimal(baseline["edge_after_fees"])
            )
            if summary["edge_after_fees"] is not None and baseline["edge_after_fees"] is not None
            else None,
        }
    study_payload = [
        {"name": row["name"], "assumptions": row["assumptions"], "config": row["config"]}
        for row in results
    ]
    return {
        "schema_version": "replay-realism-comparison/v1",
        "engine_version": "0.3.0",
        "baseline": study.baseline,
        "quote_unit": study.quote_unit,
        "order_model": "independent",
        "event_count": len(ordered),
        "decision_count": sum(isinstance(event, DecisionEvent) for event in ordered),
        "scenario_count": len(results),
        "gate_failure_count": sum(row["gate_failure_count"] for row in results),
        "study_sha256": hashlib.sha256(
            json.dumps(
                {
                    "baseline": study.baseline,
                    "quote_unit": study.quote_unit,
                    "profiles": study_payload,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest(),
        "scenarios": results,
    }


def write_comparison_csv(report: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in report["scenarios"]:
            summary, delta = row["summary"], row["delta_from_baseline"]
            writer.writerow(
                {
                    "name": row["name"],
                    **{key: summary[key] for key in CSV_FIELDS[1:7]},
                    "gate_failure_count": row["gate_failure_count"],
                    "delta_filled_count": delta["filled_count"],
                    "delta_fee_total": delta["fee_total"],
                    "delta_edge_after_fees": delta["edge_after_fees"],
                }
            )


def write_comparison_markdown(report: dict[str, Any], path: str | Path) -> None:
    lines = [
        "# Execution assumption comparison",
        "",
        f"Baseline: `{report['baseline']}`. Quote unit: {report['quote_unit']}.",
        f"{report['event_count']} events; {report['decision_count']} independent decisions; {report['scenario_count']} scenarios.",
        "",
        "| Scenario | Filled decisions | Markout coverage | Fees | Complete markout after fees | Failed gates |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report["scenarios"]:
        summary = row["summary"]
        lines.append(
            f"| {row['name']} | {summary['filled_count']}/{summary['decision_count']} | "
            f"{summary['markout_coverage'] if summary['markout_coverage'] is not None else 'n/a'} | "
            f"{summary['fee_total']} | {summary['edge_after_fees'] if summary['edge_after_fees'] is not None else 'unavailable'} | {row['gate_failure_count']} |"
        )
    lines.extend(
        [
            "",
            "Missing markouts remain unavailable, rather than becoming zero. Quantities are reported per instrument in JSON.",
            "All scenarios replay the same decisions independently; liquidity is not shared. Fees and edges assume the declared common quote unit.",
            "The sweep exposes sensitivity; it does not select an optimal strategy, estimate real fills, or establish statistical adequacy.",
            "",
            "## Rejections and gate failures",
            "",
        ]
    )
    for row in report["scenarios"]:
        reasons = (
            ", ".join(
                f"{name}={count}" for name, count in row["summary"]["rejection_counts"].items()
            )
            or "none"
        )
        failed = (
            ", ".join(gate["reason_code"] for gate in row["gates"] if gate["severity"] == "fail")
            or "none"
        )
        lines.append(f"- `{row['name']}`: rejections {reasons}; failed gates {failed}.")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
