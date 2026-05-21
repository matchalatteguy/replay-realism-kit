# Synthetic book example

This directory contains a tiny invented event stream for `FOO-USD`. It is designed for tests, documentation, and local smoke checks. It has no network dependency and is not sourced from a real venue.

## Files

- `events.csv`: synthetic `book`, `decision`, and `trade` rows.
- `assumptions.yaml`: conservative demo profile with non-zero latency, explicit fees, stale-book limits, and required future markouts.

## Run it

From the repository root:

```bash
uv run replay-realism validate-events --events examples/synthetic-book/events.csv
uv run replay-realism simulate \
  --events examples/synthetic-book/events.csv \
  --assumptions examples/synthetic-book/assumptions.yaml \
  --json-out reports/replay.json
uv run replay-realism gate \
  --report reports/replay.json \
  --md-out reports/replay-review.md
```

The event stream is intentionally small:

1. a starting top-of-book snapshot;
2. a hypothetical taker buy decision;
3. a future book after the configured latency;
4. a synthetic trade row useful for maker-fill tests;
5. a later book used for future-only markout.

Use this example as a format reference, not as market data.
