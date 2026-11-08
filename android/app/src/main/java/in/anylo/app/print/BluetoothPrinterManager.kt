package `in`.anylo.app.print

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothSocket
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.OutputStream
import java.util.UUID

data class PrinterDevice(val name: String, val mac: String)

class PrinterException(message: String) : Exception(message)

/**
 * Classic-Bluetooth (SPP/RFCOMM) thermal printer link, ported from PlantBill. A real socket is far
 * more reliable than Web Bluetooth. Callers need BLUETOOTH_CONNECT (API 31+); every method fails
 * with a plain message instead of crashing when it's missing.
 */
class BluetoothPrinterManager(private val context: Context) {
    private val sppUuid: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
    private val adapter: BluetoothAdapter?
        get() = (context.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager)?.adapter
    private var socket: BluetoothSocket? = null
    private var stream: OutputStream? = null

    val isSupported: Boolean get() = adapter != null
    val isEnabled: Boolean get() = adapter?.isEnabled == true

    fun hasPermission(): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.S ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED

    @SuppressLint("MissingPermission")
    fun pairedPrinters(): List<PrinterDevice> {
        if (!hasPermission()) return emptyList()
        return try {
            adapter?.bondedDevices.orEmpty().map { PrinterDevice(it.name ?: "Printer", it.address) }
        } catch (e: SecurityException) {
            emptyList()
        }
    }

    @SuppressLint("MissingPermission")
    suspend fun connect(mac: String): Result<PrinterDevice> = withContext(Dispatchers.IO) {
        if (!hasPermission()) return@withContext Result.failure(PrinterException("Allow Bluetooth so Anylo can reach the printer."))
        val ad = adapter ?: return@withContext Result.failure(PrinterException("This phone has no Bluetooth."))
        if (!ad.isEnabled) return@withContext Result.failure(PrinterException("Please turn on Bluetooth."))
        disconnect()
        try {
            val device = ad.getRemoteDevice(mac)
            val sock = device.createRfcommSocketToServiceRecord(sppUuid)
            ad.cancelDiscovery()
            sock.connect()
            socket = sock
            stream = sock.outputStream
            Result.success(PrinterDevice(device.name ?: "Printer", mac))
        } catch (e: SecurityException) {
            disconnect(); Result.failure(PrinterException("Allow Bluetooth so Anylo can reach the printer."))
        } catch (e: Exception) {
            disconnect(); Result.failure(PrinterException("Couldn't reach the printer. Check it's on and paired."))
        }
    }

    /** Throttled chunks so cheap printer buffers keep up. */
    suspend fun write(bytes: ByteArray): Result<Unit> = withContext(Dispatchers.IO) {
        val os = stream ?: return@withContext Result.failure(PrinterException("No printer connected."))
        try {
            var i = 0
            while (i < bytes.size) {
                val end = minOf(i + 256, bytes.size)
                os.write(bytes, i, end - i)
                os.flush()
                Thread.sleep(12)
                i = end
            }
            Result.success(Unit)
        } catch (e: Exception) {
            disconnect(); Result.failure(PrinterException("Printing stopped. Reconnect the printer and try again."))
        }
    }

    fun disconnect() {
        runCatching { stream?.close() }
        runCatching { socket?.close() }
        stream = null
        socket = null
    }
}
