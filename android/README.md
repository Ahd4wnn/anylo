# Anylo Android

Kotlin + Jetpack Compose + Hilt + Retrofit. Uses the same `/v1` API as the web.

- Spec: [docs/14-android.md](../docs/14-android.md)
- POS behaviour and printing: [docs/07-pos-billing.md](../docs/07-pos-billing.md)

Release signing uses `keystore.properties` (git-ignored). Never commit APK/AAB files.

## Build

Requires the Android SDK (platform 36) and JDK 17+ (Android Studio's bundled JBR works).

```bash
echo "sdk.dir=C:/Users/<you>/AppData/Local/Android/Sdk" > local.properties   # forward slashes
JAVA_HOME="/c/Program Files/Android/Android Studio/jbr" ./gradlew assembleDevDebug testDevDebugUnitTest
```

The `dev` flavor talks to the local API at `http://10.0.2.2:8000/v1/` (the emulator's alias for your laptop).
Unit tests read the shared GST fixtures straight from `backend/tests/fixtures/`.
