package com.revayato.app.core.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.sp
import com.revayato.app.R

// Mikhak — the same face as the website. The TTFs are static cuts of the web's
// variable font (wght 400/500/600/700/850) with the web's size-adjust (78% of the em)
// and line metrics (ascent 107%, descent 59%) baked in, so Persian text sits at the
// same visual size as before while Latin letters and ASCII digits (absent from the
// files, exactly like the web's unicode-range) fall back to Roboto at full size.
private val Mikhak = FontFamily(
    Font(R.font.mikhak_regular, FontWeight.Normal),
    Font(R.font.mikhak_medium, FontWeight.Medium),
    Font(R.font.mikhak_semibold, FontWeight.SemiBold),
    Font(R.font.mikhak_bold, FontWeight.Bold),
    Font(R.font.mikhak_black, FontWeight.ExtraBold),
    Font(R.font.mikhak_black, FontWeight.Black),
)

/** Body / UI face. */
val YekanPlus = Mikhak

/** Display face for the large headline roles. */
val YekanBoom = Mikhak

private val base = Typography()

// Gentle lift over the base scale: Persian glyphs land ~9% larger than the old
// Yekan, Latin fallback stays close to its old size.
private const val YEKAN_SCALE = 1.04f

// Bigger, bolder, and airier than the Material default scale — Persian text reads
// better with heavier strokes and a touch more line-height. Role names are kept
// identical to the Material 3 scale so every existing call site is unaffected.
val RevayatoTypography = Typography(
    displayLarge = base.displayLarge.withFont(FontWeight.Bold, 60.sp, 68.sp, YekanBoom),
    displayMedium = base.displayMedium.withFont(FontWeight.Bold, 48.sp, 56.sp, YekanBoom),
    displaySmall = base.displaySmall.withFont(FontWeight.Bold, 38.sp, 46.sp, YekanBoom),
    headlineLarge = base.headlineLarge.withFont(FontWeight.Bold, 34.sp, 42.sp, YekanBoom),
    headlineMedium = base.headlineMedium.withFont(FontWeight.Bold, 30.sp, 38.sp, YekanBoom),
    headlineSmall = base.headlineSmall.withFont(FontWeight.Bold, 25.sp, 33.sp, YekanBoom),
    titleLarge = base.titleLarge.withFont(FontWeight.Bold, 23.sp, 30.sp),
    titleMedium = base.titleMedium.withFont(FontWeight.Bold, 19.sp, 26.sp),
    titleSmall = base.titleSmall.withFont(FontWeight.SemiBold, 16.sp, 22.sp),
    bodyLarge = base.bodyLarge.withFont(FontWeight.Medium, 17.sp, 27.sp),
    bodyMedium = base.bodyMedium.withFont(FontWeight.Medium, 15.sp, 23.sp),
    bodySmall = base.bodySmall.withFont(FontWeight.Normal, 13.sp, 19.sp),
    labelLarge = base.labelLarge.withFont(FontWeight.SemiBold, 15.sp, 20.sp),
    labelMedium = base.labelMedium.withFont(FontWeight.SemiBold, 13.sp, 17.sp),
    labelSmall = base.labelSmall.withFont(FontWeight.Medium, 12.sp, 16.sp),
)

private fun TextStyle.withFont(
    weight: FontWeight = fontWeight ?: FontWeight.Normal,
    size: TextUnit = fontSize,
    lineHeight: TextUnit = this.lineHeight,
    family: FontFamily = YekanPlus,
): TextStyle = copy(
    fontFamily = family,
    fontWeight = weight,
    fontSize = size * YEKAN_SCALE,
    lineHeight = lineHeight * YEKAN_SCALE,
)
