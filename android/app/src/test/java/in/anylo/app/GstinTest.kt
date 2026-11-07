package `in`.anylo.app

import `in`.anylo.app.core.Gstin
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Test

/** Same vectors as the backend and web (backend/tests/fixtures/gst_cases.json). */
class GstinTest {
    @Test fun matchesSharedFixtures() {
        val text = javaClass.classLoader!!.getResource("gst_cases.json")!!.readText()
        val cases = Json.parseToJsonElement(text).jsonObject["gstin"]!!.jsonArray
        check(cases.size >= 10)
        for (c in cases) {
            val o = c.jsonObject
            val gstin = o["gstin"]!!.jsonPrimitive.content
            assertEquals(gstin, o["valid"]!!.jsonPrimitive.boolean, Gstin.isValid(gstin))
        }
    }
}
