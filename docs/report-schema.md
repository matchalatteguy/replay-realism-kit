# Report contracts

Numeric prices, quantities, fees, and markouts serialize as decimal strings. Counts and millisecond timestamps are JSON integers. Unknown future fields can be ignored by consumers; use version fields and reason codes when applying policy.

## Single replay: `replay-realism-report/v1`

The existing v1 required fields remain: `schema_version`, `assumptions`, `summary`, and `fills`. Version 0.3 adds `engine_version: "0.3.0"`, `order_model: "independent"`, and `simulation_config` for generated causal reports. Older complete reports without simulation configuration receive structural/arithmetic checks; they carry no new trace verification.

`assumptions` contains the typed profile, fee model, and recomputed heuristic label. `simulation_config` records `maker_queue_ahead` as a decimal string and positive integer horizon, lifetime, and maximum observation-delay fields.

`summary` includes `fill_count` (decision-result rows, including rejections), `filled_count` (positive-fill rows), `fee_total`, `markout_count`, and `rejection_counts` keyed by reason. A partial execution counts as one positive-filled decision.

### Fill rows

| Fields | Types and meaning |
| --- | --- |
| `decision_id` | Stable SHA-256 identifier derived from venue, instrument, decision time, and sequence. |
| `instrument_id`, `venue_id`, `side`, `order_type` | Decision market and instruction. |
| `decision_timestamp`, `decision_sequence` | Integer source decision key. |
| `requested_size`, `limit_price`, `queue_ahead` | Decimal strings; requested size equals fill plus remainder. |
| `arrival_timestamp` | Decision time plus latency. |
| `execution_timestamp` | Arrival for takers; last contributing trade for makers; `null` when unfilled. |
| `book_timestamp`, `book_sequence` | Taker source snapshot key; otherwise `null`. |
| `expiry_timestamp` | Exclusive maker expiry; otherwise `null`. |
| `observation_end_timestamp` | Last matching market event, for maker-window coverage; otherwise `null`. |
| `completion_reason` | Maker `filled`, `expired`, or `incomplete-evidence`; `null` for takers and request-constraint rejections. |
| `filled_size`, `remaining_size`, `notional`, `fee` | Decimal strings. |
| `average_price`, `slippage` | Decimal strings, or `null` for no fill. |
| `reason_code`, `evidence` | Machine-readable reason and legacy human-readable evidence strings. |
| `trace` | Structured actual fill/queue accounting; rejected tentative fills are omitted. |
| `markout` | Future observation object or `null`. |

Each trace item has `kind` (`fill`/`queue`), integer `timestamp` and `sequence`, and decimal-string `price`, `quantity`, `available_quantity`, and `source_price`. Maker `source_side` identifies the opposing print; takers use `null`. Taker trace time is execution/arrival, while its sequence identifies the retained source snapshot. Maker trace time and sequence identify a trade. Maker fill price is the request limit; source price preserves the observed trade price.

Within a single decision, summed consumed volume cannot exceed a source event's available quantity. Across decisions, liquidity is intentionally reused by this independent-order model. The trace is an internal explanation; it cannot prove that a supplied source event occurred.

A markout contains positive integer `horizon_ms`, `midpoint` and `edge_after_fees` as decimal strings or `null`, `reason_code`, and optional observation timestamp/sequence. `ok` requires a positive fill and valid future midpoint. Aggregate maker horizons start at the last partial execution.

## Comparison: `replay-realism-comparison/v1`

| Field | Meaning |
| --- | --- |
| `engine_version`, `order_model` | Reference engine version and `independent` abstraction. |
| `baseline`, `quote_unit` | Named reference profile and caller-declared common fee/markout unit. |
| `event_count`, `decision_count`, `scenario_count` | Integer counts. |
| `gate_failure_count` | Total failed gates across all scenarios; zero is a necessary check, not a scientific conclusion. |
| `study_sha256` | Hash of semantic baseline, quote unit, assumptions, and simulation settings. |
| `events_sha256` | CLI-only SHA-256 of raw event-file bytes. The Python API accepts typed events and omits this file hash. |
| `scenarios` | Ordered named profiles, followed by all sweep combinations. |

Each scenario contains:

- `name`, serialized `assumptions`, and `config`;
- `summary`, `gates`, and integer `gate_failure_count`;
- `report`: embedded single-replay v1 report with complete traces;
- `delta_from_baseline`: signed filled-decision count and decimal-string fee delta; edge delta is a decimal string or `null`.

Comparison summary fields:

| Field | Type and rule |
| --- | --- |
| `decision_count`, `filled_count`, `markout_count` | Integers. Markout count counts positive-filled decisions with `ok` marks. |
| `markout_coverage` | Decimal string `markout_count / filled_count`; `null` when no decisions fill. |
| `fee_total` | Sum of all row fees, in the declared quote unit. |
| `edge_after_fees` | Sum of row edges only when at least one decision fills and every filled decision has a markout; otherwise `null`. |
| `rejection_counts` | Zero-filled decision counts by reason. |
| `instruments` | Sorted instrument/venue summaries: requested size, filled size, and fill ratio as decimal strings. Quantities are never summed across instruments. |

Each gate has `name`, `severity`, `reason_code`, and `message`. Automation should use reason codes; human text may change. Compare retains failed scenarios and missing fields, and exits `1` for any failed gate.

### Stable comparison CSV

```text
name,decision_count,filled_count,markout_count,markout_coverage,fee_total,edge_after_fees,gate_failure_count,delta_filled_count,delta_fee_total,delta_edge_after_fees
```

One row per scenario in JSON order. Missing coverage/edge/delta fields are empty CSV cells. All decimals retain the JSON string representation. Markdown contains the summary table plus rejection and failed-gate reasons. [The tested expected CSV](../examples/execution-stress/expected-summary.csv) is a compact complete example.
