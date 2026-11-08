package `in`.anylo.app.print

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import kotlinx.coroutines.delay
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * Printing facade, ported from PlantBill. One shared SPP printer serves several phones but accepts
 * only one connection at a time, so every print is connect → write → ALWAYS disconnect, serialised
 * by a mutex. The chosen printer is only remembered (its MAC), never kept connected.
 */
class PrinterController(context: Context) {
    private val manager = BluetoothPrinterManager(context)
    private val prefs = context.getSharedPreferences("anylo_printer", Context.MODE_PRIVATE)
    private val mutex = Mutex()

    val isSupported get() = manager.isSupported
    val isEnabled get() = manager.isEnabled
    fun hasPermission() = manager.hasPermission()
    fun pairedPrinters() = manager.pairedPrinters()

    var rememberedMac: String?
        get() = prefs.getString("mac", null)
        private set(v) = prefs.edit().putString("mac", v).apply()
    var paperDots: Int
        get() = prefs.getInt("dots", DOTS_58MM)
        set(v) = prefs.edit().putInt("dots", v).apply()
    var autoCut: Boolean
        get() = prefs.getBoolean("autocut", true)
        set(v) = prefs.edit().putBoolean("autocut", v).apply()

    /** Verify the printer answers right now, release it, then remember it. */
    suspend fun select(device: PrinterDevice): Result<PrinterDevice> = mutex.withLock {
        val r = connectWithRetry(device.mac)
        manager.disconnect()
        if (r.isSuccess) rememberedMac = device.mac
        r
    }

    /** The printer may have just been released by another phone, so retry briefly. */
    private suspend fun connectWithRetry(mac: String): Result<PrinterDevice> {
        var last: Result<PrinterDevice> = Result.failure(PrinterException("Couldn't reach the printer."))
        repeat(3) { i ->
            last = manager.connect(mac)
            if (last.isSuccess) return last
            if (i < 2) delay(500)
        }
        return last
    }

    suspend fun print(buildBitmap: () -> Bitmap): Result<Unit> = mutex.withLock {
        val mac = rememberedMac ?: return@withLock Result.failure(PrinterException("Choose a printer in Settings → Printer first."))
        connectWithRetry(mac).onFailure { return@withLock Result.failure(it) }
        try {
            val bmp = buildBitmap()
            val bytes = RasterEscPos.INIT + toRaster(bmp) + byteArrayOf(0x0a, 0x0a, 0x0a, 0x0a) +
                (if (autoCut) RasterEscPos.CUT else byteArrayOf(0x0a, 0x0a, 0x0a))
            bmp.recycle()
            manager.write(bytes)
        } finally {
            manager.disconnect() // release no matter what, so the next phone can print
        }
    }

    suspend fun printTest(): Result<Unit> {
        val label = pairedPrinters().firstOrNull { it.mac == rememberedMac }?.name ?: "Bluetooth"
        return print { testBitmap(paperDots, label) }
    }

    companion object {
        const val DOTS_58MM = 384
        const val DOTS_80MM = 576

        fun toRaster(bmp: Bitmap): ByteArray {
            val w = bmp.width
            val h = bmp.height
            val px = IntArray(w * h)
            bmp.getPixels(px, 0, w, 0, 0, w, h)
            val mono = BooleanArray(px.size) { i ->
                val c = px[i]
                val luma = (Color.red(c) * 299 + Color.green(c) * 587 + Color.blue(c) * 114) / 1000
                Color.alpha(c) > 127 && luma < 128
            }
            return RasterEscPos.raster(mono, w, h)
        }

        /** Proves width, the ₹ sign and Indic scripts all print (drawn as an image, not printer fonts). */
        fun testBitmap(dots: Int, connection: String): Bitmap {
            val lines = listOf(
                "TEST PRINT" to 40f, "Anylo printer is working" to 24f, "Printer: $connection" to 22f,
                "Paper: ${if (dots == DOTS_80MM) "80 mm" else "58 mm"} ($dots dots)" to 22f,
                "₹1,25,450.75" to 32f, "नमस्ते · നന്ദി · நன்றி · ಧನ್ಯವಾದ" to 24f,
            )
            val height = lines.sumOf { (it.second + 14).toInt() } + 40
            val bmp = Bitmap.createBitmap(dots, height, Bitmap.Config.ARGB_8888)
            val c = Canvas(bmp)
            c.drawColor(Color.WHITE)
            val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.BLACK; textAlign = Paint.Align.CENTER }
            var y = 10f
            lines.forEachIndexed { i, (text, size) ->
                paint.textSize = size
                paint.typeface = if (i == 0 || i == 4) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
                y += size + 14
                c.drawText(text, dots / 2f, y, paint)
            }
            c.drawRect(0f, y + 14, dots.toFloat(), y + 18, paint) // full-width bar shows if width matches the head
            return bmp
        }
    }
}
