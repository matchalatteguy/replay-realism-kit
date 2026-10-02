# Adapter guide

Replay Realism Kit deliberately does not include venue adapters or live integrations. The reusable boundary is the normalized event model in `replay_realism.events` and the CSV/JSONL schema documented in `docs/event-schema.md`.

Use this guide when you have private or venue-specific replay logs and want a synthetic fixture or a local-only CI check.

## Recommended adapter pattern

1. Keep raw/private data outside this repository.
2. Write a project-local conversion script in your private workspace.
3. Map records into `BookEvent`, `TradeEvent`, and `DecisionEvent` or into the documented CSV/JSONL fields.
4. Replace real identifiers with generic fixture identifiers before committing examples.
5. Run `replay-realism validate-events` on the normalized events.
6. Commit only small synthetic CSV/JSONL/YAML examples and expected behavior tests.

## Python mapping example

```python
from decimal import Decimal

from replay_realism.events import BookEvent, DecisionEvent, sort_events

private_rows = [
    {"ts_ms": 1000, "symbol": "PRIVATE_SYMBOL", "bid": "99.90", "ask": "100.00"},
    {"ts_ms": 1010, "symbol": "PRIVATE_SYMBOL", "side": "buy", "qty": "2", "limit": "100.00"},
]

public_instrument = "FOO-USD"
events = [
    BookEvent(
        timestamp=int(private_rows[0]["ts_ms"]),
        sequence=1,
        instrument_id=public_instrument,
        venue_id="SIM",
        source="fixture",
        bid_price=Decimal(private_rows[0]["bid"]),
        bid_size=Decimal("10"),
        ask_price=Decimal(private_rows[0]["ask"]),
        ask_size=Decimal("5"),
    ),
    DecisionEvent(
        timestamp=int(private_rows[1]["ts_ms"]),
        sequence=2,
        instrument_id=public_instrument,
        venue_id="SIM",
        source="fixture",
        side="buy",
        size=Decimal(private_rows[1]["qty"]),
        limit_price=Decimal(private_rows[1]["limit"]),
        order_type="taker",
    ),
]

normalized = sort_events(events)
```

## What not to adapt into this repo

Do not add:

- network clients, API keys, account identifiers, wallets, signing flows, or live order code;
- real venue dumps, account exports, production hostnames, local absolute paths, or private strategy names;
- large historical datasets or generated reports as committed artifacts;
- code that implies the snapshot reference model proves real fills.

## Extension seam

JSONL supports multiple depth levels. Preserve source ordering, millisecond units, and separate instrument/venue keys. Include future observations and enough market coverage for attempted maker expiry windows. Document assumptions about timestamp ties, snapshots persisting between updates, and source completeness. Keep venue-specific adapters outside this package.
