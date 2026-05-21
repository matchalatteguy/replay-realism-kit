# Replay Realism Kit

Replay Realism Kit is a small offline Python toolkit for checking whether replayed trading decisions still look plausible after conservative execution assumptions are applied.

Naive backtests can overstate results by assuming instant fills, zero fees, perfect queue position, fresh books, or lookahead-prone markouts. This package makes those assumptions explicit, simulates deterministic maker/taker fills over local synthetic event streams, and emits machine-readable quality gates before a replay is treated as reviewable evidence.

## What it does

- Normalizes local `book`, `trade`, and `decision` events with stable `(timestamp, sequence)` ordering.
- Applies deterministic latency and staleness rules.
- Simulates conservative maker queue fills and depth-aware taker fills.
- Requires explicit fee assumptions, including explicit zero-fee baselines.
- Computes future-only midpoint markouts.
- Writes JSON and Markdown reports with fail-closed quality gates.

## Non-goals and safety boundaries

This is not a broker, exchange connector, live trading bot, alpha model, data vendor, wallet, or credentialed integration. It does not place orders, authenticate to services, fetch market data from networks, or provide financial advice. Examples are tiny synthetic fixtures intended for testing and education.

## Install

```bash
uv sync
```

## Quickstart

Validate a tiny synthetic event file:

```bash
uv run replay-realism validate-events --events examples/synthetic-book/events.csv
```

Run a replay and write a JSON report:

```bash
uv run replay-realism simulate \
  --events examples/synthetic-book/events.csv \
  --assumptions examples/synthetic-book/assumptions.yaml \
  --json-out reports/replay.json
```

Gate the report and write a Markdown review:

```bash
uv run replay-realism gate --report reports/replay.json --md-out reports/replay-review.md
```

Passing gates exit with code `0`; required failures exit non-zero so the commands can be used in local scripts or CI.

## Python API

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

book = BookSnapshot(
    instrument_id="FOO-USD",
    timestamp=1_000,
    sequence=1,
    bids=((Decimal("99.90"), Decimal("10")),),
    asks=((Decimal("100.00"), Decimal("5")),),
)
assumptions = ExecutionAssumptionProfile(
    name="explicit-demo",
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
    decision_timestamp=950,
)
fill = simulate_taker_fill(request, book, assumptions)
assert fill.filled_size == Decimal("2")
```

## Documentation

- `docs/assumptions.md` explains assumption profiles and fee handling.
- `docs/fill-policies.md` explains conservative maker/taker semantics.
- `docs/quality-gates.md` explains gate results and reason codes.

## Project status

Alpha public-candidate. APIs are intentionally small and deterministic; broad data adapters and live integrations are out of scope.
