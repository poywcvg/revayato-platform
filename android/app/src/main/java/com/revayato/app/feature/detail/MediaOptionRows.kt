package com.revayato.app.feature.detail

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.DownloadForOffline
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.SaveAlt
import androidx.compose.material.icons.rounded.SdStorage
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.revayato.app.core.theme.DownloadAccent
import com.revayato.app.core.theme.NeutralSurfaceActive
import com.revayato.app.core.theme.OnDownloadAccent
import com.revayato.app.core.theme.OnPlayAccent
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.feature.player.PlaybackGroup
import com.revayato.app.feature.player.PlaybackOption

/*
 * The rows shared by the online-play and download sheets (movie and series).
 *
 * Each version (دوبله / زیرنویس چسبیده / زیرنویس نرم / نسخه اصلی) is its own card,
 * so versions never run together; inside a card every quality is one row that
 * leads with the resolution and always shows the file size — the number people
 * actually choose by on a metered connection.
 */

private val RESOLUTION_RE = Regex("""(?i)\b(2160p|1440p|1080p|720p|576p|480p|360p|4k|uhd)\b""")

/** «1080p WEB-DL x264» → ("1080p", "WEB-DL x264"); anything unparseable stays whole. */
internal fun splitQuality(label: String): Pair<String, String> {
    val match = RESOLUTION_RE.find(label) ?: return label.trim() to ""
    val rest = label.removeRange(match.range)
        .replace(Regex("""\s*[·|\-–]\s*$|^\s*[·|\-–]\s*"""), "")
        .replace(Regex("""\s{2,}"""), " ")
        .trim()
    return match.value.lowercase().replace("4k", "4K").replace("uhd", "4K") to rest
}

/** One version section as a single bordered card: header, then its qualities. */
@Composable
internal fun VersionGroupCard(
    group: PlaybackGroup,
    showHeader: Boolean,
    row: @Composable (PlaybackOption) -> Unit,
) {
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(MaterialTheme.colorScheme.surface)
            .border(1.dp, OutlineSoft, RoundedCornerShape(18.dp)),
    ) {
        if (showHeader) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .background(versionColor(group.kind).copy(alpha = 0.10f))
                    .padding(horizontal = 16.dp, vertical = 11.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Box(Modifier.size(9.dp).clip(CircleShape).background(versionColor(group.kind)))
                Text(
                    group.kind.title,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f),
                )
                Text(
                    "${group.options.size} کیفیت",
                    style = MaterialTheme.typography.labelSmall,
                    color = TextSecondary,
                )
            }
        }
        group.options.forEachIndexed { index, option ->
            if (index > 0 || showHeader) {
                Box(Modifier.fillMaxWidth().height(1.dp).background(OutlineSoft))
            }
            row(option)
        }
    }
}

/** Resolution as the headline, encode details underneath. */
@Composable
private fun QualityText(label: String, modifier: Modifier = Modifier) {
    val (headline, detail) = splitQuality(label)
    Column(modifier, verticalArrangement = Arrangement.spacedBy(1.dp)) {
        Text(
            headline,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Black,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        if (detail.isNotBlank()) {
            Text(
                detail,
                style = MaterialTheme.typography.labelSmall,
                color = TextSecondary,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

/** The file size, always present: a measured size, or an honest «نامشخص». */
@Composable
internal fun SizeBadge(sizeLabel: String, accent: Color) {
    val known = sizeLabel.isNotBlank()
    Row(
        Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(if (known) accent.copy(alpha = 0.14f) else NeutralSurfaceActive)
            .padding(horizontal = 10.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        Icon(
            Icons.Rounded.SdStorage,
            contentDescription = null,
            tint = if (known) accent else TextSecondary,
            modifier = Modifier.size(14.dp),
        )
        Text(
            if (known) sizeLabel else "حجم نامشخص",
            style = MaterialTheme.typography.labelMedium,
            fontWeight = if (known) FontWeight.Bold else FontWeight.Normal,
            color = if (known) TextPrimary else TextSecondary,
            maxLines = 1,
        )
    }
}

/** Online play: the whole row is the play button. */
@Composable
internal fun PlayOptionRow(option: PlaybackOption, accent: Color, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 13.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        QualityText(option.qualityLabel, Modifier.weight(1f))
        SizeBadge(option.sizeLabel, accent)
        Box(
            modifier = Modifier.size(38.dp).clip(CircleShape).background(accent),
            contentAlignment = Alignment.Center,
        ) {
            Icon(Icons.Rounded.PlayArrow, contentDescription = "پخش", tint = OnPlayAccent, modifier = Modifier.size(22.dp))
        }
    }
}

/** Download: quality + size on top, the two ways to keep it underneath. */
@Composable
internal fun DownloadOptionRow(option: PlaybackOption, onOffline: () -> Unit, onFile: () -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 13.dp),
        verticalArrangement = Arrangement.spacedBy(11.dp),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            QualityText(option.qualityLabel, Modifier.weight(1f))
            SizeBadge(option.sizeLabel, DownloadAccent)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            // Offline in-app viewing is the emphasised action → filled azure.
            OptionAction(
                icon = Icons.Rounded.DownloadForOffline,
                label = "تماشای آفلاین",
                container = DownloadAccent,
                content = OnDownloadAccent,
                onClick = onOffline,
                modifier = Modifier.weight(1f),
            )
            OptionAction(
                icon = Icons.Rounded.SaveAlt,
                label = "ذخیره فایل",
                container = NeutralSurfaceActive,
                content = TextPrimary,
                onClick = onFile,
                modifier = Modifier.weight(1f),
            )
        }
    }
}

@Composable
private fun OptionAction(
    icon: ImageVector,
    label: String,
    container: Color,
    content: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier
            .clip(RoundedCornerShape(11.dp))
            .background(container)
            .clickable(onClick = onClick)
            .padding(vertical = 10.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, contentDescription = null, tint = content, modifier = Modifier.size(18.dp))
        Spacer(Modifier.size(6.dp))
        Text(label, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold, color = content)
    }
}
