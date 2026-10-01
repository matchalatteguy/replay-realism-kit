from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from replay_realism.assumptions import ExecutionAssumptionProfile
from replay_realism.events import BookEvent, DecisionEvent, ReplayEvent, TradeEvent
from replay_realism.fills import (
    BookSnapshot,
    FillRequest,
    FillResult,
    OrderSide,
    OrderType,
    simulate_maker_fill,
    simulate_taker_fill,
)
from replay_realism.markout import MarkoutResult, compute_markout, future_midpoint
from replay_realism.reports import ReplayReport


@dataclass(frozen=True, slots=True)
class ReplaySimulationConfig:
    """Knobs for deterministic local replay simulation.

    The defaults intentionally match the bundled synthetic example, while allowing
    library users and the CLI to make queue and markout assumptions explicit.
    """

    maker_queue_ahead: Decimal = Decimal("1")
    markout_horizon_ms: int = 100

    def __post_init__(self) -> None:
        if not self.maker_queue_ahead.is_finite() or self.maker_queue_ahead < 0:
            raise ValueError("maker_queue_ahead cannot be negative")
        if type(self.markout_horizon_ms) is not int or self.markout_horizon_ms <= 0:
            raise ValueError("markout_horizon_ms must be a positive integer")


def simulate_replay(
    events: Iterable[ReplayEvent],
    assumptions: ExecutionAssumptionProfile,
    config: ReplaySimulationConfig | None = None,
) -> ReplayReport:
    """Simulate all decision events and return a serializable replay report.

    Events may be any iterable; they are copied into deterministic event-time order.
    Taker decisions use the first book snapshot at or after latency-adjusted arrival.
    Maker decisions use post-arrival trades with conservative queue-ahead depletion.
    Markouts are computed only from future book snapshots for the same instrument.
    """

    settings = config or ReplaySimulationConfig()
    ordered_events = sorted(events, key=lambda event: event.sort_key)
    book_events = [event for event in ordered_events if isinstance(event, BookEvent)]
    trade_events = [event for event in ordered_events if isinstance(event, TradeEvent)]
    decision_events = [event for event in ordered_events if isinstance(event, DecisionEvent)]

    fills: list[tuple[FillResult, MarkoutResult | None]] = []
    for decision in decision_events:
        fill = simulate_decision(decision, book_events, trade_events, assumptions, settings)
        midpoint = future_midpoint(
            ordered_events,
            fill.execution_timestamp
            if fill.execution_timestamp is not None
            else fill.arrival_timestamp,
            settings.markout_horizon_ms,
            instrument_id=fill.request.instrument_id,
        )
        markout = compute_markout(fill, midpoint, horizon_ms=settings.markout_horizon_ms)
        fills.append((fill, markout))
    return ReplayReport(assumptions=assumptions, fills=fills)


def simulate_decision(
    decision: DecisionEvent,
    book_events: Iterable[BookEvent],
    trade_events: Iterable[TradeEvent],
    assumptions: ExecutionAssumptionProfile,
    config: ReplaySimulationConfig | None = None,
) -> FillResult:
    """Simulate one decision against already-normalized book/trade evidence."""

    settings = config or ReplaySimulationConfig()
    request = decision_to_fill_request(decision, settings)
    arrival = decision.timestamp + assumptions.latency_ms

    if request.order_type == OrderType.TAKER:
        book = first_eligible_book(book_events, decision.instrument_id, arrival)
        if book is None:
            return FillResult(
                request,
                arrival,
                Decimal("0"),
                request.size,
                None,
                Decimal("0"),
                Decimal("0"),
                None,
                "no-book-after-arrival",
            )
        return simulate_taker_fill(request, book_event_to_snapshot(book), assumptions)
    eligible_trades = [trade for trade in trade_events if trade.sort_key > decision.sort_key]
    return simulate_maker_fill(request, eligible_trades, assumptions)


def decision_to_fill_request(
    decision: DecisionEvent,
    config: ReplaySimulationConfig | None = None,
) -> FillRequest:
    """Convert a normalized decision event into a fill request."""

    settings = config or ReplaySimulationConfig()
    return FillRequest(
        instrument_id=decision.instrument_id,
        side=OrderSide(decision.side),
        order_type=OrderType(decision.order_type),
        size=decision.size,
        limit_price=decision.limit_price,
        decision_timestamp=decision.timestamp,
        queue_ahead=settings.maker_queue_ahead,
    )


def first_eligible_book(
    book_events: Iterable[BookEvent],
    instrument_id: str,
    arrival_timestamp: int,
) -> BookEvent | None:
    """Return the first book for an instrument at or after arrival."""

    candidates = [
        book
        for book in book_events
        if book.instrument_id == instrument_id and book.timestamp >= arrival_timestamp
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda event: event.sort_key)


def book_event_to_snapshot(event: BookEvent) -> BookSnapshot:
    """Convert the compact CSV book row into a one-level book snapshot."""

    return BookSnapshot(
        instrument_id=event.instrument_id,
        timestamp=event.timestamp,
        sequence=event.sequence,
        bids=((event.bid_price, event.bid_size),),
        asks=((event.ask_price, event.ask_size),),
    )
