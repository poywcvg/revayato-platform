package com.revayato.app.feature.detail

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Download
import androidx.compose.material.icons.rounded.DownloadForOffline
import androidx.compose.material.icons.rounded.SaveAlt
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
import com.revayato.app.core.theme.DownloadAccent
import com.revayato.app.core.theme.DownloadAccentSoft
import com.revayato.app.core.theme.NeutralSurface
import com.revayato.app.core.theme.OnDownloadAccent
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.data.model.DownloadLinkDto
import com.revayato.app.feature.player.PlaybackGroup
import com.revayato.app.feature.player.PlaybackOption
import com.revayato.app.feature.player.PlaybackVersionKind
import com.revayato.app.feature.player.groupPlaybackLinks

/**
 * Lets the user pick a version (دوبله / زیرنویس چسبیده / زیرنویس نرم) and quality,
 * then choose between in-app offline playback and saving a shareable file — both
 * modes the platform supports. Mirrors the online-play picker's grouping so the two
 * sheets read as siblings.
 *
 * Carries the azure "download" accent so the whole save-offline path reads as one
 * colour, deliberately different from the emerald online-play flow.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DownloadOptionsSheet(
    links: List<DownloadLinkDto>,
    fallbackStreamUrl: String?,
    onOffline: (url: String) -> Unit,
    onFile: (url: String) -> Unit,
    onDismiss: () -> Unit,
) {
    val groups = remember(links, fallbackStreamUrl) {
        buildDownloadGroups(links, fallbackStreamUrl)
    }
    val showVersionHeaders = groups.size > 1 ||
        groups.firstOrNull()?.kind != PlaybackVersionKind.ORIGINAL
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = BgElevated,
    ) {
        // Header stays pinned; only the version/quality list scrolls, so long lists
        // never push the header off-screen. navigationBarsPadding keeps the last row
        // clear of the phone's gesture/navigation bar.
        Column(
            Modifier
                .fillMaxWidth()
                .navigationBarsPadding(),
        ) {
            Column(Modifier.padding(horizontal = 20.dp)) {
                SheetHeader(
                    icon = Icons.Rounded.Download,
                    accent = DownloadAccent,
                    accentSoft = DownloadAccentSoft,
                    title = "دانلود",
                    subtitle = "کیفیت را با توجه به حجمش انتخاب کن؛ آفلاین در برنامه ببین یا فایل را ذخیره کن.",
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
                    DownloadOptionRow(
                        option = option,
                        onOffline = {
                            onOffline(option.url)
                            onDismiss()
                        },
                        onFile = {
                            onFile(option.url)
                            onDismiss()
                        },
                    )
                }
            }
            }
        }
    }
}

/**
 * Build the download sheet's version groups from a title's links, falling back to a
 * single default-quality entry on the stream URL when no download mirrors exist.
 */
fun buildDownloadGroups(
    links: List<DownloadLinkDto>,
    fallbackStreamUrl: String?,
): List<PlaybackGroup> {
    val groups = groupPlaybackLinks(links)
    if (groups.isNotEmpty()) return groups
    val fallback = fallbackStreamUrl?.takeIf { it.isNotBlank() } ?: return emptyList()
    return listOf(
        PlaybackGroup(
            kind = PlaybackVersionKind.ORIGINAL,
            options = listOf(
                PlaybackOption(
                    url = fallback,
                    qualityLabel = "کیفیت پیش‌فرض",
                    kind = PlaybackVersionKind.ORIGINAL,
                ),
            ),
        ),
    )
}

/** True when there is at least one downloadable/streamable mirror to offer. */
fun hasDownloadableLinks(links: List<DownloadLinkDto>, fallbackStreamUrl: String?): Boolean =
    buildDownloadGroups(links, fallbackStreamUrl).isNotEmpty()
