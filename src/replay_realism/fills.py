from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from replay_realism.arithmetic import reference_arithmetic
from replay_realism.assumptions import ExecutionAssumptionProfile
from replay_realism.events import TradeEvent, sort_events, validated_levels


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
    venue_id: str = "synthetic"

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_id, str) or not self.instrument_id:
            raise ValueError("instrument_id is required")
        if not isinstance(self.venue_id, str) or not self.venue_id:
            raise ValueError("venue_id is required")
        if type(self.timestamp) is not int or type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("book timestamp must be an integer and sequence non-negative")
        bids = validated_levels(self.bids, "bids", reverse=True)
        asks = validated_levels(self.asks, "asks", reverse=False)
        if bids[0][0] > asks[0][0]:
            raise ValueError("book is crossed")
        object.__setattr__(self, "bids", bids)
        object.__setattr__(self, "asks", asks)

    @property
    @reference_arithmetic
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
    maker_lifetime_ms: int = 1000
    decision_sequence: int | None = None
    venue_id: str = "synthetic"


@dataclass(frozen=True, slots=True)
class FillTrace:
    kind: str
    timestamp: int
    sequence: int
    price: Decimal
    quantity: Decimal
    available_quantity: Decimal
    source_price: Decimal | None = None
    source_side: str | None = None


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
    execution_timestamp: int | None = None
    trace: tuple[FillTrace, ...] = ()
    book_timestamp: int | None = None
    book_sequence: int | None = None
    expiry_timestamp: int | None = None
    observation_end_timestamp: int | None = None
    completion_reason: str | None = None

    @property
    def is_filled(self) -> bool:
        return self.filled_size > 0


def _violates_tick(value: Decimal, tick_size: Decimal) -> bool:
    return value % tick_size != 0


def _empty(
    request: FillRequest,
    arrival: int,
    reason: str,
    evidence: list[str] | None = None,
    trace: list[FillTrace] | None = None,
    *,
    observation_end_timestamp: int | None = None,
    completion_reason: str | None = None,
) -> FillResult:
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
        trace=tuple(item for item in (trace or []) if item.kind == "queue"),
        observation_end_timestamp=observation_end_timestamp,
        completion_reason=completion_reason,
        expiry_timestamp=arrival + request.maker_lifetime_ms
        if request.order_type == OrderType.MAKER
        else None,
    )


@reference_arithmetic
def simulate_taker_fill(
    request: FillRequest,
    book: BookSnapshot,
    assumptions: ExecutionAssumptionProfile,
) -> FillResult:
    arrival = request.decision_timestamp + assumptions.latency_ms
    common = _validate_request(request, assumptions)
    if common:
        return _empty(request, arrival, common)
    if book.instrument_id != request.instrument_id or book.venue_id != request.venue_id:
        return _empty(request, arrival, "instrument-mismatch")
    if book.timestamp > arrival:
        return _empty(request, arrival, "book-after-arrival")
    if (
        book.timestamp == request.decision_timestamp == arrival
        and request.decision_sequence is not None
        and book.sequence >= request.decision_sequence
    ):
        return _empty(request, arrival, "book-after-decision-sequence")
    if arrival - book.timestamp > assumptions.stale_book_ms:
        return _empty(request, arrival, "stale-book")

    levels = book.asks if request.side == OrderSide.BUY else book.bids
    levels = tuple(sorted(levels, key=lambda item: item[0], reverse=request.side == OrderSide.SELL))
    remaining = request.size
    filled = Decimal("0")
    notional = Decimal("0")
    evidence: list[str] = []
    trace: list[FillTrace] = []
    for price, available in levels:
        crossable = (
            price <= request.limit_price
            if request.side == OrderSide.BUY
            else price >= request.limit_price
        )
        if not crossable or remaining <= 0:
            break
        take = min(remaining, available)
        filled += take
        remaining -= take
        notional += take * price
        evidence.append(f"depth@{price}:{take}")
        trace.append(FillTrace("fill", arrival, book.sequence, price, take, available, price))

    if request.policy == FillPolicy.FOK and filled < request.size:
        return _empty(request, arrival, "fok-not-filled", evidence, trace)
    if filled <= 0:
        return _empty(request, arrival, "insufficient-crossable-depth", evidence)
    if not assumptions.allow_partial_fills and remaining > 0:
        return _empty(request, arrival, "partial-fill-not-allowed", evidence, trace)
    average = notional / filled
    fee = assumptions.fee_model.fee_for(notional, "taker")
    signed_slippage = (
        (average - request.limit_price)
        if request.side == OrderSide.BUY
        else (request.limit_price - average)
    )
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
        execution_timestamp=arrival,
        trace=tuple(trace),
        book_timestamp=book.timestamp,
        book_sequence=book.sequence,
    )


@reference_arithmetic
def simulate_maker_fill(
    request: FillRequest,
    trades: list[TradeEvent],
    assumptions: ExecutionAssumptionProfile,
    *,
    observed_until_timestamp: int | None = None,
) -> FillResult:
    if any(not isinstance(trade, TradeEvent) for trade in trades):
        raise ValueError("maker evidence must consist of TradeEvent objects")
    ordered = sort_events(trades)
    trade_end = max(
        (
            trade.timestamp
            for trade in ordered
            if trade.instrument_id == request.instrument_id and trade.venue_id == request.venue_id
        ),
        default=None,
    )
    if observed_until_timestamp is None:
        observed_until_timestamp = trade_end
    if observed_until_timestamp is not None and type(observed_until_timestamp) is not int:
        raise ValueError("observed_until_timestamp must be an integer or None")
    if trade_end is not None and observed_until_timestamp < trade_end:
        raise ValueError("observation end precedes supplied matching trade evidence")
    arrival = request.decision_timestamp + assumptions.latency_ms
    common = _validate_request(request, assumptions)
    if common:
        return _empty(request, arrival, common)
    remaining_queue = request.queue_ahead
    remaining_order = request.size
    filled = Decimal("0")
    notional = Decimal("0")
    evidence: list[str] = []
    execution_timestamp = None
    expiry = arrival + request.maker_lifetime_ms
    trace: list[FillTrace] = []
    for trade in ordered:
        after_arrival = trade.timestamp > arrival or (
            trade.timestamp == arrival == request.decision_timestamp
            and request.decision_sequence is not None
            and trade.sequence > request.decision_sequence
        )
        if (
            not after_arrival
            or trade.timestamp >= expiry
            or trade.instrument_id != request.instrument_id
            or trade.venue_id != request.venue_id
        ):
            continue
        consumes_our_side = (
            request.side == OrderSide.BUY
            and trade.side == "sell"
            and trade.price <= request.limit_price
        ) or (
            request.side == OrderSide.SELL
            and trade.side == "buy"
            and trade.price >= request.limit_price
        )
        if not consumes_our_side:
            continue
        residual = trade.size
        if remaining_queue > 0:
            consumed_queue = min(remaining_queue, residual)
            remaining_queue -= consumed_queue
            residual -= consumed_queue
            evidence.append(f"queue@{trade.timestamp}:{consumed_queue}")
            trace.append(
                FillTrace(
                    "queue",
                    trade.timestamp,
                    trade.sequence,
                    trade.price,
                    consumed_queue,
                    trade.size,
                    trade.price,
                    trade.side,
                )
            )
        if residual > 0 and remaining_order > 0:
            take = min(remaining_order, residual)
            remaining_order -= take
            filled += take
            notional += take * request.limit_price
            execution_timestamp = trade.timestamp
            evidence.append(f"maker@{trade.timestamp}:{take}")
            trace.append(
                FillTrace(
                    "fill",
                    trade.timestamp,
                    trade.sequence,
                    request.limit_price,
                    take,
                    trade.size,
                    trade.price,
                    trade.side,
                )
            )
        if remaining_order == 0:
            break
    completion = (
        "filled"
        if remaining_order == 0
        else "expired"
        if observed_until_timestamp is not None and observed_until_timestamp >= expiry
        else "incomplete-evidence"
    )
    tail = {"observation_end_timestamp": observed_until_timestamp, "completion_reason": completion}
    if filled <= 0:
        reason = "maker-expired" if completion == "expired" else "maker-evidence-incomplete"
        return _empty(request, arrival, reason, evidence, trace, **tail)
    if not assumptions.allow_partial_fills and remaining_order > 0:
        return _empty(request, arrival, "partial-fill-not-allowed", evidence, trace, **tail)
    if request.policy == FillPolicy.FOK and remaining_order > 0:
        return _empty(request, arrival, "fok-not-filled", evidence, trace, **tail)
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
        execution_timestamp=execution_timestamp,
        trace=tuple(trace),
        expiry_timestamp=expiry,
        **tail,
    )


def _validate_request(request: FillRequest, assumptions: ExecutionAssumptionProfile) -> str | None:
    if (
        type(request.decision_timestamp) is not int
        or request.side not in (OrderSide.BUY, OrderSide.SELL)
        or request.order_type not in (OrderType.MAKER, OrderType.TAKER)
        or request.policy not in (FillPolicy.FAK, FillPolicy.FOK)
        or not isinstance(request.instrument_id, str)
        or not request.instrument_id
        or not isinstance(request.venue_id, str)
        or not request.venue_id
    ):
        return "invalid-request"
    if (
        not isinstance(request.size, Decimal)
        or not isinstance(request.limit_price, Decimal)
        or not isinstance(request.queue_ahead, Decimal)
        or not request.size.is_finite()
        or not request.limit_price.is_finite()
        or not request.queue_ahead.is_finite()
        or request.queue_ahead < 0
    ):
        return "invalid-request-number"
    if type(request.maker_lifetime_ms) is not int or request.maker_lifetime_ms <= 0:
        return "invalid-maker-lifetime"
    if request.decision_sequence is not None and (
        type(request.decision_sequence) is not int or request.decision_sequence < 0
    ):
        return "invalid-decision-sequence"
    if request.size < assumptions.min_size:
        return "min-size-violation"
    if _violates_tick(request.limit_price, assumptions.tick_size):
        return "tick-size-violation"
    if request.size <= 0 or request.limit_price <= 0:
        return "non-positive-request"
    return None
