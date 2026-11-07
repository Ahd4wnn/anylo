"""Pure GST calculation engine. Spec: docs/06-gst.md §5. Decimal in, Decimal out, no I/O."""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.errors import AppError
from app.schemas.money import q2

ZERO = Decimal("0")
Scheme = Literal["regular", "composition", "unregistered"]
SupplyType = Literal["intra", "inter"]


@dataclass(frozen=True)
class LineIn:
    qty: Decimal
    unit_price: Decimal
    rate: Decimal = ZERO
    cess_rate: Decimal = ZERO
    price_includes_tax: bool = True
    line_discount: Decimal = ZERO


@dataclass(frozen=True)
class InvoiceIn:
    lines: list[LineIn]
    supply_type: SupplyType = "intra"
    scheme: Scheme = "regular"
    discount_type: Literal["flat", "percent"] | None = None
    discount_value: Decimal = ZERO
    round_off: bool = True


@dataclass
class LineOut:
    gross: Decimal
    line_discount: Decimal
    invoice_discount_share: Decimal
    taxable: Decimal
    rate: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    cess: Decimal
    total: Decimal


@dataclass
class InvoiceOut:
    lines: list[LineOut] = field(default_factory=list)
    subtotal_gross: Decimal = ZERO
    discount_total: Decimal = ZERO
    taxable_total: Decimal = ZERO
    cgst_total: Decimal = ZERO
    sgst_total: Decimal = ZERO
    igst_total: Decimal = ZERO
    cess_total: Decimal = ZERO
    round_off: Decimal = ZERO
    grand_total: Decimal = ZERO


def _err(code: str, detail: str) -> AppError:
    return AppError(f"gst.{code}", detail, status=422)


def _allocate(amount: Decimal, bases: list[Decimal]) -> list[Decimal]:
    """Split amount by bases; the paise remainder goes to the largest base (first on ties)."""
    total = sum(bases, ZERO)
    if amount == ZERO or total == ZERO:
        return [ZERO] * len(bases)
    shares = [q2(amount * b / total) for b in bases]
    biggest = max(range(len(bases)), key=lambda i: (bases[i], -i))
    shares[biggest] += amount - sum(shares, ZERO)
    return shares


def compute(inv: InvoiceIn) -> InvoiceOut:
    if not inv.lines:
        raise _err("empty", "Add at least one item to the bill.")
    if inv.scheme == "composition" and inv.supply_type == "inter":
        raise _err(
            "composition_interstate_blocked",
            "Composition shops cannot sell goods to another state.",
        )

    bases: list[Decimal] = []
    for ln in inv.lines:
        if ln.qty <= ZERO:
            raise _err("qty_invalid", "Quantity must be more than zero.")
        if ln.unit_price < ZERO or ln.line_discount < ZERO or ln.rate < ZERO or ln.cess_rate < ZERO:
            raise _err("negative_value", "Prices, discounts and rates cannot be negative.")
        gross = q2(ln.unit_price * ln.qty)
        if ln.line_discount > gross:
            raise _err("line_discount_too_large", "An item discount is more than the item price.")
        bases.append(gross - ln.line_discount)

    base_sum = sum(bases, ZERO)
    if inv.discount_type == "percent":
        if not ZERO <= inv.discount_value <= 100:
            raise _err("discount_invalid", "Discount percent must be between 0 and 100.")
        inv_discount = q2(base_sum * inv.discount_value / 100)
    elif inv.discount_type == "flat":
        inv_discount = inv.discount_value
        if inv_discount < ZERO or inv_discount > base_sum:
            raise _err("discount_invalid", "Discount cannot be more than the bill amount.")
    else:
        inv_discount = ZERO

    taxed = inv.scheme == "regular"
    intra = inv.supply_type == "intra"
    out = InvoiceOut()
    for ln, base, share in zip(inv.lines, bases, _allocate(inv_discount, bases), strict=True):
        net = base - share
        rate = ln.rate if taxed else ZERO
        cess_rate = ln.cess_rate if taxed else ZERO
        cgst = sgst = igst = ZERO
        if ln.price_includes_tax:
            k = 100 + rate + cess_rate
            cess = q2(net * cess_rate / k)
            if intra:
                cgst = sgst = q2(net * rate / (2 * k))
            else:
                igst = q2(net * rate / k)
            taxable = net - cgst - sgst - igst - cess
        else:
            taxable = net
            cess = q2(taxable * cess_rate / 100)
            if intra:
                cgst = sgst = q2(taxable * rate / 200)
            else:
                igst = q2(taxable * rate / 100)
        total = taxable + cgst + sgst + igst + cess
        out.lines.append(
            LineOut(
                q2(ln.unit_price * ln.qty),
                ln.line_discount,
                share,
                taxable,
                rate,
                cgst,
                sgst,
                igst,
                cess,
                total,
            )
        )

    out.subtotal_gross = sum((x.gross for x in out.lines), ZERO)
    out.discount_total = sum((x.line_discount + x.invoice_discount_share for x in out.lines), ZERO)
    out.taxable_total = sum((x.taxable for x in out.lines), ZERO)
    out.cgst_total = sum((x.cgst for x in out.lines), ZERO)
    out.sgst_total = sum((x.sgst for x in out.lines), ZERO)
    out.igst_total = sum((x.igst for x in out.lines), ZERO)
    out.cess_total = sum((x.cess for x in out.lines), ZERO)
    before = sum((x.total for x in out.lines), ZERO)
    out.grand_total = before.quantize(Decimal("1"), ROUND_HALF_UP) if inv.round_off else before
    out.grand_total = q2(out.grand_total)
    out.round_off = out.grand_total - before
    return out
