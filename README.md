# Replay Realism Kit

Replay Realism Kit is a small offline Python toolkit for checking whether replayed trading decisions still look plausible after conservative execution assumptions are applied.

Naive backtests can overstate results by assuming instant fills, zero fees, perfect queue position, fresh books, or lookahead-prone markouts. This package makes those assumptions explicit, simulates deterministic maker/taker fills over local synthetic event streams, and emits machine-readable quality gates before a replay is treated as reviewable evidence.

The project is intentionally narrow: it helps engineers and LLM agents review execution realism for local replay artifacts. It is not a strategy engine or a live trading system.

## What it does

- Normalizes local `book`, `trade`, and `decision` events with stable `(timestamp, sequence)` ordering.
- Applies deterministic latency and stale-book rules before a decision can use book evidence.
- Simulates conservative maker queue fills and depth-aware taker fills.
- Requires explicit fee assumptions, including explicit zero-fee baselines.
- Computes future-only midpoint markouts so reports do not use pre-fill state.
- Writes JSON and Markdown reports with fail-closed quality gates.
- Runs fully offline on tiny CSV/YAML fixtures.

## Non-goals and safety boundaries

Replay Realism Kit is not:

- a broker, exchange connector, market-data client, wallet, signing tool, or live trading bot;
- an alpha model, portfolio optimizer, financial adviser, or data vendor;
- a networked service, credentialed integration, or order-capable framework;
- a venue-specific simulator or guarantee that historical fills would have happened in production.

All examples are synthetic and invented for testing/documentation. They do not come from a real venue or private trading history.

## Install

This repository uses `uv` and Python 3.11+.

```bash
uv sync
```

Run the test and lint gates locally:

```bash
uv run pytest
uv run ruff check
```

## Quickstart

Validate the bundled synthetic event file:

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
uv run replay-realism gate \
  --report reports/replay.json \
  --md-out reports/replay-review.md
```

Passing gates exit with code `0`. Required failures exit non-zero, so the command can be used in local scripts or CI checks.

Copy the bundled example into another directory:

```bash
uv run replay-realism init-example synthetic-book --out-dir scratch-examples
```

## Synthetic event format

The CLI accepts a small CSV event stream with these event types:

- `book`: one top-of-book snapshot row with bid/ask price and size;
- `trade`: one post-arrival trade row used by conservative maker-fill logic;
- `decision`: one hypothetical order decision row to replay.

Rows are sorted deterministically by `(timestamp, sequence)`. Use fake instruments such as `FOO-USD`, `BAR-USD`, or `instrument-A` in examples and tests.

Minimal columns used by the bundled fixture:

```csv
event_type,timestamp,sequence,instrument_id,venue_id,source,bid_price,bid_size,ask_price,ask_size,side,price,size,limit_price,order_type
book,1000,1,FOO-USD,SIM,fixture,99.90,10,100.00,5,,,,,
decision,1010,2,FOO-USD,SIM,fixture,,,,,buy,,2,100.00,taker
book,1060,3,FOO-USD,SIM,fixture,99.95,10,100.00,5,,,,,
```

## Assumption profile

Assumptions are explicit YAML inputs. A profile names latency, stale-book tolerance, tick/min-size constraints, partial-fill behavior, markout requirements, and fees.

```yaml
name: conservative-demo
latency_ms: 50
stale_book_ms: 250
tick_size: "0.01"
min_size: "0.0001"
allow_partial_fills: true
require_future_markout: true
fee_model:
  name: demo-bps-fees
  maker_bps: "1"
  taker_bps: "5"
  explicit_zero_fees: false
```

A profile is `reviewable` only when it avoids obviously optimistic defaults such as zero latency or very loose stale-book windows, and when future markouts are required. See `docs/assumptions.md` for details.

## Python API

```python
from decimal import Decimal

from replay_realism import (
    BookSnapshot,
    ExecutionAssumptionProfile,
    FeeModel,
    FillPolicy,
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
    policy=FillPolicy.FAK,
)
fill = simulate_taker_fill(request, book, assumptions)
assert fill.reason_code == "filled"
assert fill.filled_size == Decimal("2")
```

Important public objects:

- `ReplayEvent`, `BookEvent`, `TradeEvent`, `DecisionEvent`, `load_events_csv`
- `ExecutionAssumptionProfile`, `SafetyLevel`, `FeeModel`
- `BookSnapshot`, `FillRequest`, `FillResult`, `OrderSide`, `OrderType`, `FillPolicy`
- `simulate_taker_fill`, `simulate_maker_fill`
- `future_midpoint`, `compute_markout`, `MarkoutResult`
- `ReplayReport`, `write_json_report`, `write_markdown_report`
- `validate_replay_report`, `QualityGateResult`, `GateSeverity`

## CLI reference

```text
replay-realism validate-events --events PATH
replay-realism simulate --events PATH --assumptions PATH --json-out PATH
replay-realism gate --report PATH [--md-out PATH]
replay-realism init-example synthetic-book [--out-dir PATH]
```

The current `simulate` command is a deterministic demo runner for small local fixtures. It is meant for tests, examples, and report-shape validation rather than large historical replay jobs.

## Quality gates

The default gate checks fail closed when:

- assumptions are optimistic or incomplete;
- a report is missing an explicit fee model;
- no fill rows are present;
- future markouts are required but missing;
- stale-book fills appear in the report.

Gate output is a list of stable `pass`/`fail` results with reason codes and human messages. See `docs/quality-gates.md`.

## Documentation

- `docs/assumptions.md` explains assumption profiles, fee handling, and safety levels.
- `docs/fill-policies.md` explains conservative maker/taker semantics and reason codes.
- `docs/quality-gates.md` explains gate results, report contracts, and CI usage.
- `docs/api-and-cli.md` gives task-oriented API and CLI recipes.
- `examples/synthetic-book/README.md` walks through the bundled offline fixture.
- `PUBLIC_SAFETY_REVIEW.md` records the local public-safety review status and boundaries.

## Project status

Alpha public-candidate. APIs are intentionally small and deterministic; broad data adapters, venue plugins, live integrations, dashboards, and large sensitivity sweeps are out of scope for the MVP.

## License

MIT.
