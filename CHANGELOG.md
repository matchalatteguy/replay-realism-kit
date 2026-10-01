# Changelog

## 0.2.0 — 2026-10-01

- Anchor generated markouts to actual execution instead of order arrival. For aggregate maker fills, use the final contributing trade; reports add `execution_timestamp`.
- Apply maker fill-or-kill policy when available opposing volume cannot fill the entire request.
- Gates validate typed report rows, finite values, schema version, counts, fee totals, and markout fields. Reconstruct assumptions to prevent a forged `reviewable` label from bypassing checks.
- Reject malformed YAML mappings, fractional or boolean latency settings, non-finite fee/profile/event values, ambiguous CSV shapes, and crossed book rows.
- Preserve event sequence when filtering maker trade evidence, including zero-latency baselines at equal timestamps.
- Reject non-positive markout horizons in public helpers; `compute_markout` now defaults to a 100 ms horizon.
- CLI input errors return a clean message and exit code `2`; invalid report shapes can still produce Markdown gate reviews.
- Add a reproducible four-case fee/queue/latency comparison and Python 3.11–3.14 CI with installed-wheel validation outside the source tree.

This release intentionally rejects incomplete handcrafted reports that previously passed. Markout horizons in simulation and public helpers must be positive integers. The report schema remains v1 with an additive execution timestamp; old complete reports without that field remain accepted.

## 0.1.0

Initial event normalization, fee/latency assumptions, maker/taker primitives, replay runner, reports, and CLI.
