# Replay Realism Kit

A deterministic execution simulator for small replay fixtures. Compare the same decisions under different fees, latency, and maker queue assumptions, and inspect why a fill succeeded or failed.

The [seven-event comparison](examples/assumption-comparison/README.md) produces this result:

| Setting | Taker size | Maker size | Fees | Future markout after fees |
| --- | ---: | ---: | ---: | ---: |
| explicit zero fees | 2 | 2 | 0.00 | 1.60 |
| fees | 2 | 2 | 0.12008 | 1.47992 |
| fees + queue | 2 | 1 | 0.11009 | 0.98991 |
| fees + queue + delay | 0 | 0 | 0 | 0 |

These are invented prices and decisions, with amounts in the fixture's quote unit. The last row misses the trade and the crossable ask because arrival is later. This demonstrates sensitivity to assumptions; it provides no estimate of strategy performance or real fill probability.

## Try it

Python 3.11+ and [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/matchalatteguy/replay-realism-kit.git
cd replay-realism-kit
uv sync --locked
uv run python examples/assumption-comparison/compare.py
```

To generate and validate a report:

```bash
uv run replay-realism validate-events --events examples/synthetic-book/events.csv
uv run replay-realism simulate \
  --events examples/synthetic-book/events.csv \
  --assumptions examples/synthetic-book/assumptions.yaml \
  --json-out reports/replay.json \
  --maker-queue-ahead 1 \
  --markout-horizon-ms 100
uv run replay-realism gate --report reports/replay.json --md-out reports/review.md
```

The bundled fixture passes all five default gates. JSON contains individual fill reasons, execution timestamps, fees, and markouts; Markdown adds the gate results. Commands exit `0` on success, `1` when gates fail, and `2` for unreadable or malformed input.

## What is modeled

- Takers consume crossable depth in the first snapshot at or after order arrival. That snapshot must be within the configured time tolerance.
- Makers fill only after opposing post-arrival trades consume a declared queue size.
- Fees use explicit maker/taker basis points; a zero-fee baseline must be labeled explicitly.
- Markouts use the first same-instrument book at or after the positive horizon following actual execution. For makers with multiple partial executions, the final contributing trade anchors the aggregate markout.
- Events sort by timestamp and sequence. Arithmetic uses `Decimal` for prices, quantities, and fees.

The CLI accepts compact CSV `book`, `trade`, and `decision` events. Profiles are YAML. The [event schema](docs/event-schema.md), [assumption guide](docs/assumptions.md), and [fill policies](docs/fill-policies.md) define the inputs and semantics.

## Python API

```python
from decimal import Decimal

from replay_realism import load_events_csv, simulate_replay
from replay_realism.assumptions import load_assumption_profile
from replay_realism.simulation import ReplaySimulationConfig

report = simulate_replay(
    load_events_csv("examples/synthetic-book/events.csv"),
    load_assumption_profile("examples/synthetic-book/assumptions.yaml"),
    ReplaySimulationConfig(maker_queue_ahead=Decimal("1"), markout_horizon_ms=100),
)
print(report.to_dict()["summary"])
```

The public API also exposes individual maker/taker fill functions, request and book types, fee models, markout arithmetic, and report writers. See [API and CLI recipes](docs/api-and-cli.md).

## What a passing gate means

Gates check report structure, finite numeric fields, internally consistent counts and fees, typed assumptions, and required markout fields. They recompute the assumption heuristic rather than trusting a `safety_level` label supplied in JSON.

`reviewable` means positive latency, a configured tolerance of at most 5 seconds, and a required future markout. It is a heuristic, not a certification. A report cannot prove that its source events are authentic or that an execution model matches a venue. The `sample-count` gate only requires one decision result; it does not establish statistical adequacy. See [quality gates](docs/quality-gates.md) and the [report contract](docs/report-schema.md).

## Limits

This is a small, inspectable reference model. Each decision is replayed independently: orders do not share depleted liquidity, queue state, cancellations, inventory, or capital. Maker queue size is supplied rather than inferred. The CSV fixture has one book level; the Python taker primitive accepts multiple levels. The runner waits for the next snapshot instead of reconstructing a full exchange book at arrival, and maker orders have no time-in-force deadline.

Hidden liquidity, venue matching rules, cross-venue routing, and full order lifecycle simulation are outside this model. Use it for fixture tests and assumption comparisons, and validate a separate execution model against appropriate data before making claims about real fills. The package makes no network calls and places no orders. All bundled events are synthetic.

## Development

```bash
uv run pytest
uv run ruff check .
uv build
```

CI runs tests and lint on Python 3.11–3.14, builds the package, and executes the installed wheel from outside the checkout. [CHANGELOG.md](CHANGELOG.md) records the `0.x` API's behavior changes. [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md) cover contributions and reporting issues.

MIT licensed.
