import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.errors import AppError
from app.services.gst.engine import InvoiceIn, LineIn, compute
from app.services.gst.india import amount_in_words, fy_label, gstin_check_char, is_valid_gstin

DATA = json.loads((Path(__file__).parent / "fixtures" / "gst_cases.json").read_text("utf-8"))


def _invoice(case: dict) -> InvoiceIn:
    return InvoiceIn(
        lines=[
            LineIn(
                qty=Decimal(ln["qty"]),
                unit_price=Decimal(ln["unit_price"]),
                rate=Decimal(ln.get("rate", "0")),
                price_includes_tax=ln.get("price_includes_tax", True),
                line_discount=Decimal(ln.get("line_discount", "0")),
            )
            for ln in case["lines"]
        ],
        supply_type=case["supply_type"],
        scheme=case["scheme"],
        discount_type=case.get("discount_type"),
        discount_value=Decimal(case.get("discount_value", "0")),
        round_off=case["round_off"],
    )


@pytest.mark.parametrize("case", DATA["cases"], ids=lambda c: c["id"])
def test_fixture(case: dict) -> None:
    if "expect_error" in case:
        with pytest.raises(AppError) as e:
            compute(_invoice(case))
        assert e.value.code == case["expect_error"]
        return
    out = compute(_invoice(case))
    exp = case["expect"]
    for i, line in enumerate(exp.get("lines", [])):
        for key, val in line.items():
            assert getattr(out.lines[i], key) == Decimal(val), (case["id"], i, key)
    for key, val in exp.items():
        if key != "lines":
            assert getattr(out, key) == Decimal(val), (case["id"], key)


@pytest.mark.parametrize("w", DATA["words"], ids=lambda w: w["amount"])
def test_amount_in_words(w: dict) -> None:
    assert amount_in_words(Decimal(w["amount"])) == w["text"]


money = st.decimals(min_value="0.01", max_value="99999.99", places=2)
rates = st.sampled_from([Decimal(r) for r in ("0", "0.25", "1.5", "3", "5", "18", "40")])
lines = st.lists(
    st.builds(
        LineIn,
        qty=st.integers(1, 50).map(Decimal),
        unit_price=money,
        rate=rates,
        price_includes_tax=st.booleans(),
    ),
    min_size=1,
    max_size=8,
)


@settings(max_examples=300)
@given(lines=lines, supply=st.sampled_from(["intra", "inter"]), pct=st.integers(0, 100))
def test_invariants(lines: list[LineIn], supply: str, pct: int) -> None:
    out = compute(
        InvoiceIn(
            lines=lines,
            supply_type=supply,
            discount_type="percent",  # type: ignore[arg-type]
            discount_value=Decimal(pct),
        )
    )
    for ln_in, ln in zip(lines, out.lines, strict=True):
        assert ln.cgst == ln.sgst
        assert ln.total == ln.taxable + ln.cgst + ln.sgst + ln.igst + ln.cess
        if ln_in.price_includes_tax:
            assert ln.total == ln.gross - ln.line_discount - ln.invoice_discount_share
    assert (
        out.grand_total
        == out.taxable_total
        + out.cgst_total
        + out.sgst_total
        + out.igst_total
        + out.cess_total
        + out.round_off
    )
    assert Decimal("-0.50") < out.round_off <= Decimal("0.50")
    assert out.grand_total == out.grand_total.to_integral_value()


def test_gstin() -> None:
    body = "32ABCDE1234F1Z"
    good = body + gstin_check_char(body)
    assert is_valid_gstin(good)
    assert not is_valid_gstin(body + ("0" if good[-1] != "0" else "1"))
    assert not is_valid_gstin("99ABCDE1234F1Z5")
    assert not is_valid_gstin("32abcde1234f1z")


def test_fy_label() -> None:
    assert fy_label(date(2026, 3, 31)) == "25-26"
    assert fy_label(date(2026, 4, 1)) == "26-27"
