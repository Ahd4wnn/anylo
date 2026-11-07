package `in`.anylo.app

import android.app.Application
import `in`.anylo.app.core.Session
import `in`.anylo.app.core.TokenStore

/** Manual DI: one session for the whole app (docs/14-android.md notes why Hilt was dropped). */
class AnyloApp : Application() {
    val session by lazy { Session(TokenStore(this)) }
}
