package `in`.anylo.app

import `in`.anylo.app.core.voiceScore
import `in`.anylo.app.gst.GstEngine
import `in`.anylo.app.gst.GstException
import `in`.anylo.app.gst.GstLine
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

/** The backend's gst_cases.json is the single source of truth for every platform. */
class GstEngineTest {
    private fun JsonObject.str(k: String) = this[k]?.jsonPrimitive?.content
    private fun dec(s: String?) = BigDecimal(s ?: "0")
    private val camel = { k: String -> Regex("_(\\w)").replace(k) { it.groupValues[1].uppercase() } }

    @Test fun matchesSharedFixtures() {
        val text = javaClass.classLoader!!.getResource("gst_cases.json")!!.readText()
        val cases = Json.parseToJsonElement(text).jsonObject["cases"]!!.jsonArray
        check(cases.size >= 10)
        for (el in cases) {
            val c = el.jsonObject
            val id = c.str("id")
            val run = {
                GstEngine.compute(
                    c["lines"]!!.jsonArray.map { l ->
                        val o = l.jsonObject
                        GstLine(dec(o.str("qty")), dec(o.str("unit_price")), dec(o.str("rate")),
                            priceIncludesTax = o["price_includes_tax"]?.jsonPrimitive?.boolean ?: true, lineDiscount = dec(o.str("line_discount")))
                    },
                    c.str("supply_type") ?: "intra", c.str("scheme") ?: "regular", c.str("discount_type"),
                    dec(c.str("discount_value")), c["round_off"]?.jsonPrimitive?.boolean ?: true,
                )
            }
            val code = c.str("expect_error")
            if (code != null) {
                val e = runCatching { run() }.exceptionOrNull()
                assertTrue("$id should fail", e is GstException)
                assertEquals(id, code, (e as GstException).code)
                continue
            }
            val out = run()
            val expect = c["expect"]!!.jsonObject
            fun get(obj: Any, k: String) = obj.javaClass.getMethod("get" + camel(k).replaceFirstChar(Char::uppercase)).invoke(obj) as BigDecimal
            expect["lines"]?.jsonArray?.forEachIndexed { i, l ->
                l.jsonObject.forEach { (k, v) -> assertEquals("$id line $i $k", dec(v.jsonPrimitive.content).setScale(2), get(out.lines[i], k).setScale(2)) }
            }
            expect.filterKeys { it != "lines" }.forEach { (k, v) ->
                assertEquals("$id $k", dec(v.jsonPrimitive.content).setScale(2), get(out, k).setScale(2))
            }
        }
    }

    @Test fun voiceMatchesIndianEnglish() {
        val names = listOf("Basmati Rice 5kg", "Sunflower Oil", "Toor Dal", "Phenyl Cleaner", "Biscuits")
        fun best(s: String) = names.maxBy { voiceScore(s, it) }
        assertEquals("Basmati Rice 5kg", best("basmati rice"))
        assertEquals("Sunflower Oil", best("oil"))
        assertEquals("Phenyl Cleaner", best("fenyl cleaner"))
        assertEquals("Toor Dal", best("tur daal"))
        assertEquals("Biscuits", best("biskets"))
        assertTrue(voiceScore("hammer", "Sunflower Oil") < 0.5)
    }
}
