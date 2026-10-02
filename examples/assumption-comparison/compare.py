"""Repeat four assumption settings on the same invented two-decision fixture."""

from decimal import Decimal
from pathlib import Path

from replay_realism import ExecutionAssumptionProfile, FeeModel, load_events_csv, simulate_replay
from replay_realism.simulation import ReplaySimulationConfig


def comparison_rows() -> list[dict[str, str]]:
    events = load_events_csv(Path(__file__).with_name("events.csv"))
    fees = FeeModel(Decimal("1"), Decimal("5"), name="demo-fees")
    cases = [
        ("explicit zero fees", 10, Decimal("0"), FeeModel.explicit_zero()),
        ("fees", 10, Decimal("0"), fees),
        ("fees + queue", 10, Decimal("2"), fees),
        ("fees + queue + delay", 50, Decimal("2"), fees),
    ]
    rows = []
    for name, latency, queue, fee_model in cases:
        assumptions = ExecutionAssumptionProfile(name, latency, 250, fee_model)
        report = simulate_replay(events, assumptions, ReplaySimulationConfig(queue, 100, maker_lifetime_ms=100))
        edge = sum(
            (
                markout.edge_after_fees
                for _, markout in report.fills
                if markout is not None and markout.edge_after_fees is not None
            ),
            Decimal("0"),
        )
        rows.append(
            {
                "case": name,
                "taker_size": str(report.fills[0][0].filled_size),
                "maker_size": str(report.fills[1][0].filled_size),
                "fees": report.to_dict()["summary"]["fee_total"],
                "edge_after_fees": str(edge),
            }
        )
    return rows


def main() -> None:
    print("| Setting | Taker size | Maker size | Fees | Future markout after fees |")
    print("| --- | ---: | ---: | ---: | ---: |")
    for row in comparison_rows():
        print(
            f"| {row['case']} | {row['taker_size']} | {row['maker_size']} | "
            f"{row['fees']} | {row['edge_after_fees']} |"
        )


if __name__ == "__main__":
    main()
