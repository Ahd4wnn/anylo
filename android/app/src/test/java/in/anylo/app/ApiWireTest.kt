package `in`.anylo.app

import `in`.anylo.app.core.ChangePasswordReq
import `in`.anylo.app.core.LoginReq
import kotlinx.serialization.json.Json
import org.junit.Assert.assertTrue
import org.junit.Test

/** Without "platform":"android" the server issues a web cookie session and the app is logged out on every restart. */
class ApiWireTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false } // same as Session.json

    @Test fun loginAlwaysSendsPlatform() {
        assertTrue(json.encodeToString(LoginReq.serializer(), LoginReq("a@b.in", "x")).contains("\"platform\":\"android\""))
        assertTrue(json.encodeToString(ChangePasswordReq.serializer(), ChangePasswordReq("a", "b")).contains("\"platform\":\"android\""))
    }
}
