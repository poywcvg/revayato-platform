package com.revayato.app.feature.downloads

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.Downloading
import androidx.compose.material.icons.rounded.PlayCircle
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.media3.exoplayer.offline.Download
import com.revayato.app.core.download.DownloadItem
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.BrandDeep
import com.revayato.app.core.theme.Brand
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.ui.components.EmptyState

@Composable
fun DownloadsScreen(
    onBack: () -> Unit,
    onPlay: (contentType: String, id: Int, slug: String, title: String, url: String, positionMs: Long, episodeId: Int, subtitlesEncoded: String, qualitiesEncoded: String) -> Unit,
    viewModel: DownloadsViewModel = hiltViewModel(),
) {
    LaunchedEffect(Unit) { viewModel.refresh() }
    val downloads by viewModel.downloads.collectAsStateWithLifecycle()

    Column(Modifier.fillMaxSize().navigationBarsPadding()) {
        Row(
            Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 4.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Rounded.ArrowForward, contentDescription = "بازگشت")
            }
            Text("دانلودهای من", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        }

        if (downloads.isEmpty()) {
            EmptyState(
                title = "هنوز دانلودی نداری",
                subtitle = "از صفحهٔ هر فیلم یا قسمت، دکمهٔ دانلود را بزن تا آفلاین تماشا کنی",
                modifier = Modifier.fillMaxSize(),
            )
            return
        }

        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            items(downloads, key = { it.id }) { item ->
                DownloadRow(
                    item = item,
                    onPlay = {
                        onPlay(item.contentType, item.contentId, "", item.title, item.uri, 0L, 0, "", "")
                    },
                    onDelete = { viewModel.remove(item.id) },
                )
            }
        }
    }
}

@Composable
private fun DownloadRow(
    item: DownloadItem,
    onPlay: () -> Unit,
    onDelete: () -> Unit,
) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(BgElevated)
            .clickable(enabled = item.isComplete, onClick = onPlay)
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        val (icon, tint) = when {
            item.isComplete -> Icons.Rounded.PlayCircle to Brand
            item.state == Download.STATE_FAILED -> Icons.Rounded.Downloading to TextMuted
            else -> Icons.Rounded.Downloading to BrandDeep
        }
        Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(34.dp))
        Spacer(Modifier.size(12.dp))
        Column(Modifier.weight(1f)) {
            Text(
                item.title,
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Spacer(Modifier.size(4.dp))
            if (item.isComplete) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = BrandDeep, modifier = Modifier.size(14.dp))
                    Spacer(Modifier.size(4.dp))
                    Text("آمادهٔ تماشای آفلاین", style = MaterialTheme.typography.labelSmall, color = TextSecondary)
                }
            } else {
                LinearProgressIndicator(
                    progress = { (item.percentDownloaded / 100f).coerceIn(0f, 1f) },
                    modifier = Modifier.fillMaxWidth(),
                    color = Brand,
                    trackColor = BgElevated,
                )
                Spacer(Modifier.size(4.dp))
                Text(
                    "${item.percentDownloaded.toInt()}٪ دانلود شد",
                    style = MaterialTheme.typography.labelSmall,
                    color = TextMuted,
                )
            }
        }
        IconButton(onClick = onDelete) {
            Icon(Icons.Rounded.Delete, contentDescription = "حذف", tint = TextMuted)
        }
    }
}
