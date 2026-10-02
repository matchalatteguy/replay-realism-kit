"""A fixed Decimal context isolates reference results from caller process settings."""

from collections.abc import Callable
from decimal import (
    ROUND_HALF_EVEN,
    Clamped,
    Context,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    Underflow,
    localcontext,
)
from functools import wraps
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


def reference_arithmetic(function: Callable[P, T]) -> Callable[P, T]:
    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        with localcontext(
            Context(
                prec=28,
                rounding=ROUND_HALF_EVEN,
                Emin=-999999,
                Emax=999999,
                capitals=1,
                clamp=0,
                traps=[InvalidOperation, DivisionByZero, Overflow, Underflow, Clamped],
            )
        ):
            return function(*args, **kwargs)

    return wrapped
