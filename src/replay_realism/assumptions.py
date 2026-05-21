from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

import yaml

from replay_realism.fees import FeeModel


class SafetyLevel(StrEnum):
    REVIEWABLE = "reviewable"
    OPTIMISTIC = "optimistic"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True, slots=True)
class ExecutionAssumptionProfile:
    name: str
    latency_ms: int
    stale_book_ms: int
    fee_model: FeeModel
    tick_size: Decimal = Decimal("0.01")
    min_size: Decimal = Decimal("0.0001")
    allow_partial_fills: bool = True
    require_future_markout: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("assumption profile name is required")
        if self.latency_ms < 0:
            raise ValueError("latency_ms cannot be negative")
        if self.stale_book_ms <= 0:
            raise ValueError("stale_book_ms must be positive")
        if self.tick_size <= 0 or self.min_size <= 0:
            raise ValueError("tick_size and min_size must be positive")

    @property
    def safety_level(self) -> SafetyLevel:
        if self.latency_ms == 0 or self.stale_book_ms > 5_000:
            return SafetyLevel.OPTIMISTIC
        if not self.require_future_markout:
            return SafetyLevel.INCOMPLETE
        return SafetyLevel.REVIEWABLE

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "latency_ms": self.latency_ms,
            "stale_book_ms": self.stale_book_ms,
            "tick_size": str(self.tick_size),
            "min_size": str(self.min_size),
            "allow_partial_fills": self.allow_partial_fills,
            "require_future_markout": self.require_future_markout,
            "safety_level": self.safety_level.value,
            "fee_model": {
                "name": self.fee_model.name,
                "maker_bps": str(self.fee_model.maker_bps),
                "taker_bps": str(self.fee_model.taker_bps),
                "explicit_zero_fees": self.fee_model.explicit_zero_fees,
            },
        }


def load_assumption_profile(path: str | Path) -> ExecutionAssumptionProfile:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    fee = data.get("fee_model") or {}
    return ExecutionAssumptionProfile(
        name=str(data.get("name") or "local-profile"),
        latency_ms=int(data.get("latency_ms", 0)),
        stale_book_ms=int(data.get("stale_book_ms", 250)),
        tick_size=Decimal(str(data.get("tick_size", "0.01"))),
        min_size=Decimal(str(data.get("min_size", "0.0001"))),
        allow_partial_fills=bool(data.get("allow_partial_fills", True)),
        require_future_markout=bool(data.get("require_future_markout", True)),
        description=str(data.get("description") or ""),
        fee_model=FeeModel(
            maker_bps=Decimal(str(fee.get("maker_bps", "0"))),
            taker_bps=Decimal(str(fee.get("taker_bps", "0"))),
            name=str(fee.get("name") or "configured-fees"),
            explicit_zero_fees=bool(fee.get("explicit_zero_fees", False)),
        ),
    )
