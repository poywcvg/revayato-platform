package com.revayato.app.feature.support

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.HelpOutline
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.BugReport
import androidx.compose.material.icons.rounded.EditNote
import androidx.compose.material.icons.rounded.Favorite
import androidx.compose.material.icons.rounded.Movie
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.revayato.app.core.theme.AccentBlue
import com.revayato.app.core.theme.AccentYellow
import com.revayato.app.core.theme.BrandMint
import com.revayato.app.core.theme.PlayAccent
import com.revayato.app.core.theme.TextMuted

/** Icon for a support category code; falls back to a help glyph for unknowns. */
fun categoryIcon(category: String): ImageVector = when (category) {
    "content_request" -> Icons.Rounded.Movie
    "bug" -> Icons.Rounded.BugReport
    "content_fix" -> Icons.Rounded.EditNote
    "suggestion" -> Icons.Rounded.AutoAwesome
    "cooperation" -> Icons.Rounded.Favorite
    else -> Icons.AutoMirrored.Rounded.HelpOutline
}

/** Persian label for a category code, used when the server label is missing. */
fun categoryLabelFallback(category: String): String = when (category) {
    "content_request" -> "درخواست عنوان"
    "bug" -> "گزارش مشکل"
    "content_fix" -> "اصلاح محتوا"
    "suggestion" -> "پیشنهاد"
    "cooperation" -> "همکاری"
    else -> "پشتیبانی"
}

/** The six categories a user can open a request under, in composer order. */
val SUPPORT_CATEGORIES: List<Pair<String, String>> = listOf(
    "content_request" to "درخواست عنوان",
    "bug" to "گزارش مشکل",
    "content_fix" to "اصلاح محتوا",
    "suggestion" to "پیشنهاد",
    "support" to "پشتیبانی",
    "cooperation" to "همکاری",
)

/** Map ASCII digits in a string to Persian digits, leaving everything else. */
fun toFaDigits(value: String): String =
    value.map { ch -> if (ch in '0'..'9') '۰' + (ch - '0') else ch }.joinToString("")

/**
 * Format an ISO-8601 timestamp for display without pulling in java.time (minSdk 24,
 * no desugaring). Shows `yyyy/MM/dd HH:mm` in Persian digits, or just the date when
 * no time part is present. Falls back to the raw string if it isn't ISO-shaped.
 */
fun supportDateTime(iso: String): String {
    if (iso.length < 10) return toFaDigits(iso)
    val date = iso.substring(0, 10).replace('-', '/')
    val time = if (iso.length >= 16 && iso[10] == 'T') iso.substring(11, 16) else ""
    return toFaDigits(if (time.isNotEmpty()) "$date · $time" else date)
}

/** Accent colour that encodes a ticket's lifecycle state at a glance. */
fun statusColor(status: String): Color = when (status) {
    "open" -> AccentBlue
    "in_progress" -> AccentYellow
    "waiting_user" -> BrandMint
    "resolved" -> PlayAccent
    else -> TextMuted // closed / unknown
}

fun statusLabelFallback(status: String): String = when (status) {
    "open" -> "باز"
    "in_progress" -> "در حال بررسی"
    "waiting_user" -> "منتظر پاسخ شما"
    "resolved" -> "حل‌شده"
    "closed" -> "بسته"
    else -> status
}

/**
 * Compact status chip: a coloured dot + label, tinted by [statusColor]. Shared by
 * the requests list and the conversation header so state reads the same everywhere.
 */
@Composable
fun StatusPill(status: String, label: String, modifier: Modifier = Modifier) {
    val color = statusColor(status)
    Row(
        modifier = modifier
            .background(color.copy(alpha = 0.14f), RoundedCornerShape(999.dp))
            .padding(horizontal = 9.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        Box(Modifier.size(6.dp).background(color, CircleShape))
        Text(
            text = label.ifBlank { statusLabelFallback(status) },
            color = color,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
        )
    }
}
