from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any

from replay_realism.fees import FeeModel
from replay_realism.serialization import load_unique_yaml


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
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("assumption profile name is required")
        if type(self.latency_ms) is not int or type(self.stale_book_ms) is not int:
            raise ValueError("latency_ms and stale_book_ms must be integers")
        if not isinstance(self.allow_partial_fills, bool) or not isinstance(
            self.require_future_markout, bool
        ):
            raise ValueError("fill and markout flags must be booleans")
        if not self.tick_size.is_finite() or not self.min_size.is_finite():
            raise ValueError("tick_size and min_size must be finite")
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
            "description": self.description,
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


def _yaml_bool(data: dict[str, object], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a YAML boolean (true or false), got {value!r}")
    return value


def profile_from_mapping(
    data: Any, *, require_complete: bool = False
) -> ExecutionAssumptionProfile:
    """Parse typed assumptions without trusting a serialized safety label."""
    if not isinstance(data, dict):
        raise ValueError("assumption profile must be a mapping")
    if require_complete:
        required = {
            "name",
            "latency_ms",
            "stale_book_ms",
            "tick_size",
            "min_size",
            "allow_partial_fills",
            "require_future_markout",
            "fee_model",
        }
        if required.difference(data):
            raise ValueError("report assumptions are incomplete")
    fee = data.get("fee_model")
    if not isinstance(fee, dict):
        raise ValueError("fee_model must be a mapping")
    if require_complete and {"name", "maker_bps", "taker_bps", "explicit_zero_fees"}.difference(
        fee
    ):
        raise ValueError("report fee model is incomplete")
    latency = data.get("latency_ms", 0)
    stale_book = data.get("stale_book_ms", 250)
    if type(latency) is not int or type(stale_book) is not int:
        raise ValueError("latency_ms and stale_book_ms must be integers")
    try:
        return ExecutionAssumptionProfile(
            name=data.get("name", "local-profile"),
            latency_ms=latency,
            stale_book_ms=stale_book,
            tick_size=Decimal(str(data.get("tick_size", "0.01"))),
            min_size=Decimal(str(data.get("min_size", "0.0001"))),
            allow_partial_fills=_yaml_bool(data, "allow_partial_fills", True),
            require_future_markout=_yaml_bool(data, "require_future_markout", True),
            description=str(data.get("description") or ""),
            fee_model=FeeModel(
                maker_bps=Decimal(str(fee.get("maker_bps", "0"))),
                taker_bps=Decimal(str(fee.get("taker_bps", "0"))),
                name=fee.get("name", "configured-fees"),
                explicit_zero_fees=_yaml_bool(fee, "explicit_zero_fees", False),
            ),
        )
    except InvalidOperation as exc:
        raise ValueError("assumption decimal values must be finite numbers") from exc


def load_assumption_profile(path: str | Path) -> ExecutionAssumptionProfile:
    data = load_unique_yaml(Path(path).read_text(encoding="utf-8"))
    return profile_from_mapping(data)
