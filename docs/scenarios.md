# Scenario studies and sweeps

`compare` applies named assumptions to exactly the same sorted decisions and emits all scenario results. Inputs are local `.csv` or `.jsonl` events plus YAML using `replay-realism-scenarios/v1`.

## Minimal study

```yaml
schema_version: replay-realism-scenarios/v1
baseline: reference
quote_unit: synthetic USD
profiles:
  - name: reference
    assumptions:
      latency_ms: 10
      stale_book_ms: 250
      tick_size: '0.01'
      min_size: '0.0001'
      allow_partial_fills: true
      require_future_markout: true
      fee_model:
        name: explicit-fees
        maker_bps: '1'
        taker_bps: '5'
        explicit_zero_fees: false
    simulation:
      maker_queue_ahead: '0'
      markout_horizon_ms: 100
      maker_lifetime_ms: 300
      markout_max_delay_ms: 200
```

`baseline` must name an included profile. Names are unique slugs of 1–64 characters using letters, digits, `_`, `.`, and `-`. Declare the common quote unit before combining fees or markouts across instruments. The tool does not perform currency conversion or infer units from symbol names.

Assumption fields and fee-model fields are complete and typed. YAML booleans must be actual booleans; quote decimal values to preserve the intended precision. Duplicate mapping keys and unknown study/profile/settings keys are errors. [Assumptions](assumptions.md) describes their validation and heuristic labels.

Simulation defaults when omitted:

| Field | Default | Meaning |
| --- | ---: | --- |
| `maker_queue_ahead` | `'1'` | Supplied non-negative quantity ahead of each independent maker. |
| `markout_horizon_ms` | `100` | Positive horizon after execution. |
| `maker_lifetime_ms` | `1000` | Positive duration from arrival to exclusive expiry. |
| `markout_max_delay_ms` | `1000` | Maximum permitted delay after the markout target. |

## Cartesian sweep

Add to the study:

```yaml
sweep:
  profile: reference
  latency_ms: [10, 30, 80, 150]
  maker_queue_ahead: ['0', '2', '4']
  maker_lifetime_ms: [150, 300]
```

At least one axis is required. Omitted axes keep the base profile's value. Lists are non-empty and contain unique values; latency is a non-negative integer, lifetime a positive integer, and queue a finite non-negative decimal. The total number of named plus expanded scenarios is bounded at 64. Generated names contain the three parameter values. Overlong generated names are rejected.

Named profiles appear first, followed by Cartesian combinations in listed axis order. Baseline deltas compare counts, fees, and complete aggregate markouts. Changing assumptions may change which decisions fill; compare rejected decisions and per-instrument quantities before interpreting a delta. Missing marks make aggregate edge and its delta unavailable.

## Python API

```python
from replay_realism import compare_scenarios, load_events, load_scenarios

study = load_scenarios("examples/execution-stress/sweep.yaml")
result = compare_scenarios(load_events("examples/execution-stress/events.jsonl"), study)
assert result["scenario_count"] == 29
assert result["gate_failure_count"] == 0
```

`Scenario`, `ScenarioStudy`, and `ReplaySimulationConfig` support programmatic studies with the same policy. Reports are deterministic for the same typed inputs and engine version. The CLI adds a raw-event SHA-256; the semantic study hash includes the baseline, quote unit, profile assumptions, and simulation settings.
