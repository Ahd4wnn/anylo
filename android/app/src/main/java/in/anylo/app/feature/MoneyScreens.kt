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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
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
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import `in`.anylo.app.AppState
import `in`.anylo.app.core.ApprovalDto
import `in`.anylo.app.core.AttendanceReq
import `in`.anylo.app.core.CashDayDto
import `in`.anylo.app.core.CloseReq
import `in`.anylo.app.core.CollectReq
import `in`.anylo.app.core.CustomerDto
import `in`.anylo.app.core.CustomerPage
import `in`.anylo.app.core.ExpenseCategory
import `in`.anylo.app.core.ExpensePage
import `in`.anylo.app.core.ExpenseReq
import `in`.anylo.app.core.LabourPayReq
import `in`.anylo.app.core.LedgerDto
import `in`.anylo.app.core.LoanDto
import `in`.anylo.app.core.LoanPage
import `in`.anylo.app.core.LoanReq
import `in`.anylo.app.core.Me
import `in`.anylo.app.core.NoteReq
import `in`.anylo.app.core.RepayReq
import `in`.anylo.app.core.WorkerDto
import `in`.anylo.app.core.WorkerPage
import `in`.anylo.app.core.WorkerReq
import `in`.anylo.app.print.money
import `in`.anylo.app.ui.Anylo
import `in`.anylo.app.ui.AnyloField
import `in`.anylo.app.ui.Card
import `in`.anylo.app.ui.ErrorBanner
import `in`.anylo.app.ui.Logo
import `in`.anylo.app.ui.PrimaryButton
import `in`.anylo.app.ui.SecondaryButton
import kotlinx.coroutines.launch
import java.math.BigDecimal
import java.time.LocalDate
import java.util.UUID

private fun rs(v: String) = "₹" + money(v)
private fun num(v: String) = v.toBigDecimalOrNull() ?: BigDecimal.ZERO

private enum class Hub(val label: String, val permission: String) {
    Reports("Reports", "report.view"), Customers("Customers", "customer.view"), Cash("Cash & close day", "cash.view_today"), Expenses("Expenses", "expense.create"),
    Labour("Labour", "labour.attendance"), Loans("Loans", "borrowing.manage"), Purchases("Purchases", "purchase.manage"),
    StockCount("Stock count", "stock.manage"), Approvals("Approvals", "approval.decide"),
}

/** Home is the hub for everything that doesn't fit in the bottom bar. */
@Composable
fun HomeHub(app: AppState, me: Me) {
    val scope = rememberCoroutineScope()
    var open by remember { mutableStateOf<Hub?>(null) }
    var cash by remember { mutableStateOf<CashDayDto?>(null) }
    var sales by remember { mutableStateOf<Pair<String, Int>?>(null) }
    var pending by remember { mutableIntStateOf(0) }
    var dash by remember { mutableStateOf<`in`.anylo.app.core.DashboardDto?>(null) }
    var goals by remember { mutableStateOf(emptyList<`in`.anylo.app.core.GoalDto>()) }
    LaunchedEffect(open, me.activeShopId) {
        if (open != null || me.activeShopId == null) return@LaunchedEffect
        val today = LocalDate.now().toString()
        runCatching { app.session.sales.list(null, today, today) }.onSuccess { sales = it.salesTotal to it.total }
        if (app.can("cash.view_today")) runCatching { cash = app.session.money.cashToday() }
        if (app.can("approval.decide")) runCatching { pending = app.session.money.approvals().size }
        if (app.can("report.view")) runCatching { dash = app.session.reports.dashboard(today, today) }
        runCatching { goals = app.session.reports.goals().filter { it.daysLeft > 0 || it.status == "achieved" }.take(3) }
    }
    when (open) {
        Hub.Reports -> { ReportsScreen(app) { open = null }; return }
        Hub.Customers -> { CustomersScreen(app) { open = null }; return }
        Hub.Cash -> { CashScreen(app) { open = null }; return }
        Hub.Expenses -> { ExpensesScreen(app) { open = null }; return }
        Hub.Labour -> { LabourScreen(app) { open = null }; return }
        Hub.Loans -> { LoansScreen(app) { open = null }; return }
        Hub.Approvals -> { ApprovalsScreen(app) { open = null }; return }
        Hub.Purchases -> { PurchasesScreen(app) { open = null }; return }
        Hub.StockCount -> { StockCountScreen(app) { open = null }; return }
        null -> Unit
    }
    Column(Modifier.fillMaxSize().statusBarsPadding().verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Logo(30)
        me.subscription?.takeIf { it.status == "trialing" }?.let { Pill("Free trial: ${it.daysLeft} days left") }
        if (me.activeShopId == null && me.shops.size > 1) {
            Text("Choose a shop", style = MaterialTheme.typography.headlineMedium)
            me.shops.forEach { s -> Card(Modifier.clickable { scope.launch { app.switchShop(s.id) } }) { Text(s.name, style = MaterialTheme.typography.titleMedium) } }
            return@Column
        }
        Text(me.shops.firstOrNull { it.id == me.activeShopId }?.name.orEmpty(), color = Anylo.colors.text2)
        Text("Welcome, ${me.user.fullName.substringBefore(' ')}", style = MaterialTheme.typography.headlineMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Stat("Today's sales", sales?.first?.let(::rs) ?: "…", Modifier.weight(1f))
            Stat("Bills today", sales?.second?.toString() ?: "…", Modifier.weight(1f))
        }
        dash?.current?.let { m ->
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Stat("Gross profit today", rs(m.grossProfit), Modifier.weight(1f))
                Stat("Average bill", rs(m.avgBillValue), Modifier.weight(1f))
            }
        }
        cash?.let { Stat("Cash in drawer", rs(it.expected), Modifier.fillMaxWidth()) }
        goals.forEach { GoalRow(it) }
        Hub.entries.filter { app.can(it.permission) }.forEach { h ->
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Anylo.colors.surface).clickable { open = h }.padding(16.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Text(h.label, Modifier.weight(1f), fontWeight = FontWeight.Medium)
                if (h == Hub.Approvals && pending > 0) Pill("$pending waiting")
                Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, null, tint = Anylo.colors.text3)
            }
        }
        if (me.shops.size > 1) me.shops.filter { it.id != me.activeShopId }.forEach { s ->
            SecondaryButton("Switch to ${s.name}", { scope.launch { app.switchShop(s.id) } }, Modifier.fillMaxWidth())
        }
    }
}

@Composable
private fun Stat(label: String, value: String, modifier: Modifier) {
    Column(modifier.clip(RoundedCornerShape(16.dp)).background(Anylo.colors.surface).padding(16.dp)) {
        Text(label, color = Anylo.colors.text2, style = MaterialTheme.typography.bodyMedium)
        Text(value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
    }
}

@Composable
internal fun Screen(title: String, onBack: () -> Unit, content: @Composable () -> Unit) {
    Column(Modifier.fillMaxSize().background(Anylo.colors.bg).statusBarsPadding().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") }
            Text(title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        }
        content()
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
internal fun RowItem(title: String, sub: String?, trailing: String? = null, onClick: (() -> Unit)? = null) {
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Anylo.colors.surface)
        .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier).padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, fontWeight = FontWeight.Medium)
            sub?.let { Text(it, color = Anylo.colors.text2, style = MaterialTheme.typography.bodySmall) }
        }
        trailing?.let { Text(it, fontWeight = FontWeight.SemiBold) }
    }
}

@Composable
private fun Methods(selected: String, options: List<String>, onSelect: (String) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        options.forEach { m -> FilterChip(selected = selected == m, onClick = { onSelect(m) }, label = { Text(m.uppercase()) }) }
    }
}

// --- customers ---

@Composable
private fun CustomersScreen(app: AppState, onBack: () -> Unit) {
    var q by remember { mutableStateOf("") }
    var due by remember { mutableStateOf(false) }
    var page by remember { mutableStateOf<CustomerPage?>(null) }
    var openId by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(q, due, openId) {
        if (openId != null) return@LaunchedEffect
        kotlinx.coroutines.delay(250)
        runCatching { app.session.money.customers(q.ifBlank { null }, due) }.onSuccess { page = it }
    }
    openId?.let { CustomerScreen(app, it) { openId = null }; return }
    Screen("Customers", onBack) {
        page?.let { Text("${it.total} customers · ${rs(it.dueTotal)} to collect", color = Anylo.colors.text2) }
        AnyloField("Search", q, { q = it }, hint = "Name, mobile or GSTIN")
        FilterChip(selected = due, onClick = { due = !due }, label = { Text("Has due") })
        page?.items?.forEach { c ->
            val b = num(c.balance)
            RowItem(c.name ?: c.phone.orEmpty(), if (c.name != null) c.phone else null,
                when { b > BigDecimal.ZERO -> "Due ${rs(c.balance)}"; b < BigDecimal.ZERO -> "Credit ${rs(b.negate().toPlainString())}"; else -> null }) { openId = c.id }
        }
        if (page?.items?.isEmpty() == true) Text("Customers are added when you save a bill with their mobile number.", color = Anylo.colors.text2)
    }
}

@Composable
private fun CustomerScreen(app: AppState, id: String, onBack: () -> Unit) {
    var c by remember { mutableStateOf<CustomerDto?>(null) }
    var ledger by remember { mutableStateOf<LedgerDto?>(null) }
    var collecting by remember { mutableStateOf(false) }
    var reload by remember { mutableIntStateOf(0) }
    LaunchedEffect(reload) {
        runCatching { c = app.session.money.customer(id) }
        if (app.can("customer.manage")) runCatching { ledger = app.session.money.ledger(id) }
    }
    val cust = c ?: return Screen("Customer", onBack) { Text("Loading…", color = Anylo.colors.text2) }
    val bal = num(cust.balance)
    Screen(cust.name ?: cust.phone.orEmpty(), onBack) {
        Card {
            Text(if (bal < BigDecimal.ZERO) "Store credit" else "Balance due", color = Anylo.colors.text2)
            Text(rs(bal.abs().toPlainString()), style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold,
                color = if (bal > BigDecimal.ZERO) Anylo.colors.warning else Anylo.colors.text)
            Text(listOfNotNull(cust.phone, "${cust.bills ?: 0} bills", cust.spent?.let { "bought ${rs(it)}" }).joinToString(" · "), color = Anylo.colors.text2)
            if (bal > BigDecimal.ZERO && app.can("payment.collect")) PrimaryButton("Collect payment", { collecting = true })
        }
        ledger?.let { l ->
            Text("Statement", fontWeight = FontWeight.SemiBold)
            l.entries.reversed().forEach { e ->
                val label = mapOf("bill" to "Bill", "paid_at_bill" to "Paid at bill", "payment" to "Payment", "return" to "Return", "refund" to "Refund")[e.kind] ?: e.kind
                RowItem("$label ${e.ref.orEmpty()}", e.at.take(10) + " · balance ${rs(e.balance)}",
                    if (num(e.debit) > BigDecimal.ZERO) "+${rs(e.debit)}" else "−${rs(e.credit)}")
            }
        }
    }
    if (collecting) CollectDialog(app, cust) { collecting = false; reload++ }
}

@Composable
private fun CollectDialog(app: AppState, c: CustomerDto, onClose: () -> Unit) {
    val scope = rememberCoroutineScope()
    val key = remember { UUID.randomUUID().toString() } // one key per dialog: a retry can't record the payment twice
    var amount by remember { mutableStateOf(c.balance) }
    var method by remember { mutableStateOf("cash") }
    var error by remember { mutableStateOf<String?>(null) }
    var done by remember { mutableStateOf<String?>(null) }
    AlertDialog(onDismissRequest = onClose, title = { Text(done?.let { "Payment saved" } ?: "Collect payment") },
        dismissButton = { if (done == null) TextButton(onClick = onClose) { Text("Cancel") } },
        confirmButton = {
            TextButton(onClick = {
                if (done != null) onClose() else scope.launch {
                    runCatching { app.session.money.collect(c.id, CollectReq(amount, method, key)) }
                        .onSuccess { r -> done = if (r.status == "pending_approval") "${r.receiptNo}: sent to the owner or manager to approve." else "${r.receiptNo} · balance now ${rs(r.balanceAfter)}" }
                        .onFailure { error = app.session.messageOf(it) }
                }
            }) { Text(if (done != null) "Done" else "Save") }
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                done?.let { Text(it) } ?: run {
                    ErrorBanner(error)
                    AnyloField("Amount ₹", amount, { amount = it }, keyboard = KeyboardType.Decimal, hint = "Settles the oldest bills first.")
                    Methods(method, listOf("cash", "upi", "card"), { method = it })
                }
            }
        })
}

// --- cash ---

@Composable
private fun CashScreen(app: AppState, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var t by remember { mutableStateOf<CashDayDto?>(null) }
    var counted by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) { runCatching { t = app.session.money.cashToday() }.onFailure { error = app.session.messageOf(it) } }
    Screen("Cash", onBack) {
        ErrorBanner(error)
        val d = t ?: return@Screen
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Stat("Opening", rs(d.opening), Modifier.weight(1f)); Stat("In drawer", rs(d.expected), Modifier.weight(1f))
        }
        d.breakdown.forEach { b -> RowItem(b.label, null, (if (b.direction == "in") "+" else "−") + rs(b.amount)) }
        if (num(d.pending) > BigDecimal.ZERO) Text("${rs(d.pending)} collected by staff is waiting for approval.", color = Anylo.colors.warning)
        val close = d.close
        if (close != null) Card {
            Text("Today is closed", fontWeight = FontWeight.SemiBold)
            val diff = num(close.difference)
            Text("Counted ${rs(close.counted)} · " + when { diff.signum() == 0 -> "matches"; diff < BigDecimal.ZERO -> "short by ${rs(diff.negate().toPlainString())}"; else -> "over by ${rs(close.difference)}" })
            if (close.status == "pending") Text("Waiting for the owner or manager to confirm.", color = Anylo.colors.text2)
        } else if (app.can("cash.close")) Card {
            Text("Close the day", fontWeight = FontWeight.SemiBold)
            AnyloField("Cash counted ₹", counted, { counted = it.filter { ch -> ch.isDigit() || ch == '.' } }, keyboard = KeyboardType.Decimal,
                hint = counted.toBigDecimalOrNull()?.let { val diff = it - num(d.expected); if (diff.signum() == 0) "Matches exactly." else if (diff < BigDecimal.ZERO) "Short by ${rs(diff.negate().toPlainString())}" else "Over by ${rs(diff.toPlainString())}" })
            PrimaryButton("Close day", {
                scope.launch { runCatching { app.session.money.close(CloseReq(counted)) }.onSuccess { t = it; error = null }.onFailure { error = app.session.messageOf(it) } }
            }, enabled = counted.toBigDecimalOrNull() != null)
        }
    }
}

// --- expenses ---

@Composable
private fun ExpensesScreen(app: AppState, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var page by remember { mutableStateOf<ExpensePage?>(null) }
    var cats by remember { mutableStateOf(emptyList<ExpenseCategory>()) }
    var cat by remember { mutableStateOf<String?>(null) }
    var amount by remember { mutableStateOf("") }
    var method by remember { mutableStateOf("cash") }
    var note by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var managing by remember { mutableStateOf(false) }
    suspend fun load() { runCatching { page = app.session.money.expenses() } }
    suspend fun loadCats() { runCatching { cats = app.session.money.expenseCategories() } }
    LaunchedEffect(Unit) { loadCats(); load() }
    if (managing) CategoryDialog(app, cats, onChange = { scope.launch { loadCats() } }) { managing = false }
    Screen("Expenses", onBack) {
        if (app.can("expense.manage")) SecondaryButton("Manage categories", { managing = true }, Modifier.fillMaxWidth())
        Card {
            Text("Add an expense", fontWeight = FontWeight.SemiBold)
            ErrorBanner(error)
            Picker("Category", cats.map { `in`.anylo.app.core.Option(it.id, it.name) }, cat.orEmpty()) { cat = it }
            AnyloField("Amount ₹", amount, { amount = it }, keyboard = KeyboardType.Decimal)
            Methods(method, listOf("cash", "upi", "card", "bank"), { method = it })
            AnyloField("Note (optional)", note, { note = it })
            PrimaryButton("Add", {
                scope.launch {
                    runCatching { app.session.money.addExpense(ExpenseReq(cat, amount, method, note.ifBlank { null })) }
                        .onSuccess { amount = ""; note = ""; error = null; load() }.onFailure { error = app.session.messageOf(it) }
                }
            }, enabled = cat != null && amount.toBigDecimalOrNull() != null)
        }
        page?.let { p ->
            Text("This month: ${rs(p.total)}", fontWeight = FontWeight.SemiBold)
            p.items.forEach { e -> RowItem(e.category, listOfNotNull(e.day, e.method.uppercase(), e.note).joinToString(" · "), rs(e.amount)) }
        }
    }
}

// --- labour ---

@Composable
private fun LabourScreen(app: AppState, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    val manage = app.can("labour.manage")
    var page by remember { mutableStateOf<WorkerPage?>(null) }
    var paying by remember { mutableStateOf<WorkerDto?>(null) }
    var adding by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    suspend fun load() { runCatching { page = app.session.money.workers() }.onFailure { error = app.session.messageOf(it) } }
    LaunchedEffect(Unit) { load() }
    Screen("Labour", onBack) {
        ErrorBanner(error)
        page?.let { p -> if (manage) Text("Wages to pay: ${rs(p.balanceToPay)}", fontWeight = FontWeight.SemiBold) }
        page?.items?.forEach { w ->
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Anylo.colors.surface).padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(w.name, fontWeight = FontWeight.Medium)
                        Text(if (w.wageType == "monthly") "${rs(w.monthlyWage)}/month" else "${rs(w.dailyWage)}/day", color = Anylo.colors.text2, style = MaterialTheme.typography.bodySmall)
                    }
                    if (manage) Text(if (num(w.balance) < BigDecimal.ZERO) "Adv ${rs(num(w.balance).negate().toPlainString())}" else rs(w.balance), fontWeight = FontWeight.SemiBold)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    listOf("present" to "Present", "half_day" to "Half", "absent" to "Absent").forEach { (s, label) ->
                        FilterChip(selected = w.today == s, label = { Text(label) }, onClick = {
                            scope.launch {
                                runCatching { app.session.money.mark(AttendanceReq(w.id, LocalDate.now().toString(), s)) }
                                    .onSuccess { load() }.onFailure { error = app.session.messageOf(it) }
                            }
                        })
                    }
                    Spacer(Modifier.weight(1f))
                    if (manage) TextButton(onClick = { paying = w }) { Text("Pay") }
                }
            }
        }
        if (page?.items?.isEmpty() == true) Text("Add your workers to mark attendance and keep wages straight.", color = Anylo.colors.text2)
        if (manage) SecondaryButton("Add worker", { adding = true }, Modifier.fillMaxWidth())
    }
    paying?.let { w ->
        var cash by remember(w.id) { mutableStateOf(num(w.balance).max(BigDecimal.ZERO).toPlainString().takeIf { it != "0" }.orEmpty()) }
        var upi by remember(w.id) { mutableStateOf("") }
        var err by remember(w.id) { mutableStateOf<String?>(null) }
        AlertDialog(onDismissRequest = { paying = null }, title = { Text("Pay ${w.name}") },
            dismissButton = { TextButton(onClick = { paying = null }) { Text("Cancel") } },
            confirmButton = {
                TextButton(enabled = num(cash) + num(upi) > BigDecimal.ZERO, onClick = {
                    scope.launch {
                        val kind = if (num(w.balance) > BigDecimal.ZERO) "wage" else "advance"
                        runCatching { app.session.money.pay(LabourPayReq(w.id, kind, cash.ifBlank { "0" }, upi.ifBlank { "0" })) }
                            .onSuccess { paying = null; load() }.onFailure { err = app.session.messageOf(it) }
                    }
                }) { Text("Pay ${rs((num(cash) + num(upi)).toPlainString())}") }
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    ErrorBanner(err)
                    Text("Earned ${rs(w.earned)} · paid ${rs(w.paid)}", color = Anylo.colors.text2)
                    AnyloField("Cash ₹", cash, { cash = it }, keyboard = KeyboardType.Decimal)
                    AnyloField("UPI ₹", upi, { upi = it }, keyboard = KeyboardType.Decimal)
                }
            })
    }
    if (adding) {
        var name by remember { mutableStateOf("") }
        var monthly by remember { mutableStateOf(false) }
        var wage by remember { mutableStateOf("") }
        var gender by remember { mutableStateOf("male") }
        var err by remember { mutableStateOf<String?>(null) }
        AlertDialog(onDismissRequest = { adding = false }, title = { Text("Add worker") },
            dismissButton = { TextButton(onClick = { adding = false }) { Text("Cancel") } },
            confirmButton = {
                TextButton(enabled = name.isNotBlank() && wage.toBigDecimalOrNull() != null, onClick = {
                    scope.launch {
                        val req = WorkerReq(name.trim(), gender, if (monthly) "monthly" else "daily", if (monthly) "0" else wage, if (monthly) wage else "0")
                        runCatching { app.session.money.addWorker(req) }.onSuccess { adding = false; load() }.onFailure { err = app.session.messageOf(it) }
                    }
                }) { Text("Save") }
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    ErrorBanner(err)
                    AnyloField("Name", name, { name = it })
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        listOf("male" to "Male", "female" to "Female", "other" to "Other").forEach { (g, l) -> FilterChip(selected = gender == g, onClick = { gender = g }, label = { Text(l) }) }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        FilterChip(selected = !monthly, onClick = { monthly = false }, label = { Text("Daily wage") })
                        FilterChip(selected = monthly, onClick = { monthly = true }, label = { Text("Monthly salary") })
                    }
                    AnyloField(if (monthly) "Salary per month ₹" else "Wage per day ₹", wage, { wage = it }, keyboard = KeyboardType.Decimal)
                }
            })
    }
}

// --- loans ---

@Composable
private fun LoansScreen(app: AppState, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var page by remember { mutableStateOf<LoanPage?>(null) }
    var repaying by remember { mutableStateOf<LoanDto?>(null) }
    var adding by remember { mutableStateOf(false) }
    suspend fun load() { runCatching { page = app.session.money.loans() } }
    LaunchedEffect(Unit) { load() }
    Screen("Loans", onBack) {
        page?.let { Text("To repay: ${rs(it.outstanding)}", fontWeight = FontWeight.SemiBold) }
        page?.items?.forEach { l ->
            RowItem(l.lender, if (l.status == "closed") "Repaid" else "${rs(l.principal)} taken", if (l.status == "open") rs(l.outstanding) else null,
                if (l.status == "open") ({ repaying = l }) else null)
        }
        SecondaryButton("Add money borrowed", { adding = true }, Modifier.fillMaxWidth())
    }
    if (adding) AmountDialog("Money borrowed", withName = true, onClose = { adding = false }) { name, amount, method ->
        app.session.money.addLoan(LoanReq(name, amount, method)); load()
    }
    repaying?.let { l ->
        AmountDialog("Repay ${l.lender}", initial = l.outstanding, onClose = { repaying = null }) { _, amount, method ->
            app.session.money.repay(l.id, RepayReq(amount, method)); load()
        }
    }
}

@Composable
private fun AmountDialog(title: String, withName: Boolean = false, initial: String = "", onClose: () -> Unit, save: suspend (String, String, String) -> Unit) {
    val scope = rememberCoroutineScope()
    val app = androidx.compose.ui.platform.LocalContext.current.applicationContext as `in`.anylo.app.AnyloApp
    var name by remember { mutableStateOf("") }
    var amount by remember { mutableStateOf(initial) }
    var method by remember { mutableStateOf("cash") }
    var err by remember { mutableStateOf<String?>(null) }
    AlertDialog(onDismissRequest = onClose, title = { Text(title) },
        dismissButton = { TextButton(onClick = onClose) { Text("Cancel") } },
        confirmButton = {
            TextButton(enabled = (!withName || name.isNotBlank()) && amount.toBigDecimalOrNull() != null, onClick = {
                scope.launch { runCatching { save(name.trim(), amount, method) }.onSuccess { onClose() }.onFailure { err = app.session.messageOf(it) } }
            }) { Text("Save") }
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                ErrorBanner(err)
                if (withName) AnyloField("From (lender)", name, { name = it })
                AnyloField("Amount ₹", amount, { amount = it }, keyboard = KeyboardType.Decimal)
                Methods(method, listOf("cash", "upi", "bank"), { method = it })
            }
        })
}

// --- approvals ---

@Composable
private fun ApprovalsScreen(app: AppState, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var items by remember { mutableStateOf<List<ApprovalDto>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    suspend fun load() { runCatching { items = app.session.money.approvals() }.onFailure { error = app.session.messageOf(it) } }
    LaunchedEffect(Unit) { load() }
    Screen("Approvals", onBack) {
        ErrorBanner(error)
        if (items?.isEmpty() == true) Text("Nothing waiting. Collections, returns and day closes by salespeople show up here.", color = Anylo.colors.text2)
        items?.forEach { a ->
            Card {
                Text(a.summary, fontWeight = FontWeight.Medium)
                a.requestedBy?.let { Text(it, color = Anylo.colors.text2) }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SecondaryButton("Reject", { scope.launch { runCatching { app.session.money.reject(a.id, NoteReq()) }.onFailure { error = app.session.messageOf(it) }; load() } }, Modifier.weight(1f))
                    PrimaryButton("Approve", { scope.launch { runCatching { app.session.money.approve(a.id, NoteReq()) }.onFailure { error = app.session.messageOf(it) }; load() } }, Modifier.weight(1f))
                }
            }
        }
    }
}

/** Returning customers from the first digits of their mobile, so nobody has to say the full number every visit. */
@Composable
fun ReturningCustomers(app: AppState, phone: String, onPick: (CustomerDto) -> Unit) {
    var matches by remember { mutableStateOf(emptyList<CustomerDto>()) }
    LaunchedEffect(phone) {
        if (phone.length < 5) { matches = emptyList(); return@LaunchedEffect }
        kotlinx.coroutines.delay(200)
        runCatching { app.session.money.lookup(phone) }.onSuccess { matches = it }
    }
    matches.forEach { m ->
        val b = num(m.balance)
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(Anylo.colors.surface2).clickable { onPick(m) }.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(m.name ?: "No name", fontWeight = FontWeight.Medium)
                Text(m.phone.orEmpty(), color = Anylo.colors.text2, style = MaterialTheme.typography.bodySmall)
            }
            if (b > BigDecimal.ZERO) Pill("Due ${rs(m.balance)}")
        }
    }
}

/** Owners add their own expense categories; built-in ones stay. Saved expenses keep their category name. */
@Composable
private fun CategoryDialog(app: AppState, cats: List<`in`.anylo.app.core.ExpenseCategory>, onChange: () -> Unit, onClose: () -> Unit) {
    val scope = rememberCoroutineScope()
    var name by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    AlertDialog(onDismissRequest = onClose, title = { Text("Expense categories") },
        confirmButton = { TextButton(onClick = onClose) { Text("Done") } },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                ErrorBanner(error)
                Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    AnyloField("New category", name, { name = it.take(60) }, Modifier.weight(1f))
                    androidx.compose.material3.Button(enabled = name.isNotBlank(), modifier = Modifier.height(56.dp), onClick = {
                        scope.launch {
                            runCatching { app.session.money.addCategory(`in`.anylo.app.core.CategoryReq(name.trim())) }
                                .onSuccess { name = ""; error = null; onChange() }.onFailure { error = app.session.messageOf(it) }
                        }
                    }) { Text("Add") }
                }
                cats.forEach { c ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(c.name, Modifier.weight(1f))
                        if (c.isSystem) Text("Built-in", color = Anylo.colors.text3, style = MaterialTheme.typography.bodySmall)
                        else TextButton(onClick = {
                            scope.launch { runCatching { app.session.money.deleteCategory(c.id) }.onSuccess { onChange() }.onFailure { error = app.session.messageOf(it) } }
                        }) { Text("Remove", color = Anylo.colors.danger) }
                    }
                }
            }
        })
}
