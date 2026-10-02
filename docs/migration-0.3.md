# Migration from 0.2 to 0.3

0.3 intentionally changes execution timing to use causal market evidence and finite maker windows. Re-run previous fixtures and update expected results with an explanation.

## Known quotes at arrival

Previously the runner waited for the first book at/after arrival. It now selects the latest known same-instrument and same-venue book and executes a taker at arrival. Book age means `arrival − book.timestamp`, bounded by `stale_book_ms`. A future snapshot cannot supply depth. Add a genuinely known quote before arrival to fixtures that relied on later quotes.

`first_eligible_book` remains importable as a compatibility name, but now returns the latest known book. Prefer `latest_eligible_book`. Direct taker primitives reject `book-after-arrival` and `book-after-decision-sequence`; old `book-before-arrival` behavior is removed.

Zero-latency book ties use earlier sequence numbers; maker ties use later sequence numbers. At positive latency, market events at the arrival timestamp precede synthetic order arrival, so maker consumption starts strictly later. Fill and markout evidence are venue-scoped as well as instrument-scoped.

## Finite maker windows

`ReplaySimulationConfig` keeps its first two positional arguments and adds positive `maker_lifetime_ms=1000` and `markout_max_delay_ms=1000`. `FillRequest` adds lifetime, optional sequence, and venue at the end of its existing fields.

Maker expiry is exclusive. An unfinished maker requires matching market evidence through expiry; otherwise the generated report retains `completion_reason: incomplete-evidence` and fails the observation gate. New unfilled reasons are `maker-expired` and `maker-evidence-incomplete`; they replace the ambiguous `queue-not-exhausted` / `no-post-arrival-trade` distinction in the primitive. Inspect the queue trace for the actual volume consumed.

The direct maker API accepts keyword `observed_until_timestamp`. If omitted, the last matching trade defines coverage. The runner includes matching books when deriving the observation end. Markouts must be within the configured maximum delay following their execution-anchored horizon.

## Reports and inputs

The single-replay schema remains v1 with additive configuration and trace fields. Older complete v1 reports without simulation configuration retain structural and arithmetic gating, with no new trace verification. The comparison and scenario schemas are separately versioned v1 contracts.

JSONL adds multi-level depth; CSV remains the compact one-level format. Duplicate event keys, duplicate JSON/YAML members, non-finite numbers, and malformed depth are rejected. Unknown harmless event metadata is ignored. Multi-level arrays take precedence over scalar top-of-book fields when both are supplied.

Numeric entry points isolate their 28-digit, round-half-even Decimal context from caller settings. Unsupported exponent ranges, overflow, and inexact underflow raise numeric errors; they never silently become zero amounts. Markout arithmetic uses filled notional directly to avoid weighted-average rounding noise. New comparisons keep missing markouts and zero-fill aggregate edges as `null`, so consumers must handle unavailable values explicitly.

A stable decision identifier is derived from its full market/event key. These reference-model results may differ from prior release outputs; version and preserve the assumptions with any stored evidence.
