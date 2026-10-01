# Fees, queue size, and latency on the same decisions

Run from the repository root:

```bash
uv run python examples/assumption-comparison/compare.py
```

The seven CSV events include a taker buy and maker buy, both of size 2. With 10 ms latency the taker reaches the 100.10 ask at time 120 and the maker reaches the sell trade of size 3 at time 130. A queue of 2 leaves only 1 unit for the maker. With 50 ms latency, arrival is time 150: the sell trade has already occurred, and the next ask at time 200 exceeds the taker limit.

The first two cases change fees only. The next case adds a maker queue of 2. The final case also raises latency to 50 ms. Each filled row uses a 100 ms horizon after actual execution; the book at time 250 provides midpoint 100.40 for the filled cases.

| Setting | Taker size | Maker size | Fees | Future markout after fees |
| --- | ---: | ---: | ---: | ---: |
| explicit zero fees | 2 | 2 | 0.00 | 1.60 |
| fees | 2 | 2 | 0.12008 | 1.47992 |
| fees + queue | 2 | 1 | 0.11009 | 0.98991 |
| fees + queue + delay | 0 | 0 | 0 | 0 |

Fee rates are 5 basis points for takers and 1 for makers. For the second row, taker fees are `2 × 100.10 × 5 / 10000 = 0.10010`; maker fees are `2 × 99.90 × 1 / 10000 = 0.01998`. The markout before fees is `2 × (100.40 − 100.10) + 2 × (100.40 − 99.90) = 1.60`, leaving `1.47992`.

All amounts are in the invented fixture's quote unit. These are arithmetic examples of assumption sensitivity, not forecasts, realized returns, statistical estimates, or evidence about any venue. Tests lock the table to the implemented simulator so it cannot drift from its example.
