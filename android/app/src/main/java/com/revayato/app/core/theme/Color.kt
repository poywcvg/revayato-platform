package com.revayato.app.core.theme

import androidx.compose.ui.graphics.Color

// Brand palette mirrored from the Nuxt web app (dark-first cinema theme).
val BrandMint = Color(0xFFB0E4CC)
val BrandMintHover = Color(0xFFC8EFDC)
val BrandMintActive = Color(0xFF8FD4B4)
val BrandGreen = Color(0xFF408A71)
val BrandGreenHover = Color(0xFF54A287)
val OnBrand = Color(0xFF0D1A14)

val BgMain = Color(0xFF15161B)
val BgSoft = Color(0xFF101116)
val BgSurface = Color(0xFF0A0B0E)
val BgElevated = Color(0xFF181A21)
val SurfaceHover = Color(0xFF20232B)
val SurfaceSelected = Color(0xFF2A2E38)

val TextPrimary = Color(0xFFF7F8F7)
val TextSecondary = Color(0xFFC9CDCB)
val TextMuted = Color(0xFF969B9A)
val OutlineSoft = Color(0xFF2E323C)
val ErrorRed = Color(0xFFE5484D)
val StarGold = Color(0xFFF5C518)

val ScrimStrong = Color(0xCC000000)
val ScrimSoft = Color(0x66000000)

// Semantic action accents — the only two saturated colors in an otherwise
// neutral UI, each tied to the meaning of its action so the two primary player
// actions read apart from each other and from the rest of the app.
// Online play / live streaming → emerald "go".
val PlayAccent = Color(0xFF2EE6A6)
val PlayAccentSoft = Color(0x1F2EE6A6)
val OnPlayAccent = Color(0xFF04160F)
// Download / save offline → azure.
val DownloadAccent = Color(0xFF5B9CFF)
val DownloadAccentSoft = Color(0x1F5B9CFF)
val OnDownloadAccent = Color(0xFF061224)

// Neutral interactive surfaces (chips, secondary rows). Keeping chrome
// desaturated lets the two action accents above carry all the color meaning.
val NeutralSurface = Color(0x14FFFFFF)
val NeutralSurfaceActive = Color(0x26FFFFFF)

// Home accent trio (زرد / قرمز / آبی) used to give the discovery shelves and
// genre chips a lively, branded rhythm. Solid tones for text/bars, soft alphas
// for chip and tile fills.
val AccentYellow = Color(0xFFFFC24B)
val AccentYellowSoft = Color(0x1FFFC24B)
val AccentRed = Color(0xFFFF5A6A)
val AccentRedSoft = Color(0x1FFF5A6A)
val AccentBlue = Color(0xFF4F9DFF)
val AccentBlueSoft = Color(0x1F4F9DFF)
