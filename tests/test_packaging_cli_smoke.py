from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )


def test_built_wheel_installs_and_runs_cli_example(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    dist_dir = tmp_path / "dist"
    venv_dir = tmp_path / "venv"

    run(["uv", "build", "--wheel", "--out-dir", str(dist_dir)], cwd=root)
    wheel = next(dist_dir.glob("replay_realism_kit-*.whl"))

    run(["uv", "venv", "--python", sys.executable, str(venv_dir)], cwd=tmp_path)
    python = venv_dir / "bin" / "python"
    replay_realism = venv_dir / "bin" / "replay-realism"
    run(["uv", "pip", "install", "--python", str(python), str(wheel)], cwd=tmp_path)

    import_result = run(
        [str(python), "-c", "import replay_realism; print('import-ok')"],
        cwd=tmp_path,
    )
    assert "import-ok" in import_result.stdout
    assert "simulate" in run([str(replay_realism), "--help"], cwd=tmp_path).stdout

    example_out = tmp_path / "example-out"
    run(
        [str(replay_realism), "init-example", "synthetic-book", "--out-dir", str(example_out)],
        cwd=tmp_path,
    )
    example = example_out / "synthetic-book"
    report = tmp_path / "replay.json"
    markdown = tmp_path / "replay.md"

    run(
        [str(replay_realism), "validate-events", "--events", str(example / "events.csv")],
        cwd=tmp_path,
    )
    run(
        [
            str(replay_realism),
            "simulate",
            "--events",
            str(example / "events.csv"),
            "--assumptions",
            str(example / "assumptions.yaml"),
            "--json-out",
            str(report),
        ],
        cwd=tmp_path,
    )
    run(
        [str(replay_realism), "gate", "--report", str(report), "--md-out", str(markdown)],
        cwd=tmp_path,
    )

    assert report.exists()
    assert markdown.exists()

    # Exercise the packaged multi-level example and comparison/sweep from outside the checkout.
    run(
        [str(replay_realism), "init-example", "execution-stress", "--out-dir", str(example_out)],
        cwd=tmp_path,
    )
    stress = example_out / "execution-stress"
    comparison = tmp_path / "comparison.json"
    summary_csv = tmp_path / "comparison.csv"
    summary_md = tmp_path / "comparison.md"
    run(
        [
            str(replay_realism),
            "compare",
            "--events",
            str(stress / "events.jsonl"),
            "--scenarios",
            str(stress / "scenarios.yaml"),
            "--json-out",
            str(comparison),
            "--csv-out",
            str(summary_csv),
            "--md-out",
            str(summary_md),
        ],
        cwd=tmp_path,
    )
    assert summary_csv.read_text() == (stress / "expected-summary.csv").read_text()
    assert "higher-fees" in summary_md.read_text()
    run(
        [
            str(replay_realism),
            "compare",
            "--events",
            str(stress / "events.jsonl"),
            "--scenarios",
            str(stress / "sweep.yaml"),
            "--json-out",
            str(tmp_path / "sweep.json"),
        ],
        cwd=tmp_path,
    )
    import json

    assert json.loads((tmp_path / "sweep.json").read_text())["scenario_count"] == 29
    version = run(
        [
            str(python),
            "-c",
            "from importlib.metadata import version; from importlib.resources import files; import replay_realism; print(version('replay-realism-kit')); assert files(replay_realism).joinpath('py.typed').is_file()",
        ],
        cwd=tmp_path,
    )
    assert "0.3.0" in version.stdout
