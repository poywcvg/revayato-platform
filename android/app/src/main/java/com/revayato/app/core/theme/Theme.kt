package com.revayato.app.core.theme

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.unit.dp

private fun RevayatoPalette.toColorScheme(): ColorScheme {
    val base = if (isDark) darkColorScheme() else lightColorScheme()
    return base.copy(
        primary = brand,
        onPrimary = onBrand,
        primaryContainer = surfaceSelected,
        onPrimaryContainer = textPrimary,
        secondary = brandDeep,
        onSecondary = if (isDark) textPrimary else onBrand,
        secondaryContainer = surfaceSelected,
        onSecondaryContainer = textPrimary,
        tertiary = brandActive,
        onTertiary = onBrand,
        background = bgMain,
        onBackground = textPrimary,
        surface = bgSurface,
        onSurface = textPrimary,
        surfaceVariant = bgElevated,
        onSurfaceVariant = textSecondary,
        surfaceContainerLowest = bgSurface,
        surfaceContainerLow = bgSoft,
        surfaceContainer = if (isDark) bgSoft else bgElevated,
        surfaceContainerHigh = bgElevated,
        surfaceContainerHighest = surfaceHover,
        inverseSurface = textPrimary,
        inverseOnSurface = bgMain,
        outline = outlineSoft,
        outlineVariant = outlineSoft,
        error = errorRed,
        onError = if (isDark) textPrimary else onBrand,
        scrim = ScrimStrong,
    )
}

private val DarkScheme = DarkPalette.toColorScheme()
private val LightScheme = LightPalette.toColorScheme()

private val RevayatoShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp),
    small = RoundedCornerShape(12.dp),
    medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(22.dp),
    extraLarge = RoundedCornerShape(28.dp),
)

/**
 * App theme. [darkTheme] picks the palette; the player and watch-party room
 * pass `true` explicitly because video chrome is always dark.
 */
@Composable
fun RevayatoTheme(darkTheme: Boolean = true, content: @Composable () -> Unit) {
    val palette = if (darkTheme) DarkPalette else LightPalette
    CompositionLocalProvider(LocalRevayatoPalette provides palette) {
        MaterialTheme(
            colorScheme = if (darkTheme) DarkScheme else LightScheme,
            typography = RevayatoTypography,
            shapes = RevayatoShapes,
            content = content,
        )
    }
}
