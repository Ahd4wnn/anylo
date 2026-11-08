package `in`.anylo.app.gst

import java.math.BigDecimal
import java.math.MathContext
import java.math.RoundingMode

// Port of backend/app/services/gst/engine.py (docs/06-gst.md §5); same fixtures, same results.
// Display only: the server recomputes every bill and is authoritative.

private fun q2(x: BigDecimal) = x.setScale(2, RoundingMode.HALF_UP)
private val ZERO = BigDecimal.ZERO.setScale(2)
private val HUNDRED = BigDecimal(100)
// Kotlin's `/` keeps the dividend's scale (and rounds HALF_EVEN), so divide at full precision.
private infix fun BigDecimal.over(d: BigDecimal): BigDecimal = divide(d, MathContext.DECIMAL128)
private fun List<BigDecimal>.total() = fold(ZERO, BigDecimal::add)

class GstException(val code: String, message: String) : Exception(message)

data class GstLine(
    val qty: BigDecimal, val unitPrice: BigDecimal, val rate: BigDecimal = BigDecimal.ZERO,
    val cessRate: BigDecimal = BigDecimal.ZERO, val priceIncludesTax: Boolean = true, val lineDiscount: BigDecimal = BigDecimal.ZERO,
)

data class GstLineOut(
    val gross: BigDecimal, val lineDiscount: BigDecimal, val invoiceDiscountShare: BigDecimal, val taxable: BigDecimal, val rate: BigDecimal,
    val cgst: BigDecimal, val sgst: BigDecimal, val igst: BigDecimal, val cess: BigDecimal, val total: BigDecimal,
)

data class GstInvoice(
    val lines: List<GstLineOut>, val subtotalGross: BigDecimal, val discountTotal: BigDecimal, val taxableTotal: BigDecimal,
    val cgstTotal: BigDecimal, val sgstTotal: BigDecimal, val igstTotal: BigDecimal, val cessTotal: BigDecimal,
    val roundOff: BigDecimal, val grandTotal: BigDecimal,
)

object GstEngine {
    /** Invoice discount is spread pre-tax by base; the paisa remainder goes to the biggest line. */
    private fun allocate(amount: BigDecimal, bases: List<BigDecimal>): List<BigDecimal> {
        val total = bases.total()
        if (amount.signum() == 0 || total.signum() == 0) return bases.map { ZERO }
        val shares = bases.map { q2(amount * it over total) }.toMutableList()
        val biggest = bases.indices.maxBy { bases[it] }
        shares[biggest] = shares[biggest] + (amount - shares.total())
        return shares
    }

    fun compute(
        lines: List<GstLine>, supplyType: String = "intra", scheme: String = "regular",
        discountType: String? = null, discountValue: BigDecimal = BigDecimal.ZERO, roundOff: Boolean = true,
    ): GstInvoice {
        if (lines.isEmpty()) throw GstException("gst.empty", "Add at least one item to the bill.")
        if (scheme == "composition" && supplyType == "inter")
            throw GstException("gst.composition_interstate_blocked", "Composition shops cannot sell goods to another state.")

        val bases = lines.map { ln ->
            if (ln.qty.signum() <= 0) throw GstException("gst.qty_invalid", "Quantity must be more than zero.")
            if (ln.unitPrice.signum() < 0 || ln.lineDiscount.signum() < 0 || ln.rate.signum() < 0)
                throw GstException("gst.negative_value", "Prices, discounts and rates cannot be negative.")
            val gross = q2(ln.unitPrice * ln.qty)
            if (ln.lineDiscount > gross) throw GstException("gst.line_discount_too_large", "An item discount is more than the item price.")
            gross - ln.lineDiscount
        }
        val baseSum = bases.total()
        val invDiscount = when (discountType) {
            "percent" -> {
                if (discountValue.signum() < 0 || discountValue > HUNDRED) throw GstException("gst.discount_invalid", "Discount percent must be between 0 and 100.")
                q2(baseSum * discountValue over HUNDRED)
            }
            "flat" -> {
                if (discountValue.signum() < 0 || discountValue > baseSum) throw GstException("gst.discount_invalid", "Discount cannot be more than the bill amount.")
                discountValue
            }
            else -> ZERO
        }

        val taxed = scheme == "regular"
        val intra = supplyType == "intra"
        val shares = allocate(invDiscount, bases)
        val out = lines.mapIndexed { i, ln ->
            val net = bases[i] - shares[i]
            val rate = if (taxed) ln.rate else BigDecimal.ZERO
            val cessRate = if (taxed) ln.cessRate else BigDecimal.ZERO
            var cgst = ZERO; var sgst = ZERO; var igst = ZERO
            val cess: BigDecimal
            val taxable: BigDecimal
            if (ln.priceIncludesTax) {
                val k = rate + cessRate + HUNDRED
                cess = q2(net * cessRate over k)
                if (intra) { cgst = q2(net * rate over (k * BigDecimal(2))); sgst = cgst } else igst = q2(net * rate over k)
                taxable = net - cgst - sgst - igst - cess
            } else {
                taxable = net
                cess = q2(taxable * cessRate over HUNDRED)
                if (intra) { cgst = q2(taxable * rate over BigDecimal(200)); sgst = cgst } else igst = q2(taxable * rate over HUNDRED)
            }
            GstLineOut(q2(ln.unitPrice * ln.qty), ln.lineDiscount, shares[i], taxable, rate, cgst, sgst, igst, cess, taxable + cgst + sgst + igst + cess)
        }
        val before = out.map { it.total }.total()
        val grand = if (roundOff) before.setScale(0, RoundingMode.HALF_UP).setScale(2) else before
        return GstInvoice(
            out, out.map { it.gross }.total(), out.map { it.lineDiscount + it.invoiceDiscountShare }.total(), out.map { it.taxable }.total(),
            out.map { it.cgst }.total(), out.map { it.sgst }.total(), out.map { it.igst }.total(), out.map { it.cess }.total(),
            grand - before, grand,
        )
    }
}
