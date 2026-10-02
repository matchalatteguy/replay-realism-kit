from copy import deepcopy
from dataclasses import replace
from decimal import ROUND_UP, Decimal, localcontext
from pathlib import Path

import pytest
import yaml

from replay_realism import (
    ScenarioStudy,
    compare_scenarios,
    load_events,
    load_events_jsonl,
    load_scenarios,
    write_comparison_csv,
    write_comparison_markdown,
)
from replay_realism.cli import main
from replay_realism.comparison import CSV_FIELDS, MAX_SCENARIOS
from replay_realism.events import BookEvent, DecisionEvent

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/execution-stress"


def fixture_study():
    return load_scenarios(FIXTURE / "scenarios.yaml")


def write_study(tmp_path, data):
    path = tmp_path / "scenarios.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_stress_study_matches_checked_in_summary_and_keeps_all_scenarios(tmp_path):
    events = load_events(FIXTURE / "events.jsonl")
    study = fixture_study()
    result = compare_scenarios(events, study)
    assert result["event_count"] == 33
    assert result["decision_count"] == 8
    assert result["scenario_count"] == 5
    assert result["gate_failure_count"] == 0
    assert len(result["study_sha256"]) == 64
    output = tmp_path / "summary.csv"
    write_comparison_csv(result, output)
    assert output.read_text() == (FIXTURE / "expected-summary.csv").read_text()
    assert output.read_text().splitlines()[0].split(",") == list(CSV_FIELDS)
    for row in result["scenarios"]:
        assert row["summary"]["markout_coverage"] == "1"
        assert len(row["summary"]["instruments"]) == 2
        assert row["summary"]["decision_count"] == len(row["report"]["fills"])
    reference, fees, queue, delayed, short = result["scenarios"]
    assert reference["report"]["fills"] != fees["report"]["fills"]  # Fees/edges change.
    assert [row["filled_size"] for row in reference["report"]["fills"]] == [
        row["filled_size"] for row in fees["report"]["fills"]
    ]
    assert fees["delta_from_baseline"]["filled_count"] == 0
    assert Decimal(fees["delta_from_baseline"]["edge_after_fees"]) == -Decimal(
        fees["delta_from_baseline"]["fee_total"]
    )
    assert queue["summary"]["filled_count"] == 7
    assert delayed["summary"]["filled_count"] == 5
    assert short["summary"]["filled_count"] == 8
    assert [row["filled_size"] for row in short["report"]["fills"]] != [
        row["filled_size"] for row in reference["report"]["fills"]
    ]
    markdown = tmp_path / "summary.md"
    write_comparison_markdown(result, markdown)
    assert "independently" in markdown.read_text()
    assert "Failed gates" in markdown.read_text()


def test_sweep_is_bounded_cartesian_and_deterministic_under_reordering(tmp_path):
    events = load_events(FIXTURE / "events.jsonl")
    study = load_scenarios(FIXTURE / "sweep.yaml")
    result = compare_scenarios(events, study)
    assert result["scenario_count"] == 29
    assert result["gate_failure_count"] == 0
    names = [row["name"] for row in result["scenarios"]]
    assert len(set(names)) == len(names)
    assert names[-1] == "reference.latency-150.queue-4.lifetime-300"
    assert result == compare_scenarios(list(reversed(events)), study)
    with localcontext() as context:
        context.prec = 5
        context.rounding = ROUND_UP
        assert compare_scenarios(events, study) == result
    altered = compare_scenarios(events, replace(study, quote_unit="different declared unit"))
    assert altered["study_sha256"] != result["study_sha256"]


@pytest.mark.parametrize(
    "kind",
    [
        "extra-profile",
        "duplicate-name",
        "missing-rate",
        "false-string",
        "nan-queue",
        "bad-horizon",
        "bad-baseline",
        "unknown-axis",
        "empty-axis",
        "duplicate-axis",
        "too-many",
        "bool-latency",
    ],
)
def test_invalid_studies_fail_before_simulation(tmp_path, kind):
    data = yaml.safe_load((FIXTURE / "scenarios.yaml").read_text())
    first = data["profiles"][0]
    if kind == "extra-profile":
        first["latency_ms"] = 10
    elif kind == "duplicate-name":
        data["profiles"][1]["name"] = first["name"]
    elif kind == "missing-rate":
        del first["assumptions"]["fee_model"]["maker_bps"]
    elif kind == "false-string":
        first["assumptions"]["require_future_markout"] = "false"
    elif kind == "nan-queue":
        first["simulation"]["maker_queue_ahead"] = "NaN"
    elif kind == "bad-horizon":
        first["simulation"]["markout_horizon_ms"] = 0
    elif kind == "bad-baseline":
        data["baseline"] = "missing"
    elif kind == "unknown-axis":
        data["sweep"] = {"profile": "reference", "fees": [1, 5]}
    else:
        values = {
            "empty-axis": [],
            "duplicate-axis": [10, 10],
            "too-many": list(range(MAX_SCENARIOS)),
            "bool-latency": [True],
        }[kind]
        data["sweep"] = {"profile": "reference", "latency_ms": values}
    with pytest.raises(ValueError):
        load_scenarios(write_study(tmp_path, data))


def test_duplicate_yaml_members_do_not_silently_change_an_assumption(tmp_path):
    original = (FIXTURE / "scenarios.yaml").read_text()
    path = tmp_path / "duplicate.yaml"
    path.write_text(
        original.replace("  assumptions:\n", "  name: overwritten\n  assumptions:\n", 1)
    )
    with pytest.raises(ValueError, match="unique"):
        load_scenarios(path)


def test_missing_markouts_and_no_fills_are_never_summed_as_zero():
    study = fixture_study()
    events = load_events(FIXTURE / "events.jsonl")
    # Leave arrival books but remove all future midpoint observations.
    reduced = [
        event for event in events if not isinstance(event, BookEvent) or event.timestamp <= 150
    ]
    report = compare_scenarios(reduced, study)
    assert report["gate_failure_count"] > 0
    assert all(row["summary"]["edge_after_fees"] is None for row in report["scenarios"])
    assert any(row["summary"]["markout_coverage"] == "0" for row in report["scenarios"])
    decisions = [event for event in events if isinstance(event, DecisionEvent)]
    result = compare_scenarios(decisions, study)
    assert all(row["summary"]["markout_coverage"] is None for row in result["scenarios"])
    assert all(row["delta_from_baseline"]["edge_after_fees"] is None for row in result["scenarios"])
    assert result["gate_failure_count"] > 0


def test_comparison_does_not_mutate_scenarios_events_or_other_results():
    study = fixture_study()
    events = load_events(FIXTURE / "events.jsonl")
    before = deepcopy(events)
    expected = compare_scenarios(events, study)
    changed = compare_scenarios(events, study)
    changed["scenarios"][0]["report"]["fills"][0]["trace"][0]["quantity"] = "0"
    assert events == before
    assert compare_scenarios(events, study) == expected
    assert changed["scenarios"][1] == expected["scenarios"][1]
    assert study.scenarios[0].config.maker_lifetime_ms == 300


def test_compare_cli_writes_reports_on_failed_gates_and_reports_clean_input_errors(
    tmp_path, capsys
):
    missing = tmp_path / "missing.jsonl"
    events = [
        line
        for line in (FIXTURE / "events.jsonl").read_text().splitlines()
        if '"event_type":"book"' not in line
    ]
    missing.write_text("\n".join(events) + "\n")
    paths = [tmp_path / "out.json", tmp_path / "out.csv", tmp_path / "out.md"]
    args = [
        "compare",
        "--events",
        str(missing),
        "--scenarios",
        str(FIXTURE / "scenarios.yaml"),
        "--json-out",
        str(paths[0]),
        "--csv-out",
        str(paths[1]),
        "--md-out",
        str(paths[2]),
    ]
    assert main(args) == 1
    assert all(path.is_file() for path in paths)
    original = missing.read_bytes()
    assert main([*args[:-4], "--csv-out", str(missing)]) == 2
    assert missing.read_bytes() == original
    assert "cannot replace input" in capsys.readouterr().err
    duplicate = tmp_path / "duplicate.jsonl"
    duplicate.write_text(
        (FIXTURE / "events.jsonl").read_text().splitlines()[0]
        + "\n"
        + (FIXTURE / "events.jsonl").read_text().splitlines()[0]
        + "\n"
    )
    bad_out = tmp_path / "bad-out.json"
    assert (
        main(
            [
                "compare",
                "--events",
                str(duplicate),
                "--scenarios",
                str(FIXTURE / "scenarios.yaml"),
                "--json-out",
                str(bad_out),
            ]
        )
        == 2
    )
    assert not bad_out.exists()
    assert "Traceback" not in capsys.readouterr().err


def test_jsonl_levels_are_strict_but_auxiliary_metadata_is_allowed(tmp_path):
    path = tmp_path / "input.jsonl"
    path.write_text(
        '{"event_type":"book","timestamp":90,"sequence":0,"instrument_id":"FOO","bids":[["99","1"]],"asks":[["100","2"]],"observed_at":"2026-01-01T00:00:00Z"}\n'
    )
    events = load_events_jsonl(path)
    assert events[0].asks == ((Decimal("100"), Decimal("2")),)
    for invalid in [
        '"asks":[["100","0"]]',
        '"asks":[["100","2"],["100","3"]]',
        '"asks":[["98","1"]]',
    ]:
        path.write_text(
            '{"event_type":"book","timestamp":90,"sequence":0,"instrument_id":"FOO","bids":[["99","1"]],'
            + invalid
            + "}\n"
        )
        with pytest.raises(ValueError):
            load_events_jsonl(path)
    path.write_text(
        '{"event_type":"book","timestamp":90,"timestamp":91,"sequence":0,"instrument_id":"FOO"}\n'
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_events_jsonl(path)


def test_study_api_requires_an_included_unique_baseline():
    study = fixture_study()
    with pytest.raises(ValueError, match="baseline"):
        ScenarioStudy("missing", "USD", study.scenarios)
    with pytest.raises(ValueError, match="uniquely"):
        ScenarioStudy("reference", "USD", (study.scenarios[0], study.scenarios[0]))


@pytest.mark.parametrize(
    "field,value",
    [
        ("timestamp", "90"),
        ("sequence", True),
        ("venue_id", False),
        ("source", 7),
        ("order_type", False),
    ],
)
def test_jsonl_does_not_replace_wrongly_typed_fields_with_defaults(tmp_path, field, value):
    import json

    row = {
        "event_type": "decision",
        "timestamp": 90,
        "sequence": 0,
        "instrument_id": "FOO",
        "side": "buy",
        "size": "1",
        "limit_price": "100",
        "order_type": "taker",
    }
    row[field] = value
    path = tmp_path / "input.jsonl"
    path.write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError):
        load_events_jsonl(path)
