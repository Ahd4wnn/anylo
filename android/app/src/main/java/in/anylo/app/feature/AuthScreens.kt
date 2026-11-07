package `in`.anylo.app.feature

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.anylo.app.AppState
import `in`.anylo.app.core.Option
import `in`.anylo.app.core.SignupReq
import `in`.anylo.app.ui.Anylo
import `in`.anylo.app.ui.AnyloField
import `in`.anylo.app.ui.ErrorBanner
import `in`.anylo.app.ui.Logo
import `in`.anylo.app.ui.PrimaryButton
import kotlinx.coroutines.launch

/** Tinted brand header with the motto, shared by all auth screens. */
@Composable
fun AuthScaffold(content: @Composable () -> Unit) {
    val c = Anylo.colors
    Column(Modifier.fillMaxSize().background(c.bg).verticalScroll(rememberScrollState()).imePadding()) {
        Column(Modifier.fillMaxWidth().background(c.tint).statusBarsPadding().padding(24.dp)) {
            Logo(36)
            Spacer(Modifier.height(28.dp))
            Text(
                buildAnnotatedString {
                    append("Bill anything.\nSell anything.\nRun ")
                    withStyle(SpanStyle(color = c.brand)) { append("everything.") }
                },
                fontSize = 34.sp, lineHeight = 38.sp, fontWeight = FontWeight.Bold, color = c.text, letterSpacing = (-0.8).sp,
            )
        }
        Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) { content() }
    }
}

@Composable
fun LoginScreen(app: AppState, onSignup: () -> Unit) {
    val scope = rememberCoroutineScope()
    var login by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    AuthScaffold {
        Text("Welcome back", style = MaterialTheme.typography.headlineMedium)
        ErrorBanner(error)
        AnyloField("Email or mobile number", login, { login = it }, keyboard = KeyboardType.Email)
        AnyloField("Password", password, { password = it }, password = true)
        PrimaryButton("Log in", loading = busy, onClick = {
            scope.launch {
                busy = true; error = null
                runCatching { app.login(login, password) }.onFailure { error = app.session.messageOf(it) }
                busy = false
            }
        })
        TextButton(onClick = onSignup, modifier = Modifier.fillMaxWidth()) {
            Text("New to Anylo? Start your 30-day free trial", color = Anylo.colors.primary, fontWeight = FontWeight.SemiBold)
        }
        Text("Staff: ask your owner or manager if you forgot your password.", color = Anylo.colors.text2, style = MaterialTheme.typography.bodyMedium)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Picker(label: String, options: List<Option>, selected: String, onSelect: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Column {
        Text(label, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(6.dp))
        ExposedDropdownMenuBox(expanded = open, onExpandedChange = { open = it }) {
            OutlinedTextField(
                value = options.firstOrNull { it.value == selected }?.label ?: "Select", onValueChange = {}, readOnly = true,
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(open) }, shape = RoundedCornerShape(10.dp),
                modifier = Modifier.fillMaxWidth().menuAnchor(),
            )
            ExposedDropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                options.forEach { o -> DropdownMenuItem(text = { Text(o.label) }, onClick = { onSelect(o.value); open = false }) }
            }
        }
    }
}

@Composable
fun SignupScreen(app: AppState, onLogin: () -> Unit) {
    val scope = rememberCoroutineScope()
    var states by remember { mutableStateOf(emptyList<Option>()) }
    var types by remember { mutableStateOf(emptyList<Option>()) }
    LaunchedEffect(Unit) { runCatching { app.session.api.reference() }.onSuccess { states = it.states; types = it.businessTypes } }
    var shop by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var type by remember { mutableStateOf("general") }
    var state by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val phoneErr = if (phone.isNotEmpty() && !Regex("^[6-9][0-9]{9}$").matches(phone)) "Enter a 10-digit mobile number." else null
    AuthScaffold {
        Text("Start your free trial", style = MaterialTheme.typography.headlineMedium)
        Text("30 days free, every feature. Then ₹599/month per shop, GST included.", color = Anylo.colors.text2)
        ErrorBanner(error)
        AnyloField("Shop name", shop, { shop = it })
        AnyloField("Your name", name, { name = it })
        Picker("Type of shop", types, type) { type = it }
        Picker("State", states, state) { state = it }
        AnyloField("Mobile number", phone, { phone = it.filter(Char::isDigit).take(10) }, keyboard = KeyboardType.Phone, error = phoneErr)
        AnyloField("Email", email, { email = it.trim() }, keyboard = KeyboardType.Email)
        AnyloField("Password", password, { password = it }, password = true, hint = "At least 8 characters.")
        PrimaryButton("Create my shop", loading = busy,
            enabled = shop.length >= 2 && name.length >= 2 && state.isNotEmpty() && phoneErr == null && phone.length == 10 && password.length >= 8 && "@" in email,
            onClick = {
                scope.launch {
                    busy = true; error = null
                    runCatching { app.signup(SignupReq(shop.trim(), name.trim(), phone, email, password, type, state)) }
                        .onFailure { error = app.session.messageOf(it) }
                    busy = false
                }
            })
        TextButton(onClick = onLogin, modifier = Modifier.fillMaxWidth()) {
            Text("Already have an account? Log in", color = Anylo.colors.primary, fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
fun ChangePasswordContent(app: AppState, title: String, button: String, onDone: () -> Unit = {}) {
    val scope = rememberCoroutineScope()
    var current by remember { mutableStateOf("") }
    var new by remember { mutableStateOf("") }
    var confirm by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(title, style = MaterialTheme.typography.titleLarge)
        ErrorBanner(error)
        AnyloField("Current password", current, { current = it }, password = true)
        AnyloField("New password", new, { new = it }, password = true, hint = "At least 8 characters.")
        AnyloField("Type it again", confirm, { confirm = it }, password = true,
            error = if (confirm.isNotEmpty() && confirm != new) "The passwords don't match." else null)
        PrimaryButton(button, loading = busy, enabled = new.length >= 8 && new == confirm && current.isNotEmpty(), onClick = {
            scope.launch {
                busy = true; error = null
                runCatching { app.changePassword(current, new) }.onSuccess { onDone() }.onFailure { error = app.session.messageOf(it) }
                busy = false
            }
        })
    }
}

@Composable
fun ForceChangeScreen(app: AppState, name: String) {
    AuthScaffold {
        Text("Welcome, ${name.substringBefore(' ')}", style = MaterialTheme.typography.headlineMedium)
        Text("Choose your own password. Enter the temporary one you were given first.", color = Anylo.colors.text2)
        ChangePasswordContent(app, "Your password", "Save my password")
        TextButton(onClick = app::logout) { Text("Log out", color = Anylo.colors.text2) }
    }
}

@Composable
fun Pill(text: String, modifier: Modifier = Modifier) {
    Text(text, modifier.clip(RoundedCornerShape(50)).background(Anylo.colors.warningSoft).padding(horizontal = 10.dp, vertical = 4.dp),
        color = Anylo.colors.warning, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
}
