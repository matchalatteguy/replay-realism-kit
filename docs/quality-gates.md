# Quality gates

Quality gates are small fail-closed checks over replay reports. They are designed for local scripts, CI jobs, and LLM-agent review loops where a report should not be treated as evidence until basic realism assumptions are visible.

## Report contract

A JSON report contains three top-level sections:

- `assumptions`: serialized `ExecutionAssumptionProfile` including `safety_level` and `fee_model`;
- `summary`: counts and aggregate fee totals;
- `fills`: fill rows with reason codes, evidence, and markout status.

The Markdown report is a human-readable review of the same data plus gate outcomes.

## Built-in gates

| Gate | Pass condition | Failure reason |
| --- | --- | --- |
| `assumption-profile` | `assumptions.safety_level == "reviewable"` | `optimistic-or-incomplete-assumptions` |
| `fee-model` | an explicit fee model name is present | `missing-fee-model` |
| `sample-count` | at least one fill row is present | `low-sample-count` |
| `future-markout` | required markouts are present and `ok` | `missing-future-markout` |
| `stale-book` | no fill row has reason `stale-book` | `stale-book-used` |

A gate result includes:

- `name`
- `severity`: `pass`, `warn`, or `fail`
- `reason_code`
- `message`

The current built-in policy emits `pass` and `fail`; `warn` exists for future extension.

## CLI usage

```bash
uv run replay-realism simulate \
  --events examples/synthetic-book/events.csv \
  --assumptions examples/synthetic-book/assumptions.yaml \
  --json-out reports/replay.json

uv run replay-realism gate \
  --report reports/replay.json \
  --md-out reports/replay-review.md
```

The `gate` command exits `0` only when all required gates pass. It exits non-zero when any gate fails.

## CI pattern

A minimal shell check can fail a build when replay evidence becomes optimistic or incomplete:

```bash
uv run replay-realism validate-events --events examples/synthetic-book/events.csv
uv run replay-realism simulate \
  --events examples/synthetic-book/events.csv \
  --assumptions examples/synthetic-book/assumptions.yaml \
  --json-out reports/replay.json
uv run replay-realism gate --report reports/replay.json --md-out reports/replay-review.md
```

Keep generated `reports/` output out of source control unless the report itself is an intentional fixture.

## What gates do not prove

Passing gates do not prove profitability, real-world fill probability, venue compatibility, or live execution safety. They only show that the local replay report has explicit assumptions, fees, future-only markouts, and no obvious stale-book usage under the built-in policy.
