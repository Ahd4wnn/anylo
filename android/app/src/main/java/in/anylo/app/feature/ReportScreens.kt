package `in`.anylo.app.feature

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.anylo.app.AppState
import `in`.anylo.app.core.AgeingDto
import `in`.anylo.app.core.GoalDto
import `in`.anylo.app.core.Gstr3bDto
import `in`.anylo.app.core.PnlDto
import `in`.anylo.app.print.money
import `in`.anylo.app.ui.Anylo
import `in`.anylo.app.ui.Card
import `in`.anylo.app.ui.ErrorBanner
import java.math.BigDecimal
import java.time.LocalDate

private fun rs(v: String) = "₹" + money(v)

/** Progress card shared by Home and Reports: actual vs target, with how much time has gone. */
@Composable
fun GoalRow(g: GoalDto) {
    val moneyGoal = g.metric !in setOf("invoices_count", "new_customers")
    fun fmt(v: String) = if (moneyGoal) rs(v) else BigDecimal(v).stripTrailingZeros().toPlainString()
    val status = mapOf("achieved" to "Achieved", "on_track" to "On track", "at_risk" to "At risk", "behind" to "Behind", "missed" to "Missed")[g.status] ?: g.status
    Card {
        Row {
            Column(Modifier.weight(1f)) {
                Text(g.title, fontWeight = FontWeight.SemiBold)
                Text("${g.userName ?: "Whole shop"} · ${g.daysLeft} days left", color = Anylo.colors.text2, style = MaterialTheme.typography.bodySmall)
            }
            Pill(status)
        }
        Text("${fmt(g.actual)} of ${fmt(g.target)}", fontWeight = FontWeight.Bold)
        val pct = (g.percent.toFloatOrNull() ?: 0f).coerceIn(0f, 100f) / 100f
        Box(Modifier.fillMaxWidth().height(10.dp).clip(RoundedCornerShape(5.dp)).background(Anylo.colors.surface2)) {
            Box(Modifier.fillMaxWidth(pct).height(10.dp).clip(RoundedCornerShape(5.dp)).background(Anylo.colors.primary))
        }
        Text("${g.percent}% done · ${g.elapsedPercent}% of time gone" + (g.runRateNeeded?.let { " · need ${fmt(it)}/day" } ?: ""),
            color = Anylo.colors.text2, style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
fun ReportsScreen(app: AppState, onBack: () -> Unit) {
    val today = LocalDate.now()
    val ranges = listOf(
        "Today" to (today to today),
        "This month" to (today.withDayOfMonth(1) to today),
        "Last month" to (today.minusMonths(1).withDayOfMonth(1) to today.withDayOfMonth(1).minusDays(1)),
    )
    var range by remember { mutableStateOf(ranges[1]) }
    var pnl by remember { mutableStateOf<PnlDto?>(null) }
    var owed by remember { mutableStateOf<AgeingDto?>(null) }
    var gst by remember { mutableStateOf<Gstr3bDto?>(null) }
    var goals by remember { mutableStateOf(emptyList<GoalDto>()) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(range) {
        val (a, b) = range.second
        runCatching { pnl = app.session.reports.pnl(a.toString(), b.toString()) }.onFailure { error = app.session.messageOf(it) }
        runCatching { owed = app.session.reports.receivables() }
        if (app.can("report.gst")) runCatching { gst = app.session.reports.gstr3b("%d-%02d".format(b.year, b.monthValue)) }
        runCatching { goals = app.session.reports.goals() }
    }
    Screen("Reports", onBack) {
        ErrorBanner(error)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            ranges.forEach { r -> FilterChip(selected = range.first == r.first, onClick = { range = r }, label = { Text(r.first) }) }
        }
        pnl?.total?.let { t ->
            Card {
                Text("Profit & loss", fontWeight = FontWeight.SemiBold)
                listOf(
                    "Net sales" to t.netSales, "Revenue without GST" to t.netRevenue, "Cost of goods" to t.cogs,
                    "Gross profit (${t.grossMarginPct}%)" to t.grossProfit, "Expenses" to t.expenses, "Wages" to t.labour, "Net profit" to t.netProfit,
                ).forEach { (k, v) ->
                    Row { Text(k, Modifier.weight(1f), color = Anylo.colors.text2); Text(rs(v), fontWeight = if (k == "Net profit") FontWeight.Bold else FontWeight.Normal) }
                }
                Text("${t.invoicesCount} bills · average ${rs(t.avgBillValue)}", color = Anylo.colors.text2, style = MaterialTheme.typography.bodySmall)
            }
        }
        gst?.let { g ->
            Card {
                Text("GST to pay this month", fontWeight = FontWeight.SemiBold)
                Row { Text("Sales taxable value", Modifier.weight(1f), color = Anylo.colors.text2); Text(rs(g.outward.taxable)) }
                listOf("CGST" to g.payable.cgst, "SGST" to g.payable.sgst, "IGST" to g.payable.igst).forEach { (k, v) ->
                    Row { Text("$k after input credit", Modifier.weight(1f), color = Anylo.colors.text2); Text(rs(v)) }
                }
                Text("Estimate. The full GSTR-1 and 3B Excel is on the web app.", color = Anylo.colors.text2, style = MaterialTheme.typography.bodySmall)
            }
        }
        owed?.let { o ->
            Card {
                Text("Customers owe you ${rs(o.totals["balance"] ?: "0")}", fontWeight = FontWeight.SemiBold)
                Row { listOf("0_30" to "0-30 d", "31_60" to "31-60", "61_90" to "61-90", "over_90" to "90+").forEach { (k, l) ->
                    Column(Modifier.weight(1f)) { Text(l, color = Anylo.colors.text2, style = MaterialTheme.typography.bodySmall); Text(rs(o.totals[k] ?: "0"), style = MaterialTheme.typography.bodySmall) }
                } }
            }
        }
        if (goals.isNotEmpty()) Text("Goals", fontWeight = FontWeight.SemiBold)
        goals.forEach { GoalRow(it) }
    }
}
