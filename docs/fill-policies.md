# Fill policies

Replay Realism Kit simulates simple, deterministic fills over local events. The goal is not to predict a venue perfectly; it is to avoid optimistic replay evidence.

## Shared request model

A `FillRequest` contains:

- `instrument_id`
- `side`: `buy` or `sell`
- `order_type`: `maker` or `taker`
- `size`
- `limit_price`
- `decision_timestamp`
- `queue_ahead` for maker examples
- `policy`: `fill-and-kill` or `fill-or-kill`

Before any fill logic runs, the request is rejected when it violates the assumption profile:

- `min-size-violation`
- `tick-size-violation`
- `non-positive-request`

## Taker fills

Taker fills consume displayed book depth at or better than the limit price after latency is applied.

For a buy request:

1. arrival time is `decision_timestamp + latency_ms`;
2. the book must match `instrument_id`;
3. the book timestamp must be at or after arrival;
4. the book must not be older than `stale_book_ms` relative to arrival;
5. asks are consumed from best to worse while `ask_price <= limit_price`.

For a sell request, bids are consumed from best to worse while `bid_price >= limit_price`.

Reason codes include:

- `filled`
- `partial-fill`
- `instrument-mismatch`
- `book-before-arrival`
- `stale-book`
- `insufficient-crossable-depth`
- `fok-not-filled`

## Fill-and-kill versus fill-or-kill

`fill-and-kill` accepts any crossable partial quantity and reports the unfilled remainder.

`fill-or-kill` rejects the entire request unless the full requested size is available within the limit price. When it rejects, the reason code is `fok-not-filled` and `filled_size` is zero.

## Maker fills

Maker fills are intentionally conservative. A maker request does not fill merely because a later trade touches the limit price. It fills only after post-arrival opposing trade volume consumes the declared `queue_ahead` quantity.

For a maker buy request, a post-arrival sell trade can consume the queue when `trade.price <= limit_price`. For a maker sell request, a post-arrival buy trade can consume the queue when `trade.price >= limit_price`.

The simulator records evidence strings such as:

- `queue@1070:1` when volume consumed queue ahead;
- `maker@1070:2` when residual volume filled the request.

Reason codes include:

- `filled`
- `partial-fill`
- `queue-not-exhausted`
- `no-post-arrival-trade`

## Slippage and fees

Taker slippage is signed relative to the limit price:

- buy: `average_price - limit_price`
- sell: `limit_price - average_price`

Maker fills execute at the request limit price in the MVP and report zero slippage. Fees are calculated from the explicit `FeeModel` and the filled notional.

## Limitations

The MVP uses compact deterministic primitives. It does not model hidden liquidity, probabilistic queue priority, order amendments, venue-specific matching engines, network retries, authentication, or live order placement.
