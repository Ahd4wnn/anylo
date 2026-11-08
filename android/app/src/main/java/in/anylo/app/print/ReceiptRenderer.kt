package `in`.anylo.app.print

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.qrcode.QRCodeWriter
import `in`.anylo.app.core.Receipt
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.math.BigDecimal
import java.net.URL
import java.text.NumberFormat
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

/** QR as a black-on-white bitmap, generated on the phone (the UPI ID and amount never go to a third party). */
fun qrBitmap(text: String, size: Int): Bitmap {
    val m = QRCodeWriter().encode(text, BarcodeFormat.QR_CODE, size, size, mapOf(EncodeHintType.MARGIN to 1))
    val px = IntArray(size * size) { if (m[it % size, it / size]) Color.BLACK else Color.WHITE }
    return Bitmap.createBitmap(px, size, size, Bitmap.Config.ARGB_8888)
}

fun upiUri(vpa: String, payee: String, amount: String, note: String): String {
    fun enc(s: String) = java.net.URLEncoder.encode(s, "UTF-8").replace("+", "%20")
    return "upi://pay?pa=${enc(vpa)}&pn=${enc(payee)}&am=$amount&tn=${enc(note)}&cu=INR"
}

private val inr = NumberFormat.getNumberInstance(Locale.forLanguageTag("en-IN")).apply { minimumFractionDigits = 2; maximumFractionDigits = 2 }
fun money(v: String) = inr.format(BigDecimal(v))
private fun qty(v: String) = BigDecimal(v).stripTrailingZeros().toPlainString()
private fun nonZero(v: String) = BigDecimal(v).signum() != 0

/** Fetched on IO before drawing: the print callback is not a suspend function. */
suspend fun loadLogo(url: String?): Bitmap? = url?.let {
    withContext(Dispatchers.IO) { runCatching { URL(it).openStream().use(BitmapFactory::decodeStream) }.getOrNull() }
}

/**
 * Draws the server's receipt model for the printer head, same layout as web/src/features/pos/receipt.ts,
 * so a bill looks identical from any device (docs/07-pos-billing.md §7).
 */
fun receiptBitmap(r: Receipt, dots: Int, logo: Bitmap?): Bitmap {
    val scale = dots / 384f // designed for 58 mm, scaled up for 80 mm
    val bmp = Bitmap.createBitmap(dots, 4000, Bitmap.Config.ARGB_8888)
    val c = Canvas(bmp)
    c.drawColor(Color.WHITE)
    val p = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.BLACK }
    val pad = 6 * scale
    var y = pad

    fun font(px: Int, bold: Boolean) { p.textSize = px * scale; p.typeface = if (bold) Typeface.DEFAULT_BOLD else Typeface.DEFAULT }
    fun text(s: String, px: Int, bold: Boolean = false, align: Paint.Align = Paint.Align.LEFT) {
        font(px, bold); p.textAlign = align
        y += px * scale + 4 * scale
        c.drawText(s, when (align) { Paint.Align.CENTER -> dots / 2f; Paint.Align.RIGHT -> dots - pad; else -> pad }, y, p)
    }
    fun wrap(s: String, px: Int, bold: Boolean = false) {
        font(px, bold)
        var line = ""
        for (w in s.split(" ")) {
            if (line.isNotEmpty() && p.measureText("$line $w") > dots - 2 * pad) { text(line, px, bold, Paint.Align.CENTER); line = w }
            else line = if (line.isEmpty()) w else "$line $w"
        }
        if (line.isNotEmpty()) text(line, px, bold, Paint.Align.CENTER)
    }
    fun row(left: String, right: String, px: Int = 20, bold: Boolean = false) {
        font(px, bold)
        y += px * scale + 4 * scale
        p.textAlign = Paint.Align.LEFT; c.drawText(left, pad, y, p)
        p.textAlign = Paint.Align.RIGHT; c.drawText(right, dots - pad, y, p)
    }
    fun rule() { y += 6 * scale; c.drawRect(pad, y, dots - pad, y + maxOf(1f, 2 * scale), p); y += 2 * scale }

    logo?.let {
        val h = 90 * scale
        val w = h * it.width / it.height
        c.drawBitmap(it, null, android.graphics.RectF((dots - w) / 2, y, (dots + w) / 2, y + h), p)
        y += h + pad
    }
    wrap(r.shop.name, 28, true)
    if (r.shop.address.isNotBlank()) wrap(r.shop.address, 18)
    r.shop.gstin?.let { text("GSTIN: $it", 18, align = Paint.Align.CENTER) }
    r.shop.phone?.let { text("Ph: $it", 18, align = Paint.Align.CENTER) }
    r.compositionNote?.let { wrap(it, 16) }
    text(if (r.status == "cancelled") "${r.title} · CANCELLED" else r.title, 22, true, Paint.Align.CENTER)
    val issued = runCatching { OffsetDateTime.parse(r.issuedAt).format(DateTimeFormatter.ofPattern("dd MMM yyyy, hh:mm a", Locale.forLanguageTag("en-IN"))) }.getOrDefault("")
    row(r.number, issued, 18)
    r.buyer?.let { b ->
        row("Bill to: ${b.name ?: "Customer"}", b.phone.orEmpty(), 18)
        b.gstin?.let { text("GSTIN: $it", 18) }
    }
    val taxed = r.taxSummary.isNotEmpty()
    if (taxed) row("POS: ${r.placeOfSupply}", "Rev. charge: ${r.reverseCharge}", 16)
    rule()
    row("Item", "Amount", 18, true)
    for (l in r.lines) {
        text(if (l.variantName != null) "${l.name} (${l.variantName})" else l.name, 20, true)
        val meta = "  ${qty(l.qty)} ${l.unit} × ${money(l.unitPrice)}" + (l.hsn?.let { "  HSN $it" } ?: "") + (if (taxed) "  ${qty(l.taxRate)}%" else "")
        row(meta, money(l.lineTotal), 18)
        if (nonZero(l.discount)) row("  Discount", "−${money(l.discount)}", 16)
    }
    rule()
    val t = r.totals
    if (nonZero(t.discountTotal)) row("Discount", "−${money(t.discountTotal)}")
    if (taxed) {
        row("Taxable value", money(t.taxableTotal))
        if (r.supplyType == "inter") row("IGST", money(t.igstTotal)) else { row("CGST", money(t.cgstTotal)); row(r.stateTaxLabel, money(t.sgstTotal)) }
        if (nonZero(t.cessTotal)) row("Cess", money(t.cessTotal))
    }
    if (nonZero(t.roundOff)) row("Round off", money(t.roundOff))
    row("TOTAL", "₹${money(t.grandTotal)}", 30, true)
    wrap(r.amountInWords, 16)
    for (pay in r.payments) row("Paid · ${pay.method.uppercase()}", money(pay.amount), 18)
    if (nonZero(t.dueTotal)) row("Balance due", "₹${money(t.dueTotal)}", 22, true)
    if (taxed) {
        rule()
        row("GST%  Taxable", if (r.supplyType == "inter") "IGST" else "CGST / ${r.stateTaxLabel}", 16, true)
        for (s in r.taxSummary) row("${qty(s.rate)}%  ${money(s.taxable)}", if (r.supplyType == "inter") money(s.igst) else "${money(s.cgst)} / ${money(s.sgst)}", 16)
    }
    r.remarks?.takeIf { it.isNotBlank() }?.let { rule(); wrap("Note: $it", 16) }
    rule()
    wrap(r.footer, 18, true)
    text("Computer generated · Bill anything. Sell anything.", 14, align = Paint.Align.CENTER)

    val out = Bitmap.createBitmap(bmp, 0, 0, dots, minOf(4000, (y + pad * 2).toInt()))
    if (out !== bmp) bmp.recycle()
    return out
}
