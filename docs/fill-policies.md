# Fill policies and causal timing

The runner replays each decision independently. It does not carry liquidity depletion, queue position, inventory, or capital between orders.

## Request and arrival

`FillRequest` includes the instrument and venue, side, type, size, limit, decision timestamp, optional decision sequence, maker queue, policy, and `maker_lifetime_ms`. Arrival is decision timestamp plus profile latency. Tick, minimum size, finite numbers, non-negative queue, and positive lifetime are validated.

## Takers

The runner selects the latest matching snapshot known at arrival, then consumes asks ascending for a buy or bids descending for a sell. Only prices at or better than the limit are eligible. A snapshot after arrival is rejected, and true snapshot age `arrival − book.timestamp` must not exceed `stale_book_ms`. Taker execution occurs immediately at arrival; a later quote cannot change it.

At zero latency, same-timestamp books must have a lower sequence than the decision. At positive latency, all market updates at the arrival timestamp are assumed to precede the synthetic order arrival. This tie convention is explicit and requires an adapter compatible with the input stream.

`fill-and-kill` accepts available partial size and reports the remainder. `fill-or-kill` discards the whole tentative fill when depth is insufficient. `allow_partial_fills: false` also discards incomplete fills. Rejected tentative depth is never reported as an actual fill trace.

## Makers

A maker buy consumes eligible sell prints at or below its limit; a maker sell consumes buy prints at or above its limit. Eligible volume first consumes the supplied queue, then fills the order at its limit. Each source print can supply only its recorded volume to a single independent decision. Queue and fill traces share that available-volume constraint.

At positive latency, trades must have a timestamp strictly after arrival. At zero latency, later sequence numbers at the decision timestamp are also eligible. Trades at or after `arrival + maker_lifetime_ms` are excluded; expiry is exclusive.

An order is complete when it fills or the matching market evidence reaches its expiry. A log ending earlier leaves `completion_reason: incomplete-evidence`, including partial orders, and fails the maker observation gate. A fully filled order needs no unnecessary tail. In the direct `simulate_maker_fill` API, pass `observed_until_timestamp` when a surrounding market log establishes coverage beyond the supplied trade list; otherwise its last matching trade is the evidence end.

Maker FOK here means the entire requested quantity must complete within the synthetic lifetime; it is an offline all-or-none test over that window. It does not represent a venue's immediate FOK instruction.

## Trace, fees, and markouts

Trace items contain execution/queue quantity, reference price, source price and side, source timestamp and sequence, and available source quantity. Takers also retain the selected book timestamp and sequence. Notional is the sum of actual `price × quantity`; fees apply the configured basis points to filled notional. Taker slippage is relative to the request limit (buy: average minus limit; sell: limit minus average), and maker slippage is zero in this model.

Markout gross amount is `(future midpoint × filled quantity − notional) × side direction`, minus fees. Using notional avoids multiplying a rounded weighted-average price back into quantity. The aggregate horizon starts after actual execution; the last contributing maker trade anchors multi-part fills. Select the earliest matching future book within the maximum markout delay. Missing observations remain unavailable.

## Main fill reasons

| Reason | Meaning |
| --- | --- |
| `filled`, `partial-fill` | Positive executed quantity, with zero or positive remainder. |
| `no-book-at-arrival` | Runner found no causally known matching snapshot. |
| `book-after-arrival`, `book-after-decision-sequence` | Direct primitive received unavailable quote evidence. |
| `stale-book` | Known quote exceeds the maximum age. |
| `instrument-mismatch` | Direct snapshot does not match the instrument or venue. |
| `insufficient-crossable-depth` | No displayed quantity within the limit. |
| `maker-expired` | No fill within a completely observed lifetime. |
| `maker-evidence-incomplete` | No fill and the data ends before expiry. |
| `fok-not-filled`, `partial-fill-not-allowed` | Tentative partial fill was rejected by policy. |
| `min-size-violation`, `tick-size-violation`, `non-positive-request`, `invalid-request-number`, `invalid-request` | Request rejected by validation. |

Snapshots persist until the next update or staleness rejection. The model does not infer unobserved depth changes, hidden liquidity, queue amendments, cancellations, maker marketability, actual venue priority, or shared portfolio effects. Source completeness and execution realism need external evidence.
