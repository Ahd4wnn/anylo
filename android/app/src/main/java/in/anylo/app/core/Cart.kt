package `in`.anylo.app.core

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import `in`.anylo.app.gst.GstEngine
import `in`.anylo.app.gst.GstInvoice
import `in`.anylo.app.gst.GstLine
import kotlinx.serialization.json.Json
import java.io.File
import java.math.BigDecimal

/** The bill in progress. Saved to a file on every change so a crash or app kill never loses it. */
class Cart(private val file: File, private val json: Json) {
    var state by mutableStateOf(runCatching { json.decodeFromString(CartSnapshot.serializer(), file.readText()) }.getOrDefault(CartSnapshot()))
        private set

    /** Kept until the bill is saved, so a retry after a dropped connection can't create a second bill. */
    var idempotencyKey: String? = null

    fun update(f: (CartSnapshot) -> CartSnapshot) {
        state = f(state)
        runCatching { file.writeText(json.encodeToString(CartSnapshot.serializer(), state)) }
    }

    /** Scanning or tapping the same item again adds to its quantity instead of a new line (same rule as web). */
    fun add(line: CartLine) = update { s ->
        val same = line.variantId?.let { id -> s.lines.find { it.variantId == id && it.unitPrice == line.unitPrice } }
        if (same == null) s.copy(lines = s.lines + line)
        else s.copy(lines = s.lines.map { if (it.key == same.key) it.copy(qty = (BigDecimal(it.qty) + BigDecimal(line.qty)).toPlainString()) else it })
    }

    fun setLine(key: String, f: (CartLine) -> CartLine) = update { s -> s.copy(lines = s.lines.map { if (it.key == key) f(it) else it }) }
    fun remove(key: String) = update { s -> s.copy(lines = s.lines.filter { it.key != key }) }
    fun load(snapshot: CartSnapshot) { idempotencyKey = null; update { snapshot } }
    fun clear() = load(CartSnapshot())

    /** Display totals; null while a line is half-typed or invalid. The server recomputes on save. */
    fun totals(scheme: String): GstInvoice? = runCatching {
        val s = state
        GstEngine.compute(
            s.lines.map { GstLine(BigDecimal(it.qty), BigDecimal(it.unitPrice), BigDecimal(it.rate), priceIncludesTax = it.inclusive) },
            scheme = scheme, discountType = s.discountType.takeIf { (s.discountValue.toBigDecimalOrNull() ?: BigDecimal.ZERO).signum() > 0 },
            discountValue = s.discountValue.toBigDecimalOrNull() ?: BigDecimal.ZERO,
        )
    }.getOrNull()

    fun checkoutBody(payments: List<PaymentReq>, key: String, pin: String?): CheckoutReq {
        val s = state
        val c = s.customer
        val discount = s.discountValue.toBigDecimalOrNull()?.takeIf { it.signum() > 0 }
        return CheckoutReq(
            lines = s.lines.map { LineReq(it.variantId, if (it.variantId == null) it.custom else null, it.qty, it.unitPrice) },
            customer = if (c.phone.isNotBlank() || c.name.isNotBlank() || (s.b2b && c.gstin.isNotBlank()))
                CustomerReq(c.name.ifBlank { null }, c.phone.ifBlank { null }, if (s.b2b) c.gstin.ifBlank { null } else null, c.address.ifBlank { null }) else null,
            discountType = discount?.let { s.discountType }, discountValue = discount?.toPlainString() ?: "0",
            remarks = s.remarks.ifBlank { null }, payments = payments, idempotencyKey = key, approvalPin = pin,
        )
    }
}
