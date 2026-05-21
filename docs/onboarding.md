# First five minutes

This guide is the shortest path from a fresh clone to a passing local replay gate. It assumes Python 3.11+ and `uv` are available.

## 1. Install dependencies

```bash
uv sync
```

The package has one runtime dependency, PyYAML. Test and lint tools are installed through the development dependency group.

## 2. Run the bundled replay

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

Expected terminal shape:

```text
validated 5 events
wrote reports/replay.json
wrote reports/replay-review.md
pass: assumption-profile: reviewable-assumptions
pass: fee-model: explicit-fee-model
pass: sample-count: sufficient-sample-for-demo
pass: future-markout: future-only-markouts
pass: stale-book: no-stale-book-fills
```

`reports/` is ignored by Git so local smoke outputs do not pollute commits.

## 3. Inspect the report

Open `reports/replay-review.md`. A healthy demo report should show:

- one synthetic fill row;
- an explicit conservative assumption profile;
- an explicit fee model;
- a future-only markout;
- passing fail-closed quality gates.

## 4. Run project checks

```bash
uv run pytest
uv run ruff check
```

These checks are intentionally small and offline. They should not need network access after dependencies are installed.

## 5. Change one thing safely

Good first edits:

- adjust the synthetic assumption profile and observe which gate fails;
- add a tiny event-row validation test;
- document a new reason code in `docs/fill-policies.md` after adding test coverage;
- add a small API example using `FOO-USD`, `BAR-USD`, or another invented instrument.

Avoid these in first contributions:

- real venue data or production identifiers;
- credentials, API keys, account IDs, wallets, or order-capable integrations;
- broad data adapters, dashboards, live services, or strategy/alpha claims;
- large generated artifacts checked into the repository.

## Repository map

```text
README.md                         project overview and quickstart
examples/synthetic-book/           tiny invented replay fixture
docs/assumptions.md                assumption profile reference
docs/fill-policies.md              maker/taker fill semantics
docs/quality-gates.md              gate contract and CI pattern
docs/api-and-cli.md                task-oriented API/CLI recipes
docs/llm-agent-guide.md            guardrails for coding agents
src/replay_realism/                package source
tests/                             offline pytest suite
PUBLIC_SAFETY_REVIEW.md            public-safety boundary notes
```

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `uv: command not found` | `uv` is not installed or not on PATH. | Install `uv` from the official Astral instructions, then reopen the shell. |
| `ModuleNotFoundError: replay_realism` | Commands were run outside the project environment. | Use `uv run ...` from the repository root. |
| `missing-future-markout` | The fill has no later book snapshot at the required horizon. | Add a later synthetic book row or disable the requirement only for an explicit toy baseline. |
| `optimistic-or-incomplete-assumptions` | The profile is too loose for review. | Use non-zero latency, bounded stale-book tolerance, explicit fees, and required future markouts. |
| `refusing to overwrite existing example directory` | `init-example` protects local files. | Choose a new `--out-dir` or move the existing copy yourself. |
