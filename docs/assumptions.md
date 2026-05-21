# Assumption profiles

An `ExecutionAssumptionProfile` records the execution conditions that must be true before replay evidence is considered reviewable. Profiles make hidden backtest assumptions visible and machine-checkable.

## Fields

| Field | Meaning | Why it matters |
| --- | --- | --- |
| `name` | Human-readable profile identifier. | Report readers need to know which policy produced the fills. |
| `latency_ms` | Deterministic delay from decision time to order arrival. | Prevents instant-fill assumptions. |
| `stale_book_ms` | Maximum allowed gap between arrival and the book snapshot used for taker fills. | Rejects evidence based on old books. |
| `tick_size` | Minimum valid price increment. | Catches impossible limit prices. |
| `min_size` | Minimum valid order size. | Catches dust orders or malformed requests. |
| `allow_partial_fills` | Whether partial fills are allowed by the profile. | Documents fill semantics for reviewers. |
| `require_future_markout` | Whether every filled row needs a future-only markout. | Prevents lookahead-prone evidence. |
| `fee_model` | Explicit maker/taker fee model. | Prevents silently assuming zero fees. |

## YAML example

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

Use strings for decimal values in YAML to avoid accidental floating-point representation issues.

## Fee handling

Fees must be explicit. A non-zero fee profile can be expressed with maker/taker basis points:

```yaml
fee_model:
  name: demo-bps-fees
  maker_bps: "1"
  taker_bps: "5"
  explicit_zero_fees: false
```

A zero-fee baseline is allowed only when it is named explicitly:

```yaml
fee_model:
  name: explicit-zero-demo
  maker_bps: "0"
  taker_bps: "0"
  explicit_zero_fees: true
```

Do not omit fees and rely on defaults in serious review workflows. A missing fee policy should be treated as incomplete evidence even if a toy fixture happens to run.

## Safety levels

The current profile classifier returns one of three values:

- `reviewable`: latency is non-zero, stale-book tolerance is not extremely loose, and future markouts are required.
- `optimistic`: latency is zero or stale-book tolerance is too loose for the built-in review policy.
- `incomplete`: future markouts are disabled.

The classifier is deliberately conservative. It does not prove that a result is realistic; it only filters out obviously weak evidence.

## Practical guidance

- Start with a conservative profile and relax one field at a time only when you can justify it.
- Keep profile names stable because report artifacts include them.
- Use synthetic instruments such as `FOO-USD` or `instrument-A` in examples.
- Prefer deterministic latency values for tests and CI. Random latency models are outside the MVP.
- Keep network, credential, broker, and venue-specific assumptions out of profiles; this project is offline-only.
