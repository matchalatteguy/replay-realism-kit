from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from replay_realism.arithmetic import reference_arithmetic

EventKind = Literal["book", "trade", "decision"]
Side = Literal["buy", "sell"]
Levels = tuple[tuple[Decimal, Decimal], ...]


def positive_decimal(value: Any, name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite positive decimal")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} is not a decimal: {value!r}") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def validated_levels(levels: Any, name: str, *, reverse: bool) -> Levels:
    if not isinstance(levels, (list, tuple)) or not levels:
        raise ValueError(f"{name} must be a non-empty array of [price, size] pairs")
    parsed = []
    for level in levels:
        if not isinstance(level, (list, tuple)) or len(level) != 2:
            raise ValueError(f"{name} levels must be [price, size] pairs")
        parsed.append(
            (
                positive_decimal(level[0], name + ".price"),
                positive_decimal(level[1], name + ".size"),
            )
        )
    if len({price for price, _ in parsed}) != len(parsed):
        raise ValueError(f"{name} contains duplicate prices")
    return tuple(sorted(parsed, reverse=reverse))


@dataclass(frozen=True, slots=True)
class ReplayEvent:
    timestamp: int
    sequence: int
    instrument_id: str
    venue_id: str = "synthetic"
    source: str = "local"

    def __post_init__(self) -> None:
        if type(self.timestamp) is not int or type(self.sequence) is not int or self.sequence < 0:
            raise ValueError(
                "timestamp and sequence must be integers; sequence must be non-negative"
            )
        if not isinstance(self.instrument_id, str) or not self.instrument_id.strip():
            raise ValueError("instrument_id is required")
        if not isinstance(self.venue_id, str) or not self.venue_id.strip():
            raise ValueError("venue_id is required")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source is required")

    @property
    def sort_key(self) -> tuple[int, int]:
        return (self.timestamp, self.sequence)


@dataclass(frozen=True, slots=True)
class BookEvent(ReplayEvent):
    bid_price: Decimal = Decimal("0")
    bid_size: Decimal = Decimal("0")
    ask_price: Decimal = Decimal("0")
    ask_size: Decimal = Decimal("0")
    bids: Levels = ()
    asks: Levels = ()

    def __post_init__(self) -> None:
        ReplayEvent.__post_init__(self)
        if self.bids or self.asks:
            bids = validated_levels(self.bids, "bids", reverse=True)
            asks = validated_levels(self.asks, "asks", reverse=False)
            object.__setattr__(self, "bids", bids)
            object.__setattr__(self, "asks", asks)
            for name, value in (
                ("bid_price", bids[0][0]),
                ("bid_size", bids[0][1]),
                ("ask_price", asks[0][0]),
                ("ask_size", asks[0][1]),
            ):
                object.__setattr__(self, name, value)
        else:
            object.__setattr__(self, "bid_price", positive_decimal(self.bid_price, "bid_price"))
            object.__setattr__(self, "ask_price", positive_decimal(self.ask_price, "ask_price"))
            for size in (self.bid_size, self.ask_size):
                if not isinstance(size, Decimal) or not size.is_finite() or size < 0:
                    raise ValueError("book sizes must be finite non-negative decimals")
        if self.bid_price > self.ask_price:
            raise ValueError("book bid price exceeds ask price")

    @property
    @reference_arithmetic
    def midpoint(self) -> Decimal:
        return (self.bid_price + self.ask_price) / Decimal("2")


@dataclass(frozen=True, slots=True)
class TradeEvent(ReplayEvent):
    side: Side = "buy"
    price: Decimal = Decimal("0")
    size: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        ReplayEvent.__post_init__(self)
        if self.side not in ("buy", "sell"):
            raise ValueError("trade side must be buy or sell")
        object.__setattr__(self, "price", positive_decimal(self.price, "trade price"))
        object.__setattr__(self, "size", positive_decimal(self.size, "trade size"))


@dataclass(frozen=True, slots=True)
class DecisionEvent(ReplayEvent):
    side: Side = "buy"
    size: Decimal = Decimal("0")
    limit_price: Decimal = Decimal("0")
    order_type: Literal["maker", "taker"] = "taker"

    def __post_init__(self) -> None:
        ReplayEvent.__post_init__(self)
        if self.side not in ("buy", "sell") or self.order_type not in ("maker", "taker"):
            raise ValueError("decision side/order_type is invalid")
        object.__setattr__(self, "size", positive_decimal(self.size, "decision size"))
        object.__setattr__(
            self, "limit_price", positive_decimal(self.limit_price, "decision limit price")
        )


def sort_events(events: list[ReplayEvent]) -> list[ReplayEvent]:
    seen = set()
    for event in events:
        if not isinstance(event, (BookEvent, TradeEvent, DecisionEvent)):
            raise ValueError("events must be normalized books, trades, or decisions")
        key = (event.timestamp, event.sequence, event.instrument_id, event.venue_id)
        if key in seen:
            raise ValueError(f"duplicate event ordering key: {key}")
        seen.add(key)
    return sorted(events, key=lambda event: (*event.sort_key, event.instrument_id, event.venue_id))


def load_events(path: str | Path) -> list[ReplayEvent]:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return load_events_csv(path)
    if path.suffix.lower() == ".jsonl":
        return load_events_jsonl(path)
    raise ValueError("events file must use .csv or .jsonl extension")


def load_events_csv(path: str | Path) -> list[ReplayEvent]:
    rows = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"event_type", "timestamp", "sequence", "instrument_id"}
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("events CSV requires unique, non-empty column names")
        if any(not field.strip() for field in reader.fieldnames):
            raise ValueError("events CSV has an empty column name")
        missing = required.difference(reader.fieldnames)
        if missing:
            raise ValueError(f"events CSV missing required columns: {sorted(missing)}")
        for line, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"row {line}: wrong column count")
            rows.append(_parse_event_row(row, line))
    return sort_events(rows)


def load_events_jsonl(path: str | Path) -> list[ReplayEvent]:
    rows = []
    for line, text in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not text.strip():
            continue
        try:
            row = strict_json(text)
            if not isinstance(row, dict):
                raise ValueError("event must be a JSON object")
            if type(row.get("timestamp")) is not int or type(row.get("sequence")) is not int:
                raise ValueError("JSONL timestamp and sequence must be integers")
            rows.append(_parse_event_row(row, line))
        except ValueError as exc:
            raise ValueError(f"row {line}: {exc}") from exc
    return sort_events(rows)


def strict_json(text: str) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for name, value in pairs:
            if name in result:
                raise ValueError(f"duplicate JSON member: {name}")
            result[name] = value
        return result

    def invalid_constant(value: str) -> Any:
        raise ValueError(f"non-standard JSON constant: {value}")

    return json.loads(text, object_pairs_hook=object_pairs, parse_constant=invalid_constant)


def _int(row: dict[str, Any], key: str, line: int) -> int:
    raw = row.get(key)
    if isinstance(raw, bool) or not isinstance(raw, (str, int)):
        raise ValueError(f"row {line}: {key} must be an integer")
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"row {line}: {key} is not an integer: {raw!r}") from exc


def _optional_string(row: dict[str, Any], key: str, default: str) -> str:
    value = row.get(key)
    if value is None or value == "":
        return default
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _parse_event_row(row: dict[str, Any], line: int) -> ReplayEvent:
    event_type = row.get("event_type")
    base = {
        "timestamp": _int(row, "timestamp", line),
        "sequence": _int(row, "sequence", line),
        "instrument_id": row.get("instrument_id"),
        "venue_id": _optional_string(row, "venue_id", "synthetic"),
        "source": _optional_string(row, "source", "local"),
    }
    if event_type == "book":
        if "bids" in row or "asks" in row:
            return BookEvent(
                **base,
                bids=validated_levels(row.get("bids"), "bids", reverse=True),
                asks=validated_levels(row.get("asks"), "asks", reverse=False),
            )
        return BookEvent(
            **base,
            **{
                key: positive_decimal(row.get(key), f"row {line}: {key}")
                for key in ("bid_price", "bid_size", "ask_price", "ask_size")
            },
        )
    if event_type == "trade":
        return TradeEvent(
            **base,
            side=row.get("side"),
            price=positive_decimal(row.get("price"), "price"),
            size=positive_decimal(row.get("size"), "size"),
        )
    if event_type == "decision":
        return DecisionEvent(
            **base,
            side=row.get("side"),
            order_type=_optional_string(row, "order_type", "taker"),
            size=positive_decimal(row.get("size"), "size"),
            limit_price=positive_decimal(row.get("limit_price"), "limit_price"),
        )
    raise ValueError(f"row {line}: unsupported event_type {event_type!r}")
