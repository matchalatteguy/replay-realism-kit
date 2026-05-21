# LLM agent guide

Replay Realism Kit is deliberately small, offline, and public-safe. This guide is for coding agents and automated assistants editing the repository.

## Mission

Help users decide whether a local replay artifact is reviewable under explicit execution assumptions. Keep the project focused on deterministic market-replay realism, not strategy generation or live trading.

## Hard boundaries

Do not add:

- broker, exchange, wallet, signing, authentication, credential, or live order-placement code;
- real account identifiers, venue-specific operational history, private datasets, or production logs;
- network calls in tests or examples;
- generated large datasets, caches, notebooks with embedded outputs, or runtime databases;
- claims that passing gates proves profitability, deployability, or production fill probability.

All fixtures and docs must use invented instruments such as `FOO-USD`, `BAR-USD`, `BAZ-USD`, or `instrument-A`.

## Before editing

1. Read `README.md` and `docs/onboarding.md`.
2. Run or inspect the current test suite before changing behavior.
3. Prefer small, testable changes over broad rewrites.
4. Keep API names neutral: `instrument_id`, `venue_id`, `book_event`, `trade_event`, `decision_event`, `FillRequest`, `FillResult`, `ExecutionAssumptionProfile`, `QualityGateResult`.

## Useful commands

```bash
uv sync
uv run pytest
uv run ruff check
uv run replay-realism validate-events --events examples/synthetic-book/events.csv
uv run replay-realism simulate \
  --events examples/synthetic-book/events.csv \
  --assumptions examples/synthetic-book/assumptions.yaml \
  --json-out reports/replay.json
uv run replay-realism gate --report reports/replay.json --md-out reports/replay-review.md
```

Generated `reports/` outputs are for local inspection and are ignored by Git.

## Expected design style

- Deterministic by default: stable sorting, explicit timestamps, no hidden randomness.
- Fail closed: missing assumptions should fail gates rather than silently pass.
- Decimal-safe where prices, sizes, notional, and fees are involved.
- Future-only evidence: fills and markouts should not use pre-arrival or pre-fill state.
- Offline examples: tests should run without credentials, network, or external services.
- Small public API: add new concepts only when the README can explain them briefly.

## Good task patterns

| Task | Good approach |
| --- | --- |
| Add a reason code | Add or update a failing test, implement the behavior, document the reason code in `docs/fill-policies.md` or `docs/quality-gates.md`. |
| Add a CLI flag | Update parser help, tests, `docs/api-and-cli.md`, and the quickstart if the flag changes first-use behavior. |
| Change report shape | Update `ReplayReport`, gate validation, tests, and the report contract section in `docs/quality-gates.md`. |
| Add example data | Keep it tiny, synthetic, human-readable CSV/YAML, and explain the event story in the example README. |

## Public-safety checklist for agents

Before committing, scan changed text for:

- machine-specific absolute paths, usernames, or hostnames;
- tokens, keys, secrets, cookies, account identifiers, or private infrastructure names;
- names of private projects, private repos, or internal workflows;
- real venue-specific examples presented as fixtures;
- live/auth/order-capable language outside explicit non-goal warnings.

Review matches manually. Some words may be acceptable in non-goal warnings, but credentials or private context are not.
