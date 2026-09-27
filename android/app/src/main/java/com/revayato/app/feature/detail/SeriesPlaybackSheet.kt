package com.revayato.app.feature.detail

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.rounded.Download
import androidx.compose.material.icons.rounded.DownloadForOffline
import androidx.compose.material.icons.rounded.HighQuality
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.SaveAlt
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.DownloadAccent
import com.revayato.app.core.theme.DownloadAccentSoft
import com.revayato.app.core.theme.NeutralSurface
import com.revayato.app.core.theme.NeutralSurfaceActive
import com.revayato.app.core.theme.OnDownloadAccent
import com.revayato.app.core.theme.OnPlayAccent
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.PlayAccent
import com.revayato.app.core.theme.PlayAccentSoft
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.data.model.EpisodeDto
import com.revayato.app.data.model.SeasonDto
import com.revayato.app.feature.player.PlaybackVersionKind

/** Whether the series sheet is being used to start online playback or to download. */
enum class SeriesSheetMode { PLAY, DOWNLOAD }

/** The three ordered steps of the series-selection journey. */
private enum class SeriesStep(val order: Int) { SEASON(0), EPISODE(1), VERSION(2) }

/**
 * A single modal that walks the whole series-selection journey as three clear,
 * uncluttered steps:
 *
 *   1. **فصل**  — pick the season,
 *   2. **قسمت** — pick the episode within it,
 *   3. **نسخه و کیفیت** — pick the dub/subtitle version and quality, then play/download.
 *
 * Each step fills the sheet on its own so nothing competes for attention, and a
 * breadcrumb keeps the chosen فصل/قسمت numbers visible at every later step. Serves
 * both the online-play and download flows via [mode], keeping their accents distinct.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SeriesPlaybackSheet(
    seasons: List<SeasonDto>,
    initialSeasonIndex: Int,
    mode: SeriesSheetMode,
    onPlay: (EpisodeDto, url: String) -> Unit,
    onOffline: (EpisodeDto, url: String) -> Unit,
    onFile: (EpisodeDto, url: String) -> Unit,
    onDismiss: () -> Unit,
) {
    val accent = if (mode == SeriesSheetMode.PLAY) PlayAccent else DownloadAccent
    val accentSoft = if (mode == SeriesSheetMode.PLAY) PlayAccentSoft else DownloadAccentSoft
    val multiSeason = seasons.size > 1

    var seasonIndex by remember {
        mutableIntStateOf(initialSeasonIndex.coerceIn(0, (seasons.size - 1).coerceAtLeast(0)))
    }
    // With a single season there is no season to pick, so open straight on episodes.
    var step by remember { mutableStateOf(if (multiSeason) SeriesStep.SEASON else SeriesStep.EPISODE) }
    var selectedEpisodeId by remember { mutableStateOf<Int?>(null) }

    val season = seasons.getOrNull(seasonIndex) ?: seasons.firstOrNull()
    val episodes = season?.episodes.orEmpty()
    val selectedEpisode = episodes.firstOrNull { it.id == selectedEpisodeId }

    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = BgElevated,
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .padding(horizontal = 20.dp)
                .padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            StepHeader(
                step = step,
                mode = mode,
                accent = accent,
                accentSoft = accentSoft,
                multiSeason = multiSeason,
                season = season,
                episode = selectedEpisode,
                onBack = {
                    when (step) {
                        SeriesStep.VERSION -> {
                            step = SeriesStep.EPISODE
                            selectedEpisodeId = null
                        }
                        SeriesStep.EPISODE -> if (multiSeason) step = SeriesStep.SEASON
                        SeriesStep.SEASON -> Unit
                    }
                },
            )

            AnimatedContent(
                targetState = step,
                label = "series-step",
                transitionSpec = {
                    // Slide forward toward the leading (start) edge, back the other way.
                    val forward = targetState.order > initialState.order
                    val dir = if (forward) 1 else -1
                    (slideInHorizontally(tween(220)) { w -> dir * w / 6 } + fadeIn(tween(180))) togetherWith
                        (slideOutHorizontally(tween(180)) { w -> -dir * w / 6 } + fadeOut(tween(140)))
                },
            ) { current ->
                when (current) {
                    SeriesStep.SEASON -> SeasonStep(
                        seasons = seasons,
                        selectedIndex = seasonIndex,
                        accent = accent,
                        accentSoft = accentSoft,
                        onSelect = { index ->
                            seasonIndex = index
                            selectedEpisodeId = null
                            step = SeriesStep.EPISODE
                        },
                    )

                    SeriesStep.EPISODE -> EpisodeStep(
                        episodes = episodes,
                        accent = accent,
                        onSelect = { episode ->
                            selectedEpisodeId = episode.id
                            step = SeriesStep.VERSION
                        },
                    )

                    SeriesStep.VERSION -> VersionStep(
                        episode = selectedEpisode,
                        accent = accent,
                        mode = mode,
                        onPlay = { episode, url ->
                            onPlay(episode, url)
                            onDismiss()
                        },
                        onOffline = { episode, url ->
                            onOffline(episode, url)
                            onDismiss()
                        },
                        onFile = { episode, url ->
                            onFile(episode, url)
                            onDismiss()
                        },
                    )
                }
            }
        }
    }
}

private fun seasonLabel(season: SeasonDto): String =
    season.title.ifBlank { "فصل ${season.seasonNumber}" }

/* ------------------------------------------------------------------ *
 *  Header: back control + step title/subtitle + a فصل/قسمت breadcrumb  *
 * ------------------------------------------------------------------ */
@Composable
private fun StepHeader(
    step: SeriesStep,
    mode: SeriesSheetMode,
    accent: Color,
    accentSoft: Color,
    multiSeason: Boolean,
    season: SeasonDto?,
    episode: EpisodeDto?,
    onBack: () -> Unit,
) {
    val canGoBack = when (step) {
        SeriesStep.SEASON -> false
        SeriesStep.EPISODE -> multiSeason
        SeriesStep.VERSION -> true
    }
    val title: String
    val subtitle: String
    when (step) {
        SeriesStep.SEASON -> {
            title = if (mode == SeriesSheetMode.PLAY) "پخش آنلاین سریال" else "دانلود سریال"
            subtitle = "اول فصل مورد نظرت را انتخاب کن."
        }
        SeriesStep.EPISODE -> {
            title = season?.let { seasonLabel(it) } ?: "انتخاب قسمت"
            subtitle = "قسمت مورد نظرت را انتخاب کن."
        }
        SeriesStep.VERSION -> {
            title = episode?.let { "قسمت ${it.episodeNumber}" } ?: "انتخاب نسخه"
            subtitle = "نسخه (دوبله/زیرنویس) و کیفیت را انتخاب کن."
        }
    }

    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(
            Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Box(
                modifier = Modifier
                    .size(40.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(accentSoft)
                    .then(if (canGoBack) Modifier.clickable(onClick = onBack) else Modifier),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = if (canGoBack) {
                        Icons.AutoMirrored.Rounded.ArrowBack
                    } else if (mode == SeriesSheetMode.PLAY) {
                        Icons.Rounded.PlayArrow
                    } else {
                        Icons.Rounded.Download
                    },
                    contentDescription = if (canGoBack) "بازگشت" else null,
                    tint = accent,
                    modifier = Modifier.size(if (canGoBack) 20.dp else 22.dp),
                )
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    text = title,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = TextPrimary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = subtitle,
                    style = MaterialTheme.typography.bodySmall,
                    color = TextSecondary,
                )
            }
        }

        // Breadcrumb: keeps the chosen فصل / قسمت numbers in view on later steps.
        if (step != SeriesStep.SEASON) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                season?.let {
                    Crumb(text = "فصل ${it.seasonNumber}", accent = accent, active = step == SeriesStep.EPISODE)
                }
                if (step == SeriesStep.VERSION && episode != null) {
                    Crumb(text = "قسمت ${episode.episodeNumber}", accent = accent, active = true)
                }
            }
        }
    }
}

/** A small breadcrumb pill; the current step's crumb is filled with the accent. */
@Composable
private fun Crumb(text: String, accent: Color, active: Boolean) {
    Text(
        text = text,
        style = MaterialTheme.typography.labelSmall,
        fontWeight = FontWeight.SemiBold,
        color = if (active) OnPlayAccent else accent,
        modifier = Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(if (active) accent else NeutralSurfaceActive)
            .padding(horizontal = 10.dp, vertical = 4.dp),
    )
}

/* ------------------------------ Step 1: seasons ------------------------------ */
@Composable
private fun SeasonStep(
    seasons: List<SeasonDto>,
    selectedIndex: Int,
    accent: Color,
    accentSoft: Color,
    onSelect: (Int) -> Unit,
) {
    Column(
        modifier = Modifier
            .heightIn(max = 440.dp)
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        seasons.forEachIndexed { index, season ->
            SeasonPickerCard(
                season = season,
                selected = index == selectedIndex,
                accent = accent,
                accentSoft = accentSoft,
                onClick = { onSelect(index) },
            )
        }
    }
}

@Composable
private fun SeasonPickerCard(
    season: SeasonDto,
    selected: Boolean,
    accent: Color,
    accentSoft: Color,
    onClick: () -> Unit,
) {
    val episodeCount = season.episodes.size
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(if (selected) accentSoft else MaterialTheme.colorScheme.surface)
            .border(
                1.dp,
                if (selected) accent else OutlineSoft,
                RoundedCornerShape(16.dp),
            )
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(
            modifier = Modifier
                .size(40.dp)
                .clip(RoundedCornerShape(12.dp))
                .background(if (selected) accent else NeutralSurfaceActive),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = "${season.seasonNumber}",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = if (selected) OnPlayAccent else TextPrimary,
            )
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(
                text = seasonLabel(season),
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.SemiBold,
                color = TextPrimary,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (episodeCount > 0) {
                Text(
                    text = "$episodeCount قسمت",
                    style = MaterialTheme.typography.labelMedium,
                    color = TextSecondary,
                )
            }
        }
        Icon(
            Icons.AutoMirrored.Rounded.ArrowForward,
            contentDescription = null,
            tint = accent,
            modifier = Modifier.size(20.dp),
        )
    }
}

/* ------------------------------ Step 2: episodes ------------------------------ */
@Composable
private fun EpisodeStep(
    episodes: List<EpisodeDto>,
    accent: Color,
    onSelect: (EpisodeDto) -> Unit,
) {
    Column(
        modifier = Modifier
            .heightIn(max = 440.dp)
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        episodes.forEach { episode ->
            EpisodePickerCard(
                episode = episode,
                accent = accent,
                onClick = { onSelect(episode) },
            )
        }
        if (episodes.isEmpty()) {
            Text(
                "قسمتی برای این فصل موجود نیست.",
                style = MaterialTheme.typography.bodyMedium,
                color = TextSecondary,
                modifier = Modifier.padding(vertical = 12.dp),
            )
        }
    }
}

@Composable
private fun EpisodePickerCard(
    episode: EpisodeDto,
    accent: Color,
    onClick: () -> Unit,
) {
    val playable = remember(episode) {
        buildDownloadGroups(episode.streamLinks, resolveEpisodeStreamUrl(episode)).isNotEmpty()
    }
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(MaterialTheme.colorScheme.surface)
            .border(1.dp, OutlineSoft, RoundedCornerShape(16.dp))
            .clickable(enabled = playable, onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        // A pill carrying the episode number keeps "which قسمت" unmistakable.
        Box(
            modifier = Modifier
                .size(34.dp)
                .clip(RoundedCornerShape(10.dp))
                .background(NeutralSurfaceActive),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = "${episode.episodeNumber}",
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Bold,
                color = TextPrimary,
            )
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(
                text = "قسمت ${episode.episodeNumber}",
                style = MaterialTheme.typography.labelSmall,
                color = accent,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                text = episode.title.ifBlank { "قسمت ${episode.episodeNumber}" },
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onSurface,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (!playable) {
                Text(
                    "لینک پخش موجود نیست",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.error,
                )
            }
        }
        if (playable) {
            Icon(
                Icons.AutoMirrored.Rounded.ArrowForward,
                contentDescription = null,
                tint = accent,
                modifier = Modifier.size(20.dp),
            )
        }
    }
}

/* --------------------------- Step 3: version & quality --------------------------- */
@Composable
private fun VersionStep(
    episode: EpisodeDto?,
    accent: Color,
    mode: SeriesSheetMode,
    onPlay: (EpisodeDto, url: String) -> Unit,
    onOffline: (EpisodeDto, url: String) -> Unit,
    onFile: (EpisodeDto, url: String) -> Unit,
) {
    if (episode == null) {
        Text(
            "قسمتی انتخاب نشده است.",
            style = MaterialTheme.typography.bodyMedium,
            color = TextSecondary,
            modifier = Modifier.padding(vertical = 12.dp),
        )
        return
    }
    val groups = remember(episode) {
        buildDownloadGroups(episode.streamLinks, resolveEpisodeStreamUrl(episode))
    }
    // Only surface version headers when there's a real dub/subtitle choice to make.
    val showVersionHeaders = groups.size > 1 ||
        groups.firstOrNull()?.kind != PlaybackVersionKind.ORIGINAL

    Column(
        modifier = Modifier
            .heightIn(max = 460.dp)
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        if (groups.isEmpty()) {
            Text(
                "لینک پخشی برای این قسمت موجود نیست.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.padding(vertical = 12.dp),
            )
        }
        groups.forEach { group ->
            VersionGroupCard(group = group, showHeader = showVersionHeaders) { option ->
                if (mode == SeriesSheetMode.PLAY) {
                    PlayOptionRow(option = option, accent = accent) { onPlay(episode, option.url) }
                } else {
                    DownloadOptionRow(
                        option = option,
                        onOffline = { onOffline(episode, option.url) },
                        onFile = { onFile(episode, option.url) },
                    )
                }
            }
        }
    }
}
