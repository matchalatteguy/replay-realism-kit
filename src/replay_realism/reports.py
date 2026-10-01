from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from replay_realism.assumptions import ExecutionAssumptionProfile
from replay_realism.fills import FillResult
from replay_realism.gates import QualityGateResult
from replay_realism.markout import MarkoutResult


@dataclass(frozen=True, slots=True)
class ReplayReport:
    assumptions: ExecutionAssumptionProfile
    fills: list[tuple[FillResult, MarkoutResult | None]]

    def to_dict(self) -> dict[str, Any]:
        fill_rows = []
        for fill, markout in self.fills:
            row = _fill_to_dict(fill)
            row["markout"] = _markout_to_dict(markout) if markout else None
            fill_rows.append(row)
        return {
            "schema_version": "replay-realism-report/v1",
            "assumptions": self.assumptions.to_dict(),
            "summary": {
                "fill_count": len(fill_rows),
                "filled_count": sum(1 for row in fill_rows if Decimal(row["filled_size"]) > 0),
                "fee_total": str(sum(Decimal(row["fee"]) for row in fill_rows)),
            },
            "fills": fill_rows,
        }


def write_json_report(report: ReplayReport | dict[str, Any], path: str | Path) -> None:
    data = report.to_dict() if isinstance(report, ReplayReport) else report
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_markdown_report(
    report: ReplayReport | dict[str, Any],
    path: str | Path,
    gates: list[QualityGateResult] | None = None,
) -> None:
    data = report.to_dict() if isinstance(report, ReplayReport) else report
    lines = ["# Replay Realism Review", ""]
    assumptions = data.get("assumptions") if isinstance(data, dict) else None
    assumptions = assumptions if isinstance(assumptions, dict) else {}
    summary = data.get("summary") if isinstance(data, dict) else None
    summary = summary if isinstance(summary, dict) else {}
    lines.append(f"Assumption profile: `{assumptions.get('name', 'missing')}`")
    lines.append(f"Safety level: `{assumptions.get('safety_level', 'missing')}`")
    lines.append(f"Fill count: {summary.get('fill_count', 0)}")
    lines.append(f"Filled count: {summary.get('filled_count', 0)}")
    lines.append(f"Fee total: {summary.get('fee_total', '0')}")
    lines.append("")
    if gates is not None:
        lines.extend(["## Quality gates", ""])
        for gate in gates:
            lines.append(
                f"- **{gate.severity.value.upper()}** `{gate.name}`: {gate.reason_code} — {gate.message}"
            )
        lines.append("")
    lines.extend(["## Fill rows", ""])
    rows = data.get("fills", []) if isinstance(data, dict) else []
    for fill in rows if isinstance(rows, list) else []:
        if not isinstance(fill, dict):
            lines.append("- Invalid fill row")
            continue
        lines.append(
            f"- `{fill.get('reason_code', 'missing')}` filled={fill.get('filled_size', 'missing')} remaining={fill.get('remaining_size', 'missing')} fee={fill.get('fee', 'missing')} evidence={str(fill.get('evidence', [])) or 'none'}"
        )
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fill_to_dict(fill: FillResult) -> dict[str, Any]:
    return {
        "instrument_id": fill.request.instrument_id,
        "side": fill.request.side.value,
        "order_type": fill.request.order_type.value,
        "arrival_timestamp": fill.arrival_timestamp,
        "execution_timestamp": fill.execution_timestamp,
        "filled_size": str(fill.filled_size),
        "remaining_size": str(fill.remaining_size),
        "average_price": str(fill.average_price) if fill.average_price is not None else None,
        "notional": str(fill.notional),
        "fee": str(fill.fee),
        "slippage": str(fill.slippage) if fill.slippage is not None else None,
        "reason_code": fill.reason_code,
        "evidence": fill.evidence,
    }


def _markout_to_dict(markout: MarkoutResult) -> dict[str, Any]:
    data = asdict(markout)
    data["midpoint"] = str(markout.midpoint) if markout.midpoint is not None else None
    data["edge_after_fees"] = (
        str(markout.edge_after_fees) if markout.edge_after_fees is not None else None
    )
    return data
