package com.revayato.app.feature.detail

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.HighQuality
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.OnPlayAccent
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.PlayAccent
import com.revayato.app.core.theme.PlayAccentSoft
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.data.model.DownloadLinkDto
import com.revayato.app.feature.player.PlaybackVersionKind
import com.revayato.app.feature.player.groupPlaybackLinks

/**
 * Opens when the user taps "پخش آنلاین" on a detail page. Groups the title's mirrors
 * by Persian version — دوبله / زیرنویس چسبیده / زیرنویس نرم — and, within each, lets
 * the user pick a quality *before* entering the player. Tapping a mirror reports its
 * URL back so the caller can launch the player on it.
 *
 * Carries the emerald "online play" accent so the whole streaming path — button,
 * picker, play affordance — reads as one colour, distinct from the download flow.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun QualityPickerSheet(
    links: List<DownloadLinkDto>,
    onSelect: (url: String) -> Unit,
    onDismiss: () -> Unit,
    headerTitle: String = "پخش آنلاین",
    headerSubtitle: String = "نسخه و کیفیت را انتخاب کن؛ حجم هر فایل کنارش آمده است.",
) {
    val groups = remember(links) { groupPlaybackLinks(links) }
    // Only surface version headers when there's a real choice to make.
    val showVersionHeaders = groups.size > 1 ||
        groups.firstOrNull()?.kind != PlaybackVersionKind.ORIGINAL
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = BgElevated,
    ) {
        // Pinned header + scrollable version/quality list, kept clear of the phone's
        // gesture/navigation bar so the last mirror is always tappable.
        Column(
            Modifier
                .fillMaxWidth()
                .navigationBarsPadding(),
        ) {
            Column(Modifier.padding(horizontal = 20.dp)) {
                SheetHeader(
                    icon = Icons.Rounded.PlayArrow,
                    accent = PlayAccent,
                    accentSoft = PlayAccentSoft,
                    title = headerTitle,
                    subtitle = headerSubtitle,
                )
            }
            Column(
                Modifier
                    .fillMaxWidth()
                    .weight(1f, fill = false)
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 20.dp)
                    .padding(top = 16.dp, bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
            groups.forEach { group ->
                VersionGroupCard(group = group, showHeader = showVersionHeaders) { option ->
                    PlayOptionRow(option = option, accent = PlayAccent) {
                        onSelect(option.url)
                        onDismiss()
                    }
                }
            }
            }
        }
    }
}

/** Distinct accent per version so the sections read apart at a glance. */
internal fun versionColor(kind: PlaybackVersionKind): Color = when (kind) {
    PlaybackVersionKind.DUBBED -> Color(0xFF7BD88F)
    PlaybackVersionKind.HARDSUB -> Color(0xFFF2B15A)
    PlaybackVersionKind.SOFTSUB -> Color(0xFF6FB6FF)
    PlaybackVersionKind.ORIGINAL -> Color(0xFFB8BCC6)
}

/** Shared header for the detail bottom sheets: a tinted icon badge next to a
 *  title + subtitle, carrying the sheet's semantic accent. */
@Composable
internal fun SheetHeader(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    accent: androidx.compose.ui.graphics.Color,
    accentSoft: androidx.compose.ui.graphics.Color,
    title: String,
    subtitle: String,
) {
    Row(
        Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(
            modifier = Modifier
                .size(40.dp)
                .clip(RoundedCornerShape(12.dp))
                .background(accentSoft),
            contentAlignment = Alignment.Center,
        ) {
            Icon(icon, contentDescription = null, tint = accent, modifier = Modifier.size(22.dp))
        }
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(
                title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
            Text(
                subtitle,
                style = MaterialTheme.typography.bodySmall,
                color = TextSecondary,
            )
        }
    }
}
