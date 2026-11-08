package `in`.anylo.app.print

import java.io.ByteArrayOutputStream

/**
 * Pure ESC/POS raster helpers (ported unchanged from PlantBill). No Android dependencies, so it is
 * unit-testable on the JVM. Receipts are drawn to a bitmap (Android's text engine shapes Indic
 * scripts and the ₹ sign) and packed here into `GS v 0` commands.
 */
object RasterEscPos {
    /** ESC @ — initialise the printer. */
    val INIT: ByteArray = byteArrayOf(0x1b, 0x40)

    /** GS V 66 0 — feed and full cut. */
    val CUT: ByteArray = byteArrayOf(0x1d, 0x56, 0x42, 0x00)

    /** `mono[y * width + x] == true` is a black dot; tall images are split into bands of [bandRows]. */
    fun raster(mono: BooleanArray, width: Int, height: Int, bandRows: Int = 128): ByteArray {
        require(mono.size == width * height) { "mono size ${mono.size} != $width x $height" }
        val bytesPerRow = (width + 7) / 8
        val out = ByteArrayOutputStream()
        var row = 0
        while (row < height) {
            val rows = minOf(bandRows, height - row)
            out.write(0x1d); out.write(0x76); out.write(0x30); out.write(0x00)
            out.write(bytesPerRow and 0xff); out.write((bytesPerRow ushr 8) and 0xff)
            out.write(rows and 0xff); out.write((rows ushr 8) and 0xff)
            val band = ByteArray(bytesPerRow * rows)
            for (r in 0 until rows) {
                val srcY = row + r
                val base = r * bytesPerRow
                for (x in 0 until width) {
                    if (mono[srcY * width + x]) {
                        val idx = base + (x ushr 3)
                        band[idx] = (band[idx].toInt() or (0x80 ushr (x and 7))).toByte()
                    }
                }
            }
            out.write(band)
            row += rows
        }
        return out.toByteArray()
    }
}
