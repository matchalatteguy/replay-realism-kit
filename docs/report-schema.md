# Replay report schema

Generated JSON reports are intended to be stable enough for small CI checks and automated review loops.

Current schema version: `replay-realism-report/v1`

## Top-level object

| Field | Type | Required | Stability |
| --- | --- | --- | --- |
| `schema_version` | string | yes | Stable for v1 reports. |
| `assumptions` | object | yes | Stable keys for v1. |
| `summary` | object | yes | Stable keys for v1. |
| `fills` | array | yes | Stable row keys for v1. |

## `assumptions`

| Field | Type | Notes |
| --- | --- | --- |
| `name` | string | Assumption profile name. |
| `latency_ms` | integer | Fixed latency applied to each decision. |
| `stale_book_ms` | integer | Maximum acceptable book age for taker fills. |
| `tick_size` | decimal string | Minimum price increment used by callers/fixtures. |
| `min_size` | decimal string | Minimum order size used by callers/fixtures. |
| `allow_partial_fills` | boolean | Whether partial fills are allowed. |
| `require_future_markout` | boolean | Whether filled rows must have future-only markouts. |
| `description` | string | Human context from the YAML profile. |
| `safety_level` | string | `reviewable`, `optimistic`, or `incomplete`. |
| `fee_model` | object | Explicit maker/taker fee model. |

`fee_model` contains `name`, `maker_bps`, `taker_bps`, and `explicit_zero_fees`.

## `summary`

| Field | Type | Notes |
| --- | --- | --- |
| `fill_count` | integer | Must equal `len(fills)`. Gates fail closed on mismatch. |
| `filled_count` | integer | Rows with `filled_size > 0`. |
| `fee_total` | decimal string | Sum of row fees. |

## Fill rows

| Field | Type | Notes |
| --- | --- | --- |
| `instrument_id` | string | Instrument from the decision/fill request. |
| `side` | string | `buy` or `sell`. |
| `order_type` | string | `maker` or `taker`. |
| `arrival_timestamp` | integer | Decision timestamp plus configured latency. |
| `execution_timestamp` | integer or null | Actual execution: book time for takers, final contributing trade for makers. Null for no fill. Added in 0.2; absent in older v1 reports. |
| `filled_size` | decimal string | Filled size. |
| `remaining_size` | decimal string | Unfilled size. |
| `average_price` | decimal string or null | Average fill price. |
| `notional` | decimal string | Filled notional. |
| `fee` | decimal string | Fee charged by explicit fee model. |
| `slippage` | decimal string or null | Taker slippage when applicable. |
| `reason_code` | string | Stable machine-readable fill reason. |
| `evidence` | array[string] | Synthetic evidence references. |
| `markout` | object or null | Future-only markout result. |

## Markout object

| Field | Type | Notes |
| --- | --- | --- |
| `horizon_ms` | integer | Positive future horizon after actual execution. |
| `midpoint` | decimal string or null | Future midpoint when found. |
| `edge_after_fees` | decimal string or null | Edge after fees. |
| `reason_code` | string | `ok` when usable; otherwise explains missing markout. |

## Minimal example

```json
{
  "schema_version": "replay-realism-report/v1",
  "assumptions": {
    "name": "conservative-demo",
    "latency_ms": 50,
    "stale_book_ms": 250,
    "tick_size": "0.01",
    "min_size": "0.0001",
    "allow_partial_fills": true,
    "require_future_markout": true,
    "description": "Synthetic conservative fixture.",
    "safety_level": "reviewable",
    "fee_model": {
      "name": "demo-bps-fees",
      "maker_bps": "1",
      "taker_bps": "5",
      "explicit_zero_fees": false
    }
  },
  "summary": {"fill_count": 1, "filled_count": 1, "fee_total": "0.05"},
  "fills": [
    {
      "instrument_id": "FOO-USD",
      "side": "buy",
      "order_type": "taker",
      "arrival_timestamp": 1060,
      "filled_size": "1",
      "remaining_size": "0",
      "average_price": "100.00",
      "notional": "100.00",
      "fee": "0.05",
      "slippage": "0",
      "reason_code": "filled",
      "evidence": ["depth@100.00:1"],
      "markout": {"horizon_ms": 100, "midpoint": "100.25", "edge_after_fees": "0.20", "reason_code": "ok"}
    }
  ]
}
```

## Gate stability

Reason codes are treated as the stable automation boundary within a major schema version. Human messages may become clearer over time, but code should key on `reason_code`, not the full message text.
