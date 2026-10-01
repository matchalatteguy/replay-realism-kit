from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, DecimalException, InvalidOperation, localcontext
from enum import StrEnum
from typing import Any

from replay_realism.assumptions import SafetyLevel, profile_from_mapping


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


def validate_replay_report(report: Any) -> list[QualityGateResult]:
    """Check report structure and internal consistency, without certifying real fills."""
    gates: list[QualityGateResult] = []
    if not isinstance(report, dict):
        return [_fail("report-shape", "report-not-object", "Report must be a JSON object.")]
    if report.get("schema_version") != "replay-realism-report/v1":
        gates.append(_fail("report-shape", "unsupported-schema", "Expected report schema v1."))
    assumptions = report.get("assumptions")
    assumptions = assumptions if isinstance(assumptions, dict) else {}
    summary = report.get("summary")
    if not isinstance(summary, dict):
        gates.append(_fail("report-shape", "summary-not-object", "Summary must be an object."))
        summary = {}
    fills = report.get("fills")
    if not isinstance(fills, list):
        gates.append(_fail("report-shape", "fills-not-list", "Report fills must be a list."))
        fills = []
    try:
        profile = profile_from_mapping(assumptions, require_complete=True)
    except (ValueError, TypeError):
        profile = None
    if (
        profile is not None
        and profile.safety_level == SafetyLevel.REVIEWABLE
        and assumptions.get("safety_level") == profile.safety_level.value
    ):
        gates.append(
            _pass(
                "assumption-profile",
                "reviewable-assumptions",
                "Typed assumptions satisfy the configured heuristic.",
            )
        )
    else:
        gates.append(
            _fail(
                "assumption-profile",
                "optimistic-or-incomplete-assumptions",
                "Assumptions are invalid, optimistic, or mislabeled.",
            )
        )
    if profile is not None:
        gates.append(_pass("fee-model", "explicit-fee-model", "Fee rates are finite and explicit."))
    else:
        gates.append(
            _fail("fee-model", "missing-fee-model", "Valid explicit fee rates are required.")
        )

    fill_count = summary.get("fill_count")
    if type(fill_count) is not int or fill_count < 0:
        gates.append(
            _fail(
                "report-consistency",
                "invalid-fill-count",
                "Summary fill_count must be a non-negative integer.",
            )
        )
    elif fill_count != len(fills):
        gates.append(
            _fail(
                "report-consistency",
                "summary-fill-count-mismatch",
                "Summary fill_count must match the number of fill rows.",
            )
        )

    rows = [row for row in fills if isinstance(row, dict)]
    if len(rows) != len(fills) or any(not _valid_fill(row) for row in rows):
        gates.append(
            _fail(
                "report-shape",
                "invalid-fill-row",
                "Fill rows must contain the documented typed v1 fields.",
            )
        )
    if profile is not None and any(not _consistent_fill(row, profile) for row in rows):
        gates.append(
            _fail(
                "report-consistency",
                "fill-arithmetic-mismatch",
                "Fill state, notional, configured fee, or markout arithmetic disagrees.",
            )
        )
    if rows:
        gates.append(
            _pass(
                "sample-count",
                "sufficient-sample-for-demo",
                "At least one decision result is present; no statistical test is implied.",
            )
        )
    else:
        gates.append(_fail("sample-count", "low-sample-count", "No decision results are present."))

    positive_rows = [row for row in rows if _is_filled_row(row)]
    if (
        summary.get("filled_count") != len(positive_rows)
        or type(summary.get("filled_count")) is not int
    ):
        gates.append(
            _fail(
                "report-consistency",
                "summary-filled-count-mismatch",
                "Summary filled_count must match positive filled sizes.",
            )
        )
    fees = [_decimal(row.get("fee")) for row in rows]
    total = _decimal(summary.get("fee_total"))
    if total is None or any(fee is None for fee in fees) or not _fee_total_matches(total, fees):
        gates.append(
            _fail(
                "report-consistency",
                "summary-fee-total-mismatch",
                "Summary fee_total must equal the finite row fees.",
            )
        )

    missing_markouts = [row for row in positive_rows if not _valid_markout(row.get("markout"))]
    if profile is None or (profile.require_future_markout and missing_markouts):
        gates.append(
            _fail(
                "future-markout",
                "missing-future-markout",
                "Filled rows require finite markouts at a positive future horizon.",
            )
        )
    else:
        gates.append(
            _pass(
                "future-markout",
                "future-only-markouts",
                "Markout fields are consistent; source event timing needs separate review.",
            )
        )
    if any(row.get("reason_code") == "stale-book" for row in rows):
        gates.append(
            _fail(
                "stale-book",
                "stale-book-used",
                "At least one decision lacked a book within the configured tolerance.",
            )
        )
    else:
        gates.append(
            _pass("stale-book", "no-stale-book-fills", "No stale-book rejection was reported.")
        )
    return gates


def gate_exit_code(gates: list[QualityGateResult]) -> int:
    return 1 if any(not gate.passed for gate in gates) else 0


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _valid_fill(row: dict[str, Any]) -> bool:
    required = {
        "instrument_id",
        "side",
        "order_type",
        "arrival_timestamp",
        "filled_size",
        "remaining_size",
        "average_price",
        "notional",
        "fee",
        "slippage",
        "reason_code",
        "evidence",
        "markout",
    }
    if required.difference(row):
        return False
    if not isinstance(row["instrument_id"], str) or not row["instrument_id"]:
        return False
    if row["side"] not in ("buy", "sell") or row["order_type"] not in ("maker", "taker"):
        return False
    if type(row["arrival_timestamp"]) is not int:
        return False
    if not isinstance(row["reason_code"], str) or not row["reason_code"]:
        return False
    if not isinstance(row["evidence"], list) or not all(
        isinstance(x, str) for x in row["evidence"]
    ):
        return False
    for name in ("filled_size", "remaining_size", "notional", "fee"):
        value = _decimal(row[name])
        if value is None or value < 0:
            return False
    for name in ("average_price", "slippage"):
        if row[name] is not None and _decimal(row[name]) is None:
            return False
    if _is_filled_row(row) and (
        row["average_price"] is None or _decimal(row["average_price"]) <= 0
    ):
        return False
    execution = row.get("execution_timestamp")
    return execution is None or (type(execution) is int and execution >= row["arrival_timestamp"])


def _close(actual: Decimal, expected: Decimal) -> bool:
    # Weighted average prices may be rounded; never use an absolute zero floor.
    scale = max(abs(actual), abs(expected))
    return abs(actual - expected) <= scale * Decimal("1e-24")


def _fee_total_matches(total: Decimal, fees: list[Decimal | None]) -> bool:
    try:
        with localcontext() as context:
            context.prec = 28
            return _close(total, sum((fee for fee in fees if fee is not None), Decimal("0")))
    except DecimalException:
        return False


def _consistent_fill(row: dict[str, Any], profile: Any) -> bool:
    if not _valid_fill(row):
        return False
    try:
        with localcontext() as context:
            context.prec = 28
            size = _decimal(row["filled_size"])
            remaining = _decimal(row["remaining_size"])
            notional = _decimal(row["notional"])
            fee = _decimal(row["fee"])
            price = _decimal(row["average_price"])
            reason = row["reason_code"]
            if size == 0:
                return (
                    reason not in ("filled", "partial-fill")
                    and price is None
                    and notional == 0
                    and fee == 0
                )
            if reason != ("filled" if remaining == 0 else "partial-fill"):
                return False
            if not _close(notional, size * price):
                return False
            expected_fee = profile.fee_model.fee_for(notional, row["order_type"])
            if not _close(fee, expected_fee):
                return False
            markout = row.get("markout")
            if _valid_markout(markout):
                midpoint = _decimal(markout["midpoint"])
                edge = _decimal(markout["edge_after_fees"])
                direction = Decimal("1") if row["side"] == "buy" else Decimal("-1")
                expected_edge = (midpoint - price) * direction * size - fee
                if not _close(edge, expected_edge):
                    return False
            return True
    except (DecimalException, TypeError):
        return False


def _valid_markout(markout: Any) -> bool:
    if not isinstance(markout, dict):
        return False
    midpoint = _decimal(markout.get("midpoint"))
    edge = _decimal(markout.get("edge_after_fees"))
    horizon = markout.get("horizon_ms")
    return (
        markout.get("reason_code") == "ok"
        and midpoint is not None
        and midpoint > 0
        and edge is not None
        and type(horizon) is int
        and horizon > 0
    )


def _is_filled_row(fill: dict[str, Any]) -> bool:
    size = _decimal(fill.get("filled_size"))
    if size is None:
        return fill.get("reason_code") in ("filled", "partial-fill")
    return size > 0


def _pass(name: str, reason_code: str, message: str) -> QualityGateResult:
    return QualityGateResult(name, GateSeverity.PASS, reason_code, message)


def _fail(name: str, reason_code: str, message: str) -> QualityGateResult:
    return QualityGateResult(name, GateSeverity.FAIL, reason_code, message)
