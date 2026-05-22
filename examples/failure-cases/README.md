# Failure cases

These synthetic snippets show what the quality gates are meant to catch. They are documentation examples, not production data.

Run the normal quickstart first, then experiment by editing a copied assumption profile or report.

## Zero-latency assumptions

If `latency_ms: 0`, the assumption profile is optimistic and should not be treated as reviewable evidence.

Expected gate reason code:

```text
fail: assumption-profile: optimistic-or-incomplete-assumptions
```

## Missing future markout

If a filled row has `markout: null` while `require_future_markout: true`, gates fail closed.

Expected gate reason code:

```text
fail: future-markout: missing-future-markout
```

## Stale book used

If fill evidence was based on a stale book and the row reason is `stale-book`, gates fail closed.

Expected gate reason code:

```text
fail: stale-book: stale-book-used
```

## Report shape mismatch

If `summary.fill_count` does not equal the number of `fills` rows, gates fail closed rather than trusting the summary.

Expected gate reason code:

```text
fail: report-shape: summary-fill-count-mismatch
```
