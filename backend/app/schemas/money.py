from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer

PAISE = Decimal("0.01")
MILLI = Decimal("0.001")


def q2(x: Decimal) -> Decimal:
    return x.quantize(PAISE, rounding=ROUND_HALF_UP)


def q3(x: Decimal) -> Decimal:
    return x.quantize(MILLI, rounding=ROUND_HALF_UP)


def _parse(v: object) -> Decimal:
    if isinstance(v, float):
        raise ValueError("send money as a string, not a float")
    d = Decimal(str(v))
    if not d.is_finite():
        raise ValueError("invalid amount")
    return d


def _money_in(v: object) -> Decimal:
    d = _parse(v)
    if d != q2(d):
        raise ValueError("at most 2 decimal places")
    return d


def _qty_in(v: object) -> Decimal:
    d = _parse(v)
    if d != q3(d):
        raise ValueError("at most 3 decimal places")
    return d


Money = Annotated[
    Decimal, BeforeValidator(_money_in), PlainSerializer(lambda d: f"{q2(d):.2f}", return_type=str)
]
Qty = Annotated[
    Decimal,
    BeforeValidator(_qty_in),
    PlainSerializer(lambda d: f"{q3(d).normalize():f}", return_type=str),
]
