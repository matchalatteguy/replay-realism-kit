from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from replay_realism.assumptions import ExecutionAssumptionProfile
from replay_realism.events import TradeEvent


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MAKER = "maker"
    TAKER = "taker"


class FillPolicy(StrEnum):
    FAK = "fill-and-kill"
    FOK = "fill-or-kill"


@dataclass(frozen=True, slots=True)
class BookSnapshot:
    instrument_id: str
    timestamp: int
    sequence: int
    bids: tuple[tuple[Decimal, Decimal], ...]
    asks: tuple[tuple[Decimal, Decimal], ...]

    def __post_init__(self) -> None:
        if not self.instrument_id:
            raise ValueError("instrument_id is required")
        if any(price <= 0 or size <= 0 for price, size in (*self.bids, *self.asks)):
            raise ValueError("book prices and sizes must be positive")

    @property
    def midpoint(self) -> Decimal | None:
        if not self.bids or not self.asks:
            return None
        return (self.bids[0][0] + self.asks[0][0]) / Decimal("2")


@dataclass(frozen=True, slots=True)
class FillRequest:
    instrument_id: str
    side: OrderSide
    order_type: OrderType
    size: Decimal
    limit_price: Decimal
    decision_timestamp: int
    queue_ahead: Decimal = Decimal("0")
    policy: FillPolicy = FillPolicy.FAK


@dataclass(frozen=True, slots=True)
class FillResult:
    request: FillRequest
    arrival_timestamp: int
    filled_size: Decimal
    remaining_size: Decimal
    average_price: Decimal | None
    notional: Decimal
    fee: Decimal
    slippage: Decimal | None
    reason_code: str
    evidence: list[str] = field(default_factory=list)

    @property
    def is_filled(self) -> bool:
        return self.filled_size > 0


def _violates_tick(value: Decimal, tick_size: Decimal) -> bool:
    return value % tick_size != 0


def _empty(request: FillRequest, arrival: int, reason: str, evidence: list[str] | None = None) -> FillResult:
    return FillResult(
        request=request,
        arrival_timestamp=arrival,
        filled_size=Decimal("0"),
        remaining_size=request.size,
        average_price=None,
        notional=Decimal("0"),
        fee=Decimal("0"),
        slippage=None,
        reason_code=reason,
        evidence=evidence or [],
    )


def simulate_taker_fill(
    request: FillRequest,
    book: BookSnapshot,
    assumptions: ExecutionAssumptionProfile,
) -> FillResult:
    arrival = request.decision_timestamp + assumptions.latency_ms
    common = _validate_request(request, assumptions)
    if common:
        return _empty(request, arrival, common)
    if book.instrument_id != request.instrument_id:
        return _empty(request, arrival, "instrument-mismatch")
    if book.timestamp < arrival:
        return _empty(request, arrival, "book-before-arrival")
    if book.timestamp - arrival > assumptions.stale_book_ms:
        return _empty(request, arrival, "stale-book")

    levels = book.asks if request.side == OrderSide.BUY else book.bids
    levels = tuple(sorted(levels, key=lambda item: item[0], reverse=request.side == OrderSide.SELL))
    remaining = request.size
    filled = Decimal("0")
    notional = Decimal("0")
    evidence: list[str] = []
    for price, available in levels:
        crossable = price <= request.limit_price if request.side == OrderSide.BUY else price >= request.limit_price
        if not crossable or remaining <= 0:
            break
        take = min(remaining, available)
        filled += take
        remaining -= take
        notional += take * price
        evidence.append(f"depth@{price}:{take}")

    if request.policy == FillPolicy.FOK and filled < request.size:
        return _empty(request, arrival, "fok-not-filled", evidence)
    if filled <= 0:
        return _empty(request, arrival, "insufficient-crossable-depth", evidence)
    average = notional / filled
    fee = assumptions.fee_model.fee_for(notional, "taker")
    signed_slippage = (average - request.limit_price) if request.side == OrderSide.BUY else (request.limit_price - average)
    return FillResult(
        request=request,
        arrival_timestamp=arrival,
        filled_size=filled,
        remaining_size=remaining,
        average_price=average,
        notional=notional,
        fee=fee,
        slippage=signed_slippage,
        reason_code="filled" if remaining == 0 else "partial-fill",
        evidence=evidence,
    )


def simulate_maker_fill(
    request: FillRequest,
    trades: list[TradeEvent],
    assumptions: ExecutionAssumptionProfile,
) -> FillResult:
    arrival = request.decision_timestamp + assumptions.latency_ms
    common = _validate_request(request, assumptions)
    if common:
        return _empty(request, arrival, common)
    remaining_queue = request.queue_ahead
    remaining_order = request.size
    filled = Decimal("0")
    notional = Decimal("0")
    evidence: list[str] = []
    for trade in sorted(trades, key=lambda event: event.sort_key):
        if trade.timestamp < arrival or trade.instrument_id != request.instrument_id:
            continue
        consumes_our_side = (
            request.side == OrderSide.BUY and trade.side == "sell" and trade.price <= request.limit_price
        ) or (request.side == OrderSide.SELL and trade.side == "buy" and trade.price >= request.limit_price)
        if not consumes_our_side:
            continue
        residual = trade.size
        if remaining_queue > 0:
            consumed_queue = min(remaining_queue, residual)
            remaining_queue -= consumed_queue
            residual -= consumed_queue
            evidence.append(f"queue@{trade.timestamp}:{consumed_queue}")
        if residual > 0 and remaining_order > 0:
            take = min(remaining_order, residual)
            remaining_order -= take
            filled += take
            notional += take * request.limit_price
            evidence.append(f"maker@{trade.timestamp}:{take}")
        if remaining_order == 0:
            break
    if filled <= 0:
        reason = "queue-not-exhausted" if remaining_queue > 0 else "no-post-arrival-trade"
        return _empty(request, arrival, reason, evidence)
    fee = assumptions.fee_model.fee_for(notional, "maker")
    return FillResult(
        request=request,
        arrival_timestamp=arrival,
        filled_size=filled,
        remaining_size=remaining_order,
        average_price=request.limit_price,
        notional=notional,
        fee=fee,
        slippage=Decimal("0"),
        reason_code="filled" if remaining_order == 0 else "partial-fill",
        evidence=evidence,
    )


def _validate_request(request: FillRequest, assumptions: ExecutionAssumptionProfile) -> str | None:
    if request.size < assumptions.min_size:
        return "min-size-violation"
    if _violates_tick(request.limit_price, assumptions.tick_size):
        return "tick-size-violation"
    if request.size <= 0 or request.limit_price <= 0:
        return "non-positive-request"
    return None
