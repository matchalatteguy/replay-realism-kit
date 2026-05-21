from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FixedLatencyModel:
    latency_ms: int

    def __post_init__(self) -> None:
        if self.latency_ms < 0:
            raise ValueError("latency_ms cannot be negative")

    def arrival_time(self, decision_timestamp: int) -> int:
        return decision_timestamp + self.latency_ms


def apply_latency(decision_timestamp: int, latency_model: FixedLatencyModel) -> int:
    return latency_model.arrival_time(decision_timestamp)
