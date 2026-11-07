package `in`.anylo.app

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import `in`.anylo.app.core.ChangePasswordReq
import `in`.anylo.app.core.LoginReq
import `in`.anylo.app.core.Me
import `in`.anylo.app.core.RefreshReq
import `in`.anylo.app.core.Session
import `in`.anylo.app.core.SignupReq
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

sealed interface AuthState {
    data object Loading : AuthState
    data object Anonymous : AuthState
    data class Ready(val me: Me) : AuthState
}

/** App-wide session state. Network trouble at startup retries; only a real 401 logs out. */
class AppState(val session: Session) : ViewModel() {
    private val _auth = MutableStateFlow<AuthState>(AuthState.Loading)
    val auth: StateFlow<AuthState> = _auth

    init {
        viewModelScope.launch { session.loggedOut.collect { _auth.value = AuthState.Anonymous } }
        viewModelScope.launch { restore() }
    }

    private suspend fun restore() {
        var wait = 1000L
        while (true) {
            try {
                if (!session.refresh()) { _auth.value = AuthState.Anonymous; return }
                loadMe(); return
            } catch (e: Exception) {
                delay(wait); wait = (wait * 2).coerceAtMost(15_000)
            }
        }
    }

    suspend fun loadMe() {
        val me = runCatching { session.api.me() }.getOrElse {
            session.shopId = null // remembered shop may be gone
            session.api.me()
        }
        session.shopId = me.activeShopId
        _auth.value = AuthState.Ready(me)
    }

    suspend fun login(login: String, password: String) {
        session.accept(session.api.login(LoginReq(login.trim(), password, deviceLabel = android.os.Build.MODEL)))
        loadMe()
    }

    suspend fun signup(req: SignupReq) {
        session.accept(session.api.signup(req))
        loadMe()
    }

    suspend fun changePassword(current: String, new: String) {
        session.accept(session.api.changePassword(ChangePasswordReq(current, new)))
        loadMe()
    }

    suspend fun switchShop(id: String) {
        session.shopId = id
        loadMe()
    }

    fun logout() {
        viewModelScope.launch {
            session.refreshTokenOrNull?.let { runCatching { session.api.logout(RefreshReq(it)) } }
            session.shopId = null
            session.clear()
        }
    }

    fun can(permission: String) = (auth.value as? AuthState.Ready)?.me?.permissions?.contains(permission) == true
}
