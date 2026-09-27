package com.revayato.app.core.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.sp
import com.revayato.app.R

// Yekan ships as one bold master, so lighter cuts are derived from it:
// regular for running text, medium for SemiBold labels, the original for Bold.
// Neither face carries Latin letters or ASCII digits; Android falls back to the system
// face for those, as the web does.
private fun yekanFamily(regular: Int, medium: Int, bold: Int) = FontFamily(
    Font(regular, FontWeight.Normal),
    Font(regular, FontWeight.Medium),
    Font(medium, FontWeight.SemiBold),
    Font(bold, FontWeight.Bold),
)

/** Body / UI face. */
val YekanPlus = yekanFamily(R.font.yekan_plus_regular, R.font.yekan_plus_medium, R.font.yekan_plus)

/** Display face for the large headline roles. */
val YekanBoom = yekanFamily(R.font.yekan_boom, R.font.yekan_boom, R.font.yekan_boom)

private val base = Typography()

// Yekan's letters sit ~25% smaller than Vazirmatn's at the same sp, which the scale
// below was tuned for; this brings them back to a comfortable reading size.
private const val YEKAN_SCALE = 1.12f

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
