package com.revayato.app.feature.player

import android.content.Context
import android.graphics.Color as AndroidColor
import android.graphics.Typeface
import androidx.annotation.OptIn
import androidx.core.content.res.ResourcesCompat
import androidx.media3.common.util.UnstableApi
import androidx.media3.ui.CaptionStyleCompat
import androidx.media3.ui.SubtitleView
import com.revayato.app.R

/**
 * User-selectable subtitle typeface. Yekan Plus (the app's Persian face) is the
 * default; the rest are Android system families whose Noto fallbacks also render
 * Persian, giving the viewer a real choice of shape without bundling more fonts.
 */
enum class SubtitleFont(val title: String) {
    YEKAN("یکان"),
    SANS("ساده"),
    SERIF("سریف"),
    MONO("تک‌عرض"),
    ;

    /** Resolve to a concrete [Typeface]; Yekan loads from the bundled font. */
    fun typeface(context: Context): Typeface = when (this) {
        YEKAN -> runCatching { ResourcesCompat.getFont(context, R.font.yekan_plus) }
            .getOrNull() ?: Typeface.SANS_SERIF
        SANS -> Typeface.SANS_SERIF
        SERIF -> Typeface.SERIF
        MONO -> Typeface.MONOSPACE
    }
}

/** Subtitle text size steps, mapped to fixed SP values on the [SubtitleView]. */
enum class SubtitleSize(val title: String, val sp: Float) {
    XSMALL("خیلی کوچک", 13f),
    SMALL("کوچک", 16f),
    MEDIUM("متوسط", 20f),
    LARGE("بزرگ", 26f),
    XLARGE("خیلی بزرگ", 32f),
    XXLARGE("عظیم", 40f),
}

/**
 * Subtitle text colour. Foreground plus a matching drop-shadow/edge so every
 * colour stays legible over a bright picture. Cycled by the 🖌 control.
 */
enum class SubtitleColor(val title: String, val fg: Int) {
    WHITE("سفید", AndroidColor.WHITE),
    YELLOW("زرد", 0xFFFFEB3B.toInt()),
    MINT("سبز نعنایی", 0xFF2EE6A6.toInt()),
    CYAN("آبی", 0xFF4FC3F7.toInt()),
}

/** The viewer's chosen subtitle look, persisted across sessions. */
data class SubtitleAppearance(
    val font: SubtitleFont = SubtitleFont.YEKAN,
    val size: SubtitleSize = SubtitleSize.MEDIUM,
    val color: SubtitleColor = SubtitleColor.WHITE,
    // How far above the bottom edge the caption sits, as a fraction of the view
    // height. Media3's SubtitleView default is ~0.08; the ↑/↓ controls step it.
    val bottomPaddingFraction: Float = 0.08f,
)

private const val PREFS = "subtitle_appearance"
private const val KEY_FONT = "font"
private const val KEY_SIZE = "size"
private const val KEY_COLOR = "color"
private const val KEY_PAD = "bottom_pad"

/** Load the saved appearance, falling back to sane defaults. */
fun loadSubtitleAppearance(context: Context): SubtitleAppearance {
    val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    val font = prefs.getString(KEY_FONT, null)
        ?.let { name -> SubtitleFont.entries.firstOrNull { it.name == name } }
        ?: SubtitleFont.YEKAN
    val size = prefs.getString(KEY_SIZE, null)
        ?.let { name -> SubtitleSize.entries.firstOrNull { it.name == name } }
        ?: SubtitleSize.MEDIUM
    val color = prefs.getString(KEY_COLOR, null)
        ?.let { name -> SubtitleColor.entries.firstOrNull { it.name == name } }
        ?: SubtitleColor.WHITE
    val pad = prefs.getFloat(KEY_PAD, 0.08f).coerceIn(0.04f, 0.45f)
    return SubtitleAppearance(font, size, color, pad)
}

/** Persist the viewer's appearance choice. */
fun saveSubtitleAppearance(context: Context, appearance: SubtitleAppearance) {
    context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
        .putString(KEY_FONT, appearance.font.name)
        .putString(KEY_SIZE, appearance.size.name)
        .putString(KEY_COLOR, appearance.color.name)
        .putFloat(KEY_PAD, appearance.bottomPaddingFraction)
        .apply()
}

/** Next size up (clamped), for the A⁺ control. */
fun SubtitleSize.larger(): SubtitleSize =
    SubtitleSize.entries.getOrNull(ordinal + 1) ?: this

/** Next size down (clamped), for the A⁻ control. */
fun SubtitleSize.smaller(): SubtitleSize =
    SubtitleSize.entries.getOrNull(ordinal - 1) ?: this

/** Next typeface in the ring, for the Aa control. */
fun SubtitleFont.next(): SubtitleFont =
    SubtitleFont.entries[(ordinal + 1) % SubtitleFont.entries.size]

/** Next colour in the ring, for the 🖌 control. */
fun SubtitleColor.next(): SubtitleColor =
    SubtitleColor.entries[(ordinal + 1) % SubtitleColor.entries.size]

/**
 * Apply an appearance to the player's [SubtitleView]: a clean white-on-shadow
 * caption style with the chosen typeface and a fixed size. Embedded styles are
 * turned off so the viewer's font choice always wins, even over styled soft subs.
 */
@OptIn(UnstableApi::class)
fun SubtitleView.applyAppearance(context: Context, appearance: SubtitleAppearance) {
    setApplyEmbeddedStyles(false)
    setApplyEmbeddedFontSizes(false)
    setStyle(
        CaptionStyleCompat(
            appearance.color.fg,
            AndroidColor.TRANSPARENT,
            AndroidColor.TRANSPARENT,
            CaptionStyleCompat.EDGE_TYPE_DROP_SHADOW,
            AndroidColor.BLACK,
            appearance.font.typeface(context),
        ),
    )
    setFixedTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, appearance.size.sp)
    // Lift the caption off the bottom edge by the chosen fraction (↑/↓ controls).
    setBottomPaddingFraction(appearance.bottomPaddingFraction)
}
