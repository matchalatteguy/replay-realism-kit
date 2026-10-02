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


def test_single_profile_yaml_duplicate_keys_cannot_override_latency(tmp_path):
    from replay_realism.assumptions import load_assumption_profile

    path = tmp_path / "duplicate.yaml"
    path.write_text(
        "name: reference\nlatency_ms: 10\nlatency_ms: 0\nstale_book_ms: 250\nfee_model:\n  name: explicit-fees\n  maker_bps: '1'\n  taker_bps: '5'\n"
    )
    with pytest.raises(ValueError, match="unique"):
        load_assumption_profile(path)
