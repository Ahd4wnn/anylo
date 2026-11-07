package `in`.anylo.app.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// "Mist" tokens from design/tokens.json (docs/12-design-system.md §2).
@Immutable
data class AnyloColors(
    val bg: Color, val surface: Color, val surface2: Color, val tint: Color, val border: Color,
    val text: Color, val text2: Color, val text3: Color, val primary: Color, val onPrimary: Color,
    val primarySoft: Color, val onPrimarySoft: Color, val brand: Color, val logo: Color,
    val success: Color, val successSoft: Color, val warning: Color, val warningSoft: Color,
    val danger: Color, val dangerSoft: Color,
)

val LightMist = AnyloColors(
    bg = Color(0xFFF7F8FC), surface = Color(0xFFFFFFFF), surface2 = Color(0xFFF2F4F9), tint = Color(0xFFEEF1FB),
    border = Color(0xFFE4E7F0), text = Color(0xFF1F2433), text2 = Color(0xFF5D6478), text3 = Color(0xFF8A90A3),
    primary = Color(0xFF4A5AE0), onPrimary = Color.White, primarySoft = Color(0xFFEEF0FE), onPrimarySoft = Color(0xFF3D4CCB),
    brand = Color(0xFF5B6CF0), logo = Color(0xFF4F6BFF), success = Color(0xFF2F8466), successSoft = Color(0xFFE6F4EE),
    warning = Color(0xFF9A6B12), warningSoft = Color(0xFFFBF3E2), danger = Color(0xFFC0444A), dangerSoft = Color(0xFFFBECEC),
)

val DarkMist = AnyloColors(
    bg = Color(0xFF12141C), surface = Color(0xFF1A1D28), surface2 = Color(0xFF222634), tint = Color(0xFF232846),
    border = Color(0xFF2A2F3E), text = Color(0xFFE8EAF2), text2 = Color(0xFFA3A9BC), text3 = Color(0xFF7A8196),
    primary = Color(0xFF8C96FF), onPrimary = Color(0xFF12141C), primarySoft = Color(0xFF262B4D), onPrimarySoft = Color(0xFFC5CBFF),
    brand = Color(0xFF8C96FF), logo = Color(0xFF4F6BFF), success = Color(0xFF5CC59E), successSoft = Color(0xFF18302A),
    warning = Color(0xFFE6BC6A), warningSoft = Color(0xFF33291A), danger = Color(0xFFEE7E83), dangerSoft = Color(0xFF3A2024),
)

val LocalColors = staticCompositionLocalOf { LightMist }

object Anylo {
    val colors: AnyloColors @Composable get() = LocalColors.current
}

private val type = Typography(
    headlineMedium = TextStyle(fontSize = 28.sp, fontWeight = FontWeight.Bold, lineHeight = 34.sp, letterSpacing = (-0.5).sp),
    titleLarge = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.SemiBold, lineHeight = 28.sp),
    titleMedium = TextStyle(fontSize = 17.sp, fontWeight = FontWeight.SemiBold, lineHeight = 24.sp),
    bodyLarge = TextStyle(fontSize = 16.sp, lineHeight = 24.sp),
    bodyMedium = TextStyle(fontSize = 14.sp, lineHeight = 20.sp),
    labelLarge = TextStyle(fontSize = 16.sp, fontWeight = FontWeight.SemiBold),
)

@Composable
fun AnyloTheme(content: @Composable () -> Unit) {
    val c = if (isSystemInDarkTheme()) DarkMist else LightMist
    val scheme = (if (isSystemInDarkTheme()) darkColorScheme() else lightColorScheme()).copy(
        primary = c.primary, onPrimary = c.onPrimary, background = c.bg, surface = c.surface,
        onBackground = c.text, onSurface = c.text, onSurfaceVariant = c.text2, outline = c.border, error = c.danger,
        surfaceVariant = c.surface2, primaryContainer = c.primarySoft, onPrimaryContainer = c.onPrimarySoft,
    )
    androidx.compose.runtime.CompositionLocalProvider(LocalColors provides c) {
        MaterialTheme(colorScheme = scheme, typography = type, content = content)
    }
}
