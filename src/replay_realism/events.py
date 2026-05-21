from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

EventKind = Literal["book", "trade", "decision"]
Side = Literal["buy", "sell"]


@dataclass(frozen=True, slots=True)
class ReplayEvent:
    timestamp: int
    sequence: int
    instrument_id: str
    venue_id: str = "synthetic"
    source: str = "local"

    @property
    def sort_key(self) -> tuple[int, int]:
        return (self.timestamp, self.sequence)


@dataclass(frozen=True, slots=True)
class BookEvent(ReplayEvent):
    bid_price: Decimal = Decimal("0")
    bid_size: Decimal = Decimal("0")
    ask_price: Decimal = Decimal("0")
    ask_size: Decimal = Decimal("0")

    @property
    def midpoint(self) -> Decimal:
        if self.bid_price <= 0 or self.ask_price <= 0:
            raise ValueError("book event requires positive bid and ask prices")
        return (self.bid_price + self.ask_price) / Decimal("2")


@dataclass(frozen=True, slots=True)
class TradeEvent(ReplayEvent):
    side: Side = "buy"
    price: Decimal = Decimal("0")
    size: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class DecisionEvent(ReplayEvent):
    side: Side = "buy"
    size: Decimal = Decimal("0")
    limit_price: Decimal = Decimal("0")
    order_type: Literal["maker", "taker"] = "taker"


def sort_events(events: list[ReplayEvent]) -> list[ReplayEvent]:
    return sorted(events, key=lambda event: event.sort_key)


def load_events_csv(path: str | Path) -> list[ReplayEvent]:
    rows: list[ReplayEvent] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"event_type", "timestamp", "sequence", "instrument_id"}
        if not reader.fieldnames:
            raise ValueError(f"events CSV missing required columns: {sorted(required)}")
        missing = required.difference(reader.fieldnames)
        if missing:
            raise ValueError(f"events CSV missing required columns: {sorted(missing)}")
        for row_number, row in enumerate(reader, start=2):
            rows.append(_parse_event_row(row, row_number))
    return sort_events(rows)


def _decimal(row: dict[str, str], key: str, row_number: int, default: str = "0") -> Decimal:
    raw = row.get(key) or default
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"row {row_number}: {key} is not a decimal: {raw!r}") from exc


def _int(row: dict[str, str], key: str, row_number: int) -> int:
    raw = row.get(key)
    try:
        return int(raw or "")
    except ValueError as exc:
        raise ValueError(f"row {row_number}: {key} is not an integer: {raw!r}") from exc


def _parse_event_row(row: dict[str, str], row_number: int) -> ReplayEvent:
    event_type = row.get("event_type", "").strip()
    base = {
        "timestamp": _int(row, "timestamp", row_number),
        "sequence": _int(row, "sequence", row_number),
        "instrument_id": (row.get("instrument_id") or "").strip(),
        "venue_id": (row.get("venue_id") or "synthetic").strip(),
        "source": (row.get("source") or "local").strip(),
    }
    if not base["instrument_id"]:
        raise ValueError(f"row {row_number}: instrument_id is required")
    if event_type == "book":
        return BookEvent(
            **base,
            bid_price=_decimal(row, "bid_price", row_number),
            bid_size=_decimal(row, "bid_size", row_number),
            ask_price=_decimal(row, "ask_price", row_number),
            ask_size=_decimal(row, "ask_size", row_number),
        )
    if event_type == "trade":
        side = (row.get("side") or "").strip().lower()
        if side not in {"buy", "sell"}:
            raise ValueError(f"row {row_number}: trade side must be buy or sell")
        return TradeEvent(
            **base,
            side=side,  # type: ignore[arg-type]
            price=_decimal(row, "price", row_number),
            size=_decimal(row, "size", row_number),
        )
    if event_type == "decision":
        side = (row.get("side") or "").strip().lower()
        order_type = (row.get("order_type") or "taker").strip().lower()
        if side not in {"buy", "sell"}:
            raise ValueError(f"row {row_number}: decision side must be buy or sell")
        if order_type not in {"maker", "taker"}:
            raise ValueError(f"row {row_number}: order_type must be maker or taker")
        return DecisionEvent(
            **base,
            side=side,  # type: ignore[arg-type]
            size=_decimal(row, "size", row_number),
            limit_price=_decimal(row, "limit_price", row_number),
            order_type=order_type,  # type: ignore[arg-type]
        )
    raise ValueError(f"row {row_number}: unsupported event_type {event_type!r}")
