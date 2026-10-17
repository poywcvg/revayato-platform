package com.revayato.app.core.theme

import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

/**
 * Every color the app draws with, in two sets that mirror the website's
 * `:root` (dark) and `html[data-theme="light"]` tokens. The accent is the
 * روایتو green: calm mint on dark, pine on light, never neon. The amber of the
 * logo stays in the logo and in star ratings.
 */
@Immutable
data class RevayatoPalette(
    val isDark: Boolean,
    val brand: Color,
    val brandHover: Color,
    val brandActive: Color,
    val brandDeep: Color,
    val brandDeepHover: Color,
    val onBrand: Color,
    val brandCream: Color,
    val bgMain: Color,
    val bgSoft: Color,
    val bgSurface: Color,
    val bgElevated: Color,
    val surfaceHover: Color,
    val surfaceSelected: Color,
    val textPrimary: Color,
    val textSecondary: Color,
    val textMuted: Color,
    val outlineSoft: Color,
    val errorRed: Color,
    val starGold: Color,
    val playAccentSoft: Color,
    val downloadAccent: Color,
    val downloadAccentSoft: Color,
    val onDownloadAccent: Color,
    val neutralSurface: Color,
    val neutralSurfaceActive: Color,
    val accentYellow: Color,
    val accentRed: Color,
    val accentBlue: Color,
)

val DarkPalette = RevayatoPalette(
    isDark = true,
    brand = Color(0xFFB0E4CC),
    brandHover = Color(0xFFC8EFDC),
    brandActive = Color(0xFF8FD4B4),
    brandDeep = Color(0xFF408A71),
    brandDeepHover = Color(0xFF54A287),
    onBrand = Color(0xFF07110D),
    brandCream = Color(0xFFE6F5EE),
    bgMain = Color(0xFF15161B),
    bgSoft = Color(0xFF101116),
    bgSurface = Color(0xFF0A0B0E),
    bgElevated = Color(0xFF181A21),
    surfaceHover = Color(0xFF20232B),
    surfaceSelected = Color(0xFF232D2A),
    textPrimary = Color(0xFFF7F8F7),
    textSecondary = Color(0xFFC9CDCB),
    textMuted = Color(0xFF969B9A),
    outlineSoft = Color(0xFF2E323C),
    errorRed = Color(0xFFE5484D),
    starGold = Color(0xFFF5C518),
    playAccentSoft = Color(0x1FB0E4CC),
    downloadAccent = Color(0xFFE3E8E6),
    downloadAccentSoft = Color(0x14FFFFFF),
    onDownloadAccent = Color(0xFF101614),
    neutralSurface = Color(0x14FFFFFF),
    neutralSurfaceActive = Color(0x26FFFFFF),
    accentYellow = Color(0xFFD9B26A),
    accentRed = Color(0xFFD98C84),
    accentBlue = Color(0xFF8FA8C7),
)

val LightPalette = RevayatoPalette(
    isDark = false,
    brand = Color(0xFF176B50),
    brandHover = Color(0xFF12583F),
    brandActive = Color(0xFF0D4633),
    brandDeep = Color(0xFF0D3F30),
    brandDeepHover = Color(0xFF12583F),
    onBrand = Color(0xFFFFFFFF),
    brandCream = Color(0xFFE6F2EC),
    bgMain = Color(0xFFF4F7F5),
    bgSoft = Color(0xFFEAF0EC),
    bgSurface = Color(0xFFFFFFFF),
    bgElevated = Color(0xFFFFFFFF),
    surfaceHover = Color(0xFFF0F6F2),
    surfaceSelected = Color(0xFFE6F2EC),
    textPrimary = Color(0xFF17211C),
    textSecondary = Color(0xFF455149),
    textMuted = Color(0xFF66736B),
    outlineSoft = Color(0xFFD7E0DA),
    errorRed = Color(0xFFB32631),
    starGold = Color(0xFFC99A06),
    playAccentSoft = Color(0x1A176B50),
    downloadAccent = Color(0xFF17211C),
    downloadAccentSoft = Color(0x0F17211C),
    onDownloadAccent = Color(0xFFFFFFFF),
    neutralSurface = Color(0x0D17211C),
    neutralSurfaceActive = Color(0x1C17211C),
    accentYellow = Color(0xFF946200),
    accentRed = Color(0xFFA94D2F),
    accentBlue = Color(0xFF3D6389),
)

val LocalRevayatoPalette = staticCompositionLocalOf { DarkPalette }

// Read-only accessors so screens keep writing `TextPrimary`, `Brand`, … and
// pick up whichever theme is active.
val Brand: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.brand
val BrandHover: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.brandHover
val BrandActive: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.brandActive
val BrandDeep: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.brandDeep
val BrandDeepHover: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.brandDeepHover
val OnBrand: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.onBrand
val BrandCream: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.brandCream

val BgMain: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.bgMain
val BgSoft: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.bgSoft
val BgSurface: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.bgSurface
val BgElevated: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.bgElevated
val SurfaceHover: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.surfaceHover
val SurfaceSelected: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.surfaceSelected

val TextPrimary: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.textPrimary
val TextSecondary: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.textSecondary
val TextMuted: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.textMuted
val OutlineSoft: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.outlineSoft
val ErrorRed: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.errorRed
val StarGold: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.starGold

val ScrimStrong = Color(0xCC000000)
val ScrimSoft = Color(0x66000000)

// Online play is the one filled brand button on a screen; download sits
// beside it as a quiet ink/cream secondary.
val PlayAccent: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.brand
val PlayAccentSoft: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.playAccentSoft
val OnPlayAccent: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.onBrand
val DownloadAccent: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.downloadAccent
val DownloadAccentSoft: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.downloadAccentSoft
val OnDownloadAccent: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.onDownloadAccent

// Neutral interactive surfaces (chips, secondary rows): a faint wash of the
// text color, so they work on either ground.
val NeutralSurface: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.neutralSurface
val NeutralSurfaceActive: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.neutralSurfaceActive

// Home accent trio (زرد / قرمز / آبی) for discovery shelves and genre chips.
// Dusty on dark, deepened on light so they stay readable on white.
val AccentYellow: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.accentYellow
val AccentYellowSoft: Color @Composable @ReadOnlyComposable get() = AccentYellow.copy(alpha = 0.12f)
val AccentRed: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.accentRed
val AccentRedSoft: Color @Composable @ReadOnlyComposable get() = AccentRed.copy(alpha = 0.12f)
val AccentBlue: Color @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.accentBlue
val AccentBlueSoft: Color @Composable @ReadOnlyComposable get() = AccentBlue.copy(alpha = 0.12f)

/** True while the dark palette is active — for the few places that pick artwork per theme. */
val IsDarkTheme: Boolean @Composable @ReadOnlyComposable get() = LocalRevayatoPalette.current.isDark
