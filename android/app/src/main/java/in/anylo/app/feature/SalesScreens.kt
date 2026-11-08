package `in`.anylo.app.feature

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.anylo.app.AppState
import `in`.anylo.app.core.CancelReq
import `in`.anylo.app.core.InvoicePage
import `in`.anylo.app.core.Receipt
import `in`.anylo.app.print.money
import `in`.anylo.app.ui.Anylo
import `in`.anylo.app.ui.AnyloField
import `in`.anylo.app.ui.Card
import `in`.anylo.app.ui.ErrorBanner
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.math.BigDecimal
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter

private fun whenText(iso: String, pattern: String) = runCatching { OffsetDateTime.parse(iso).format(DateTimeFormatter.ofPattern(pattern)) }.getOrDefault("")

@Composable
fun SalesScreen(app: AppState) {
    var openId by remember { mutableStateOf<String?>(null) }
    var q by remember { mutableStateOf("") }
    var days by remember { mutableStateOf(0L) } // 0 = today
    var page by remember { mutableStateOf<InvoicePage?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(q, days, openId) {
        if (openId != null) return@LaunchedEffect
        delay(250) // let typing settle
        val today = LocalDate.now()
        runCatching { app.session.sales.list(q.ifBlank { null }, today.minusDays(days).toString(), today.toString()) }
            .onSuccess { page = it; error = null }.onFailure { error = app.session.messageOf(it) }
    }
    openId?.let { InvoiceScreen(app, it) { openId = null }; return }

    Column(Modifier.fillMaxSize().statusBarsPadding().padding(horizontal = 20.dp)) {
        Spacer(Modifier.height(20.dp))
        Text("Sales", style = MaterialTheme.typography.headlineMedium)
        page?.let { Text("${it.total} bill${if (it.total == 1) "" else "s"} · ₹${money(it.salesTotal)}", color = Anylo.colors.text2) }
        Spacer(Modifier.height(12.dp))
        AnyloField("Search", q, { q = it }, hint = "Bill number, customer name or mobile")
        Row(Modifier.padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf(0L to "Today", 6L to "7 days", 29L to "30 days").forEach { (d, label) -> FilterChip(selected = days == d, onClick = { days = d }, label = { Text(label) }) }
        }
        ErrorBanner(error)
        LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(page?.items.orEmpty(), key = { it.id }) { inv ->
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Anylo.colors.surface).clickable { openId = inv.id }.padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(inv.number, fontWeight = FontWeight.Medium)
                        Text(listOfNotNull(whenText(inv.issuedAt, "dd MMM, hh:mm a"), inv.buyerName ?: inv.buyerPhone).joinToString(" · "),
                            color = Anylo.colors.text2, style = MaterialTheme.typography.bodyMedium)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text("₹${money(inv.grandTotal)}", fontWeight = FontWeight.SemiBold)
                        when {
                            inv.status == "cancelled" -> Pill("Cancelled")
                            BigDecimal(inv.dueTotal).signum() > 0 -> Pill("Due ₹${money(inv.dueTotal)}")
                            else -> Text(inv.methods.joinToString(" + ") { it.uppercase() }, color = Anylo.colors.text2, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun InvoiceScreen(app: AppState, id: String, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var r by remember { mutableStateOf<Receipt?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var message by remember { mutableStateOf<String?>(null) }
    var cancelling by remember { mutableStateOf(false) }
    LaunchedEffect(id) { runCatching { app.session.sales.get(id) }.onSuccess { r = it }.onFailure { error = app.session.messageOf(it) } }

    Column(Modifier.fillMaxSize().background(Anylo.colors.bg).statusBarsPadding().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") }
            Text(r?.number ?: "Bill", style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
            if (r?.status == "issued" && app.can("invoice.cancel")) TextButton(onClick = { cancelling = true }) { Text("Cancel bill", color = Anylo.colors.danger) }
        }
        ErrorBanner(error)
        message?.let { Text(it, color = Anylo.colors.text2) }
        val bill = r ?: return@Column
        ReceiptActions(app, bill) { message = it }
        Card {
            Text(if (bill.status == "cancelled") "${bill.title} · CANCELLED" else bill.title, fontWeight = FontWeight.Bold)
            Text(whenText(bill.issuedAt, "dd MMM yyyy, hh:mm a"), color = Anylo.colors.text2)
            bill.cancelReason?.let { Text("Reason: $it", color = Anylo.colors.danger) }
            bill.buyer?.let { b -> Text("Bill to: " + listOfNotNull(b.name, b.phone, b.gstin).joinToString(" · ")) }
            bill.lines.forEach { l ->
                Row {
                    Column(Modifier.weight(1f)) {
                        Text(if (l.variantName != null) "${l.name} (${l.variantName})" else l.name)
                        Text("${BigDecimal(l.qty).stripTrailingZeros().toPlainString()} ${l.unit.lowercase()} × ₹${money(l.unitPrice)}", color = Anylo.colors.text2, style = MaterialTheme.typography.bodySmall)
                    }
                    Text("₹${money(l.lineTotal)}")
                }
            }
            val t = bill.totals
            if (bill.taxSummary.isNotEmpty()) {
                TotalRow("Taxable", t.taxableTotal)
                if (bill.supplyType == "inter") TotalRow("IGST", t.igstTotal) else { TotalRow("CGST", t.cgstTotal); TotalRow(bill.stateTaxLabel, t.sgstTotal) }
            }
            if (BigDecimal(t.roundOff).signum() != 0) TotalRow("Round off", t.roundOff)
            Row { Text("Total", Modifier.weight(1f), fontWeight = FontWeight.Bold); Text("₹${money(t.grandTotal)}", fontWeight = FontWeight.Bold) }
            bill.payments.forEach { TotalRow("Paid · ${it.method.uppercase()}", it.amount) }
            if (BigDecimal(t.dueTotal).signum() > 0) TotalRow("Balance due", t.dueTotal)
            Text(bill.amountInWords, color = Anylo.colors.text2, style = MaterialTheme.typography.bodySmall)
        }
    }

    if (cancelling) {
        var reason by remember { mutableStateOf("") }
        AlertDialog(onDismissRequest = { cancelling = false }, title = { Text("Cancel this bill?") },
            dismissButton = { TextButton(onClick = { cancelling = false }) { Text("Keep") } },
            confirmButton = {
                TextButton(enabled = reason.trim().length >= 3, onClick = {
                    scope.launch {
                        runCatching { app.session.sales.cancel(id, CancelReq(reason.trim())) }
                            .onSuccess { r = it; cancelling = false }.onFailure { error = app.session.messageOf(it); cancelling = false }
                    }
                }) { Text("Cancel bill", color = Anylo.colors.danger) }
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("Stock and payments are reversed. The bill number is kept for GST records.", color = Anylo.colors.text2)
                    AnyloField("Reason", reason, { reason = it })
                }
            })
    }
}

@Composable
private fun TotalRow(label: String, amount: String) {
    Row { Text(label, Modifier.weight(1f), color = Anylo.colors.text2); Text("₹${money(amount)}", color = Anylo.colors.text2) }
}
