from decimal import Decimal

import pytest

from replay_realism.assumptions import ExecutionAssumptionProfile
from replay_realism.events import BookEvent, DecisionEvent, TradeEvent
from replay_realism.fees import FeeModel
from replay_realism.simulation import ReplaySimulationConfig, first_eligible_book, simulate_replay


def profile() -> ExecutionAssumptionProfile:
    return ExecutionAssumptionProfile("demo", 10, 250, FeeModel(Decimal("1"), Decimal("5")))


def test_simulate_replay_sorts_events_and_uses_instrument_scoped_markout() -> None:
    events = [
        BookEvent(
            timestamp=100,
            sequence=0,
            instrument_id="FOO",
            bid_price=Decimal("99"),
            bid_size=Decimal("1"),
            ask_price=Decimal("100"),
            ask_size=Decimal("3"),
        ),
        BookEvent(
            timestamp=130,
            sequence=3,
            instrument_id="BAR",
            bid_price=Decimal("9"),
            bid_size=Decimal("1"),
            ask_price=Decimal("11"),
            ask_size=Decimal("1"),
        ),
        BookEvent(
            timestamp=120,
            sequence=2,
            instrument_id="FOO",
            bid_price=Decimal("99"),
            bid_size=Decimal("1"),
            ask_price=Decimal("100"),
            ask_size=Decimal("3"),
        ),
        DecisionEvent(
            timestamp=100,
            sequence=1,
            instrument_id="FOO",
            side="buy",
            size=Decimal("2"),
            limit_price=Decimal("100"),
            order_type="taker",
        ),
        BookEvent(
            timestamp=220,
            sequence=4,
            instrument_id="FOO",
            bid_price=Decimal("101"),
            bid_size=Decimal("1"),
            ask_price=Decimal("103"),
            ask_size=Decimal("1"),
        ),
    ]

    report = simulate_replay(events, profile(), ReplaySimulationConfig(markout_horizon_ms=100))
    data = report.to_dict()

    assert data["summary"]["fill_count"] == 1
    assert data["fills"][0]["reason_code"] == "filled"
    assert data["fills"][0]["filled_size"] == "2"
    assert data["fills"][0]["markout"]["midpoint"] == "102"
    assert data["fills"][0]["markout"]["horizon_ms"] == 100


def test_simulate_replay_exposes_maker_queue_as_configurable_assumption() -> None:
    events = [
        DecisionEvent(
            timestamp=100,
            sequence=1,
            instrument_id="FOO",
            side="buy",
            size=Decimal("1"),
            limit_price=Decimal("100"),
            order_type="maker",
        ),
        TradeEvent(
            timestamp=115,
            sequence=2,
            instrument_id="FOO",
            side="sell",
            price=Decimal("100"),
            size=Decimal("1.5"),
        ),
    ]

    default_report = simulate_replay(events, profile()).to_dict()
    no_queue_report = simulate_replay(
        events, profile(), ReplaySimulationConfig(maker_queue_ahead=Decimal("0"))
    ).to_dict()

    assert default_report["fills"][0]["filled_size"] == "0.5"
    assert default_report["fills"][0]["reason_code"] == "partial-fill"
    assert no_queue_report["fills"][0]["filled_size"] == "1"
    assert no_queue_report["fills"][0]["reason_code"] == "filled"


def test_simulation_config_rejects_optimistic_negative_knobs() -> None:
    with pytest.raises(ValueError, match="maker_queue_ahead"):
        ReplaySimulationConfig(maker_queue_ahead=Decimal("-1"))
    with pytest.raises(ValueError, match="markout_horizon_ms"):
        ReplaySimulationConfig(markout_horizon_ms=-1)


def test_first_eligible_book_uses_arrival_and_sequence_order() -> None:
    events = [
        BookEvent(
            timestamp=110,
            sequence=2,
            instrument_id="FOO",
            bid_price=Decimal("99"),
            ask_price=Decimal("101"),
        ),
        BookEvent(
            timestamp=105,
            sequence=1,
            instrument_id="FOO",
            bid_price=Decimal("98"),
            ask_price=Decimal("100"),
        ),
        BookEvent(
            timestamp=100,
            sequence=0,
            instrument_id="FOO",
            bid_price=Decimal("97"),
            ask_price=Decimal("99"),
        ),
    ]

    assert first_eligible_book(events, "FOO", 105) == events[1]
    assert first_eligible_book(events, "BAR", 105) is None
