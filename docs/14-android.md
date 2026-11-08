# 14 · Android app

Kotlin + Jetpack Compose. This is the main counter device for most shops: a cheap Android phone or tablet with a Bluetooth thermal printer. It talks to the same `/v1` API as the web.

## 1. Stack

| Concern | Choice |
|---|---|
| Language / build | Kotlin 2.1+, AGP 8.7+, Gradle version catalog, JDK 17, KSP |
| SDK | minSdk 24, target/compile 36 |
| UI | Compose BOM, Material 3 (themed with Anylo tokens; light + dark), type-safe Navigation-Compose (`@Serializable` routes) |
| DI | Manual: one `Session` in `AnyloApp`, passed to an app-level `AppState` ViewModel. Hilt was dropped in M1 to keep builds light (no annotation processing); revisit if the graph grows past a handful of objects |
| Network | Retrofit + OkHttp + kotlinx.serialization (`ignoreUnknownKeys`, `explicitNulls=false`) |
| Local | SharedPreferences/encrypted prefs; catalogue cached as a JSON file (`ItemScreens.kt`) for instant, offline lists. Room was deferred to keep the build free of annotation processing; revisit if offline billing needs queries |
| Security | EncryptedSharedPreferences/Keystore for tokens (ported `TokenStore`, lazily initialised) |
| Camera / scan | Google code scanner (`play-services-code-scanner`): Google's UI, no camera permission or camera code in the app. CameraX + ML Kit only if continuous POS scanning needs it (M3) |
| Images | Coil |
| QR | ZXing core (local) |
| Charts | Vico (Compose charts), themed |
| Crash | ACRA → `/v1/crash-reports` (ported) + `AnrWatchdog` |
| Tests | JUnit5, Turbine, MockWebServer, Compose UI tests, Robolectric for renderer |
| Lint | ktlint, detekt, Android Lint (warnings as errors on CI) |

Package: `in.anylo.app`. App name "Anylo". Splash: logo mark + motto.

## 2. Architecture

```
app/src/main/java/in/anylo/app/
  AnyloApp.kt  MainActivity.kt  AnrWatchdog.kt
  core/
    network/      ApiClient, AuthInterceptor, TokenAuthenticator (refresh on 401, single-flight),
                  NetworkMonitor (ported), ApiError → UiText
    auth/         TokenStore (multi-account), SessionRepository
    money/        Money (BigDecimal value class), Qty, MoneyFormat (en-IN)
    gst/          GstEngine (Kotlin port; runs the shared gst_cases.json fixtures in unit tests)
    print/        ReceiptRenderer (bitmap), RasterEscPos, PrinterController, transports/{BluetoothSpp, UsbHost}
    i18n/         LocaleManager (AppCompat per-app locale API), UiText
    design/       Theme, Color (generated from tokens), Type, Shape, components/*
  data/
    remote/       *Api.kt + dto/*  (one file per backend router)
    local/        AnyloDatabase (Room), ProductDao, HeldBillDao, CartStore (DataStore)
    repo/         *Repository.kt — DTO ↔ domain mapping, caching policy
  domain/         models (Invoice, Variant, Customer, Goal …) — pure Kotlin
  feature/
    auth/ onboarding/ pos/ sales/ returns/ customers/ items/ stock/ purchases/
    expenses/ labour/ cash/ approvals/ reports/ goals/ ai/ notifications/ settings/ owner/ admin/
      each: XScreen.kt (stateless composables) + XViewModel.kt (StateFlow<UiState>, events)
```

**Rules**
- A screen file stays under 400 lines. PlantBill's 850-line `OwnerShell` is the anti-example.
- ViewModels expose a single `UiState` and accept `UiEvent`s. Strings go through `UiText`.
- Money is never `Double`. Totals displayed before the server confirms come from `GstEngine`.

## 3. Shells by role

| Role | Start | Bottom nav |
|---|---|---|
| salesperson | POS | Sell · Sales · Customers · More |
| manager | Home | Home · Sell · Items · Reports · More |
| owner | Owner overview (shop switcher at top; pick a shop to act as manager) | Home · Sell · Shops · Reports · More |
| admin/support | Admin overview (light: shops, subscriptions, notifications) | Overview · Shops · More |

"Ask Anylo" (the AI manager) is a floating button on Home and Reports for **owners only**.

## 4. POS on Android (see `07-pos-billing.md`)

- Product catalogue comes from the Room cache, synced on start and every 5 min plus on push events. Search over 10k items takes < 30 ms.
- Camera scan sheet: continuous mode with beep and haptic.
- **HID scanner support:** a Bluetooth or USB scanner acts as a keyboard. A hidden focused input on the POS screen captures bursts that end in Enter.
- Voice: `RecognizerIntent` (en-IN, with the user's language as an option) → `PhoneticMatcher` → top-3 picker.
- Cart persists in DataStore. Held bills sync with the server and are mirrored in Room.
- **Connectivity loss:** a non-blocking banner replaces PlantBill's blocking dialog. Billing continues into a **held bill** marked "Not saved – will retry". When the network returns, the user taps **Save all** to check out each one with its original idempotency key. A full automatic offline queue is a later milestone.
- Printing:
  - Classic Bluetooth SPP (UUID `00001101-0000-1000-8000-00805F9B34FB`) and USB host.
  - Connect → print → disconnect under a mutex with 3 retries (ported `PrinterController`).
  - 58/80 mm, auto-print, copies.
  - Bluetooth permissions (`BLUETOOTH_CONNECT`/`SCAN` on API 31+) are requested only when the printer settings screen opens.
- UPI QR is generated locally from the shop VPA.
- Share: Android share sheet with the PDF (`/invoices/{id}/pdf` downloaded to cache via a FileProvider) or the WhatsApp intent.

## 5. Other screens

These mirror the web feature list, phone-optimised:
- Dashboard (tiles + Vico charts + goals)
- Sales and invoice detail (actions: print, PDF, WhatsApp, collect, return, cancel)
- Customers and ledger
- Items (with variant editor and label printing to a Bluetooth label printer: later)
- Stock count with scan-to-count
- Purchases (scan items into a purchase)
- Expenses, labour, borrowings, cash/day close, approvals
- Reports with Excel download (opens with the system viewer)
- GST summary (view + download)
- Goals, AI chat, notifications
- Settings: business, tax (view; edits on web or O only), printer, language, staff, account/sessions
- Subscription **status** only (`10` §5)

## 6. i18n

- `res/values{,-hi,-ml,-ta,-kn}/strings.xml`.
- Per-app language uses the AppCompat `AppCompatDelegate.setApplicationLocales` (requires `AppCompatActivity` + AppCompat theme parent) with `locales_config.xml`. This replaces PlantBill's `attachBaseContext` wrapper.
- `bundle { language { enableSplit = false } }` so switching language never needs a download.
- Receipt labels follow the shop's receipt-language setting, independent of the UI language.

## 7. Build, signing, release

- Flavors: `dev` (API `http://10.0.2.2:8000/v1`, cleartext only in a debug network-security-config), `staging`, `prod`.
- `keystore.properties` (git-ignored). **The release build fails if signing config is missing** (no silent debug signing).
- `versionCode` derives from CI build number. `versionName` follows semver from a git tag (`android-v1.2.0`).
- R8 full mode, kotlinx.serialization keep rules, native debug symbols.
- Artifacts are uploaded to GitHub Releases and the Play Console internal track by CI. **Never committed.**
- Play listing assets: feature graphic with the motto, phone + tablet screenshots, data safety form (camera, Bluetooth, microphone for voice; no data sold).

## 8. Tests

- Unit tests:
  - `Money`, `GstEngine` (shared fixtures), cart math, `PhoneticMatcher`, `RasterEscPos`, `TokenAuthenticator` single-flight refresh, ViewModels (Turbine).
- Instrumented tests:
  - receipt render snapshot (all five scripts, 58 and 80 mm)
  - POS happy path (Compose UI + MockWebServer)
  - locale resources present for every key
- Contract test: DTOs deserialize every example in `openapi.snapshot.json`.
