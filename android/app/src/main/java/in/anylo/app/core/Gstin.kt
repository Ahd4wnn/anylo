package `in`.anylo.app.core

/** Port of backend/app/services/gst/india.py (docs/06-gst.md §8). Tested against shared fixtures. */
object Gstin {
    private const val CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    private val PATTERN = Regex("^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
    private val STATES = (listOf("25", "28", "97") + (1..38).filter { it != 25 && it != 28 }.map { "%02d".format(it) }).toSet()

    fun isValid(v: String): Boolean =
        PATTERN.matches(v) && v.substring(0, 2) in STATES && checkChar(v) == v[14]

    private fun checkChar(v: String): Char {
        var total = 0
        for (i in 0 until 14) {
            val p = CHARS.indexOf(v[i]) * (if (i % 2 == 0) 1 else 2)
            total += p / 36 + p % 36
        }
        return CHARS[(36 - total % 36) % 36]
    }
}
