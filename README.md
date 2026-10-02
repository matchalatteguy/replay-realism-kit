# Replay Realism Kit

Compare execution assumptions on the same decisions. An offline Python library and CLI for causal snapshot replay, explicit fees, finite maker lifetimes, and explainable fill traces.

The bundled [execution stress study](examples/execution-stress/README.md) contains two instruments, multiple book levels, eight decisions, and five named profiles:

| Profile | Filled decisions | Fees | Complete markout after fees |
| --- | ---: | ---: | ---: |
| reference | 8 / 8 | 0.36004 | −1.16004 |
| higher fees | 8 / 8 | 1.5002 | −2.3002 |
| queue ahead | 7 / 8 | 0.32003 | −0.92003 |
| slower arrival | 5 / 8 | 0.13499 | 0.36501 |
| shorter maker lifetime | 8 / 8 | 0.34502 | −1.74502 |

All prices, orders, and amounts are invented; amounts use the declared synthetic USD quote unit. A changed fill set can increase the summed markout by skipping a losing order. Read fill quantities, rejected decisions, and coverage together. This fixture demonstrates sensitivity and accounting; it supplies no estimate of real execution or strategy performance.

## Try the comparison

Python 3.11–3.14 and [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/matchalatteguy/replay-realism-kit.git
cd replay-realism-kit
uv sync --locked
uv run replay-realism compare \
  --events examples/execution-stress/events.jsonl \
  --scenarios examples/execution-stress/scenarios.yaml \
  --json-out reports/comparison.json \
  --csv-out reports/comparison.csv \
  --md-out reports/comparison.md
```

Expected: `compared 5 scenarios; 0 failed gates`. Use `sweep.yaml` for 29 named and Cartesian scenarios. Every scenario remains in the output, including failures. JSON retains per-instrument quantities, baseline deltas, exact fills, source-event references, and quality gates; CSV is a stable summary; Markdown is a readable review.

Install the tagged release outside a checkout:

```bash
uv tool install 'git+https://github.com/matchalatteguy/replay-realism-kit.git@v0.3.0'
replay-realism init-example execution-stress --out-dir demo
replay-realism compare \
  --events demo/execution-stress/events.jsonl \
  --scenarios demo/execution-stress/scenarios.yaml \
  --json-out comparison.json --csv-out comparison.csv --md-out comparison.md
```

## Execution semantics

- Takers consume the latest **known** same-instrument and same-venue snapshot at arrival. Future snapshots cannot supply depth. Book age is bounded by `stale_book_ms`.
- At zero latency, only earlier sequence numbers can supply a book; later sequence numbers can supply maker trades. At positive-latency arrival, market events at the arrival timestamp precede the synthetic order.
- Makers consume opposing post-arrival trade volume after a declared queue, until exclusive expiry. Partial executions retain their quantities and timestamps. Logs ending before an unfinished order expires fail the observation gate.
- Markouts use the first matching future book after the configured horizon from actual execution, bounded by `markout_max_delay_ms`. The last contributing trade anchors an aggregate maker markout.
- Missing markouts and zero-fill scenarios retain `null` aggregate edges. Coverage counts positive-filled decisions with usable markouts. All aggregate fees and edges require a declared common quote unit.
- Decimal arithmetic uses an isolated 28-digit context. Duplicate event keys, duplicate JSON/YAML members, malformed shapes, and non-finite values are rejected.

See [events](docs/event-schema.md), [scenarios and sweeps](docs/scenarios.md), [fill policies](docs/fill-policies.md), and [report schemas](docs/report-schema.md). [Migration to 0.3](docs/migration-0.3.md) explains the intentional timing changes.

## Python API

```python
from replay_realism import compare_scenarios, load_events, load_scenarios

comparison = compare_scenarios(
    load_events("examples/execution-stress/events.jsonl"),
    load_scenarios("examples/execution-stress/scenarios.yaml"),
)
assert comparison["gate_failure_count"] == 0
for scenario in comparison["scenarios"]:
    print(scenario["name"], scenario["summary"])
```

Individual maker/taker primitives, fee models, replay reports, and report gates are also available. [API and CLI recipes](docs/api-and-cli.md) cover single-profile replay and programmatic use. Exit codes are `0` for successful checks, `1` for failed gates, and `2` for invalid inputs. `simulate` writes evidence; `gate` applies its policy. `compare` performs both and writes all results even when gates fail.

## Scope and evidence

Each decision is replayed independently. Orders reuse market evidence and have no shared liquidity depletion, queue state, inventory, capital, or cancellations. Maker queue size is supplied, and fills occur at the request limit. Snapshots represent known displayed depth between updates; the model cannot infer intervening changes, hidden liquidity, venue matching priority, or a full order lifecycle.

Gates check internal quantities, fees, directional price limits, causal timing, expiry, and markout coverage. `reviewable` is a documented assumption heuristic, and the sample gate requires only one decision. Passing checks cannot establish source authenticity, venue accuracy, profitability, or statistical adequacy. See [quality gates](docs/quality-gates.md). The package makes no network calls and places no orders.

## Development

```bash
uv run pytest
uv run ruff check .
uv build
```

Pinned CI runs on Python 3.11–3.14, checks accounting and causality invariants, and builds and runs the installed wheel outside the checkout. Both small examples are included in the wheel. [CHANGELOG.md](CHANGELOG.md), [CONTRIBUTING.md](CONTRIBUTING.md), and [SECURITY.md](SECURITY.md) cover changes, contributions, and issue reporting.

MIT licensed.
