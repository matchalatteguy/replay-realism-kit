from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, DecimalException, InvalidOperation, localcontext
from enum import StrEnum
from typing import Any

from replay_realism.arithmetic import reference_arithmetic
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


@reference_arithmetic
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
    expected_marks = sum(_is_filled_row(row) and _valid_markout(row.get("markout")) for row in rows)
    expected_rejections = dict(
        Counter(row["reason_code"] for row in rows if _valid_fill(row) and not _is_filled_row(row))
    )
    if (
        "markout_count" in summary
        and (
            type(summary["markout_count"]) is not int or summary["markout_count"] != expected_marks
        )
    ) or (
        "rejection_counts" in summary
        and (
            not isinstance(summary["rejection_counts"], dict)
            or summary["rejection_counts"] != expected_rejections
            or any(type(value) is not int for value in summary["rejection_counts"].values())
        )
    ):
        gates.append(
            _fail(
                "report-consistency",
                "summary-evidence-count-mismatch",
                "Markout or rejection counts disagree with result rows.",
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
    config = report.get("simulation_config")
    if config is not None:
        if not _valid_config(config):
            gates.append(
                _fail(
                    "execution-evidence",
                    "invalid-simulation-config",
                    "Simulation configuration is invalid.",
                )
            )
        elif profile is not None and any(
            not _execution_consistent(row, profile, config) for row in rows
        ):
            gates.append(
                _fail(
                    "execution-evidence",
                    "execution-trace-mismatch",
                    "Trace quantities, causal timing, expiry, or markout timing disagree.",
                )
            )
        else:
            gates.append(
                _pass(
                    "execution-evidence",
                    "consistent-execution-trace",
                    "Trace accounting and declared timing are internally consistent.",
                )
            )
    if config is not None:
        incomplete = any(row.get("completion_reason") == "incomplete-evidence" for row in rows)
        gates.append(
            _fail(
                "maker-observation",
                "incomplete-maker-window",
                "Market evidence ends before an uncompleted maker order expires.",
            )
            if incomplete
            else _pass(
                "maker-observation",
                "complete-maker-windows",
                "Maker orders fill or have evidence through exclusive expiry.",
            )
        )
        if any(row.get("reason_code") == "no-book-at-arrival" for row in rows):
            gates.append(
                _fail(
                    "arrival-book",
                    "missing-arrival-book",
                    "A taker decision has no causally available book.",
                )
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
                expected_edge = (midpoint * size - notional) * direction - fee
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


def _valid_config(config: Any) -> bool:
    if not isinstance(config, dict):
        return False
    queue = _decimal(config.get("maker_queue_ahead"))
    return (
        queue is not None
        and queue >= 0
        and all(
            type(config.get(name)) is int and config[name] > 0
            for name in ("maker_lifetime_ms", "markout_horizon_ms", "markout_max_delay_ms")
        )
    )


def _execution_consistent(row: dict[str, Any], profile: Any, config: dict[str, Any]) -> bool:
    if not _valid_fill(row):
        return False
    try:
        with localcontext() as context:
            context.prec = 28
            requested = _decimal(row.get("requested_size"))
            limit = _decimal(row.get("limit_price"))
            size = _decimal(row["filled_size"])
            remaining = _decimal(row["remaining_size"])
            decision = row.get("decision_timestamp")
            sequence = row.get("decision_sequence")
            arrival = row["arrival_timestamp"]
            execution = row.get("execution_timestamp")
            if (
                limit is None
                or limit <= 0
                or requested is None
                or requested <= 0
                or not _close(requested, size + remaining)
                or type(decision) is not int
                or type(sequence) is not int
                or sequence < 0
                or arrival != decision + profile.latency_ms
            ):
                return False
            if row.get("queue_ahead") != config["maker_queue_ahead"]:
                return False
            trace = row.get("trace")
            if not isinstance(trace, list):
                return False
            if row["order_type"] == "maker":
                expiry = row.get("expiry_timestamp")
                end = row.get("observation_end_timestamp")
                completion = row.get("completion_reason")
                if expiry != arrival + config["maker_lifetime_ms"]:
                    return False
                # Request-constraint rejection needs no market window; all attempted makers do.
                rejected = row["reason_code"] in (
                    "min-size-violation",
                    "tick-size-violation",
                    "non-positive-request",
                    "invalid-request-number",
                    "invalid-request",
                )
                if not rejected:
                    if end is not None and type(end) is not int:
                        return False
                    expected_completion = (
                        "filled"
                        if remaining == 0
                        else "expired"
                        if end is not None and end >= expiry
                        else "incomplete-evidence"
                    )
                    if completion != expected_completion:
                        return False
            filled_quantity = Decimal("0")
            consumed_queue = Decimal("0")
            filled_notional = Decimal("0")
            available = {}
            consumed = {}
            execution_times = []
            previous_source_key = None
            source_prices = {}
            for item in trace:
                if not isinstance(item, dict) or item.get("kind") not in ("queue", "fill"):
                    return False
                quantity = _decimal(item.get("quantity"))
                price = _decimal(item.get("price"))
                liquidity = _decimal(item.get("available_quantity"))
                source_price = _decimal(item.get("source_price"))
                timestamp, source_sequence = item.get("timestamp"), item.get("sequence")
                if (
                    source_price is None
                    or source_price <= 0
                    or quantity is None
                    or price is None
                    or liquidity is None
                    or quantity <= 0
                    or price <= 0
                    or liquidity <= 0
                    or type(timestamp) is not int
                    or type(source_sequence) is not int
                    or source_sequence < 0
                ):
                    return False
                source_key = (timestamp, source_sequence)
                if previous_source_key is not None and source_key < previous_source_key:
                    return False
                previous_source_key = source_key
                if row["order_type"] == "taker":
                    if (
                        item["kind"] != "fill"
                        or timestamp != arrival
                        or source_sequence != row.get("book_sequence")
                        or source_price != price
                    ):
                        return False
                    key = (timestamp, source_sequence, price)
                else:
                    expiry = row.get("expiry_timestamp")
                    if (
                        expiry != arrival + config["maker_lifetime_ms"]
                        or timestamp >= expiry
                        or not (
                            timestamp > arrival
                            or (timestamp == arrival == decision and source_sequence > sequence)
                        )
                    ):
                        return False
                    if (
                        item.get("source_side") != ("sell" if row["side"] == "buy" else "buy")
                        or (source_price > limit if row["side"] == "buy" else source_price < limit)
                        or (item["kind"] == "fill" and price != limit)
                    ):
                        return False
                    key = (timestamp, source_sequence)
                if key in available and available[key] != liquidity:
                    return False
                if key in source_prices and source_prices[key] != source_price:
                    return False
                source_prices[key] = source_price
                available[key] = liquidity
                consumed[key] = consumed.get(key, Decimal("0")) + quantity
                if item["kind"] == "queue":
                    consumed_queue += quantity
                    if consumed_queue > _decimal(row["queue_ahead"]):
                        return False
                if item["kind"] == "fill":
                    if price > limit if row["side"] == "buy" else price < limit:
                        return False
                    if row["order_type"] == "maker" and consumed_queue != _decimal(
                        row["queue_ahead"]
                    ):
                        return False
                    filled_quantity += quantity
                    filled_notional += quantity * price
                    execution_times.append(timestamp)
            if any(consumed[key] > available[key] for key in consumed):
                return False
            if not _close(size, filled_quantity) or not _close(
                _decimal(row["notional"]), filled_notional
            ):
                return False
            if size == 0:
                return execution is None
            if type(execution) is not int or execution != max(execution_times):
                return False
            slippage = _decimal(row.get("slippage"))
            expected_slippage = (
                Decimal("0")
                if row["order_type"] == "maker"
                else (
                    (_decimal(row["average_price"]) - limit) * (1 if row["side"] == "buy" else -1)
                )
            )
            if slippage is None or not _close(slippage, expected_slippage):
                return False
            if (
                row["order_type"] == "maker"
                and row.get("observation_end_timestamp") is not None
                and row["observation_end_timestamp"] < execution
            ):
                return False
            if row["order_type"] == "taker":
                book = row.get("book_timestamp")
                book_sequence = row.get("book_sequence")
                if (
                    type(book) is not int
                    or type(book_sequence) is not int
                    or book_sequence < 0
                    or book > arrival
                    or arrival - book > profile.stale_book_ms
                    or (arrival == decision == book and book_sequence >= sequence)
                ):
                    return False
            markout = row.get("markout")
            if _valid_markout(markout):
                observation = markout.get("observation_timestamp")
                target = execution + config["markout_horizon_ms"]
                if (
                    type(markout.get("observation_sequence")) is not int
                    or markout["observation_sequence"] < 0
                    or type(observation) is not int
                    or observation < target
                    or observation - target > config["markout_max_delay_ms"]
                    or markout["horizon_ms"] != config["markout_horizon_ms"]
                ):
                    return False
            return True
    except (DecimalException, TypeError, KeyError, ValueError):
        return False
