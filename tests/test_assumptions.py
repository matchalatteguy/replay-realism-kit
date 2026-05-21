from decimal import Decimal

import pytest

from replay_realism.assumptions import ExecutionAssumptionProfile, SafetyLevel
from replay_realism.fees import FeeModel


def test_zero_fees_must_be_explicit() -> None:
    with pytest.raises(ValueError, match="zero-fee"):
        FeeModel(Decimal("0"), Decimal("0"))
    assert FeeModel.explicit_zero().fee_for(Decimal("100"), "taker") == Decimal("0")


def test_safety_level_flags_optimistic_latency() -> None:
    profile = ExecutionAssumptionProfile("demo", 0, 250, FeeModel(Decimal("1"), Decimal("5")))
    assert profile.safety_level == SafetyLevel.OPTIMISTIC
