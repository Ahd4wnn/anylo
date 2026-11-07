package `in`.anylo.app

import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import `in`.anylo.app.feature.ForceChangeScreen
import `in`.anylo.app.feature.LoginScreen
import `in`.anylo.app.feature.OnboardingScreen
import `in`.anylo.app.feature.Shell
import `in`.anylo.app.feature.SignupScreen
import `in`.anylo.app.ui.Anylo
import `in`.anylo.app.ui.AnyloTheme

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val session = (application as AnyloApp).session
        val factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = AppState(session) as T
        }
        setContent {
            AnyloTheme {
                val app: AppState = viewModel(factory = factory)
                val auth by app.auth.collectAsStateWithLifecycle()
                // Same routing rules as the web Gate (web/src/main.tsx).
                when (val a = auth) {
                    AuthState.Loading -> Box(Modifier.fillMaxSize().background(Anylo.colors.bg), Alignment.Center) { CircularProgressIndicator(color = Anylo.colors.brand) }
                    AuthState.Anonymous -> {
                        var signup by remember { mutableStateOf(false) }
                        if (signup) SignupScreen(app) { signup = false } else LoginScreen(app) { signup = true }
                    }
                    is AuthState.Ready -> when {
                        a.me.user.mustChangePassword -> ForceChangeScreen(app, a.me.user.fullName)
                        a.me.activeShopId != null && !a.me.onboardingCompleted && "shop.settings" in a.me.permissions -> OnboardingScreen(app, a.me)
                        else -> Shell(app, a.me)
                    }
                }
            }
        }
    }
}
