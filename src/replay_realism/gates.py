from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any


class GateSeverity(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class QualityGateResult:
    name: str
    severity: GateSeverity
    reason_code: str
    message: str

    @property
    def passed(self) -> bool:
        return self.severity != GateSeverity.FAIL


def validate_replay_report(report: dict[str, Any]) -> list[QualityGateResult]:
    gates: list[QualityGateResult] = []
    assumptions = report.get("assumptions") or {}
    summary = report.get("summary") or {}
    fills = report.get("fills") or []

    if not isinstance(fills, list):
        gates.append(_fail("report-shape", "fills-not-list", "Report fills must be a list."))
        fills = []

    if assumptions.get("safety_level") == "reviewable":
        gates.append(
            _pass(
                "assumption-profile",
                "reviewable-assumptions",
                "Assumptions are explicit and reviewable.",
            )
        )
    else:
        gates.append(
            _fail(
                "assumption-profile",
                "optimistic-or-incomplete-assumptions",
                "Assumptions are not reviewable.",
            )
        )

    if (assumptions.get("fee_model") or {}).get("name"):
        gates.append(_pass("fee-model", "explicit-fee-model", "Fee model is explicit."))
    else:
        gates.append(
            _fail("fee-model", "missing-fee-model", "Report must include an explicit fee model.")
        )

    summary_fill_count = int(summary.get("fill_count", len(fills)) or 0)
    if summary_fill_count != len(fills):
        gates.append(
            _fail(
                "report-consistency",
                "summary-fill-count-mismatch",
                "Summary fill_count must match the number of fill rows.",
            )
        )

    sample_count = len(fills)
    if sample_count >= 1:
        gates.append(
            _pass(
                "sample-count", "sufficient-sample-for-demo", "At least one fill result is present."
            )
        )
    else:
        gates.append(_fail("sample-count", "low-sample-count", "No fill results are present."))

    missing_markouts = [
        fill for fill in fills if _is_filled_row(fill) and _markout_reason(fill) != "ok"
    ]
    if assumptions.get("require_future_markout") and missing_markouts:
        gates.append(
            _fail(
                "future-markout",
                "missing-future-markout",
                "All filled rows need future-only markouts.",
            )
        )
    else:
        gates.append(
            _pass(
                "future-markout",
                "future-only-markouts",
                "Future-only markouts are present or not required.",
            )
        )

    stale = [fill for fill in fills if fill.get("reason_code") == "stale-book"]
    if stale:
        gates.append(
            _fail("stale-book", "stale-book-used", "At least one fill referenced a stale book.")
        )
    else:
        gates.append(_pass("stale-book", "no-stale-book-fills", "No stale-book fills were used."))
    return gates


def gate_exit_code(gates: list[QualityGateResult]) -> int:
    return 1 if any(not gate.passed for gate in gates) else 0


def _markout_reason(fill: dict[str, Any]) -> str | None:
    markout = fill.get("markout")
    if not isinstance(markout, dict):
        return None
    reason = markout.get("reason_code")
    return str(reason) if reason is not None else None


def _is_filled_row(fill: dict[str, Any]) -> bool:
    raw_size = fill.get("filled_size")
    if raw_size is not None:
        try:
            return Decimal(str(raw_size)) > 0
        except (InvalidOperation, ValueError):
            return True
    return fill.get("reason_code") in {"filled", "partial-fill"}


def _pass(name: str, reason_code: str, message: str) -> QualityGateResult:
    return QualityGateResult(name, GateSeverity.PASS, reason_code, message)


def _fail(name: str, reason_code: str, message: str) -> QualityGateResult:
    return QualityGateResult(name, GateSeverity.FAIL, reason_code, message)
