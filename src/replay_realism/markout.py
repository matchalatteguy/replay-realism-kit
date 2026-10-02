from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from replay_realism.arithmetic import reference_arithmetic
from replay_realism.events import BookEvent, ReplayEvent
from replay_realism.fills import FillResult, OrderSide


@dataclass(frozen=True, slots=True)
class MarkoutResult:
    horizon_ms: int
    midpoint: Decimal | None
    edge_after_fees: Decimal | None
    reason_code: str
    observation_timestamp: int | None = None
    observation_sequence: int | None = None


@reference_arithmetic
def future_midpoint(
    events: list[ReplayEvent],
    fill_timestamp: int,
    horizon_ms: int,
    instrument_id: str | None = None,
) -> Decimal | None:
    book = future_book(events, fill_timestamp, horizon_ms, instrument_id)
    return book.midpoint if book is not None else None


def future_book(
    events: list[ReplayEvent],
    fill_timestamp: int,
    horizon_ms: int,
    instrument_id: str | None = None,
    venue_id: str | None = None,
    *,
    max_delay_ms: int | None = None,
) -> BookEvent | None:
    if type(horizon_ms) is not int or horizon_ms <= 0:
        raise ValueError("markout horizon must be a positive integer")
    if max_delay_ms is not None and (type(max_delay_ms) is not int or max_delay_ms <= 0):
        raise ValueError("markout max delay must be a positive integer")
    target = fill_timestamp + horizon_ms
    candidates = [
        event
        for event in events
        if isinstance(event, BookEvent)
        and event.timestamp >= target
        and (max_delay_ms is None or event.timestamp - target <= max_delay_ms)
        and (instrument_id is None or event.instrument_id == instrument_id)
        and (venue_id is None or event.venue_id == venue_id)
    ]
    return min(candidates, key=lambda event: event.sort_key) if candidates else None


@reference_arithmetic
def compute_markout(
    fill: FillResult,
    midpoint: Decimal | None,
    horizon_ms: int = 100,
    *,
    observation_timestamp: int | None = None,
    observation_sequence: int | None = None,
) -> MarkoutResult:
    if type(horizon_ms) is not int or horizon_ms <= 0:
        raise ValueError("markout horizon must be a positive integer")
    if midpoint is not None and (not midpoint.is_finite() or midpoint <= 0):
        raise ValueError("markout midpoint must be finite and positive")
    if not fill.is_filled or fill.average_price is None:
        return MarkoutResult(horizon_ms, midpoint, None, "unfilled")
    if midpoint is None:
        return MarkoutResult(horizon_ms, None, None, "missing-future-midpoint")
    direction = Decimal("1") if fill.request.side == OrderSide.BUY else Decimal("-1")
    gross = (midpoint * fill.filled_size - fill.notional) * direction
    return MarkoutResult(
        horizon_ms, midpoint, gross - fill.fee, "ok", observation_timestamp, observation_sequence
    )
