# 15 · iOS app

Native **Swift + SwiftUI** client for the same `/v1` API. It is built after Android reaches feature parity (`19-roadmap.md`, M8). This doc is complete enough to start without further design work.

## 1. Stack

| Concern | Choice |
|---|---|
| Language / UI | Swift 5.10+ (Swift 6 language mode when dependencies allow), SwiftUI, Observation (`@Observable`) |
| Minimum | iOS 17.0 (iPhone + iPad) |
| Project | Xcode project + Swift Package Manager; modules as local packages: `AnyloCore`, `AnyloDesign`, `AnyloFeatures` |
| Networking | URLSession + async/await; `APIClient` with `Endpoint` (ported idea from PlantBill), `JSONDecoder` snake_case, `Decimal` for money (decoded from strings by a custom `MoneyString` wrapper) |
| Auth storage | Keychain (access + refresh), `KeychainStore` actor (PlantBill's off-main-thread approach) |
| Local | SwiftData for product cache + held bills; `UserDefaults` for small prefs |
| Scanning | VisionKit `DataScannerViewController` (barcodes) with an AVFoundation fallback |
| Printing | CoreBluetooth **BLE** ESC/POS printers (iOS cannot use classic SPP without MFi); raster via shared `ReceiptRenderer` (CoreGraphics). AirPrint for A4/A5 PDFs |
| QR | CoreImage `CIQRCodeGenerator` |
| Charts | Swift Charts |
| i18n | String Catalog (`Localizable.xcstrings`): en, hi, ml, ta, kn |
| Crash | MetricKit + upload to `/v1/crash-reports` |
| Tests | Swift Testing / XCTest, snapshot tests for the receipt renderer, UI tests for POS |

Bundle id `in.anylo.app`. App Store name "Anylo – Billing & GST".

## 2. Structure

```
ios/
  Anylo.xcodeproj
  Anylo/                     App target: AnyloApp.swift, RootView (role routing), Assets, Info.plist
  Packages/
    AnyloCore/               API client, DTOs, Money/Qty, GstEngine (Swift port + shared fixtures),
                             Auth (TokenStore, SessionStore), Printing (BLE, RasterEscPos, ReceiptRenderer)
    AnyloDesign/             tokens (generated from design/tokens.json), components
    AnyloFeatures/           POS, Sales, Customers, Items, Stock, Purchases, Expenses, Cash, Approvals,
                             Reports, Goals, AI, Settings, Owner, Onboarding
```

Pattern: each feature has a `XView` (SwiftUI) and an `XModel` (`@Observable @MainActor`) that calls repositories in `AnyloCore`.

## 3. Behaviour parity with Android

Same shells per role (`14-android.md` §3), POS behaviour (`07`), held bills, approvals with manager PIN, AI chat with SSE streaming (`URLSession.bytes(for:)` line parsing), and the read-only subscription state with no in-app purchase or steering (`10` §5).

iOS-specific notes:
- Haptics on scan and save (`sensoryFeedback`).
- iPad: split view POS (catalogue | cart).
- Hardware keyboard shortcuts mirror the web (`07` §9) via `.keyboardShortcut`.
- Background refresh is not needed; refresh on foreground.

## 4. Known iOS constraints

| Constraint | Handling |
|---|---|
| Classic Bluetooth printers (most cheap 58 mm SPP printers) don't work | Recommend BLE models in the printer setup screen; keep a tested-printer list in docs; AirPrint or a shared PDF as fallback |
| Web Bluetooth unavailable in Safari | Web POS on iPhone can't print thermal; the native app is the answer |
| App Store review: payments | No subscription purchase in app (`10` §5). Reviewer notes explain the business-account model; a demo account with an active subscription goes in the review notes |
| Camera / microphone / Bluetooth permissions | Purpose strings in Info.plist, requested on first use only |

## 5. Release

- Signing: automatic, team ID in CI secrets; App Store Connect API key for upload.
- CI: `xcodebuild test` on PRs that touch `ios/`. TestFlight upload on the `ios-v*` tag (via `xcrun altool`/`notarytool` successor or fastlane `pilot`).
- Version follows semver tags, and the build number comes from CI.

## 6. Build order (when M8 starts)

1. `AnyloCore`: API client, auth/refresh, Money, GstEngine with shared fixtures passing.
2. Design tokens + core components.
3. Login → role routing → POS (catalogue, cart, payment, checkout, success).
4. BLE printing + receipt renderer snapshot tests.
5. Sales list and detail, customers, collect due.
6. Dashboard, reports and goals (Swift Charts).
7. Items and stock, purchases.
8. AI chat.
9. Settings, onboarding, notifications.
10. TestFlight beta → App Store.
