package `in`.anylo.app.feature

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.speech.RecognizerIntent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.PauseCircle
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Switch
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
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.imePadding
import androidx.compose.material.icons.automirrored.filled.ViewList
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material3.BottomSheetDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.SheetValue
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import `in`.anylo.app.AnyloApp
import `in`.anylo.app.AppState
import `in`.anylo.app.core.CartLine
import `in`.anylo.app.core.CustomItem
import `in`.anylo.app.core.Gstin
import `in`.anylo.app.core.HeldDto
import `in`.anylo.app.core.HeldReq
import `in`.anylo.app.core.Option
import `in`.anylo.app.core.PaymentReq
import `in`.anylo.app.core.ProductDto
import `in`.anylo.app.core.RateDto
import `in`.anylo.app.core.Receipt
import `in`.anylo.app.core.Shop
import `in`.anylo.app.core.VariantDto
import `in`.anylo.app.core.voiceScore
import `in`.anylo.app.print.PrinterController
import `in`.anylo.app.print.loadLogo
import `in`.anylo.app.print.money
import `in`.anylo.app.print.qrBitmap
import `in`.anylo.app.print.receiptBitmap
import `in`.anylo.app.print.upiUri
import `in`.anylo.app.ui.Anylo
import `in`.anylo.app.ui.AnyloField
import `in`.anylo.app.ui.ErrorBanner
import `in`.anylo.app.ui.PrimaryButton
import `in`.anylo.app.ui.SecondaryButton
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.ByteArrayOutputStream
import java.math.BigDecimal
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import java.util.UUID

private fun rupees(v: BigDecimal) = "₹" + money(v.setScale(2, java.math.RoundingMode.HALF_UP).toPlainString())
private fun dec(s: String) = s.toBigDecimalOrNull() ?: BigDecimal.ZERO
private fun inStock(p: ProductDto) = !p.trackStock || p.variants.any { dec(it.stockQty).signum() > 0 }

private fun lineOf(p: ProductDto, v: VariantDto) = CartLine(
    key = UUID.randomUUID().toString(), variantId = v.id, name = p.name, variantName = v.name, unit = p.unitCode,
    qty = "1", unitPrice = v.salePrice, salePrice = v.salePrice, mrp = v.mrp, rate = p.taxRate ?: "0", inclusive = p.priceIncludesTax,
)

/** Print through the remembered printer, then mark the bill handed over (it can't be edited afterwards). */
suspend fun printBill(app: AppState, printer: PrinterController, r: Receipt): Result<Unit> {
    val logo = loadLogo(r.shop.logoUrl)
    return printer.print { receiptBitmap(r, printer.paperDots, logo) }.onSuccess { runCatching { app.session.sales.handover(r.id) } }
}

suspend fun shareBill(app: AppState, ctx: Context, r: Receipt) {
    runCatching { app.session.sales.handover(r.id) }
    val text = "${r.shop.name}: ${r.title.lowercase()} ${r.number} for ₹${money(r.totals.grandTotal)}. View: ${r.publicUrl}"
    ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, text), "Share bill"))
}

@Composable
fun ReceiptActions(app: AppState, r: Receipt, onMessage: (String) -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val printer = (ctx.applicationContext as AnyloApp).printer
    var printing by remember { mutableStateOf(false) }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        SecondaryButton(if (printing) "Printing…" else "Print", {
            if (!printing) scope.launch { printing = true; printBill(app, printer, r).onSuccess { onMessage("Printed") }.onFailure { onMessage(it.message ?: "Couldn't print.") }; printing = false }
        }, Modifier.weight(1f))
        SecondaryButton("PDF", { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(r.publicUrl))) }, Modifier.weight(1f))
        SecondaryButton("Share", { scope.launch { shareBill(app, ctx, r) } }, Modifier.weight(1f))
    }
}

@Composable
fun PosScreen(app: AppState) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val cart = (ctx.applicationContext as AnyloApp).cart
    val canEditPrice = app.can("invoice.edit") // owners and managers, same rule as web
    var products by remember { mutableStateOf(CatalogueCache.load(app, ctx)) }
    var shop by remember { mutableStateOf<Shop?>(null) }
    var rates by remember { mutableStateOf(emptyList<RateDto>()) }
    var q by remember { mutableStateOf("") }
    var category by remember { mutableStateOf<String?>(null) }
    var showCart by remember { mutableStateOf(false) }
    var picking by remember { mutableStateOf<ProductDto?>(null) }
    var customOpen by remember { mutableStateOf(false) }
    var heldOpen by remember { mutableStateOf(false) }
    // Amount fixed when the sheet opens: saving clears the cart, and the success view must outlive it.
    var paying by remember { mutableStateOf<BigDecimal?>(null) }
    var message by remember { mutableStateOf<String?>(null) }
    val prefs = remember { ctx.getSharedPreferences("anylo_pos", Context.MODE_PRIVATE) }
    var view by remember { mutableStateOf(runCatching { ItemView.valueOf(prefs.getString("view", null)!!) }.getOrDefault(ItemView.Grid)) }
    var viewMenu by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        runCatching { app.session.catalogue.products(null).items }.onSuccess { products = it; CatalogueCache.save(app, ctx, it) }
        runCatching { shop = app.session.api.shop() }
        runCatching { rates = app.session.catalogue.rates() }
    }
    LaunchedEffect(message) { if (message != null) { kotlinx.coroutines.delay(5000); message = null } }

    fun add(p: ProductDto) { if (p.variants.size > 1) picking = p else p.variants.firstOrNull()?.let { cart.add(lineOf(p, it)); message = "Added ${p.name}" } }

    /** Barcode from the camera, a USB/Bluetooth scanner (types + Enter) or the search box. */
    fun addCode(code: String) {
        val local = products.firstNotNullOfOrNull { p -> p.variants.find { it.barcode == code || it.sku.equals(code, true) }?.let { p to it } }
        if (local != null) { cart.add(lineOf(local.first, local.second)); message = "Added ${local.first.name}"; q = ""; return }
        scope.launch {
            runCatching { app.session.catalogue.lookup(code) }
                .onSuccess { cart.add(lineOf(it.product, it.variant)); message = "Added ${it.product.name}"; q = "" }
                .onFailure { message = "No item has the code $code." }
        }
    }

    val voice = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { res ->
        val heard = res.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS).orEmpty()
        val best = products.flatMap { p -> heard.map { p to voiceScore(it, p.name) } }.maxByOrNull { it.second }
        if (best != null && best.second >= 0.6) add(best.first) else q = heard.firstOrNull().orEmpty()
    }
    val snap = rememberLauncherForActivityResult(ActivityResultContracts.TakePicturePreview()) { bmp: Bitmap? ->
        bmp ?: return@rememberLauncherForActivityResult
        scope.launch {
            val jpeg = ByteArrayOutputStream().also { bmp.compress(Bitmap.CompressFormat.JPEG, 90, it) }.toByteArray()
            runCatching { app.session.catalogue.snap(MultipartBody.Part.createFormData("file", "snap.jpg", jpeg.toRequestBody("image/jpeg".toMediaType()))) }
                .onSuccess { r -> q = r.matches.firstOrNull()?.name ?: r.identifiedName; message = if (r.matches.isEmpty()) "Looks like ${r.identifiedName}. Not in your items yet." else "Looks like ${r.identifiedName}" }
                .onFailure { message = app.session.messageOf(it) }
        }
    }

    val scheme = shop?.tax?.scheme ?: "regular"
    val totals = cart.totals(scheme)
    val count = cart.state.lines.size

    if (showCart) {
        CartView(app, scheme, canEditPrice, onBack = { showCart = false }, onPay = { paying = totals?.grandTotal }, onHeld = { heldOpen = true }, onMessage = { message = it })
    } else Column(Modifier.fillMaxSize().statusBarsPadding()) {
        Row(Modifier.padding(start = 16.dp, end = 8.dp, top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(
                q, { q = it }, Modifier.weight(1f).onPreviewKeyEvent {
                    // Hardware scanners end with Enter; treat it as "add this code".
                    if (it.key == Key.Enter && it.type == KeyEventType.KeyUp && q.isNotBlank()) { addCode(q.trim()); true } else false
                },
                placeholder = { Text("Search or scan") }, singleLine = true, shape = RoundedCornerShape(12.dp),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { if (q.isNotBlank()) addCode(q.trim()) }),
                colors = OutlinedTextFieldDefaults.colors(focusedContainerColor = Anylo.colors.surface, unfocusedContainerColor = Anylo.colors.surface,
                    focusedBorderColor = Anylo.colors.primary, unfocusedBorderColor = Anylo.colors.border),
            )
            IconButton(onClick = { scanBarcode(ctx, ::addCode) { message = it } }) { Icon(Icons.Filled.QrCodeScanner, "Scan barcode") }
            IconButton(onClick = {
                runCatching { voice.launch(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                    .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-IN").putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)) }
                    .onFailure { message = "Voice search isn't available on this phone." }
            }) { Icon(Icons.Filled.Mic, "Search by voice") }
            if (app.can("product.snap")) IconButton(onClick = { runCatching { snap.launch(null) }.onFailure { message = "Couldn't open the camera." } }) { Icon(Icons.Filled.CameraAlt, "Snap and find") }
        }
        val cats = products.mapNotNull { it.categoryName }.distinct().sorted()
        Row(verticalAlignment = Alignment.CenterVertically) {
        LazyRow(Modifier.weight(1f).padding(vertical = 8.dp), contentPadding = androidx.compose.foundation.layout.PaddingValues(start = 16.dp, end = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            item { FilterChip(selected = category == null, onClick = { category = null }, label = { Text("All") }) }
            items(cats) { c -> FilterChip(selected = category == c, onClick = { category = if (category == c) null else c }, label = { Text(c) }) }
            item { FilterChip(selected = false, onClick = { customOpen = true }, label = { Text("+ Custom item") }) }
        }
            Box {
                IconButton(onClick = { viewMenu = true }, Modifier.padding(end = 8.dp)) { Icon(view.icon, "Change view: ${view.label}") }
                DropdownMenu(expanded = viewMenu, onDismissRequest = { viewMenu = false }) {
                    ItemView.entries.forEach { v ->
                        DropdownMenuItem(text = { Text(v.label, fontWeight = if (v == view) FontWeight.SemiBold else FontWeight.Normal) },
                            leadingIcon = { Icon(v.icon, null, tint = if (v == view) Anylo.colors.primary else Anylo.colors.text2) },
                            onClick = { view = v; viewMenu = false; prefs.edit().putString("view", v.name).apply() })
                    }
                }
            }
        }
        val shown = products.filter { p ->
            (category == null || p.categoryName == category) &&
                (q.isBlank() || p.name.contains(q, true) || p.variants.any { it.barcode == q.trim() || it.sku?.contains(q, true) == true })
        }
        LazyVerticalGrid(GridCells.Fixed(view.columns), Modifier.weight(1f), contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(shown, key = { it.id }) { p -> ItemTile(p, view) { add(p) } }
        }
        message?.let { Text(it, Modifier.fillMaxWidth().background(Anylo.colors.tint).padding(12.dp), textAlign = TextAlign.Center) }
        Row(Modifier.fillMaxWidth().background(Anylo.colors.surface).padding(12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            IconButton(onClick = { heldOpen = true }) { Icon(Icons.Filled.PauseCircle, "Held bills") }
            PrimaryButton(if (count == 0) "Cart is empty" else "$count item${if (count == 1) "" else "s"} · ${totals?.let { rupees(it.grandTotal) } ?: "…"}",
                { showCart = true }, Modifier.weight(1f), enabled = count > 0)
        }
    }

    picking?.let { p ->
        AlertDialog(onDismissRequest = { picking = null }, confirmButton = {}, dismissButton = { TextButton(onClick = { picking = null }) { Text("Cancel") } },
            title = { Text(p.name) },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    p.variants.forEach { v ->
                        Row(Modifier.fillMaxWidth().clickable { cart.add(lineOf(p, v)); picking = null; message = "Added ${p.name}" }.padding(vertical = 14.dp)) {
                            Text(v.name ?: "Default", Modifier.weight(1f)); Text(rupees(dec(v.salePrice)), fontWeight = FontWeight.SemiBold)
                        }
                    }
                }
            })
    }
    if (customOpen) CustomItemDialog(rates, scheme == "regular", onClose = { customOpen = false }) { cart.add(it); message = "Added ${it.name}" }
    if (heldOpen) HeldDialog(app, onClose = { heldOpen = false }, onMessage = { message = it })
    paying?.let { amount ->
        PaymentDialog(app, shop, amount, onClose = { paying = null; if (cart.state.lines.isEmpty()) showCart = false }) { r ->
            paying = null; showCart = false
            val due = dec(r.totals.dueTotal)
            message = "Saved ${r.number} · ${rupees(dec(r.totals.grandTotal))}" + if (due.signum() > 0) " · Due ${rupees(due)}" else ""
            val printer = (ctx.applicationContext as AnyloApp).printer
            if (printer.rememberedMac != null) scope.launch { printBill(app, printer, r).onFailure { message = "Saved ${r.number}. Couldn't print: ${it.message}" } }
        }
    }
}

@Composable
private fun CustomItemDialog(rates: List<RateDto>, needsRate: Boolean, onClose: () -> Unit, onAdd: (CartLine) -> Unit) {
    var name by remember { mutableStateOf("") }
    var price by remember { mutableStateOf("") }
    var rateId by remember { mutableStateOf("") }
    val rate = rates.find { it.id == rateId }
    val ok = name.isNotBlank() && dec(price).signum() > 0 && (!needsRate || rate != null)
    AlertDialog(onDismissRequest = onClose, title = { Text("Custom item") },
        dismissButton = { TextButton(onClick = onClose) { Text("Cancel") } },
        confirmButton = {
            TextButton(enabled = ok, onClick = {
                onAdd(CartLine(UUID.randomUUID().toString(), custom = CustomItem(name.trim(), rate?.id), name = name.trim(), unit = "NOS", qty = "1",
                    unitPrice = price, salePrice = price, rate = rate?.rate ?: "0", inclusive = true))
                onClose()
            }) { Text("Add") }
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                AnyloField("Name", name, { name = it })
                AnyloField("Price ₹ (incl. GST)", price, { price = it }, keyboard = KeyboardType.Decimal)
                if (needsRate) Picker("GST rate", listOf(Option("", "Choose")) + rates.map { Option(it.id, it.label) }, rateId) { rateId = it }
                Text("Not saved to your items.", color = Anylo.colors.text2, style = MaterialTheme.typography.bodySmall)
            }
        })
}

@Composable
private fun CartView(app: AppState, scheme: String, canEditPrice: Boolean, onBack: () -> Unit, onPay: () -> Unit, onHeld: () -> Unit, onMessage: (String) -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val cart = (ctx.applicationContext as AnyloApp).cart
    val s = cart.state
    val totals = cart.totals(scheme)
    var customerOpen by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().statusBarsPadding()) {
        Row(Modifier.padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back to items") }
            Text("Bill", style = MaterialTheme.typography.headlineMedium, modifier = Modifier.weight(1f))
            TextButton(onClick = {
                scope.launch {
                    val label = s.customer.name.ifBlank { s.customer.phone }.ifBlank { "Bill " + LocalTime.now().format(DateTimeFormatter.ofPattern("hh:mm a")) }
                    runCatching { app.session.sales.hold(HeldReq(label, s)) }
                        .onSuccess { cart.clear(); onMessage("Held: $label"); onBack() }.onFailure { onMessage(app.session.messageOf(it)) }
                }
            }) { Text("Hold") }
            TextButton(onClick = onHeld) { Text("Held bills") }
        }
        LazyColumn(Modifier.weight(1f).padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (s.lines.isEmpty()) item { Text("No items on this bill yet.", Modifier.fillMaxWidth().padding(vertical = 32.dp), color = Anylo.colors.text2, textAlign = TextAlign.Center) }
            items(s.lines, key = { it.key }) { l ->
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Anylo.colors.surface).padding(12.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(if (l.variantName != null) "${l.name} (${l.variantName})" else l.name, Modifier.weight(1f), fontWeight = FontWeight.Medium)
                        IconButton(onClick = { cart.remove(l.key) }) { Icon(Icons.Filled.Delete, "Remove ${l.name}", tint = Anylo.colors.text2) }
                    }
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        IconButton(onClick = {
                            val n = dec(l.qty) - BigDecimal.ONE
                            if (n.signum() <= 0) cart.remove(l.key) else cart.setLine(l.key) { it.copy(qty = n.toPlainString()) }
                        }) { Icon(Icons.Filled.Remove, "Less") }
                        SmallField(l.qty, { v -> cart.setLine(l.key) { it.copy(qty = v) } }, "Quantity", Modifier.width(76.dp))
                        IconButton(onClick = { cart.setLine(l.key) { it.copy(qty = (dec(it.qty) + BigDecimal.ONE).toPlainString()) } }) { Icon(Icons.Filled.Add, "More") }
                        Text(l.unit.lowercase(), color = Anylo.colors.text2)
                        Spacer(Modifier.weight(1f))
                        if (canEditPrice || l.custom != null) SmallField(l.unitPrice, { v -> cart.setLine(l.key) { it.copy(unitPrice = v) } }, "Price", Modifier.width(100.dp))
                        else Text(rupees(dec(l.unitPrice)), fontWeight = FontWeight.SemiBold)
                    }
                    Text(rupees(dec(l.qty) * dec(l.unitPrice)), Modifier.align(Alignment.End), fontWeight = FontWeight.SemiBold)
                }
            }
            item {
                OutlinedButton(onClick = onBack, Modifier.fillMaxWidth().height(52.dp), shape = RoundedCornerShape(14.dp)) {
                    Icon(Icons.Filled.Add, null); Spacer(Modifier.width(8.dp)); Text("Add more items", fontWeight = FontWeight.SemiBold)
                }
            }
        }
        Column(Modifier.fillMaxWidth().background(Anylo.colors.surface).padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            val c = s.customer
            Text(if (c.phone.isBlank() && c.name.isBlank()) "Add customer (optional)" else listOf(c.name, c.phone).filter { it.isNotBlank() }.joinToString(" · "),
                Modifier.fillMaxWidth().clickable { customerOpen = true }.padding(vertical = 6.dp), color = Anylo.colors.primary, fontWeight = FontWeight.SemiBold)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Discount", Modifier.weight(1f))
                FilterChip(selected = s.discountType == "flat", onClick = { cart.update { it.copy(discountType = "flat") } }, label = { Text("₹") })
                FilterChip(selected = s.discountType == "percent", onClick = { cart.update { it.copy(discountType = "percent") } }, label = { Text("%") })
                SmallField(s.discountValue, { v -> cart.update { it.copy(discountValue = v) } }, "Discount", Modifier.width(90.dp))
            }
            totals?.let { t ->
                if (scheme == "regular") Row { Text("GST", Modifier.weight(1f), color = Anylo.colors.text2); Text(rupees(t.cgstTotal + t.sgstTotal + t.igstTotal + t.cessTotal), color = Anylo.colors.text2) }
                if (t.discountTotal.signum() > 0) Row { Text("Discount", Modifier.weight(1f), color = Anylo.colors.text2); Text("−" + rupees(t.discountTotal), color = Anylo.colors.text2) }
            } ?: if (s.lines.isNotEmpty()) ErrorBanner("Check the quantities, prices and discount.") else Unit
            PrimaryButton("Pay ${totals?.let { rupees(it.grandTotal) } ?: ""}", onPay, enabled = totals != null && totals.grandTotal.signum() > 0)
        }
    }
    if (customerOpen) CustomerDialog(app) { customerOpen = false }
}

@Composable
private fun SmallField(value: String, onChange: (String) -> Unit, label: String, modifier: Modifier) {
    OutlinedTextField(value, { v -> onChange(v.filter { it.isDigit() || it == '.' }) }, modifier.semantics { contentDescription = label },
        singleLine = true, shape = RoundedCornerShape(10.dp), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
        textStyle = MaterialTheme.typography.bodyLarge, placeholder = { Text("0") },
        colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Anylo.colors.primary, unfocusedBorderColor = Anylo.colors.border),
    )
}

@Composable
private fun CustomerDialog(app: AppState, onClose: () -> Unit) {
    val cart = (LocalContext.current.applicationContext as AnyloApp).cart
    val s = cart.state
    var phone by remember { mutableStateOf(s.customer.phone) }
    var name by remember { mutableStateOf(s.customer.name) }
    var b2b by remember { mutableStateOf(s.b2b) }
    var gstin by remember { mutableStateOf(s.customer.gstin) }
    var address by remember { mutableStateOf(s.customer.address) }
    val phoneOk = phone.isBlank() || Regex("^[6-9]\\d{9}$").matches(phone)
    val gstinOk = !b2b || gstin.isBlank() || Gstin.isValid(gstin)
    AlertDialog(onDismissRequest = onClose, title = { Text("Customer") },
        dismissButton = { TextButton(onClick = onClose) { Text("Cancel") } },
        confirmButton = {
            TextButton(enabled = phoneOk && gstinOk, onClick = {
                cart.update { it.copy(customer = it.customer.copy(phone = phone, name = name.trim(), gstin = gstin, address = address.trim()), b2b = b2b) }
                onClose()
            }) { Text("Save") }
        },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                AnyloField("Mobile", phone, { phone = it.filter(Char::isDigit).take(10) }, keyboard = KeyboardType.Phone,
                    error = if (phoneOk || phone.length < 10) null else "Enter a 10-digit mobile number.", hint = "First 5 digits find returning customers.")
                if (phone.length < 10 || name.isBlank()) ReturningCustomers(app, phone) { m ->
                    phone = m.phone.orEmpty(); name = m.name.orEmpty(); gstin = m.gstin.orEmpty(); address = m.address.orEmpty(); b2b = m.gstin != null
                }
                AnyloField("Name", name, { name = it })
                Row(verticalAlignment = Alignment.CenterVertically) { Text("Business buyer (GSTIN)", Modifier.weight(1f)); Switch(b2b, { b2b = it }) }
                if (b2b) {
                    AnyloField("GSTIN", gstin, { gstin = it.uppercase().take(15) }, error = if (gstinOk) null else "This GSTIN doesn't look right.")
                    AnyloField("Address", address, { address = it })
                }
            }
        })
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun HeldDialog(app: AppState, onClose: () -> Unit, onMessage: (String) -> Unit) {
    val scope = rememberCoroutineScope()
    val cart = (LocalContext.current.applicationContext as AnyloApp).cart
    var held by remember { mutableStateOf<List<HeldDto>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) { runCatching { app.session.sales.held() }.onSuccess { held = it }.onFailure { error = app.session.messageOf(it) } }
    // Same bottom-sheet pattern as payment: swipe down or the close button dismisses it.
    val sheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val close: () -> Unit = { scope.launch { sheet.hide() }.invokeOnCompletion { onClose() } }
    ModalBottomSheet(onDismissRequest = onClose, sheetState = sheet, containerColor = Anylo.colors.bg,
        dragHandle = { BottomSheetDefaults.DragHandle(color = Anylo.colors.border) }) {
        Row(Modifier.fillMaxWidth().padding(start = 20.dp, end = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("Held bills", style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
            IconButton(onClick = close) { Icon(Icons.Filled.Close, "Close") }
        }
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(start = 20.dp, end = 20.dp, top = 8.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)) {
            ErrorBanner(error)
            if (held?.isEmpty() == true) Text("No held bills.", Modifier.fillMaxWidth().padding(vertical = 24.dp), color = Anylo.colors.text2, textAlign = TextAlign.Center)
            held?.forEach { h ->
                val n = h.payload.lines.size
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Anylo.colors.surface)
                    .border(1.dp, Anylo.colors.border, RoundedCornerShape(14.dp)).clickable {
                        scope.launch {
                            // Never lose the bill on screen: park it first.
                            if (cart.state.lines.isNotEmpty()) runCatching { app.session.sales.hold(HeldReq("Parked " + LocalTime.now().format(DateTimeFormatter.ofPattern("hh:mm a")), cart.state)) }
                                .onFailure { error = app.session.messageOf(it); return@launch }
                            cart.load(h.payload)
                            runCatching { app.session.sales.unhold(h.id) }
                            onMessage("Resumed ${h.label}"); close()
                        }
                    }.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(h.label, fontWeight = FontWeight.SemiBold)
                        h.createdByName?.let { Text("Held by $it", color = Anylo.colors.text2, style = MaterialTheme.typography.bodySmall) }
                    }
                    Text("$n item${if (n == 1) "" else "s"}", color = Anylo.colors.text2)
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PaymentDialog(app: AppState, shop: Shop?, total: BigDecimal, onClose: () -> Unit, onSaved: (Receipt) -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val appCtx = ctx.applicationContext as AnyloApp
    val cart = appCtx.cart
    var mode by remember { mutableStateOf("cash") }
    var received by remember { mutableStateOf("") }
    var split by remember { mutableStateOf(mapOf("cash" to "", "upi" to "", "card" to "")) }
    var ref by remember { mutableStateOf("") }
    var pin by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var done by remember { mutableStateOf<Receipt?>(null) }
    LaunchedEffect(Unit) { if (cart.idempotencyKey == null) cart.idempotencyKey = UUID.randomUUID().toString() }

    val payments = when (mode) {
        "due" -> emptyList()
        "split" -> split.filter { dec(it.value).signum() > 0 }.map { PaymentReq(it.key, dec(it.value).setScale(2, java.math.RoundingMode.HALF_UP).toPlainString()) }
        else -> listOf(PaymentReq(mode, total.toPlainString(), ref.ifBlank { null }?.takeIf { mode != "cash" }))
    }
    val paid = payments.fold(BigDecimal.ZERO) { a, p -> a + dec(p.amount) }
    val due = (total - paid).max(BigDecimal.ZERO)
    val over = paid > total
    val hasPhone = Regex("^[6-9]\\d{9}$").matches(cart.state.customer.phone)
    val upiAmount = when (mode) { "upi" -> total; "split" -> dec(split["upi"].orEmpty()); else -> BigDecimal.ZERO }

    fun submit(approval: String?) = scope.launch {
        busy = true; error = null
        runCatching { app.session.sales.checkout(cart.checkoutBody(payments, cart.idempotencyKey!!, approval)) }
            .onSuccess { r -> done = r; cart.clear() }
            .onFailure {
                val (code, msg) = app.session.errorOf(it)
                if (code == "invoice.approval_required") pin = "" else error = if (it is java.io.IOException) "Couldn't save the bill. Check your connection and try again; it won't be saved twice." else msg
            }
        busy = false
    }

    // Slides up from the bottom; swipe down or the close button dismisses it, except while the bill is being saved.
    val sheet = rememberModalBottomSheetState(skipPartiallyExpanded = true, confirmValueChange = { it != SheetValue.Hidden || !busy })
    val close: () -> Unit = { scope.launch { sheet.hide() }.invokeOnCompletion { onClose() } }
    // A saved bill closes the sheet straight away: the counter is ready for the next customer.
    LaunchedEffect(done) { done?.let { sheet.hide(); onSaved(it) } }
    ModalBottomSheet(onDismissRequest = onClose, sheetState = sheet, containerColor = Anylo.colors.bg,
        dragHandle = { BottomSheetDefaults.DragHandle(color = Anylo.colors.border) }) {
        Row(Modifier.fillMaxWidth().padding(start = 20.dp, end = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(when { done != null -> "Bill saved"; pin != null -> "Approval needed"; else -> "Pay ${rupees(total)}" },
                style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
            IconButton(onClick = close, enabled = !busy) { Icon(Icons.Filled.Close, "Close") }
        }
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).imePadding().padding(start = 20.dp, end = 20.dp, top = 8.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)) {
            val r = done
            when {
                r != null -> Text("Saved ${r.number}", color = Anylo.colors.success, fontWeight = FontWeight.SemiBold)
                pin != null -> {
                    Text("This discount is above your limit. Ask the owner or manager to enter their PIN.", color = Anylo.colors.text2)
                    ErrorBanner(error)
                    AnyloField("Manager PIN", pin.orEmpty(), { pin = it.filter(Char::isDigit).take(6) }, password = true, keyboard = KeyboardType.NumberPassword)
                    PrimaryButton("Approve and save", { submit(pin) }, loading = busy, enabled = (pin?.length ?: 0) >= 4)
                }
                else -> {
                    // Equal-width segments: five chips don't fit a phone and "Due" wrapped one letter per line.
                    Row(Modifier.fillMaxWidth().selectableGroup(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        listOf("cash" to "Cash", "upi" to "UPI", "card" to "Card", "split" to "Split", "due" to "Due").forEach { (m, label) ->
                            val on = mode == m
                            Box(Modifier.weight(1f).height(44.dp).clip(RoundedCornerShape(10.dp))
                                .background(if (on) Anylo.colors.primarySoft else Anylo.colors.surface)
                                .border(1.dp, if (on) Anylo.colors.primary else Anylo.colors.border, RoundedCornerShape(10.dp))
                                .selectable(selected = on, role = Role.RadioButton, onClick = { mode = m }), contentAlignment = Alignment.Center) {
                                Text(label, maxLines = 1, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium,
                                    color = if (on) Anylo.colors.onPrimarySoft else Anylo.colors.text)
                            }
                        }
                    }
                    ErrorBanner(error)
                    if (mode == "cash") {
                        AnyloField("Cash received (optional)", received, { received = it }, keyboard = KeyboardType.Decimal)
                        if (dec(received) > total) Text("Give back ${rupees(dec(received) - total)}", style = MaterialTheme.typography.titleMedium, color = Anylo.colors.success)
                    }
                    if (mode == "split") {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            listOf("cash", "upi").forEach { k -> AnyloField(k.uppercase(), split[k].orEmpty(), { v -> split = split + (k to v) }, Modifier.weight(1f), keyboard = KeyboardType.Decimal) }
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.Bottom) {
                            AnyloField("CARD", split["card"].orEmpty(), { v -> split = split + ("card" to v) }, Modifier.weight(1f), keyboard = KeyboardType.Decimal)
                            // Whatever isn't paid now is the due; filled in, never typed, so the parts always add up to the bill.
                            Column(Modifier.weight(1f)) {
                                Text("DUE", style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
                                Spacer(Modifier.height(6.dp))
                                Text(money(due.setScale(2, java.math.RoundingMode.HALF_UP).toPlainString()),
                                    Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(if (due.signum() > 0) Anylo.colors.warningSoft else Anylo.colors.surface2).padding(16.dp),
                                    color = if (due.signum() > 0) Anylo.colors.warning else Anylo.colors.text3, fontWeight = FontWeight.SemiBold)
                            }
                        }
                    }
                    if ((mode == "due" || mode == "split") && due.signum() > 0)
                        AnyloField("Customer mobile (needed for due)", cart.state.customer.phone,
                            { v -> cart.update { it.copy(customer = it.customer.copy(phone = v.filter(Char::isDigit).take(10))) } }, keyboard = KeyboardType.Phone)
                    if (mode == "upi" || mode == "card") AnyloField(if (mode == "upi") "UPI reference (optional)" else "Card last 4 / approval code (optional)", ref, { ref = it })
                    if (upiAmount.signum() > 0) {
                        val vpa = shop?.upi
                        if (vpa.isNullOrBlank()) Text("Add your UPI ID in Settings → Business to show a payment QR here.", color = Anylo.colors.warning)
                        else {
                            val amount = upiAmount.setScale(2, java.math.RoundingMode.HALF_UP).toPlainString()
                            val qr = remember(vpa, amount) { qrBitmap(upiUri(vpa, shop.upiPayeeName ?: shop.name, amount, "Anylo bill"), 560).asImageBitmap() }
                            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Anylo.colors.tint).padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                                Image(qr, "UPI payment QR code", Modifier.size(220.dp).clip(RoundedCornerShape(8.dp)))
                                Spacer(Modifier.height(8.dp))
                                Text("Customer scans with any UPI app · ₹${money(amount)} to $vpa", color = Anylo.colors.text2, textAlign = TextAlign.Center)
                            }
                        }
                    }
                    if ((mode == "due" || mode == "split") && due.signum() > 0)
                        Text("${rupees(due)} will be kept as due" + if (hasPhone) " on ${cart.state.customer.phone}" else ". Enter the customer's mobile number above.",
                            color = if (hasPhone) Anylo.colors.warning else Anylo.colors.danger)
                    if (over) Text("Payments are more than the bill. Enter the bill amount; change is shown separately.", color = Anylo.colors.danger)
                    PrimaryButton(if (due.signum() > 0 && mode != "cash") "Save with ${rupees(due)} due" else "Save bill", { submit(null) },
                        loading = busy, enabled = !over && (due.signum() == 0 || hasPhone))
                }
            }
        }
    }
}

enum class ItemView(val label: String, val columns: Int, val icon: ImageVector) {
    Grid("Grid", 3, Icons.Filled.Apps), Tiles("Large tiles", 2, Icons.Filled.GridView), List("List", 1, Icons.AutoMirrored.Filled.ViewList),
}

/** Every tile has the same fixed shape (a square, or a fixed-height row), whatever its text or stock line. */
@Composable
private fun ItemTile(p: ProductDto, view: ItemView, onClick: () -> Unit) {
    val price = rupees(p.variants.minOfOrNull { dec(it.salePrice) } ?: BigDecimal.ZERO)
    val out = !inStock(p)
    val base = Modifier.clip(RoundedCornerShape(14.dp)).background(Anylo.colors.surface)
        .border(1.dp, Anylo.colors.border, RoundedCornerShape(14.dp)).clickable(onClick = onClick)
    if (view == ItemView.List) {
        Row(base.fillMaxWidth().height(68.dp).padding(horizontal = 14.dp), verticalAlignment = Alignment.CenterVertically) {
            Initial(p.name, 40)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(p.name, fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(if (out) "Out of stock" else p.categoryName.orEmpty(), color = if (out) Anylo.colors.warning else Anylo.colors.text2,
                    style = MaterialTheme.typography.bodySmall, maxLines = 1)
            }
            Text(price, fontWeight = FontWeight.SemiBold)
        }
        return
    }
    val big = view == ItemView.Tiles
    Column(base.fillMaxWidth().aspectRatio(1f).padding(if (big) 14.dp else 10.dp)) {
        // The 3-across grid has no room for the badge once the phone's text size is above 100%.
        if (big) Initial(p.name, 40)
        Spacer(Modifier.weight(1f))
        Text(p.name, fontWeight = FontWeight.Medium, maxLines = 2, minLines = 2, overflow = TextOverflow.Ellipsis,
            style = if (big) MaterialTheme.typography.bodyLarge else MaterialTheme.typography.bodySmall)
        Text(price, fontWeight = FontWeight.SemiBold, maxLines = 1, style = if (big) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodyMedium)
        // Always reserve the stock line so every tile lays out identically.
        Text(if (out) "Out of stock" else " ", color = Anylo.colors.warning, style = MaterialTheme.typography.labelSmall, maxLines = 1)
    }
}

@Composable
private fun Initial(name: String, size: Int) {
    Box(Modifier.size(size.dp).clip(RoundedCornerShape((size * 0.3).dp)).background(Anylo.colors.primarySoft), contentAlignment = Alignment.Center) {
        Text(name.trim().take(1).uppercase(), color = Anylo.colors.onPrimarySoft, fontWeight = FontWeight.Bold,
            style = if (size >= 40) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodyMedium)
    }
}
