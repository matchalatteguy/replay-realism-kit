from pathlib import Path

import pytest

from replay_realism.events import BookEvent, load_events_csv, sort_events


def test_event_sorting_is_stable() -> None:
    events = [BookEvent(timestamp=2, sequence=1, instrument_id="FOO"), BookEvent(timestamp=1, sequence=9, instrument_id="FOO")]
    assert [event.timestamp for event in sort_events(events)] == [1, 2]


def test_load_events_csv_reports_bad_decimal(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("event_type,timestamp,sequence,instrument_id,bid_price,bid_size,ask_price,ask_size\nbook,1,1,FOO,nope,1,2,1\n")
    with pytest.raises(ValueError, match="bid_price"):
        load_events_csv(path)
