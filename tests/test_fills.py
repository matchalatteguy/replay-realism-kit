from decimal import Decimal

from replay_realism.assumptions import ExecutionAssumptionProfile
from replay_realism.events import TradeEvent
from replay_realism.fees import FeeModel
from replay_realism.fills import (
    BookSnapshot,
    FillPolicy,
    FillRequest,
    OrderSide,
    OrderType,
    simulate_maker_fill,
    simulate_taker_fill,
)


def profile() -> ExecutionAssumptionProfile:
    return ExecutionAssumptionProfile("demo", 10, 250, FeeModel(Decimal("1"), Decimal("5")))


def test_taker_fill_consumes_depth_and_fok_differs() -> None:
    book = BookSnapshot("FOO", 20, 1, bids=((Decimal("99"), Decimal("1")),), asks=((Decimal("100"), Decimal("1")), (Decimal("101"), Decimal("1"))))
    req = FillRequest("FOO", OrderSide.BUY, OrderType.TAKER, Decimal("2"), Decimal("100"), 0)
    fill = simulate_taker_fill(req, book, profile())
    assert fill.reason_code == "partial-fill"
    assert fill.filled_size == Decimal("1")
    fok = simulate_taker_fill(FillRequest("FOO", OrderSide.BUY, OrderType.TAKER, Decimal("2"), Decimal("100"), 0, policy=FillPolicy.FOK), book, profile())
    assert fok.reason_code == "fok-not-filled"
    assert fok.filled_size == Decimal("0")


def test_maker_fill_waits_for_queue_exhaustion() -> None:
    trades = [TradeEvent(timestamp=15, sequence=1, instrument_id="FOO", side="sell", price=Decimal("100"), size=Decimal("1.5"))]
    req = FillRequest("FOO", OrderSide.BUY, OrderType.MAKER, Decimal("1"), Decimal("100"), 0, queue_ahead=Decimal("1"))
    fill = simulate_maker_fill(req, trades, profile())
    assert fill.reason_code == "partial-fill"
    assert fill.filled_size == Decimal("0.5")
