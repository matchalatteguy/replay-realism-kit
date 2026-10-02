# A reproducible execution stress study

33 invented events, two instruments (`ALPHA-USD`, `BETA-USD`), multiple depth levels, eight fixed decisions. All timestamps are integer milliseconds on a local clock. The fixture is deliberately small enough to inspect line by line.

Run from the repository root:

```bash
uv run replay-realism compare \
  --events examples/execution-stress/events.jsonl \
  --scenarios examples/execution-stress/scenarios.yaml \
  --json-out reports/stress.json --csv-out reports/stress.csv --md-out reports/stress.md
uv run replay-realism compare \
  --events examples/execution-stress/events.jsonl \
  --scenarios examples/execution-stress/sweep.yaml \
  --json-out reports/sweep.json --csv-out reports/sweep.csv --md-out reports/sweep.md
```

Both commands exit `0`, with five and 29 scenarios respectively. [expected-summary.csv](expected-summary.csv) records the exact five-profile output and is checked by the test suite. Generated reports belong in the ignored `reports/` directory.

## Controlled changes

| Profile | Latency | Maker queue | Maker lifetime | Maker / taker fee bps |
| --- | ---: | ---: | ---: | ---: |
| reference | 10 ms | 0 | 300 ms | 1 / 5 |
| higher-fees | 10 ms | 0 | 300 ms | 5 / 20 |
| queue-ahead | 10 ms | 3 | 300 ms | 1 / 5 |
| slower-arrival | 80 ms | 0 | 300 ms | 1 / 5 |
| short-maker-life | 10 ms | 0 | 150 ms | 1 / 5 |

Each named profile changes one assumption from the reference. All require future markouts, allow partial fills, bound book age to 250 ms, and use a 100 ms markout horizon with at most 200 ms observation delay. The sweep crosses latency `[10, 30, 80, 150]`, queue `[0, 2, 4]`, and lifetime `[150, 300]`: 24 combinations plus the five named profiles. It retains all cases and performs no best-case selection.

## What the traces explain

- At t=110, the reference ALPHA taker buy arrives at t=120. It consumes 1 at 100 and 2 at 100.10, for notional 300.20 and taker fee 0.1501. Its future midpoint at t=240 is 100.10, giving `(100.10 × 3 − 300.20) − 0.1501 = −0.0501`. Its average price is rounded; markout arithmetic uses the recorded notional directly.
- Reference maker buys consume later opposing trades at their limit. A queue of 3 spends eligible trade volume ahead of the order and can remove a fill entirely. Trace items separate `queue` and `fill` quantities and reference the same available source volume.
- Slower arrivals miss some trades and face different known snapshots. The summed markout becomes positive while only five decisions fill. Fewer selected fills explain that change; it provides no recommendation for increasing latency.
- Shorter maker lifetimes preserve early partial executions but exclude trades at or after expiry. Both the filled-decision count and filled quantities matter.
- Books at t=900 close each market's observation window for every attempted maker in the sweep. They cannot supply earlier taker fills, and earlier eligible books provide the markouts.

All five profiles have complete markout coverage and no failed gates. Their total markouts after fees are −1.16004, −2.3002, −0.92003, 0.36501, and −1.74502 in synthetic USD.

## Deliberate failure experiments

Remove all books after t=150: filled orders lose future marks, unfinished makers lack expiry coverage, aggregate edge becomes `null`, and `compare` writes failed gates with exit `1`. Duplicate any event line: validation fails with exit `2` before replay. These cases are exercised by tests alongside future-book leakage, same-timestamp ordering, expiry boundaries, and volume conservation.

The independent-order model allows different decisions to reuse the same market volume. The study is a reference calculation, with no real data, account credentials, venue validation, or strategy-performance inference.
