# Contributing

Thanks for improving Replay Realism Kit. The project is intentionally small, offline, and synthetic-first.

## Local workflow

```bash
uv sync --group dev
uv run --group dev pytest
uv run ruff check
```

For a smoke test of the bundled replay:

```bash
mkdir -p reports
uv run replay-realism validate-events --events examples/synthetic-book/events.csv
uv run replay-realism simulate \
  --events examples/synthetic-book/events.csv \
  --assumptions examples/synthetic-book/assumptions.yaml \
  --json-out reports/replay.json
uv run replay-realism gate --report reports/replay.json --md-out reports/replay-review.md
```

`reports/` is ignored by Git and is safe for local scratch output.

## Public-safe contribution rules

- Use only invented examples and synthetic fixtures.
- Do not add credentials, real account identifiers, production paths, private hostnames, cookies, tokens, or real trading history.
- Do not add broker, exchange, wallet, signing, authentication, or live order-placement features.
- Keep tests offline and deterministic.
- Prefer small CSV/YAML fixtures that reviewers can inspect by eye.
- Document new reason codes, report fields, and CLI behavior in the same change that adds them.

## Pull request checklist

Before proposing a change, verify:

- [ ] `uv run --group dev pytest` passes.
- [ ] `uv run ruff check` passes.
- [ ] README or docs are updated for user-visible behavior changes.
- [ ] New examples use invented instruments such as `FOO-USD`, `BAR-USD`, or `instrument-A`.
- [ ] No generated reports, caches, virtual environments, or large artifacts are committed.
- [ ] The change preserves the offline-only, non-order-capable scope.
