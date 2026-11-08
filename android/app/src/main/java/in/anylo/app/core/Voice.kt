package `in`.anylo.app.core

import java.text.Normalizer

// Same phonetic matcher as web/src/features/pos/inputs.tsx (PlantBill's, generalised to any product name).

private fun norm(s: String) = Normalizer.normalize(s.lowercase(), Normalizer.Form.NFKD)
    .replace(Regex("[^\\p{L}\\p{N} ]"), " ").replace(Regex("\\s+"), " ").trim()

private fun phonetic(s: String) = norm(s).replace("ph", "f").replace('w', 'v').replace('z', 's')
    .replace(Regex("(.)\\1+"), "$1").replace(Regex("[aeiou]"), "")

private fun lev(a: String, b: String): Int {
    val d = IntArray(b.length + 1) { it }
    for (i in 1..a.length) {
        var prev = d[0]++
        for (j in 1..b.length) {
            val cur = d[j]
            d[j] = minOf(d[j] + 1, d[j - 1] + 1, prev + if (a[i - 1] == b[j - 1]) 0 else 1)
            prev = cur
        }
    }
    return d[b.length]
}

/** Score 0..1 of how well a spoken phrase matches a product name. */
fun voiceScore(spoken: String, name: String): Double {
    val s = norm(spoken); val n = norm(name)
    if (s.isEmpty() || n.isEmpty()) return 0.0
    if (s == n) return 1.0
    if (n.contains(s) || s.contains(n)) return 0.9
    val sw = s.split(" ").toSet(); val nw = n.split(" ")
    val overlap = nw.count { it in sw }.toDouble() / maxOf(nw.size, sw.size)
    val ps = phonetic(s); val pn = phonetic(n)
    val ph = if (ps.isNotEmpty() && pn.isNotEmpty()) 1 - lev(ps, pn).toDouble() / maxOf(ps.length, pn.length) else 0.0
    return maxOf(overlap * 0.85, ph * 0.8, 1 - lev(s, n).toDouble() / maxOf(s.length, n.length))
}
