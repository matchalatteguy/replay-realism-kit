from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from replay_realism.arithmetic import reference_arithmetic
from replay_realism.assumptions import ExecutionAssumptionProfile
from replay_realism.events import BookEvent, DecisionEvent, ReplayEvent, TradeEvent, sort_events
from replay_realism.fills import (
    BookSnapshot,
    FillRequest,
    FillResult,
    OrderSide,
    OrderType,
    simulate_maker_fill,
    simulate_taker_fill,
)
from replay_realism.markout import compute_markout, future_book
from replay_realism.reports import ReplayReport


@dataclass(frozen=True, slots=True)
class ReplaySimulationConfig:
    """Independent-order reference model settings; all timing is in milliseconds."""

    maker_queue_ahead: Decimal = Decimal("1")
    markout_horizon_ms: int = 100
    maker_lifetime_ms: int = 1000
    markout_max_delay_ms: int = 1000

    def __post_init__(self) -> None:
        if (
            not isinstance(self.maker_queue_ahead, Decimal)
            or not self.maker_queue_ahead.is_finite()
            or self.maker_queue_ahead < 0
        ):
            raise ValueError("maker_queue_ahead must be a finite non-negative Decimal")
        for name in ("markout_horizon_ms", "maker_lifetime_ms", "markout_max_delay_ms"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be a positive integer")

    def to_dict(self) -> dict[str, str | int]:
        return {
            "maker_queue_ahead": str(self.maker_queue_ahead),
            "markout_horizon_ms": self.markout_horizon_ms,
            "maker_lifetime_ms": self.maker_lifetime_ms,
            "markout_max_delay_ms": self.markout_max_delay_ms,
        }


@reference_arithmetic
def simulate_replay(
    events: Iterable[ReplayEvent],
    assumptions: ExecutionAssumptionProfile,
    config: ReplaySimulationConfig | None = None,
) -> ReplayReport:
    """Replay each decision independently against causally available market evidence.

    Takers use the latest known same-instrument/venue book at arrival and execute
    immediately; future snapshots cannot improve the fill. Makers consume eligible
    opposing trades until exclusive expiry. Liquidity is not shared between decisions.
    """
    settings = config or ReplaySimulationConfig()
    ordered = sort_events(list(events))
    books = [event for event in ordered if isinstance(event, BookEvent)]
    trades = [event for event in ordered if isinstance(event, TradeEvent)]
    decisions = [event for event in ordered if isinstance(event, DecisionEvent)]
    fills = []
    for decision in decisions:
        fill = simulate_decision(decision, books, trades, assumptions, settings)
        execution = (
            fill.execution_timestamp
            if fill.execution_timestamp is not None
            else fill.arrival_timestamp
        )
        observation = future_book(
            ordered,
            execution,
            settings.markout_horizon_ms,
            decision.instrument_id,
            decision.venue_id,
            max_delay_ms=settings.markout_max_delay_ms,
        )
        markout = compute_markout(
            fill,
            observation.midpoint if observation is not None else None,
            horizon_ms=settings.markout_horizon_ms,
            observation_timestamp=observation.timestamp if observation is not None else None,
            observation_sequence=observation.sequence if observation is not None else None,
        )
        fills.append((fill, markout))
    return ReplayReport(assumptions, fills, config=settings.to_dict())


@reference_arithmetic
def simulate_decision(
    decision: DecisionEvent,
    book_events: Iterable[BookEvent],
    trade_events: Iterable[TradeEvent],
    assumptions: ExecutionAssumptionProfile,
    config: ReplaySimulationConfig | None = None,
) -> FillResult:
    settings = config or ReplaySimulationConfig()
    request = decision_to_fill_request(decision, settings)
    arrival = decision.timestamp + assumptions.latency_ms
    if request.order_type == OrderType.TAKER:
        book = latest_eligible_book(
            book_events,
            decision.instrument_id,
            arrival,
            venue_id=decision.venue_id,
            decision_sequence=decision.sequence if assumptions.latency_ms == 0 else None,
        )
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
                "no-book-at-arrival",
            )
        return simulate_taker_fill(request, book_event_to_snapshot(book), assumptions)
    books, trades = list(book_events), list(trade_events)
    end = max(
        (
            event.timestamp
            for event in [*books, *trades]
            if event.instrument_id == decision.instrument_id and event.venue_id == decision.venue_id
        ),
        default=None,
    )
    return simulate_maker_fill(request, trades, assumptions, observed_until_timestamp=end)


def decision_to_fill_request(
    decision: DecisionEvent, config: ReplaySimulationConfig | None = None
) -> FillRequest:
    settings = config or ReplaySimulationConfig()
    return FillRequest(
        decision.instrument_id,
        OrderSide(decision.side),
        OrderType(decision.order_type),
        decision.size,
        decision.limit_price,
        decision.timestamp,
        queue_ahead=settings.maker_queue_ahead,
        maker_lifetime_ms=settings.maker_lifetime_ms,
        decision_sequence=decision.sequence,
        venue_id=decision.venue_id,
    )


def latest_eligible_book(
    book_events: Iterable[BookEvent],
    instrument_id: str,
    arrival_timestamp: int,
    *,
    venue_id: str | None = None,
    decision_sequence: int | None = None,
) -> BookEvent | None:
    """Latest causal quote. At zero latency, only earlier event sequences are known.

    At positive-latency arrival, all market updates at that timestamp precede
    synthetic order arrival. Maker fills therefore require later timestamps.
    """
    candidates = [
        book
        for book in book_events
        if book.instrument_id == instrument_id
        and (venue_id is None or book.venue_id == venue_id)
        and (
            book.timestamp < arrival_timestamp
            or (
                book.timestamp == arrival_timestamp
                and (decision_sequence is None or book.sequence < decision_sequence)
            )
        )
    ]
    return max(candidates, key=lambda event: event.sort_key) if candidates else None


def first_eligible_book(
    book_events: Iterable[BookEvent], instrument_id: str, arrival_timestamp: int
) -> BookEvent | None:
    """Compatibility name; since 0.3 this returns the latest causally known book."""
    return latest_eligible_book(book_events, instrument_id, arrival_timestamp)


def book_event_to_snapshot(event: BookEvent) -> BookSnapshot:
    return BookSnapshot(
        event.instrument_id,
        event.timestamp,
        event.sequence,
        event.bids or ((event.bid_price, event.bid_size),),
        event.asks or ((event.ask_price, event.ask_size),),
        event.venue_id,
    )
