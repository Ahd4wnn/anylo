package `in`.anylo.app

import `in`.anylo.app.print.RasterEscPos
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test

/** Ported from PlantBill; the web port (web/src/features/printer/escpos.test.ts) uses the same cases. */
class RasterEscPosTest {
    @Test fun init_and_cut_commands() {
        assertArrayEquals(byteArrayOf(0x1b, 0x40), RasterEscPos.INIT)
        assertArrayEquals(byteArrayOf(0x1d, 0x56, 0x42, 0x00), RasterEscPos.CUT)
    }

    @Test fun header_encodes_width_bytes_and_height() {
        val bytes = RasterEscPos.raster(BooleanArray(16) { true }, width = 16, height = 1)
        assertArrayEquals(byteArrayOf(0x1d, 0x76, 0x30, 0x00, 2, 0, 1, 0, 0xFF.toByte(), 0xFF.toByte()), bytes)
    }

    @Test fun msb_first_and_padding() {
        assertEquals(0x80.toByte(), RasterEscPos.raster(BooleanArray(8) { it == 0 }, 8, 1)[8])
        val nine = RasterEscPos.raster(BooleanArray(9) { it == 8 }, 9, 1)
        assertEquals(2.toByte(), nine[4]); assertEquals(0.toByte(), nine[8]); assertEquals(0x80.toByte(), nine[9])
    }

    @Test fun tall_images_split_into_bands() {
        val b = RasterEscPos.raster(BooleanArray(8 * 200), 8, 200, bandRows = 128)
        val headers = (0 until b.size - 2).count { b[it] == 0x1d.toByte() && b[it + 1] == 0x76.toByte() && b[it + 2] == 0x30.toByte() }
        assertEquals(2, headers)
    }
}
