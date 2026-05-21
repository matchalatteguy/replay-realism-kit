# Synthetic book example

This directory contains a tiny invented event stream for `FOO-USD`. It is designed for tests, documentation, and local smoke checks. It has no network dependency and is not sourced from a real venue.

## Files

- `events.csv`: synthetic `book`, `decision`, and `trade` rows.
- `assumptions.yaml`: conservative demo profile with non-zero latency, explicit fees, stale-book limits, and required future markouts.

## Event story

The fixture has five rows:

1. `book` at timestamp `1000`: initial top-of-book snapshot.
2. `decision` at timestamp `1010`: hypothetical taker buy for size `2` with limit `100.00`.
3. `book` at timestamp `1060`: first eligible book after the configured `50 ms` latency.
4. `trade` at timestamp `1070`: synthetic sell trade used by maker-fill examples.
5. `book` at timestamp `1200`: later midpoint used for a future-only markout.

The values are intentionally simple so a reader can compute the expected result by hand.

## Run it

From the repository root:

```bash
mkdir -p reports
uv run replay-realism validate-events --events examples/synthetic-book/events.csv
uv run replay-realism simulate \
  --events examples/synthetic-book/events.csv \
  --assumptions examples/synthetic-book/assumptions.yaml \
  --json-out reports/replay.json
uv run replay-realism gate \
  --report reports/replay.json \
  --md-out reports/replay-review.md
```

Expected gate output:

```text
pass: assumption-profile: reviewable-assumptions
pass: fee-model: explicit-fee-model
pass: sample-count: sufficient-sample-for-demo
pass: future-markout: future-only-markouts
pass: stale-book: no-stale-book-fills
```

## What to inspect

- `reports/replay.json` for the machine-readable report contract.
- `reports/replay-review.md` for the human-readable gate review.
- `docs/quality-gates.md` for why each gate passes or fails.
- `docs/onboarding.md` for safe next edits.

Use this example as a format reference, not as market data.
