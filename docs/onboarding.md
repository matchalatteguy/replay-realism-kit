# First five minutes

Start with Python 3.11–3.14 and uv. From a fresh checkout:

```bash
uv sync --locked
uv run replay-realism validate-events --events examples/execution-stress/events.jsonl
uv run replay-realism compare \
  --events examples/execution-stress/events.jsonl \
  --scenarios examples/execution-stress/scenarios.yaml \
  --json-out reports/comparison.json --csv-out reports/comparison.csv --md-out reports/comparison.md
```

Expected output: `validated 33 events`, then `compared 5 scenarios; 0 failed gates`.

Read `reports/comparison.md` for the summary and gate reasons. In JSON, inspect `scenarios[0].report.fills[0]`: a multi-level ALPHA buy records both consumed levels, its arrival, the known source snapshot, fees, and the actual future markout. Compare queue and lifetime profiles using per-instrument fill quantities. An increased summed edge can reflect skipped losing fills, so interpret counts, quantities, and coverage together.

Use `sweep.yaml` for the full 29-case sensitivity study. Generated reports are ignored by Git. The [stress README](../examples/execution-stress/README.md) explains exact arithmetic and deliberate failure experiments.

## Checks

```bash
uv run pytest
uv run ruff check .
uv build
```

Core tests run offline after dependencies are installed. The packaging smoke test builds and installs a wheel in a temporary environment and may need the dependency/build cache or network access. CI executes it on Python 3.11–3.14.

## Useful references

- [Events](event-schema.md): CSV/JSONL, multi-level depth, timing, duplicate rejection.
- [Scenarios](scenarios.md): named profiles, complete settings, bounded Cartesian sweeps.
- [Fill policies](fill-policies.md): causal book selection, maker expiry, independent-order scope.
- [Report schemas](report-schema.md): decimal types, nulls, trace accounting, stable CSV header.
- [Quality gates](quality-gates.md): policy, reason codes, practical limits.
- [API and CLI](api-and-cli.md): individual primitives and installed examples.
- [0.3 migration](migration-0.3.md): behavior changes from earlier releases.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `missing-arrival-book` | Provide a matching snapshot known before/at arrival; a later quote cannot fill the order. |
| `stale-book` | The latest known quote is older than the configured tolerance. |
| `missing-future-markout` | Supply a matching future book within the horizon plus maximum delay. |
| `incomplete-maker-window` | Extend the matching market log through expiry, preserving genuine source coverage. |
| `optimistic-or-incomplete-assumptions` | Positive latency, bounded tolerance, and required future markouts are necessary for the heuristic. |
| `refusing to overwrite existing example directory` | Pick a fresh output directory. |
| Input exits `2` | Inspect the row/field error; duplicate event keys and malformed shapes are rejected. |
