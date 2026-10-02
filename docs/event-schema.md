# Event inputs

Load local `.csv` for compact one-level books or `.jsonl` for multiple depth levels. Both normalize into the same immutable event types. Timestamps are integer milliseconds on a caller-defined clock. Sequence numbers are non-negative integers.

Events are deterministically ordered by `(timestamp, sequence, instrument_id, venue_id)`. An event key `(timestamp, sequence, instrument_id, venue_id)` must be unique across all event types. Conflicting sources cannot silently overwrite an event. Unknown metadata such as an auxiliary ISO UTC `observed_at` field is ignored; it never changes execution timing.

## Shared fields

| Field | Required | Meaning |
| --- | --- | --- |
| `event_type` | yes | `book`, `trade`, or `decision`. |
| `timestamp` | yes | Integer milliseconds; strings containing an integer are accepted in CSV. |
| `sequence` | yes | Non-negative integer, used to resolve same-time events. |
| `instrument_id` | yes | Non-empty normalized instrument string. |
| `venue_id` | no | Non-empty string; defaults to `synthetic`. |
| `source` | no | Non-empty string; defaults to `local`. |

Prices and quantities must be finite and positive. Decimal strings preserve the intended input precision. Books with `bid > ask`, duplicate price levels, missing sides, or zero depth are rejected. Locked books are accepted.

## Multi-level JSONL

One JSON object per line; blank lines are ignored. JSON duplicate member names and non-standard `NaN`/`Infinity` constants are rejected.

```jsonl
{"event_type":"book","timestamp":100,"sequence":0,"instrument_id":"FOO-USD","venue_id":"SIM","bids":[["99.90","3"],["99.80","5"]],"asks":[["100.00","1"],["100.05","2"]]}
{"event_type":"decision","timestamp":110,"sequence":1,"instrument_id":"FOO-USD","venue_id":"SIM","side":"buy","size":"3","limit_price":"100.05","order_type":"taker"}
{"event_type":"trade","timestamp":140,"sequence":2,"instrument_id":"FOO-USD","venue_id":"SIM","side":"sell","price":"99.90","size":"1.5"}
```

`bids` and `asks` are arrays of `[price, size]` pairs. Levels are normalized best-first (descending bids, ascending asks). Both sides are required when either array is present. JSONL also accepts the scalar book fields below.

## Compact CSV

```csv
event_type,timestamp,sequence,instrument_id,venue_id,source,bid_price,bid_size,ask_price,ask_size,side,price,size,limit_price,order_type
book,100,0,FOO-USD,SIM,fixture,99.90,3,100.00,1,,,,,
decision,110,1,FOO-USD,SIM,fixture,,,,,buy,,3,100.05,taker
trade,140,2,FOO-USD,SIM,fixture,,,,,sell,99.90,1.5,,
```

Each CSV row must match the header width. Headers must be unique and non-empty; shared columns are required. Extra metadata columns are accepted. `book` rows require positive `bid_price`, `bid_size`, `ask_price`, and `ask_size`. `trade` rows require `side` (`buy`/`sell`), positive `price`, and positive `size`. `decision` rows require `side`, positive `size`, and positive `limit_price`; `order_type` defaults to `taker` or can be `maker`.

Validation raises a `ValueError` identifying the row or field. The CLI prints a clean error and exits `2` before simulation. See the [stress fixture](../examples/execution-stress/events.jsonl) for a complete multi-instrument input, including future observations and maker expiry coverage.

Normalize source logs outside this repository and retain rights and provenance separately. Only small invented fixtures are bundled. Accepted metadata and a passing report cannot verify the authenticity or completeness of a source stream.
