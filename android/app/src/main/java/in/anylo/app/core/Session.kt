package `in`.anylo.app.core

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import `in`.anylo.app.BuildConfig
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.Authenticator
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.Route
import retrofit2.HttpException
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.io.IOException
import java.util.concurrent.TimeUnit

/** Refresh token and chosen shop, encrypted at rest (Keystore). Built lazily: Keystore init can be slow. */
class TokenStore(private val context: Context) {
    private val prefs: SharedPreferences by lazy {
        try {
            EncryptedSharedPreferences.create(
                context, "anylo_secure",
                MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
            )
        } catch (e: Exception) {
            // Broken Keystore on some devices: fall back rather than lock the user out.
            context.getSharedPreferences("anylo_fallback", Context.MODE_PRIVATE)
        }
    }
    var refreshToken: String?
        get() = prefs.getString("refresh", null)
        set(v) = prefs.edit().putString("refresh", v).apply()
    var shopId: String?
        get() = prefs.getString("shop", null)
        set(v) = prefs.edit().putString("shop", v).apply()
}

/** Holds the in-memory access token and performs single-flight refresh on 401. */
class Session(private val store: TokenStore) {
    @Volatile var accessToken: String? = null
    private val _loggedOut = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    val loggedOut = _loggedOut.asSharedFlow()
    private val lock = Any()

    val json = Json { ignoreUnknownKeys = true; explicitNulls = false; coerceInputValues = true }

    private val authInterceptor = Interceptor { chain ->
        val b = chain.request().newBuilder()
        accessToken?.let { b.header("Authorization", "Bearer $it") }
        store.shopId?.let { b.header("X-Shop-Id", it) }
        chain.proceed(b.build())
    }

    private val authenticator = object : Authenticator {
        override fun authenticate(route: Route?, response: Response): Request? {
            if (response.request.url.encodedPath.contains("/auth/")) return null
            val used = response.request.header("Authorization")?.removePrefix("Bearer ")
            synchronized(lock) {
                if (accessToken != null && accessToken != used) {
                    return response.request.newBuilder().header("Authorization", "Bearer $accessToken").build()
                }
                val ok = runBlocking { refresh() }
                if (!ok) return null
            }
            return response.request.newBuilder().header("Authorization", "Bearer $accessToken").build()
        }
    }

    private val retrofit: Retrofit = Retrofit.Builder()
        .baseUrl(BuildConfig.API_BASE_URL)
        .client(
            OkHttpClient.Builder()
                .connectTimeout(20, TimeUnit.SECONDS).readTimeout(30, TimeUnit.SECONDS)
                .addInterceptor(authInterceptor).authenticator(authenticator).build(),
        )
        .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
        .build()
    val api: AnyloApi = retrofit.create(AnyloApi::class.java)
    val catalogue: CatalogueApi = retrofit.create(CatalogueApi::class.java)
    val sales: SalesApi = retrofit.create(SalesApi::class.java)
    val money: MoneyApi = retrofit.create(MoneyApi::class.java)
    val buying: PurchasingApi = retrofit.create(PurchasingApi::class.java)
    val reports: ReportsApi = retrofit.create(ReportsApi::class.java)

    /** true = new tokens; false = session really invalid (logged out). Network errors throw. */
    suspend fun refresh(): Boolean {
        val rt = store.refreshToken ?: return false
        return try {
            accept(api.refresh(RefreshReq(rt)))
            true
        } catch (e: HttpException) {
            if (e.code() == 401) { clear(); false } else throw e
        }
    }

    fun accept(t: Tokens) {
        accessToken = t.accessToken
        t.refreshToken?.let { store.refreshToken = it }
    }

    fun clear() {
        accessToken = null
        store.refreshToken = null
        _loggedOut.tryEmit(Unit)
    }

    val refreshTokenOrNull get() = store.refreshToken
    var shopId: String?
        get() = store.shopId
        set(v) { store.shopId = v }

    /** Machine code (e.g. "invoice.approval_required") and plain-language message. Reads the error body once: OkHttp can't re-read it. */
    fun errorOf(e: Throwable): Pair<String?, String> = when (e) {
        is HttpException -> {
            val body = runCatching { json.decodeFromString(ErrorBody.serializer(), e.response()?.errorBody()?.string().orEmpty()) }.getOrNull()
            body?.code to ((body?.detail as? JsonPrimitive)?.content
                ?: if (e.code() == 422) "Please check the details you entered." else "Something went wrong (${e.code()}).")
        }
        is IOException -> null to "Can't reach Anylo. Check your internet connection."
        else -> null to "Something went wrong. Please try again."
    }

    /** Plain-language message from any API/network failure. */
    fun messageOf(e: Throwable): String = errorOf(e).second
}
