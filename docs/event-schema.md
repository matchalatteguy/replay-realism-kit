# Event CSV schema

Replay Realism Kit accepts one compact, synthetic, top-of-book CSV shape. It is intentionally a normalization target for small fixtures, not a venue-native market-data format.

Rows are sorted by `(timestamp, sequence)` after loading. Timestamps are integer milliseconds in an arbitrary local clock chosen by the fixture author. `instrument_id` values should be synthetic or generic, for example `FOO-USD` or `instrument-A`.

## Shared columns

| Column | Required | Type | Notes |
| --- | --- | --- | --- |
| `event_type` | yes | enum | One of `book`, `trade`, `decision`. |
| `timestamp` | yes | integer | Event timestamp in milliseconds. |
| `sequence` | yes | integer | Tie-breaker for events with equal timestamps. |
| `instrument_id` | yes | string | Non-empty normalized instrument key. |
| `venue_id` | no | string | Defaults to `synthetic`. Keep generic/public-safe. |
| `source` | no | string | Defaults to `local`. Keep generic/public-safe. |

## `book` rows

A `book` row represents one top-of-book snapshot. It is not a full order book.

| Column | Required | Type | Validation |
| --- | --- | --- | --- |
| `bid_price` | yes | decimal | Must be positive. |
| `bid_size` | yes | decimal | Must be positive. |
| `ask_price` | yes | decimal | Must be positive. |
| `ask_size` | yes | decimal | Must be positive. |

Example:

```csv
event_type,timestamp,sequence,instrument_id,venue_id,source,bid_price,bid_size,ask_price,ask_size,side,price,size,limit_price,order_type
book,1000,1,FOO-USD,SIM,fixture,99.90,10,100.00,5,,,,,
```

## `trade` rows

A `trade` row is post-arrival evidence used by conservative maker-fill examples.

| Column | Required | Type | Validation |
| --- | --- | --- | --- |
| `side` | yes | enum | `buy` or `sell`. |
| `price` | yes | decimal | Must be positive. |
| `size` | yes | decimal | Must be positive. |

Example:

```csv
trade,1070,4,FOO-USD,SIM,fixture,,,,,sell,100.00,3,,
```

## `decision` rows

A `decision` row is a hypothetical order decision to replay after configured latency.

| Column | Required | Type | Validation |
| --- | --- | --- | --- |
| `side` | yes | enum | `buy` or `sell`. |
| `size` | yes | decimal | Must be positive. |
| `limit_price` | yes | decimal | Must be positive. |
| `order_type` | no | enum | `maker` or `taker`; defaults to `taker`. |

Example:

```csv
decision,1010,2,FOO-USD,SIM,fixture,,,,,buy,,2,100.00,taker
```

## Common validation errors

The parser raises `ValueError` with a row number for invalid data. Examples:

- missing required shared columns: `events CSV missing required columns: [...]`
- unsupported event type: `row 2: unsupported event_type 'quote'`
- empty instrument: `row 2: instrument_id is required`
- bad integer: `row 2: timestamp is not an integer: 'abc'`
- bad decimal: `row 2: bid_price is not a decimal: 'abc'`
- bad enum: `row 2: decision side must be buy or sell`
- non-positive size/price: `row 2: size must be positive`

## Adapter guidance

Normalize private or venue-specific replay logs into this public CSV shape outside the repository. Keep the raw source data elsewhere, commit only synthetic fixtures, and preserve enough generic `source`/`venue_id` labels for tests without leaking real venues, accounts, hostnames, paths, or strategy context.
