package `in`.anylo.app.feature

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.anylo.app.print.PrinterController
import `in`.anylo.app.ui.Anylo
import `in`.anylo.app.ui.Card
import `in`.anylo.app.ui.PrimaryButton
import `in`.anylo.app.ui.SecondaryButton
import kotlinx.coroutines.launch

/** Ported from PlantBill's PrinterScreen: pick a paired printer, paper width, auto-cut, test print. */
@Composable
fun PrinterScreen(printer: PrinterController, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var tick by remember { mutableStateOf(0) } // bump to re-read paired devices and permission state
    var selecting by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }
    var dots by remember { mutableStateOf(printer.paperDots) }
    var autoCut by remember { mutableStateOf(printer.autoCut) }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { grants ->
        if (!grants.values.all { it }) message = "Bluetooth permission is needed to print." else tick++
    }
    @Suppress("UNUSED_EXPRESSION") tick
    val devices = printer.pairedPrinters()
    val chosen = devices.firstOrNull { it.mac == printer.rememberedMac }

    Column(Modifier.fillMaxSize().background(Anylo.colors.bg).statusBarsPadding().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") }
            Text("Printer", style = MaterialTheme.typography.headlineMedium)
        }
        Card {
            Text(when {
                chosen != null -> "Printing to ${chosen.name}"
                printer.rememberedMac != null -> "Your printer isn't paired with this phone any more."
                else -> "No printer chosen yet"
            }, style = MaterialTheme.typography.titleMedium)
            Text("One printer can be shared by several phones. Anylo connects only while printing, then lets go.", color = Anylo.colors.text2)
            if (printer.rememberedMac != null) SecondaryButton(if (busy) "Printing…" else "Test print", {
                scope.launch { busy = true; message = printer.printTest().fold({ "Test page printed." }, { it.message }); busy = false }
            }, Modifier.fillMaxWidth())
        }
        when {
            !printer.isSupported -> Text("This phone has no Bluetooth.")
            !printer.hasPermission() -> PrimaryButton("Allow Bluetooth", onClick = {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) permission.launch(arrayOf(Manifest.permission.BLUETOOTH_CONNECT, Manifest.permission.BLUETOOTH_SCAN))
            })
            !printer.isEnabled -> Text("Turn on Bluetooth, then come back.", color = Anylo.colors.warning)
        }
        Text("Paired printers", style = MaterialTheme.typography.titleMedium)
        if (devices.isEmpty()) Text("Pair your printer in the phone's Bluetooth settings first (PIN is usually 0000 or 1234).", color = Anylo.colors.text2)
        devices.forEach { d ->
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Anylo.colors.surface)
                    .clickable(enabled = selecting == null) {
                        selecting = d.mac
                        scope.launch { message = printer.select(d).fold({ "${it.name} is ready." }, { it.message }); selecting = null; tick++ }
                    }.padding(16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(d.name, fontWeight = FontWeight.Medium)
                    Text(d.mac, color = Anylo.colors.text2, style = MaterialTheme.typography.bodyMedium)
                }
                when {
                    selecting == d.mac -> CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp)
                    printer.rememberedMac == d.mac -> Icon(Icons.Filled.CheckCircle, "Chosen", tint = Anylo.colors.success)
                }
            }
        }
        SecondaryButton("Refresh list", { tick++ }, Modifier.fillMaxWidth())
        Text("Paper", style = MaterialTheme.typography.titleMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(selected = dots == PrinterController.DOTS_58MM, onClick = { dots = PrinterController.DOTS_58MM; printer.paperDots = dots }, label = { Text("58 mm") })
            FilterChip(selected = dots == PrinterController.DOTS_80MM, onClick = { dots = PrinterController.DOTS_80MM; printer.paperDots = dots }, label = { Text("80 mm") })
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Cut paper after each bill", Modifier.weight(1f))
            Switch(checked = autoCut, onCheckedChange = { autoCut = it; printer.autoCut = it })
        }
        message?.let { Text(it, color = Anylo.colors.text2) }
    }
}
