package `in`.anylo.app.feature

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import `in`.anylo.app.AppState
import `in`.anylo.app.core.CountDto
import `in`.anylo.app.core.CountLineReq
import `in`.anylo.app.core.CountReq
import `in`.anylo.app.core.CountRowDto
import `in`.anylo.app.core.Option
import `in`.anylo.app.core.PaidReq
import `in`.anylo.app.core.PurchaseLineReq
import `in`.anylo.app.core.PurchaseReq
import `in`.anylo.app.core.PurchaseRows
import `in`.anylo.app.core.SupplierPage
import `in`.anylo.app.core.SupplierReq
import `in`.anylo.app.print.money
import `in`.anylo.app.ui.Anylo
import `in`.anylo.app.ui.AnyloField
import `in`.anylo.app.ui.Card
import `in`.anylo.app.ui.ErrorBanner
import `in`.anylo.app.ui.PrimaryButton
import `in`.anylo.app.ui.SecondaryButton
import kotlinx.coroutines.launch
import java.math.BigDecimal
import java.util.UUID

private fun rs(v: String) = "₹" + money(v)
private fun qty(v: String?) = v?.toBigDecimalOrNull()?.stripTrailingZeros()?.toPlainString() ?: "—"

private data class PLine(val variantId: String, val name: String, val qty: String, val cost: String)

@Composable
fun PurchasesScreen(app: AppState, onBack: () -> Unit) {
    var rows by remember { mutableStateOf<PurchaseRows?>(null) }
    var creating by remember { mutableStateOf(false) }
    LaunchedEffect(creating) { if (!creating) runCatching { rows = app.session.buying.purchases() } }
    if (creating) { NewPurchaseScreen(app) { creating = false }; return }
    Screen("Purchases", onBack) {
        PrimaryButton("New purchase", { creating = true })
        rows?.items?.forEach { p ->
            RowItem(p.supplierName + (p.billNo?.let { " · $it" } ?: ""), p.createdAt.take(10) + " · " + p.status.replaceFirstChar { it.uppercase() }, rs(p.total))
        }
        if (rows?.items?.isEmpty() == true) Text("Enter the bills from your suppliers here. Stock goes up and item costs stay right.", color = Anylo.colors.text2)
    }
}

@Composable
private fun NewPurchaseScreen(app: AppState, onDone: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val key = remember { UUID.randomUUID().toString() } // one key per bill: a retry can't enter it twice
    var suppliers by remember { mutableStateOf<SupplierPage?>(null) }
    var supplierId by remember { mutableStateOf("") }
    var billNo by remember { mutableStateOf("") }
    val lines = remember { mutableStateListOf<PLine>() }
    var q by remember { mutableStateOf("") }
    var paid by remember { mutableStateOf("") }
    var addingSupplier by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    suspend fun loadSuppliers() { runCatching { suppliers = app.session.buying.suppliers() } }
    LaunchedEffect(Unit) { loadSuppliers() }
    var results by remember { mutableStateOf(emptyList<Pair<String, PLine>>()) }
    LaunchedEffect(q) {
        if (q.length < 2) { results = emptyList(); return@LaunchedEffect }
        kotlinx.coroutines.delay(250)
        runCatching { app.session.catalogue.products(q) }.onSuccess { page ->
            results = page.items.flatMap { p -> p.variants.mapNotNull { v -> v.id?.let { id -> (p.name + (v.name?.let { " · $it" } ?: "")) to PLine(id, p.name + (v.name?.let { " · $it" } ?: ""), "1", v.costPrice.takeIf { BigDecimal(it).signum() > 0 }.orEmpty()) } } }
        }
    }
    fun add(l: PLine) {
        val i = lines.indexOfFirst { it.variantId == l.variantId }
        if (i >= 0) lines[i] = lines[i].copy(qty = (BigDecimal(lines[i].qty) + BigDecimal.ONE).toPlainString()) else lines.add(l)
    }
    val ready = supplierId.isNotEmpty() && lines.isNotEmpty() && lines.all { it.qty.toBigDecimalOrNull()?.signum() == 1 && it.cost.toBigDecimalOrNull() != null }
    val total = lines.fold(BigDecimal.ZERO) { a, l -> a + (l.qty.toBigDecimalOrNull() ?: BigDecimal.ZERO) * (l.cost.toBigDecimalOrNull() ?: BigDecimal.ZERO) }
    Screen("New purchase", onDone) {
        ErrorBanner(error)
        Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f)) {
                Picker("Supplier", listOf(Option("", "Choose")) + suppliers?.items.orEmpty().map { Option(it.id, it.name) }, supplierId) { supplierId = it }
            }
            TextButton(onClick = { addingSupplier = true }) { Text("New") }
        }
        AnyloField("Their bill no. (optional)", billNo, { billNo = it })
        Row(verticalAlignment = Alignment.CenterVertically) {
            AnyloField("Search items", q, { q = it }, Modifier.weight(1f))
            IconButton(onClick = {
                scanBarcode(ctx, { code ->
                    scope.launch {
                        runCatching { app.session.catalogue.lookup(code) }.onSuccess { r ->
                            val n = r.product.name + (r.variant.name?.let { " · $it" } ?: "")
                            add(PLine(r.variant.id!!, n, "1", r.variant.costPrice.takeIf { BigDecimal(it).signum() > 0 }.orEmpty()))
                        }.onFailure { error = "No item has barcode $code." }
                    }
                }, { error = it })
            }) { Icon(Icons.Filled.QrCodeScanner, "Scan barcode") }
        }
        results.take(8).forEach { (label, l) -> RowItem(label, "Tap to add", null) { add(l); q = "" } }
        lines.forEachIndexed { i, l ->
            Card {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(l.name, Modifier.weight(1f), fontWeight = FontWeight.Medium)
                    TextButton(onClick = { lines.removeAt(i) }) { Text("Remove", color = Anylo.colors.text2) }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    AnyloField("Qty", l.qty, { v -> lines[i] = l.copy(qty = v) }, Modifier.weight(1f), keyboard = KeyboardType.Decimal)
                    AnyloField("Rate before GST ₹", l.cost, { v -> lines[i] = l.copy(cost = v) }, Modifier.weight(1.4f), keyboard = KeyboardType.Decimal)
                }
            }
        }
        if (lines.isNotEmpty()) {
            Text("About ${rs(total.toPlainString())} before GST", color = Anylo.colors.text2)
            AnyloField("Paid now in cash ₹ (optional)", paid, { paid = it }, keyboard = KeyboardType.Decimal)
            PrimaryButton("Post · stock in", {
                scope.launch {
                    busy = true
                    val req = PurchaseReq(supplierId, billNo.ifBlank { null }, lines.map { PurchaseLineReq(it.variantId, it.qty, it.cost) }, true,
                        paid.toBigDecimalOrNull()?.takeIf { it.signum() > 0 }?.let { listOf(PaidReq("cash", it.toPlainString())) }.orEmpty(), key)
                    runCatching { app.session.buying.create(req) }.onSuccess { onDone() }.onFailure { error = app.session.messageOf(it) }
                    busy = false
                }
            }, loading = busy, enabled = ready)
        }
    }
    if (addingSupplier) {
        var name by remember { mutableStateOf("") }
        var phone by remember { mutableStateOf("") }
        AlertDialog(onDismissRequest = { addingSupplier = false }, title = { Text("Add supplier") },
            dismissButton = { TextButton(onClick = { addingSupplier = false }) { Text("Cancel") } },
            confirmButton = {
                TextButton(enabled = name.isNotBlank(), onClick = {
                    scope.launch {
                        runCatching { app.session.buying.addSupplier(SupplierReq(name.trim(), phone.ifBlank { null })) }
                            .onSuccess { supplierId = it.id; addingSupplier = false; loadSuppliers() }.onFailure { error = app.session.messageOf(it); addingSupplier = false }
                    }
                }) { Text("Save") }
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    AnyloField("Supplier name", name, { name = it })
                    AnyloField("Mobile (optional)", phone, { phone = it }, keyboard = KeyboardType.Phone)
                }
            })
    }
}

@Composable
fun StockCountScreen(app: AppState, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var counts by remember { mutableStateOf<List<CountRowDto>?>(null) }
    var openId by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(openId) { if (openId == null) runCatching { counts = app.session.buying.counts() } }
    openId?.let { CountSheetScreen(app, it) { openId = null }; return }
    Screen("Stock count", onBack) {
        ErrorBanner(error)
        Text("Count what's on the shelf. Each scan adds one. Items you don't count are left alone.", color = Anylo.colors.text2)
        PrimaryButton("Start a count", {
            scope.launch { runCatching { app.session.buying.startCount(CountReq("Stock count")) }.onSuccess { openId = it.id }.onFailure { error = app.session.messageOf(it) } }
        })
        counts?.forEach { c -> RowItem(c.name, "${c.counted} of ${c.items} counted · ${c.status}", null) { openId = c.id } }
    }
}

@Composable
private fun CountSheetScreen(app: AppState, id: String, onBack: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var c by remember { mutableStateOf<CountDto?>(null) }
    var editing by remember { mutableStateOf<String?>(null) }
    var message by remember { mutableStateOf<String?>(null) }
    suspend fun load() { runCatching { c = app.session.buying.count(id) } }
    LaunchedEffect(id) { load() }
    val sheet = c ?: return Screen("Stock count", onBack) { Text("Loading…", color = Anylo.colors.text2) }
    val open = sheet.status == "open"
    fun scanLoop() {
        scanBarcode(ctx, { code ->
            scope.launch {
                runCatching { app.session.buying.countLine(id, CountLineReq(code = code, add = "1")) }
                    .onSuccess { message = "Counted $code"; load(); scanLoop() } // keep scanning until the user backs out
                    .onFailure { message = app.session.messageOf(it) }
            }
        }, { message = it })
    }
    Screen(sheet.name, onBack) {
        Text("${sheet.counted} of ${sheet.lines.size} counted · difference ${rs(sheet.varianceValue)} at cost", color = Anylo.colors.text2)
        message?.let { Text(it, color = Anylo.colors.primary) }
        if (open) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            PrimaryButton("Scan items", { scanLoop() }, Modifier.weight(1f))
            SecondaryButton("Post count", {
                scope.launch { runCatching { c = app.session.buying.postCount(id) }.onSuccess { message = "Stock updated" }.onFailure { message = app.session.messageOf(it) } }
            }, Modifier.weight(1f))
        }
        sheet.lines.forEach { l ->
            val diff = l.counted?.let { BigDecimal(it) - BigDecimal(l.expected) }
            RowItem(l.name + (l.variantName?.let { " · $it" } ?: ""), "System ${qty(l.expected)}" + (diff?.let { " · diff ${if (it.signum() > 0) "+" else ""}${qty(it.toPlainString())}" } ?: ""),
                qty(l.counted), if (open) ({ editing = l.variantId }) else null)
        }
    }
    editing?.let { vid ->
        var value by remember(vid) { mutableStateOf(sheet.lines.find { it.variantId == vid }?.counted?.let(::qty)?.takeIf { it != "—" }.orEmpty()) }
        AlertDialog(onDismissRequest = { editing = null }, title = { Text("Counted") },
            dismissButton = { TextButton(onClick = { editing = null }) { Text("Cancel") } },
            confirmButton = {
                TextButton(enabled = value.toBigDecimalOrNull() != null, onClick = {
                    scope.launch { runCatching { app.session.buying.countLine(id, CountLineReq(variantId = vid, counted = value)) }.onSuccess { editing = null; load() }.onFailure { message = app.session.messageOf(it) } }
                }) { Text("Save") }
            },
            text = { AnyloField("Quantity on the shelf", value, { value = it }, keyboard = KeyboardType.Decimal) })
    }
}
