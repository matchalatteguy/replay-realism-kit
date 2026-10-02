# Changelog

## 0.3.0 — 2026-10-02

- Add first-class named scenario comparisons and bounded Cartesian latency/queue/lifetime sweeps with deterministic JSON, stable CSV, and Markdown outputs. Keep all failed cases, coverage, per-market quantities, and baseline deltas.
- Use the latest causally known instrument/venue book at taker arrival; reject future quotes and stale known books. Make zero-latency sequence ordering and positive-latency market-first ties explicit.
- Bound maker orders by exclusive finite lifetimes, retain partial execution traces, and fail observation gates when unfinished orders outlive the supplied market evidence.
- Add structured source-volume accounting, directional price-limit and maker-limit checks, execution timing, exact notional-based markout arithmetic, and bounded future-observation delay.
- Isolate Decimal results from caller precision/rounding and reject duplicate event keys, duplicate JSON/YAML members, malformed multi-level books, and conflicting output/input paths.
- Add a bundled two-instrument, multi-level stress study, five controlled profiles, a 29-case sweep, exact expected CSV, counterexample regressions, and seeded conservation/sensitivity checks.
- Include both synthetic examples in wheels and exercise installed comparison/sweep commands outside the checkout in Python 3.11–3.14 CI.

These changes intentionally alter 0.2 timing and no-fill reason codes. See [migration notes](docs/migration-0.3.md). Single-replay v1 fields remain compatible; new causal evidence fields and separate scenario/comparison contracts are documented.

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
