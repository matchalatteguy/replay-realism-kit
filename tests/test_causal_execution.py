"""Counterexamples and conservation laws for the independent-order reference model."""

from dataclasses import replace
from decimal import ROUND_DOWN, Decimal, localcontext
from random import Random

import pytest

from replay_realism import (
    BookEvent,
    BookSnapshot,
    DecisionEvent,
    ExecutionAssumptionProfile,
    FeeModel,
    FillPolicy,
    FillRequest,
    OrderSide,
    OrderType,
    ReplaySimulationConfig,
    TradeEvent,
    simulate_maker_fill,
    simulate_replay,
    simulate_taker_fill,
    validate_replay_report,
)

D = Decimal
PROFILE = ExecutionAssumptionProfile("reference", 10, 250, FeeModel(D("1"), D("5")))
CONFIG = ReplaySimulationConfig(D("0"), 100, 100, 100)


def book(timestamp, sequence=0, instrument="FOO", venue="synthetic", price="100", size="10"):
    return BookEvent(
        timestamp,
        sequence,
        instrument,
        venue,
        bids=((D(price) - 1, D(size)),),
        asks=((D(price), D(size)),),
    )


def decision(timestamp=100, sequence=1, kind="taker", venue="synthetic", size="2"):
    return DecisionEvent(
        timestamp,
        sequence,
        "FOO",
        venue,
        side="buy",
        size=D(size),
        limit_price=D("100"),
        order_type=kind,
    )


def trade(timestamp, sequence=0, size="1", instrument="FOO", venue="synthetic"):
    return TradeEvent(
        timestamp, sequence, instrument, venue, side="sell", price=D("100"), size=D(size)
    )


def failures(report):
    return {gate.reason_code for gate in validate_replay_report(report) if not gate.passed}


def test_future_depth_cannot_change_an_immediate_taker_fill():
    events = [book(90, size="1"), decision(), book(220)]
    expected = simulate_replay(events, PROFILE, CONFIG).to_dict()["fills"][0]
    actual = simulate_replay(
        [*events, book(111, 9, price="90", size="1000")], PROFILE, CONFIG
    ).to_dict()["fills"][0]
    assert (actual["filled_size"], actual["average_price"], actual["execution_timestamp"]) == (
        "1",
        "100",
        110,
    )
    assert actual["trace"] == expected["trace"]
    assert actual["book_timestamp"] == 90


def test_missing_causal_book_is_a_failed_gate_even_with_a_later_snapshot():
    report = simulate_replay([decision(), book(111), book(220)], PROFILE, CONFIG).to_dict()
    assert report["fills"][0]["reason_code"] == "no-book-at-arrival"
    assert "missing-arrival-book" in failures(report)


@pytest.mark.parametrize("age,reason", [(250, "filled"), (251, "stale-book")])
def test_staleness_measures_age_of_the_known_book(age, reason):
    report = simulate_replay([book(110 - age), decision(), book(220)], PROFILE, CONFIG).to_dict()
    assert report["fills"][0]["reason_code"] == reason


def test_same_timestamp_books_obey_decision_sequence_only_at_zero_latency():
    events = [book(100, 0, price="100"), decision(sequence=2), book(100, 3, price="99")]
    zero = simulate_replay(events, replace(PROFILE, latency_ms=0), CONFIG).to_dict()["fills"][0]
    assert zero["average_price"] == "100"
    positive = simulate_replay([decision(), book(110, 999)], PROFILE, CONFIG).to_dict()["fills"][0]
    assert positive["reason_code"] == "filled"  # Market updates precede positive-latency arrival.


def test_maker_does_not_consume_earlier_same_timestamp_or_arrival_boundary_trade():
    events = [
        trade(100, 0, "10"),
        decision(sequence=2, kind="maker"),
        trade(100, 3, "1"),
        trade(110, 4, "10"),
        book(300),
    ]
    zero = simulate_replay(events, replace(PROFILE, latency_ms=0), CONFIG).to_dict()["fills"][0]
    assert zero["filled_size"] == "2"  # later same-timestamp volume plus later t=110 volume
    assert zero["trace"][0]["sequence"] == 3
    positive = simulate_replay(events, PROFILE, CONFIG).to_dict()["fills"][0]
    assert positive["filled_size"] == "0"
    assert positive["reason_code"] == "maker-expired"


def test_exclusive_maker_expiry_and_markout_after_last_partial_execution():
    events = [
        decision(kind="maker", size="3"),
        trade(120, 2, "1"),
        book(200, 3, price="90"),
        trade(209, 4, "1"),
        trade(210, 5, "9"),
        book(310, 6, price="102"),
    ]
    row = simulate_replay(events, PROFILE, CONFIG).to_dict()["fills"][0]
    assert row["filled_size"] == "2"
    assert row["remaining_size"] == "1"
    assert row["expiry_timestamp"] == 210
    assert row["execution_timestamp"] == 209
    assert row["markout"]["observation_timestamp"] == 310
    assert row["markout"]["midpoint"] == "101.5"
    assert {item["timestamp"] for item in row["trace"]} == {120, 209}
    assert row["completion_reason"] == "expired"


def test_truncated_maker_tail_is_not_presented_as_expiry():
    events = [decision(kind="maker", size="3"), trade(120, 2, "1"), book(220, 3)]
    config = replace(CONFIG, maker_lifetime_ms=300)
    report = simulate_replay(events, PROFILE, config).to_dict()
    assert report["fills"][0]["completion_reason"] == "incomplete-evidence"
    assert "incomplete-maker-window" in failures(report)
    repaired = simulate_replay([*events, book(410, 4)], PROFILE, config).to_dict()
    assert repaired["fills"][0]["filled_size"] == "1"
    assert not failures(repaired)
    unfilled = simulate_replay([decision(kind="maker"), book(200)], PROFILE, config).to_dict()
    assert unfilled["fills"][0]["reason_code"] == "maker-evidence-incomplete"


def test_a_fully_filled_maker_needs_no_unnecessary_expiry_tail():
    report = simulate_replay(
        [decision(kind="maker"), trade(120, 2, "2"), book(220, 3)],
        PROFILE,
        replace(CONFIG, maker_lifetime_ms=10000),
    ).to_dict()
    assert report["fills"][0]["completion_reason"] == "filled"
    assert not failures(report)


def test_cross_instrument_and_venue_evidence_cannot_supply_fill_or_markout():
    events = [
        decision(kind="maker"),
        trade(120, 2, "10", "BAR"),
        trade(130, 3, "10", venue="other"),
        book(400, 4),
    ]
    report = simulate_replay(events, PROFILE, CONFIG).to_dict()
    assert report["fills"][0]["filled_size"] == "0"
    taker = simulate_replay(
        [decision(), book(90, venue="other"), book(220, instrument="BAR")], PROFILE, CONFIG
    ).to_dict()
    assert taker["fills"][0]["reason_code"] == "no-book-at-arrival"


def test_late_markout_is_unavailable_instead_of_a_best_available_value():
    events = [book(90), decision(), book(311, 2)]
    report = simulate_replay(events, PROFILE, CONFIG).to_dict()
    assert report["fills"][0]["markout"]["edge_after_fees"] is None
    assert "missing-future-markout" in failures(report)


def test_multilevel_taker_conserves_notional_and_keeps_partial_trace():
    quote = BookSnapshot(
        "FOO",
        90,
        0,
        ((D("99"), D("3")),),
        ((D("100.02"), D("4")), (D("100"), D("1")), (D("100.01"), D("1"))),
    )
    request = FillRequest("FOO", OrderSide.BUY, OrderType.TAKER, D("3"), D("100.01"), 100)
    fill = simulate_taker_fill(request, quote, PROFILE)
    assert (fill.filled_size, fill.remaining_size, fill.notional, fill.average_price) == (
        D("2"),
        D("1"),
        D("200.01"),
        D("100.005"),
    )
    assert [(item.price, item.quantity) for item in fill.trace] == [
        (D("100"), D("1")),
        (D("100.01"), D("1")),
    ]
    rejected = simulate_taker_fill(replace(request, policy=FillPolicy.FOK), quote, PROFILE)
    assert (rejected.filled_size, rejected.notional, rejected.fee, rejected.trace) == (
        D("0"),
        D("0"),
        D("0"),
        (),
    )


def test_duplicate_maker_trade_cannot_be_consumed_twice_by_public_primitive():
    request = FillRequest("FOO", OrderSide.BUY, OrderType.MAKER, D("2"), D("100"), 100)
    with pytest.raises(ValueError, match="duplicate"):
        simulate_maker_fill(request, [trade(120), trade(120)], PROFILE)


@pytest.mark.parametrize(
    "mutation",
    [
        "book-future",
        "double-volume",
        "expiry",
        "queue",
        "markout-timing",
        "markout-edge",
        "fee",
        "limit",
        "slippage",
        "source-price",
        "source-side",
    ],
)
def test_gates_reject_tampered_causal_and_accounting_evidence(mutation):
    events = [book(90), decision(kind="maker"), trade(120, 2, "3"), book(220, 3)]
    if mutation == "book-future":
        events[1] = decision()
    report = simulate_replay(events, PROFILE, CONFIG).to_dict()
    assert not failures(report)
    row = report["fills"][0]
    if mutation == "book-future":
        row["book_timestamp"] = 111
    elif mutation == "double-volume":
        row["trace"] *= 2
    elif mutation == "expiry":
        row["expiry_timestamp"] += 1
    elif mutation == "queue":
        row["queue_ahead"] = "1"
    elif mutation == "markout-timing":
        row["markout"]["observation_timestamp"] = 121
    elif mutation == "markout-edge":
        row["markout"]["edge_after_fees"] = "9999"
    elif mutation == "limit":
        row["limit_price"] = "99"
    elif mutation == "slippage":
        row["slippage"] = "1"
    elif mutation == "source-price":
        row["trace"][0]["source_price"] = "101"
    elif mutation == "source-side":
        row["trace"][0]["source_side"] = "buy"
    else:
        row["fee"] = "0"
        report["summary"]["fee_total"] = "0"
    assert failures(report)


def test_model_is_isolated_from_global_decimal_context_and_output_mutation():
    events = [
        BookEvent(
            90,
            0,
            "FOO",
            bids=((D("99"), D("10")),),
            asks=((D("100"), D("1")), (D("100.01"), D("2"))),
        ),
        replace(decision(size="3"), limit_price=D("100.01")),
        book(220, 2, price="102"),
    ]
    original = simulate_replay(events, PROFILE, CONFIG)
    expected = original.to_dict()
    with localcontext() as context:
        context.prec = 6
        context.rounding = ROUND_DOWN
        assert simulate_replay(events, PROFILE, CONFIG).to_dict() == expected
        assert context.prec == 6
    changed = original.to_dict()
    changed["fills"][0]["evidence"].clear()
    changed["simulation_config"]["maker_lifetime_ms"] = 1
    assert original.to_dict() == expected
    assert expected["fills"][0]["markout"]["edge_after_fees"] == "4.32999"
    assert not failures(expected)


def test_seeded_queue_volume_conservation_and_monotonic_sensitivity():
    random = Random(1047)
    for case in range(40):
        volumes = [D(random.randint(1, 20)) / 10 for _ in range(5)]
        trades = [
            trade(120 + index, index + 2, str(volume)) for index, volume in enumerate(volumes)
        ]
        events = [decision(kind="maker", size="3"), *trades, book(230, 9), book(400, 10)]
        previous = D("3")
        for queue in [D("0"), D("1"), D("3"), D("20")]:
            report = simulate_replay(
                events, PROFILE, replace(CONFIG, maker_queue_ahead=queue)
            ).to_dict()
            row = report["fills"][0]
            filled = D(row["filled_size"])
            assert filled == min(D("3"), max(D("0"), sum(volumes) - queue)), case
            assert filled <= previous
            assert filled + D(row["remaining_size"]) == D("3")
            consumed = sum((D(item["quantity"]) for item in row["trace"]), D("0"))
            assert consumed <= sum(volumes)
            assert not failures(report)
            previous = filled
        # Independent orders intentionally reuse the same evidence; no portfolio claim.
        repeated = [*events, replace(events[0], sequence=99)]
        rows = simulate_replay(repeated, PROFILE, CONFIG).to_dict()["fills"]
        assert rows[0]["trace"] == rows[1]["trace"]
        assert events[0].sequence == 1


@pytest.mark.parametrize("side,limit", [("buy", "99.99"), ("sell", "100.01")])
def test_generated_taker_report_cannot_change_its_limit_to_reject_its_own_fill(side, limit):
    quote = BookEvent(90, 0, "FOO", bids=((D("100"), D("10")),), asks=((D("100"), D("10")),))
    request = replace(decision(), side=side)
    report = simulate_replay([quote, request, book(220, 2)], PROFILE, CONFIG).to_dict()
    assert not failures(report)
    report["fills"][0]["limit_price"] = limit
    assert "execution-trace-mismatch" in failures(report)


@pytest.mark.parametrize("field", ["markout_count", "rejection_counts"])
def test_generated_summary_evidence_counts_must_agree_with_rows(field):
    report = simulate_replay([book(90), decision(), book(220, 2)], PROFILE, CONFIG).to_dict()
    report["summary"][field] = 0 if field == "markout_count" else {"no-book-at-arrival": 1}
    assert "summary-evidence-count-mismatch" in failures(report)


def test_queue_consumption_cannot_be_moved_after_the_fill_it_enables():
    config = replace(CONFIG, maker_queue_ahead=D("1"))
    events = [decision(kind="maker"), trade(120, 2, "1"), trade(130, 3, "2"), book(230, 4)]
    report = simulate_replay(events, PROFILE, config).to_dict()
    assert not failures(report)
    report["fills"][0]["trace"][0]["timestamp"] = 160
    assert "execution-trace-mismatch" in failures(report)


def test_explicit_observation_end_cannot_precede_supplied_matching_trades():
    request = FillRequest("FOO", OrderSide.BUY, OrderType.MAKER, D("2"), D("100"), 100)
    with pytest.raises(ValueError, match="observation end precedes"):
        simulate_maker_fill(request, [trade(130, 3, "2")], PROFILE, observed_until_timestamp=115)


def test_shared_queue_fill_source_must_have_one_source_price():
    config = replace(CONFIG, maker_queue_ahead=D("1"))
    report = simulate_replay(
        [decision(kind="maker"), trade(120, 2, "3"), book(220, 3)], PROFILE, config
    ).to_dict()
    assert not failures(report)
    report["fills"][0]["trace"][0]["source_price"] = "99"
    assert "execution-trace-mismatch" in failures(report)


def test_reference_context_does_not_inherit_modified_decimal_defaults(monkeypatch):
    from decimal import DefaultContext

    events = [book(90), decision(), book(220, 2)]
    expected = simulate_replay(events, PROFILE, CONFIG).to_dict()
    monkeypatch.setattr(DefaultContext, "rounding", ROUND_DOWN)
    monkeypatch.setattr(DefaultContext, "Emax", 1)
    assert simulate_replay(events, PROFILE, CONFIG).to_dict() == expected


def test_decimal_underflow_is_an_error_instead_of_a_silent_zero_fee():
    from decimal import DecimalException

    tiny_fees = FeeModel(D("1E-1000050"), D("1E-1000050"))
    with pytest.raises(DecimalException):
        simulate_replay(
            [book(90), decision(), book(220, 2)], replace(PROFILE, fee_model=tiny_fees), CONFIG
        )
