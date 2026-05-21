# API and CLI usage notes

This page gives task-oriented recipes for outside engineers and LLM agents using Replay Realism Kit on small local fixtures.

## Validate local events

Use `validate-events` before running a replay. It loads the CSV, validates event-specific fields, and applies deterministic `(timestamp, sequence)` ordering.

```bash
uv run replay-realism validate-events --events examples/synthetic-book/events.csv
```

Expected output shape:

```text
validated 5 events
```

## Simulate a replay

`simulate` reads local events and an assumption profile, then writes a JSON report.

```bash
uv run replay-realism simulate \
  --events examples/synthetic-book/events.csv \
  --assumptions examples/synthetic-book/assumptions.yaml \
  --json-out reports/replay.json
```

The MVP simulator is intentionally compact. It is best for:

- smoke-testing report shape;
- demonstrating conservative taker and maker fill behavior;
- creating fixtures for quality-gate tests;
- teaching future-only markout rules.

It is not intended as a high-throughput historical data engine.

## Gate a report

`gate` validates report evidence and optionally writes a Markdown review.

```bash
uv run replay-realism gate \
  --report reports/replay.json \
  --md-out reports/replay-review.md
```

Exit codes:

- `0`: all required gates passed;
- `1`: one or more required gates failed.

## Initialize the example fixture

Copy the bundled synthetic fixture to a new location without overwriting existing files:

```bash
uv run replay-realism init-example synthetic-book --out-dir scratch-examples
```

This creates `scratch-examples/synthetic-book/`.

## Programmatic taker fill

```python
from decimal import Decimal

from replay_realism import (
    BookSnapshot,
    ExecutionAssumptionProfile,
    FeeModel,
    FillRequest,
    OrderSide,
    OrderType,
    simulate_taker_fill,
)

assumptions = ExecutionAssumptionProfile(
    name="conservative-demo",
    latency_ms=50,
    stale_book_ms=250,
    fee_model=FeeModel(maker_bps=Decimal("1"), taker_bps=Decimal("5")),
)
request = FillRequest(
    instrument_id="FOO-USD",
    side=OrderSide.BUY,
    order_type=OrderType.TAKER,
    size=Decimal("2"),
    limit_price=Decimal("100.00"),
    decision_timestamp=1_010,
)
book = BookSnapshot(
    instrument_id="FOO-USD",
    timestamp=1_060,
    sequence=3,
    bids=((Decimal("99.95"), Decimal("10")),),
    asks=((Decimal("100.00"), Decimal("5")),),
)

fill = simulate_taker_fill(request, book, assumptions)
assert fill.reason_code == "filled"
```

## Programmatic maker fill

```python
from decimal import Decimal

from replay_realism import (
    ExecutionAssumptionProfile,
    FeeModel,
    FillRequest,
    OrderSide,
    OrderType,
    TradeEvent,
    simulate_maker_fill,
)

assumptions = ExecutionAssumptionProfile(
    name="queue-demo",
    latency_ms=50,
    stale_book_ms=250,
    fee_model=FeeModel(maker_bps=Decimal("1"), taker_bps=Decimal("5")),
)
request = FillRequest(
    instrument_id="FOO-USD",
    side=OrderSide.BUY,
    order_type=OrderType.MAKER,
    size=Decimal("2"),
    limit_price=Decimal("100.00"),
    decision_timestamp=1_010,
    queue_ahead=Decimal("1"),
)
trades = [
    TradeEvent(
        timestamp=1_070,
        sequence=4,
        instrument_id="FOO-USD",
        venue_id="SIM",
        source="fixture",
        side="sell",
        price=Decimal("100.00"),
        size=Decimal("3"),
    )
]

fill = simulate_maker_fill(request, trades, assumptions)
assert fill.evidence == ["queue@1070:1", "maker@1070:2"]
```

## Report-writing API

```python
from replay_realism import ReplayReport, validate_replay_report, write_json_report, write_markdown_report

report = ReplayReport(assumptions=assumptions, fills=[(fill, None)])
write_json_report(report, "reports/replay.json")
gates = validate_replay_report(report.to_dict())
write_markdown_report(report, "reports/replay-review.md", gates)
```

If `require_future_markout` is true, pass real `MarkoutResult` objects instead of `None` for filled rows.

## Data hygiene

Keep examples small, local, synthetic, and generic. Do not include credentials, private paths, real account identifiers, generated large datasets, or venue-specific operational history in fixtures or docs.
