from decimal import Decimal
from pathlib import Path

import pytest

from replay_realism.events import BookEvent, load_events_csv, sort_events


def test_event_sorting_is_stable() -> None:
    events = [
        BookEvent(
            timestamp=2,
            sequence=1,
            instrument_id="FOO",
            bid_price=Decimal("99"),
            ask_price=Decimal("101"),
        ),
        BookEvent(
            timestamp=1,
            sequence=9,
            instrument_id="FOO",
            bid_price=Decimal("99"),
            ask_price=Decimal("101"),
        ),
    ]
    assert [event.timestamp for event in sort_events(events)] == [1, 2]


def test_load_events_csv_reports_bad_decimal(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(
        "event_type,timestamp,sequence,instrument_id,bid_price,bid_size,ask_price,ask_size\nbook,1,1,FOO,nope,1,2,1\n"
    )
    with pytest.raises(ValueError, match="bid_price"):
        load_events_csv(path)


def test_load_events_csv_rejects_non_positive_book_depth(tmp_path: Path) -> None:
    path = tmp_path / "bad-depth.csv"
    path.write_text(
        "event_type,timestamp,sequence,instrument_id,bid_price,bid_size,ask_price,ask_size\n"
        "book,1,1,FOO,99,0,101,1\n"
    )

    with pytest.raises(ValueError, match="bid_size must be finite and positive"):
        load_events_csv(path)


def test_load_events_csv_rejects_non_positive_decision_size(tmp_path: Path) -> None:
    path = tmp_path / "bad-decision.csv"
    path.write_text(
        "event_type,timestamp,sequence,instrument_id,side,size,limit_price,order_type\n"
        "decision,1,1,FOO,buy,0,100,taker\n"
    )

    with pytest.raises(ValueError, match="size must be finite and positive"):
        load_events_csv(path)
