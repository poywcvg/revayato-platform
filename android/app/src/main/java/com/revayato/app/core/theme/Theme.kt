package com.revayato.app.core.theme

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp

private val RevayatoColors = darkColorScheme(
    primary = BrandMint,
    onPrimary = OnBrand,
    primaryContainer = BrandGreen,
    onPrimaryContainer = TextPrimary,
    secondary = BrandGreen,
    onSecondary = TextPrimary,
    secondaryContainer = SurfaceSelected,
    onSecondaryContainer = TextPrimary,
    tertiary = BrandMintActive,
    onTertiary = OnBrand,
    background = BgMain,
    onBackground = TextPrimary,
    surface = BgSurface,
    onSurface = TextPrimary,
    surfaceVariant = BgElevated,
    onSurfaceVariant = TextSecondary,
    surfaceContainer = BgSoft,
    surfaceContainerHigh = BgElevated,
    surfaceContainerHighest = SurfaceHover,
    outline = OutlineSoft,
    outlineVariant = OutlineSoft,
    error = ErrorRed,
    onError = TextPrimary,
    scrim = ScrimStrong,
)

private val RevayatoShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp),
    small = RoundedCornerShape(12.dp),
    medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(22.dp),
    extraLarge = RoundedCornerShape(28.dp),
)

@Composable
fun RevayatoTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = RevayatoColors,
        typography = RevayatoTypography,
        shapes = RevayatoShapes,
        content = content,
    )
}
