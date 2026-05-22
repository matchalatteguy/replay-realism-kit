from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from replay_realism.events import BookEvent, ReplayEvent
from replay_realism.fills import FillResult, OrderSide


@dataclass(frozen=True, slots=True)
class MarkoutResult:
    horizon_ms: int
    midpoint: Decimal | None
    edge_after_fees: Decimal | None
    reason_code: str


def future_midpoint(
    events: list[ReplayEvent],
    fill_timestamp: int,
    horizon_ms: int,
    instrument_id: str | None = None,
) -> Decimal | None:
    target = fill_timestamp + horizon_ms
    candidates = [
        event
        for event in events
        if isinstance(event, BookEvent)
        and event.timestamp >= target
        and (instrument_id is None or event.instrument_id == instrument_id)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda event: event.sort_key).midpoint


def compute_markout(
    fill: FillResult, midpoint: Decimal | None, horizon_ms: int = 0
) -> MarkoutResult:
    if not fill.is_filled or fill.average_price is None:
        return MarkoutResult(horizon_ms, midpoint, None, "unfilled")
    if midpoint is None:
        return MarkoutResult(horizon_ms, None, None, "missing-future-midpoint")
    direction = Decimal("1") if fill.request.side == OrderSide.BUY else Decimal("-1")
    gross = (midpoint - fill.average_price) * direction * fill.filled_size
    return MarkoutResult(horizon_ms, midpoint, gross - fill.fee, "ok")
