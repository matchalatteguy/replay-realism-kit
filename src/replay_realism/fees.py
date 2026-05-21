from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

LiquidityRole = Literal["maker", "taker"]


@dataclass(frozen=True, slots=True)
class FeeModel:
    maker_bps: Decimal
    taker_bps: Decimal
    name: str = "explicit-fee-model"
    explicit_zero_fees: bool = False

    def __post_init__(self) -> None:
        if self.maker_bps < 0 or self.taker_bps < 0:
            raise ValueError("fee rates cannot be negative")
        if self.maker_bps == 0 and self.taker_bps == 0 and not self.explicit_zero_fees:
            raise ValueError("zero-fee assumptions must set explicit_zero_fees=True")

    @classmethod
    def explicit_zero(cls, name: str = "explicit-zero-fee-baseline") -> FeeModel:
        return cls(Decimal("0"), Decimal("0"), name=name, explicit_zero_fees=True)

    def fee_for(self, notional: Decimal, role: LiquidityRole) -> Decimal:
        bps = self.maker_bps if role == "maker" else self.taker_bps
        return (abs(notional) * bps) / Decimal("10000")
