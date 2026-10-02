# A small fee, queue, and latency comparison

The original seven-event, two-decision example remains available:

```bash
uv run python examples/assumption-comparison/compare.py
```

Version 0.3 uses the known book at arrival: at t=110, the taker consumes the 100.00 ask from t=100. At t=150, it consumes the 100.10 ask known since t=120. The maker starts after arrival, expires after 100 ms, and consumes eligible sell volume at t=130 only in the low-latency cases. Its queue of 2 leaves 1 unit from that print.

| Setting | Taker size | Maker size | Fees | Future markout after fees |
| --- | ---: | ---: | ---: | ---: |
| explicit zero fees | 2 | 2 | 0.00 | 1.80 |
| fees | 2 | 2 | 0.11998 | 1.68002 |
| fees + queue | 2 | 1 | 0.10999 | 1.19001 |
| fees + queue + delay | 2 | 0 | 0.1001 | 0.4999 |

Fee rates are 5 bps for takers and 1 bps for makers. The fee-only row has taker fees `2 × 100.00 × 5 / 10000 = 0.10000`, maker fees `2 × 99.90 × 1 / 10000 = 0.01998`, and gross markout `2 × (100.40 − 100.00) + 2 × (100.40 − 99.90) = 1.80`.

All events are invented. This compact arithmetic example uses complete future marks; the first-class [execution stress study](../execution-stress/README.md) additionally retains failure gates, unavailable aggregates, multi-level trace accounting, and a bounded scenario sweep.
