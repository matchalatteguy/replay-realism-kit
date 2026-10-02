# API and CLI recipes

All commands operate on local files. Event input extension selects compact CSV or multi-level JSONL. Use Python 3.11–3.14.

## Compare profiles and sweeps

```bash
uv run replay-realism compare \
  --events examples/execution-stress/events.jsonl \
  --scenarios examples/execution-stress/scenarios.yaml \
  --json-out reports/comparison.json --csv-out reports/comparison.csv --md-out reports/comparison.md
```

Replace `scenarios.yaml` with `sweep.yaml` for the 29-case study. Every result remains visible, including failed gates. See [scenarios](scenarios.md), [report contracts](report-schema.md), and the [stress study](../examples/execution-stress/README.md).

```python
from replay_realism import compare_scenarios, load_events, load_scenarios

result = compare_scenarios(
    load_events("examples/execution-stress/events.jsonl"),
    load_scenarios("examples/execution-stress/scenarios.yaml"),
)
for scenario in result["scenarios"]:
    print(scenario["name"], scenario["summary"]["markout_coverage"])
```

Programmatic studies use `Scenario(name, assumptions, config)` and `ScenarioStudy(baseline, quote_unit, scenarios)`. `write_json_report`, `write_comparison_csv`, and `write_comparison_markdown` accept the returned comparison dictionary.

## Single-profile replay

```bash
uv run replay-realism validate-events --events examples/synthetic-book/events.csv
uv run replay-realism simulate \
  --events examples/synthetic-book/events.csv \
  --assumptions examples/synthetic-book/assumptions.yaml \
  --maker-queue-ahead 1 --maker-lifetime-ms 1000 \
  --markout-horizon-ms 100 --markout-max-delay-ms 1000 \
  --json-out reports/replay.json
uv run replay-realism gate --report reports/replay.json --md-out reports/review.md
```

The fixture validates five events and yields one positive taker fill with a future markout. `simulate` writes evidence with exit `0`; `gate` checks it. Malformed input exits `2`, failed gates exit `1`, and successful checks exit `0`.

```python
from decimal import Decimal
from replay_realism import ReplaySimulationConfig, load_events, simulate_replay
from replay_realism.assumptions import load_assumption_profile

report = simulate_replay(
    load_events("examples/synthetic-book/events.csv"),
    load_assumption_profile("examples/synthetic-book/assumptions.yaml"),
    ReplaySimulationConfig(maker_queue_ahead=Decimal("1")),
)
assert report.to_dict()["summary"]["filled_count"] == 1
```

## Individual fill primitives

```python
from decimal import Decimal
from replay_realism import (
    BookSnapshot, ExecutionAssumptionProfile, FeeModel, FillRequest,
    OrderSide, OrderType, TradeEvent, simulate_taker_fill, simulate_maker_fill,
)

assumptions = ExecutionAssumptionProfile(
    "reference", 50, 250, FeeModel(Decimal("1"), Decimal("5")),
)
request = FillRequest(
    "FOO-USD", OrderSide.BUY, OrderType.TAKER,
    Decimal("2"), Decimal("100"), 1010, venue_id="SIM",
)
book = BookSnapshot(
    "FOO-USD", 1000, 1,
    bids=((Decimal("99.95"), Decimal("10")),),
    asks=((Decimal("100"), Decimal("5")),), venue_id="SIM",
)
fill = simulate_taker_fill(request, book, assumptions)
assert fill.execution_timestamp == 1060
assert fill.book_timestamp == 1000

maker = FillRequest(
    "FOO-USD", OrderSide.BUY, OrderType.MAKER,
    Decimal("2"), Decimal("100"), 1010,
    queue_ahead=Decimal("1"), maker_lifetime_ms=300, venue_id="SIM",
)
trades = [TradeEvent(
    1070, 4, "FOO-USD", "SIM", side="sell", price=Decimal("100"), size=Decimal("3"),
)]
maker_fill = simulate_maker_fill(maker, trades, assumptions)
assert maker_fill.filled_size == Decimal("2")
assert [(item.kind, item.quantity) for item in maker_fill.trace] == [
    ("queue", Decimal("1")), ("fill", Decimal("2")),
]
```

For an unfinished maker, pass a justified `observed_until_timestamp` from the surrounding market log or retain incomplete-window evidence. The direct primitive has no access to future books; the runner derives the observation end from same-market book/trade records. [Fill policies](fill-policies.md) defines the boundaries.

`compute_markout(fill, midpoint, horizon_ms=100)` performs arithmetic for a supplied positive future midpoint. The replay runner selects and retains the actual future book; the arithmetic helper cannot authenticate or time an externally supplied price.

## Installed examples

```bash
replay-realism init-example execution-stress --out-dir demo
replay-realism init-example synthetic-book --out-dir demo
```

Both fixtures are included in built wheels. Existing example directories are never overwritten. Report outputs may be regenerated at chosen paths, but cannot share a path or replace an input file. Keep private source data outside the repository and commit only small invented examples.
