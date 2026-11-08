package `in`.anylo.app.feature

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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Inventory2
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import `in`.anylo.app.AppState
import `in`.anylo.app.core.Gstin
import `in`.anylo.app.core.Me
import `in`.anylo.app.core.Shop
import `in`.anylo.app.core.ShopPatch
import `in`.anylo.app.core.Staff
import `in`.anylo.app.core.StaffPatch
import `in`.anylo.app.core.StaffReq
import `in`.anylo.app.core.TaxReq
import `in`.anylo.app.ui.Anylo
import `in`.anylo.app.ui.AnyloField
import `in`.anylo.app.ui.Card
import `in`.anylo.app.ui.ErrorBanner
import `in`.anylo.app.ui.Logo
import `in`.anylo.app.ui.PrimaryButton
import `in`.anylo.app.ui.SecondaryButton
import kotlinx.coroutines.launch

@Composable
fun BusinessCard(app: AppState, shop: Shop, button: String, onSaved: (Shop) -> Unit) {
    val scope = rememberCoroutineScope()
    var name by remember { mutableStateOf(shop.name) }
    var phone by remember { mutableStateOf(shop.phone.orEmpty()) }
    var address by remember { mutableStateOf(shop.address.orEmpty()) }
    var city by remember { mutableStateOf(shop.city.orEmpty()) }
    var pin by remember { mutableStateOf(shop.pincode.orEmpty()) }
    var upi by remember { mutableStateOf(shop.upi.orEmpty()) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val owner = app.can("shop.payment_details")
    Card {
        Text("Business details", style = MaterialTheme.typography.titleLarge)
        ErrorBanner(error)
        AnyloField("Shop name", name, { name = it })
        AnyloField("Shop phone", phone, { phone = it.filter(Char::isDigit).take(10) }, keyboard = KeyboardType.Phone)
        AnyloField("Address", address, { address = it })
        AnyloField("City", city, { city = it })
        AnyloField("PIN code", pin, { pin = it.filter(Char::isDigit).take(6) }, keyboard = KeyboardType.Number)
        AnyloField("UPI ID", upi, { upi = it.trim() }, enabled = owner, hint = if (owner) "Used for the payment QR on bills." else "Only the owner can change this.")
        Text("State: ${shop.stateName}", color = Anylo.colors.text2)
        PrimaryButton(button, loading = busy, enabled = address.isNotBlank() && pin.length == 6 && city.isNotBlank(), onClick = {
            scope.launch {
                busy = true; error = null
                runCatching {
                    app.session.api.patchShop(ShopPatch(name.trim(), phone.ifBlank { null }, address.trim(), city.trim(), pin, if (owner) upi.ifBlank { null } else null))
                }.onSuccess(onSaved).onFailure { error = app.session.messageOf(it) }
                busy = false
            }
        })
    }
}

@Composable
fun GstCard(app: AppState, shop: Shop, button: String, onSaved: (Shop) -> Unit) {
    val scope = rememberCoroutineScope()
    var scheme by remember { mutableStateOf(shop.tax.scheme) }
    var gstin by remember { mutableStateOf(shop.tax.gstin.orEmpty()) }
    var legal by remember { mutableStateOf(shop.tax.legalName.orEmpty()) }
    var inclusive by remember { mutableStateOf(shop.tax.pricesIncludeTax) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val canEdit = app.can("shop.tax_profile")
    val needs = scheme != "unregistered"
    val valid = !needs || Gstin.isValid(gstin)
    Card {
        Text("GST", style = MaterialTheme.typography.titleLarge)
        if (!canEdit) Text("Only the owner can change GST settings.", color = Anylo.colors.text2)
        ErrorBanner(error)
        listOf("regular" to "Regular GST", "composition" to "Composition", "unregistered" to "Not registered").forEach { (v, label) ->
            val on = scheme == v
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (on) Anylo.colors.primarySoft else Anylo.colors.surface2)
                    .clickable(enabled = canEdit) { scheme = v }.padding(16.dp),
            ) { Text(label, fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal, color = if (on) Anylo.colors.onPrimarySoft else Anylo.colors.text) }
        }
        if (needs) {
            AnyloField("GSTIN", gstin, { gstin = it.uppercase().filter(Char::isLetterOrDigit).take(15) }, enabled = canEdit,
                error = if (gstin.length == 15 && !valid) "This GSTIN doesn't look right. Check each character." else null,
                hint = if (gstin.length < 15) "${15 - gstin.length} more characters" else "Looks good.")
            AnyloField("Legal name (as on GST certificate)", legal, { legal = it }, enabled = canEdit)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("My prices include GST", Modifier.weight(1f))
                Switch(checked = inclusive, onCheckedChange = { inclusive = it }, enabled = canEdit)
            }
        }
        if (canEdit) PrimaryButton(button, loading = busy, enabled = valid, onClick = {
            scope.launch {
                busy = true; error = null
                runCatching { app.session.api.putTax(TaxReq(scheme, if (needs) gstin else null, legal.ifBlank { null }, inclusive)) }
                    .onSuccess(onSaved).onFailure { error = app.session.messageOf(it) }
                busy = false
            }
        })
    }
}

@Composable
fun OnboardingScreen(app: AppState, me: Me) {
    val scope = rememberCoroutineScope()
    var shop by remember { mutableStateOf<Shop?>(null) }
    var step by remember { mutableStateOf(0) }
    LaunchedEffect(Unit) { shop = runCatching { app.session.api.shop() }.getOrNull() }
    val skipTax = !app.can("shop.tax_profile")
    Column(Modifier.fillMaxSize().background(Anylo.colors.bg).statusBarsPadding().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Logo(30)
        Text("Step ${step + 1} of 3", color = Anylo.colors.brand, fontWeight = FontWeight.SemiBold)
        Text("Let's set up your shop", style = MaterialTheme.typography.headlineMedium)
        val s = shop ?: return@Column Text("Loading…", color = Anylo.colors.text2)
        when (step) {
            0 -> BusinessCard(app, s, "Save and continue") { shop = it; step = if (skipTax) 2 else 1 }
            1 -> GstCard(app, s, "Save and continue") { shop = it; step = 2 }
            else -> Card {
                Text("Your shop is ready", style = MaterialTheme.typography.titleLarge)
                Text("${s.name} is set up, ${me.user.fullName.substringBefore(' ')}. Add your logo and staff any time in Settings.", color = Anylo.colors.text2)
                PrimaryButton("Go to my shop", onClick = { scope.launch { runCatching { app.session.api.completeOnboarding(); app.loadMe() } } })
            }
        }
    }
}

private enum class Tab(val label: String, val icon: ImageVector) { Home("Home", Icons.Filled.Home), Sell("Sell", Icons.Filled.ShoppingCart), Items("Items", Icons.Filled.Inventory2), Settings("Settings", Icons.Filled.Settings) }

@Composable
fun Shell(app: AppState, me: Me) {
    var tab by remember { mutableStateOf(Tab.Home) }
    Column(Modifier.fillMaxSize().background(Anylo.colors.bg)) {
        Box(Modifier.weight(1f)) {
            when (tab) {
                Tab.Home -> HomeScreen(app, me)
                Tab.Settings -> SettingsScreen(app, me)
                Tab.Items -> ItemsScreen(app)
                else -> Soon(tab.label)
            }
        }
        NavigationBar(containerColor = Anylo.colors.surface) {
            Tab.entries.forEach { t ->
                NavigationBarItem(selected = tab == t, onClick = { tab = t }, icon = { Icon(t.icon, null) }, label = { Text(t.label) })
            }
        }
    }
}

@Composable
private fun Soon(what: String) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Text("$what is coming in the next update.", color = Anylo.colors.text2)
    }
}

@Composable
fun HomeScreen(app: AppState, me: Me) {
    val scope = rememberCoroutineScope()
    Column(Modifier.fillMaxSize().statusBarsPadding().verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Logo(30)
        me.subscription?.takeIf { it.status == "trialing" }?.let { Pill("Free trial: ${it.daysLeft} days left") }
        if (me.activeShopId == null && me.shops.size > 1) {
            Text("Choose a shop", style = MaterialTheme.typography.headlineMedium)
            me.shops.forEach { s ->
                Card(Modifier.clickable { scope.launch { app.switchShop(s.id) } }) { Text(s.name, style = MaterialTheme.typography.titleMedium) }
            }
            return@Column
        }
        Text(me.shops.firstOrNull { it.id == me.activeShopId }?.name.orEmpty(), color = Anylo.colors.text2)
        Text("Welcome, ${me.user.fullName.substringBefore(' ')}", style = MaterialTheme.typography.headlineMedium)
        listOf("Today's sales" to "₹0", "Bills today" to "0", "Cash in hand" to "₹0").forEach { (k, v) ->
            Card { Text(k, color = Anylo.colors.text2); Text(v, style = MaterialTheme.typography.headlineMedium) }
        }
        if ("ai.use" in me.permissions) {
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Anylo.colors.tint).padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.AutoAwesome, null, tint = Anylo.colors.brand)
                Spacer(Modifier.size(12.dp))
                Text("Your AI manager is coming soon.")
            }
        }
        if (me.shops.size > 1) me.shops.filter { it.id != me.activeShopId }.forEach { s ->
            SecondaryButton("Switch to ${s.name}", { scope.launch { app.switchShop(s.id) } }, Modifier.fillMaxWidth())
        }
    }
}

@Composable
fun SettingsScreen(app: AppState, me: Me) {
    val printer = (androidx.compose.ui.platform.LocalContext.current.applicationContext as `in`.anylo.app.AnyloApp).printer
    var showPrinter by remember { mutableStateOf(false) }
    if (showPrinter) { PrinterScreen(printer) { showPrinter = false }; return }
    var shop by remember { mutableStateOf<Shop?>(null) }
    LaunchedEffect(me.activeShopId) { if (app.can("shop.settings")) shop = runCatching { app.session.api.shop() }.getOrNull() }
    Column(Modifier.fillMaxSize().statusBarsPadding().verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text("Settings", style = MaterialTheme.typography.headlineMedium)
        SecondaryButton("Printer setup", { showPrinter = true }, Modifier.fillMaxWidth())
        shop?.let { s ->
            BusinessCard(app, s, "Save changes") { shop = it }
            GstCard(app, s, "Save GST settings") { shop = it }
        }
        if (app.can("staff.salespeople")) StaffCard(app)
        Card { ChangePasswordContent(app, "Password", "Change password") }
        SecondaryButton("Log out", app::logout, Modifier.fillMaxWidth())
    }
}

@Composable
fun StaffCard(app: AppState) {
    val scope = rememberCoroutineScope()
    var staff by remember { mutableStateOf(emptyList<Staff>()) }
    var adding by remember { mutableStateOf(false) }
    var created by remember { mutableStateOf<Staff?>(null) }
    suspend fun reload() { staff = runCatching { app.session.api.staff() }.getOrDefault(staff) }
    LaunchedEffect(Unit) { reload() }
    Card {
        Text("Staff", style = MaterialTheme.typography.titleLarge)
        if (staff.isEmpty()) Text("No staff yet. Add a salesperson so they can make bills on their own login.", color = Anylo.colors.text2)
        staff.forEach { s ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(40.dp).clip(CircleShape).background(Anylo.colors.primarySoft), contentAlignment = Alignment.Center) {
                    Text(s.fullName.take(1), color = Anylo.colors.onPrimarySoft, fontWeight = FontWeight.SemiBold)
                }
                Column(Modifier.weight(1f).padding(horizontal = 12.dp)) {
                    Text(s.fullName, fontWeight = FontWeight.Medium, color = if (s.isActive) Anylo.colors.text else Anylo.colors.text3)
                    Text(if (s.role == "manager") "Manager" else "Salesperson", color = Anylo.colors.text2, style = MaterialTheme.typography.bodyMedium)
                }
                if (s.role != "manager" || app.can("staff.managers")) {
                    TextButton(onClick = { scope.launch { runCatching { app.session.api.patchStaff(s.id, StaffPatch(!s.isActive)) }; reload() } }) {
                        Text(if (s.isActive) "Switch off" else "Switch on")
                    }
                }
            }
        }
        SecondaryButton("Add staff", { adding = true }, Modifier.fillMaxWidth())
    }
    if (adding) AddStaffDialog(app, onDismiss = { adding = false }) { created = it; adding = false; scope.launch { reload() } }
    created?.let { c ->
        AlertDialog(
            onDismissRequest = { created = null }, confirmButton = { TextButton(onClick = { created = null }) { Text("Done") } },
            title = { Text("Login details") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Share these with ${c.fullName}. This password is shown only once.")
                    Text("Email: ${c.email}\nPassword: ${c.temporaryPassword}", fontFamily = FontFamily.Monospace,
                        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(Anylo.colors.tint).padding(12.dp))
                }
            },
        )
    }
}

@Composable
private fun AddStaffDialog(app: AppState, onDismiss: () -> Unit, onCreated: (Staff) -> Unit) {
    val scope = rememberCoroutineScope()
    var name by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var manager by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    AlertDialog(
        onDismissRequest = onDismiss, title = { Text("Add staff") },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
        confirmButton = {
            TextButton(enabled = name.length >= 2 && "@" in email, onClick = {
                scope.launch {
                    runCatching { app.session.api.addStaff(StaffReq(name.trim(), email.trim(), if (manager) "manager" else "salesperson")) }
                        .onSuccess(onCreated).onFailure { error = app.session.messageOf(it) }
                }
            }) { Text("Add") }
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                ErrorBanner(error)
                AnyloField("Full name", name, { name = it })
                AnyloField("Email (used to log in)", email, { email = it }, keyboard = KeyboardType.Email)
                if (app.can("staff.managers")) Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Make them a manager", Modifier.weight(1f)); Switch(checked = manager, onCheckedChange = { manager = it })
                }
            }
        },
    )
}
