package `in`.anylo.app

import android.app.Application
import `in`.anylo.app.core.Cart
import `in`.anylo.app.core.Session
import `in`.anylo.app.core.TokenStore
import `in`.anylo.app.print.PrinterController

/** Manual DI: one session for the whole app (docs/14-android.md notes why Hilt was dropped). */
class AnyloApp : Application() {
    val session by lazy { Session(TokenStore(this)) }
    val printer by lazy { PrinterController(this) }
    val cart by lazy { Cart(java.io.File(filesDir, "cart.json"), session.json) }
}
