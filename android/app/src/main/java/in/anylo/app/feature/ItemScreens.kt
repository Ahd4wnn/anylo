package `in`.anylo.app.feature

import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.AutoFixHigh
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import `in`.anylo.app.AppState
import `in`.anylo.app.core.AdjustReq
import `in`.anylo.app.core.CategoryDto
import `in`.anylo.app.core.Option
import `in`.anylo.app.core.ProductDto
import `in`.anylo.app.core.RateDto
import `in`.anylo.app.core.UnitDto
import `in`.anylo.app.core.VariantDto
import `in`.anylo.app.ui.Anylo
import `in`.anylo.app.ui.AnyloField
import `in`.anylo.app.ui.Card
import `in`.anylo.app.ui.ErrorBanner
import `in`.anylo.app.ui.PrimaryButton
import `in`.anylo.app.ui.SecondaryButton
import kotlinx.coroutines.launch
import kotlinx.serialization.builtins.ListSerializer
import java.io.File
import java.math.BigDecimal

/** Last catalogue fetched, kept as JSON so the list opens instantly and offline (Room is not needed for this). */
private object CatalogueCache {
    private fun file(ctx: Context) = File(ctx.filesDir, "catalogue.json")
    fun load(app: AppState, ctx: Context): List<ProductDto> = runCatching {
        app.session.json.decodeFromString(ListSerializer(ProductDto.serializer()), file(ctx).readText())
    }.getOrDefault(emptyList())
    fun save(app: AppState, ctx: Context, items: List<ProductDto>) {
        runCatching { file(ctx).writeText(app.session.json.encodeToString(ListSerializer(ProductDto.serializer()), items)) }
    }
}

/** Google's code scanner: no camera permission or camera code in our app. Calls back with the raw value. */
fun scanBarcode(ctx: Context, onCode: (String) -> Unit, onError: (String) -> Unit) {
    GmsBarcodeScanning.getClient(ctx).startScan()
        .addOnSuccessListener { it.rawValue?.let(onCode) }
        .addOnFailureListener { onError("Couldn't open the scanner on this phone.") }
}

private fun qty(s: String) = BigDecimal(s).stripTrailingZeros().toPlainString()
private fun isLow(v: VariantDto) = BigDecimal(v.reorderLevel) > BigDecimal.ZERO && BigDecimal(v.stockQty) <= BigDecimal(v.reorderLevel)

@Composable
fun ItemsScreen(app: AppState) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var editing by remember { mutableStateOf<String?>(null) } // product id, or "" for new
    var all by remember { mutableStateOf(CatalogueCache.load(app, ctx)) }
    var q by remember { mutableStateOf("") }
    var lowOnly by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val canManage = app.can("product.manage")

    suspend fun reload() {
        runCatching { app.session.catalogue.products(null).items }
            .onSuccess { all = it; CatalogueCache.save(app, ctx, it); error = null }
            .onFailure { error = if (all.isEmpty()) app.session.messageOf(it) else "Offline: showing the last saved list." }
    }
    LaunchedEffect(editing) { if (editing == null) reload() }

    editing?.let { id -> ProductEditScreen(app, id.ifEmpty { null }) { editing = null }; return }

    val shown = all.filter { p ->
        (q.isBlank() || p.name.contains(q, true) || p.variants.any { it.sku?.contains(q, true) == true || it.barcode == q.trim() }) &&
            (!lowOnly || p.variants.any(::isLow))
    }
    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().statusBarsPadding().padding(horizontal = 20.dp)) {
            Spacer(Modifier.height(20.dp))
            Text("Items", style = MaterialTheme.typography.headlineMedium)
            Text("${all.size} items", color = Anylo.colors.text2)
            Spacer(Modifier.height(12.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                AnyloField("Search", q, { q = it }, Modifier.weight(1f))
                IconButton(onClick = {
                    scanBarcode(ctx, { code ->
                        scope.launch {
                            runCatching { app.session.catalogue.lookup(code) }
                                .onSuccess { editing = it.product.id }
                                .onFailure { q = code; error = "No item has barcode $code." }
                        }
                    }, { error = it })
                }, modifier = Modifier.padding(top = 22.dp)) { Icon(Icons.Filled.QrCodeScanner, "Scan barcode") }
            }
            Row(Modifier.padding(vertical = 8.dp)) { FilterChip(selected = lowOnly, onClick = { lowOnly = !lowOnly }, label = { Text("Low stock") }) }
            ErrorBanner(error)
            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.weight(1f)) {
                items(shown, key = { it.id }) { p ->
                    val stock = p.variants.fold(BigDecimal.ZERO) { a, v -> a + BigDecimal(v.stockQty) }
                    val low = p.variants.any(::isLow)
                    Row(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Anylo.colors.surface)
                            .clickable { editing = p.id }.padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(p.name, fontWeight = FontWeight.Medium)
                            Text(listOfNotNull(p.categoryName, if (p.variants.size > 1) "${p.variants.size} variants" else p.variants.firstOrNull()?.sku).joinToString(" · "),
                                color = Anylo.colors.text2, style = MaterialTheme.typography.bodyMedium)
                            if (p.missingTaxInfo) Pill("Set GST", Modifier.padding(top = 4.dp))
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text("₹" + (p.variants.minOfOrNull { BigDecimal(it.salePrice) }?.stripTrailingZeros()?.toPlainString() ?: "0"), fontWeight = FontWeight.SemiBold)
                            if (p.trackStock) Text("${qty(stock.toPlainString())} ${p.unitCode.lowercase()}",
                                color = if (low) Anylo.colors.warning else Anylo.colors.text2, style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                }
            }
        }
        if (canManage) FloatingActionButton(onClick = { editing = "" }, containerColor = Anylo.colors.primary,
            modifier = Modifier.align(Alignment.BottomEnd).padding(20.dp)) { Icon(Icons.Filled.Add, "Add item", tint = Anylo.colors.onPrimary) }
    }
}

@Composable
fun ProductEditScreen(app: AppState, productId: String?, onDone: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val canManage = app.can("product.manage")
    var name by remember { mutableStateOf("") }
    var categoryId by remember { mutableStateOf<String?>(null) }
    var unit by remember { mutableStateOf("NOS") }
    var hsn by remember { mutableStateOf("") }
    var rateId by remember { mutableStateOf<String?>(null) }
    var track by remember { mutableStateOf(true) }
    val variants = remember { mutableStateListOf(VariantDto()) }
    var cats by remember { mutableStateOf(emptyList<CategoryDto>()) }
    var units by remember { mutableStateOf(emptyList<UnitDto>()) }
    var rates by remember { mutableStateOf(emptyList<RateDto>()) }
    var adjusting by remember { mutableStateOf<VariantDto?>(null) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    suspend fun load() {
        val c = app.session.catalogue
        runCatching { cats = c.categories(); units = c.units(); rates = c.rates() }
        if (productId != null) runCatching { c.product(productId) }.onSuccess { p ->
            name = p.name; categoryId = p.categoryId; unit = p.unitCode; hsn = p.hsnCode.orEmpty(); rateId = p.taxRateId; track = p.trackStock
            variants.clear(); variants.addAll(p.variants)
        }.onFailure { error = app.session.messageOf(it) }
    }
    LaunchedEffect(productId) { load() }

    Column(Modifier.fillMaxSize().background(Anylo.colors.bg).statusBarsPadding().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onDone) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") }
            Text(if (productId == null) "Add item" else name.ifBlank { "Item" }, style = MaterialTheme.typography.headlineMedium)
        }
        ErrorBanner(error)
        Card {
            AnyloField("Item name", name, { name = it }, enabled = canManage)
            Picker("Category", listOf(Option("", "No category")) + cats.map { Option(it.id, it.name) }, categoryId.orEmpty()) { categoryId = it.ifEmpty { null } }
            Picker("Sold in", units.map { Option(it.code, "${it.label} (${it.code})") }, unit) { unit = it }
            AnyloField("HSN code", hsn, { hsn = it.filter(Char::isDigit).take(8) }, keyboard = KeyboardType.Number, enabled = canManage)
            Picker("GST rate", listOf(Option("", "Not set")) + rates.map { Option(it.id, it.label) }, rateId.orEmpty()) { rateId = it.ifEmpty { null } }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Track stock", Modifier.weight(1f)); Switch(checked = track, onCheckedChange = { track = it }, enabled = canManage)
            }
        }
        variants.forEachIndexed { i, v ->
            Card {
                if (variants.size > 1) AnyloField("Variant name", v.name.orEmpty(), { variants[i] = v.copy(name = it) }, enabled = canManage)
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    AnyloField("Price ₹", v.salePrice.takeIf { it != "0" }.orEmpty(), { variants[i] = v.copy(salePrice = it.ifBlank { "0" }) }, Modifier.weight(1f), keyboard = KeyboardType.Decimal, enabled = canManage)
                    AnyloField("MRP ₹", v.mrp.orEmpty(), { variants[i] = v.copy(mrp = it.ifBlank { null }) }, Modifier.weight(1f), keyboard = KeyboardType.Decimal, enabled = canManage)
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    AnyloField("Barcode", v.barcode.orEmpty(), { variants[i] = v.copy(barcode = it.trim().ifBlank { null }) }, Modifier.weight(1f), enabled = canManage)
                    if (canManage) {
                        IconButton(onClick = { scanBarcode(ctx, { variants[i] = variants[i].copy(barcode = it) }, { error = it }) }, Modifier.padding(top = 22.dp)) { Icon(Icons.Filled.QrCodeScanner, "Scan barcode") }
                        IconButton(onClick = { scope.launch { runCatching { app.session.catalogue.generateBarcode().barcode }.onSuccess { variants[i] = variants[i].copy(barcode = it) } } }, Modifier.padding(top = 22.dp)) { Icon(Icons.Filled.AutoFixHigh, "Make a barcode") }
                    }
                }
                if (track && v.id == null) AnyloField("Opening stock", v.openingStock.orEmpty(), { variants[i] = v.copy(openingStock = it.ifBlank { null }) }, keyboard = KeyboardType.Decimal)
                if (track && v.id != null) TextButton(onClick = { adjusting = v }) {
                    Text("In stock: ${qty(v.stockQty)} · Adjust", color = if (isLow(v)) Anylo.colors.warning else Anylo.colors.primary, fontWeight = FontWeight.SemiBold)
                }
                if (variants.size > 1 && canManage) TextButton(onClick = { variants.removeAt(i) }) { Text("Remove variant", color = Anylo.colors.text2) }
            }
        }
        if (canManage) {
            SecondaryButton("Add variant (size / colour)", { variants.add(VariantDto(name = "")) }, Modifier.fillMaxWidth())
            PrimaryButton("Save", loading = busy, enabled = name.isNotBlank(), onClick = {
                scope.launch {
                    busy = true; error = null
                    val body = ProductDto(name = name.trim(), categoryId = categoryId, unitCode = unit, hsnCode = hsn.ifBlank { null },
                        taxRateId = rateId, trackStock = track, variants = variants.map { it.copy(stockQty = "0") })
                    runCatching { if (productId == null) app.session.catalogue.create(body) else app.session.catalogue.update(productId, body) }
                        .onSuccess { onDone() }.onFailure { error = app.session.messageOf(it) }
                    busy = false
                }
            })
        }
    }
    adjusting?.let { v -> AdjustDialog(app, v, onClose = { adjusting = null; scope.launch { load() } }) }
}

@Composable
private fun AdjustDialog(app: AppState, v: VariantDto, onClose: () -> Unit) {
    val scope = rememberCoroutineScope()
    var mode by remember { mutableStateOf("set") }
    var amount by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    AlertDialog(
        onDismissRequest = onClose, title = { Text("Stock: ${qty(v.stockQty)} now") },
        dismissButton = { TextButton(onClick = onClose) { Text("Cancel") } },
        confirmButton = {
            TextButton(enabled = amount.toBigDecimalOrNull() != null, onClick = {
                scope.launch {
                    runCatching { app.session.catalogue.adjust(AdjustReq(v.id!!, mode, amount)) }
                        .onSuccess { onClose() }.onFailure { error = app.session.messageOf(it) }
                }
            }) { Text("Save") }
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                ErrorBanner(error)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("set" to "Counted", "add" to "Add", "remove" to "Remove").forEach { (m, label) ->
                        FilterChip(selected = mode == m, onClick = { mode = m }, label = { Text(label) })
                    }
                }
                AnyloField(if (mode == "set") "Quantity you counted" else "Quantity", amount, { amount = it }, keyboard = KeyboardType.Decimal)
            }
        },
    )
}

