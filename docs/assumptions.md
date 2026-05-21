# Assumption profiles

An `ExecutionAssumptionProfile` records the conditions required before replay evidence is reviewable: deterministic latency, stale-book threshold, tick size, minimum size, fee model, partial-fill policy, and future-markout requirements.

Zero fees are never inferred silently. Use `FeeModel.explicit_zero()` or set `explicit_zero_fees: true` in YAML when a zero-fee baseline is intentional.
