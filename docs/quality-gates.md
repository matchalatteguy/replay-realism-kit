# Quality gates

Quality gates are small fail-closed checks over replay reports. The default gates require reviewable assumptions, an explicit fee model, at least one fill row, future-only markouts when required, and no stale-book fills.

Gate results are machine-readable records with stable names, severities, reason codes, and messages.
