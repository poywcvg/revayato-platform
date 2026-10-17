package com.revayato.app.feature.detail

import com.revayato.app.ui.components.FlatSnackbar
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.runtime.Composable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.getValue
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.launch
import com.revayato.app.data.model.EpisodeDto
import com.revayato.app.data.model.GenreDto
import com.revayato.app.data.model.SeasonDto
import com.revayato.app.data.model.SeriesDetailDto
import com.revayato.app.data.model.englishCatalogTitle
import com.revayato.app.feature.collections.AddToCollectionSheet
import com.revayato.app.feature.player.buildQualitiesFromLinks
import com.revayato.app.feature.player.encodeQualities
import com.revayato.app.feature.player.encodeSubtitles
import com.revayato.app.ui.components.ErrorState
import com.revayato.app.ui.components.LoadingState
import com.revayato.app.ui.components.MediaRail
import com.revayato.app.core.ui.UiState

@Composable
fun SeriesDetailScreen(
    slug: String,
    onBack: () -> Unit,
    onOpenTitle: (contentType: String, slug: String) -> Unit,
    onPlay: (contentType: String, id: Int, slug: String, title: String, url: String, positionMs: Long, episodeId: Int, subtitles: String, qualities: String) -> Unit,
    onWatchTogether: (code: String) -> Unit,
    onRequireLogin: () -> Unit,
    onOpenPerson: (kind: String, slug: String) -> Unit = { _, _ -> },
    onOpenGenre: (GenreDto) -> Unit = {},
    onOpenLibrary: () -> Unit = {},
    modifier: Modifier = Modifier,
    viewModel: SeriesDetailViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }

    LaunchedEffect(state.actionMessage) {
        state.actionMessage?.let { msg ->
            // On "added to watchlist" attach a «مشاهده» action that takes the user
            // straight to their library, so a saved title is one tap from findable.
            val result = snackbar.showSnackbar(
                message = msg,
                actionLabel = if (msg == MSG_ADDED_TO_WATCHLIST) "مشاهده" else null,
                duration = SnackbarDuration.Short,
            )
            if (result == SnackbarResult.ActionPerformed && msg == MSG_ADDED_TO_WATCHLIST) {
                onOpenLibrary()
            }
            viewModel.consumeMessage()
        }
    }
    LaunchedEffect(state.pendingRoomCode) {
        state.pendingRoomCode?.let {
            onWatchTogether(it)
            viewModel.consumeRoomCode()
        }
    }

    Box(modifier = modifier.fillMaxSize()) {
        when (val content = state.content) {
            is UiState.Loading -> LoadingState()
            is UiState.Error -> ErrorState(content.message, onRetry = viewModel::load)
            is UiState.Success -> SeriesDetailBody(
                series = content.data,
                state = state,
                onPlayEpisode = { ep, url ->
                    onPlay(
                        "episode", ep.id, content.data.slug, ep.title, url, 0L, ep.id,
                        encodeSubtitles(ep.subtitleTracks),
                        encodeQualities(buildQualitiesFromLinks(ep.streamLinks)),
                    )
                },
                onWatchTogetherEpisode = { viewModel.createWatchParty(it.id) },
                onToggleWatchlist = viewModel::toggleWatchlist,
                onToggleLike = viewModel::toggleLike,
                onOpenTitle = onOpenTitle,
                onOpenPerson = onOpenPerson,
                onOpenGenre = onOpenGenre,
                onDownloadEpisodeOffline = viewModel::downloadEpisodeOffline,
                onDownloadEpisodeFile = viewModel::downloadEpisodeFile,
                onSubmitRating = viewModel::submitRating,
                onRequireLogin = onRequireLogin,
            )
        }
        // statusBarsPadding keeps both top controls below the status bar / camera
        // cutout instead of hiding under the phone's own UI.
        BackButton(
            onBack = onBack,
            modifier = Modifier
                .align(Alignment.TopEnd)
                .statusBarsPadding(),
        )
        // Minimal «گزارش خطا» trigger, opposite corner from the back button, shown
        // once the title has loaded so the report can be attached to it.
        if (state.content is UiState.Success) {
            ReportProblemButton(
                onClick = viewModel::openReport,
                modifier = Modifier
                    .align(Alignment.TopStart)
                    .statusBarsPadding()
                    .padding(16.dp),
            )
        }
        SnackbarHost(
            snackbar,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .navigationBarsPadding(),
        ) { FlatSnackbar(it) }
    }

    if (state.showReportSheet) {
        ReportProblemSheet(
            contentLabel = "این سریال",
            submitting = state.reportSubmitting,
            onSubmit = viewModel::submitReport,
            onDismiss = viewModel::dismissReport,
        )
    }
}

@Composable
private fun SeriesDetailBody(
    series: SeriesDetailDto,
    state: SeriesDetailState,
    onPlayEpisode: (EpisodeDto, url: String) -> Unit,
    onWatchTogetherEpisode: (EpisodeDto) -> Unit,
    onToggleWatchlist: () -> Unit,
    onToggleLike: () -> Unit,
    onOpenTitle: (String, String) -> Unit,
    onOpenPerson: (kind: String, slug: String) -> Unit,
    onOpenGenre: (GenreDto) -> Unit,
    onDownloadEpisodeOffline: (EpisodeDto, String) -> Unit,
    onDownloadEpisodeFile: (EpisodeDto, String) -> Unit,
    onSubmitRating: (Double, String, Boolean) -> Unit,
    onRequireLogin: () -> Unit,
) {
    val seasons = series.seasons
    val selectedSeason = seasons.getOrNull(state.selectedSeasonIndex) ?: seasons.firstOrNull()
    // Any episode anywhere in the series is enough to enable the play/download
    // actions — the sheet itself lets the user pick the season and episode.
    val anyPlayable = remember(seasons) {
        seasons.any { s -> s.episodes.any { resolveEpisodeStreamUrl(it) != null } }
    }
    // Header actions open a full season → episode → version/quality picker; this
    // is the single entry point for playback now that the inline episode list is
    // gone (its shortcut-tap quality picker went with it).
    var showPlaySheet by remember { mutableStateOf(false) }
    var showDownloadSheet by remember { mutableStateOf(false) }
    var showCollectionSheet by remember { mutableStateOf(false) }

    // Add the gesture/navigation-bar height to the bottom padding so the last row
    // clears the phone's system bar (this screen has no Scaffold bottom bar).
    val navBottom = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()
    // hero, body, [similar], ratings — the stars in the hero scroll to the last.
    val ratingsIndex = if (state.similar.isNotEmpty()) 3 else 2
    val latest = remember(seasons) { latestEpisodeStream(seasons) }
    val heroData = remember(series, anyPlayable) {
        DetailHeroData(
            isSeries = true,
            title = series.title,
            englishTitle = englishCatalogTitle(series.title, series.secondaryTitle, series.originalTitle),
            year = series.startYear,
            posterUrl = series.poster,
            backdropUrl = series.backdrop,
            genres = series.genres,
            ageRating = series.ageRating,
            facts = heroFacts(null, series.seasons.size, series.countries.map { it.name }),
            freshPills = freshPills(isSeries = true, links = series.downloadLinks),
            hasSubtitle = series.hasSubtitle,
            isDubbed = series.isDubbed,
            canPlay = anyPlayable,
            trailerUrl = series.trailerUrl,
            ratings = series.ratings,
            imdbRating = series.imdbRating,
            siteRating = series.siteRating,
            siteRatingCount = series.siteRatingCount,
            imdbRank = series.imdbRank,
        )
    }
    LazyColumn(
        state = listState,
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = 32.dp + navBottom),
    ) {
        item {
            DetailHero(
                data = heroData,
                inWatchlist = state.inWatchlist,
                liked = state.liked,
                actions = DetailHeroActions(
                    onPlay = { showPlaySheet = true },
                    onPlayLatest = latest?.let { (episode, url) -> { onPlayEpisode(episode, url) } },
                    onDownload = if (anyPlayable) ({ showDownloadSheet = true }) else null,
                    onToggleWatchlist = onToggleWatchlist,
                    onToggleLike = onToggleLike,
                    onWatchTogether = {
                        selectedSeason?.episodes
                            ?.firstOrNull { resolveEpisodeStreamUrl(it) != null }
                            ?.let(onWatchTogetherEpisode)
                    },
                    onAddToCollection = {
                        if (state.isLoggedIn) showCollectionSheet = true else onRequireLogin()
                    },
                    onGenreClick = onOpenGenre,
                    onRate = { scope.launch { listState.animateScrollToItem(ratingsIndex) } },
                ),
            )
        }
        item {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(start = 16.dp, end = 16.dp, top = 8.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                series.description?.takeIf { it.isNotBlank() }?.let {
                    SectionTitle("خلاصه داستان")
                    ExpandableText(text = it)
                }
                if (series.cast.isNotEmpty()) {
                    SectionTitle("بازیگران")
                    CastRow(
                        cast = series.cast,
                        onActorClick = { slug -> onOpenPerson("actor", slug) },
                    )
                }
                if (series.directors.isNotEmpty()) {
                    SectionTitle("کارگردان")
                    PeoplePills(
                        people = series.directors,
                        onPersonClick = { slug -> onOpenPerson("director", slug) },
                    )
                }
                val facts = remember(series) { buildSeriesFacts(series) }
                if (facts.isNotEmpty()) {
                    SectionTitle("مشخصات")
                    DetailFacts(facts = facts)
                }
                // Episode selection now lives entirely in the play/download sheets
                // (season → episode → quality), opened from the hero above —
                // the long inline episode list was replaced by the comments &
                // ratings panel below, consistent with the movie detail screen.
            }
        }
        if (state.similar.isNotEmpty()) {
            item {
                MediaRail(
                    title = "سریال‌های مشابه",
                    items = state.similar,
                    onItemClick = { onOpenTitle(it.contentType, it.slug) },
                )
            }
        }
        item {
            RatingsAndComments(
                ui = state.ratings,
                isLoggedIn = state.isLoggedIn,
                onSubmit = onSubmitRating,
                onRequireLogin = onRequireLogin,
                modifier = Modifier.padding(top = 20.dp),
            )
        }
    }

    if (showPlaySheet) {
        SeriesPlaybackSheet(
            seasons = seasons,
            initialSeasonIndex = state.selectedSeasonIndex,
            mode = SeriesSheetMode.PLAY,
            onPlay = { episode, url -> onPlayEpisode(episode, url) },
            onOffline = { _, _ -> },
            onFile = { _, _ -> },
            onDismiss = { showPlaySheet = false },
        )
    }

    if (showDownloadSheet) {
        SeriesPlaybackSheet(
            seasons = seasons,
            initialSeasonIndex = state.selectedSeasonIndex,
            mode = SeriesSheetMode.DOWNLOAD,
            onPlay = { _, _ -> },
            onOffline = { episode, url -> onDownloadEpisodeOffline(episode, url) },
            onFile = { episode, url -> onDownloadEpisodeFile(episode, url) },
            onDismiss = { showDownloadSheet = false },
        )
    }

    if (showCollectionSheet) {
        AddToCollectionSheet(
            contentType = "series",
            objectId = series.id,
            title = series.title,
            onDismiss = { showCollectionSheet = false },
        )
    }
}

/** Assemble the non-empty «مشخصات» rows for a series detail page. */
internal fun buildSeriesFacts(series: SeriesDetailDto): List<Pair<String, String>> = buildList {
    series.countries.mapNotNull { it.name.takeIf(String::isNotBlank) }
        .takeIf { it.isNotEmpty() }?.let { add("کشور" to it.joinToString("، ")) }
    series.language?.takeIf { it.isNotBlank() }?.let { add("زبان" to it) }
    contentFormatLabel(series.contentFormat)?.let { add("فرمت" to it) }
    val years = when {
        series.startYear != null && series.endYear != null && series.endYear != series.startYear ->
            "${series.startYear} تا ${series.endYear}"
        series.startYear != null -> series.startYear.toString()
        else -> null
    }
    years?.let { add("سال پخش" to it) }
    series.seasons.size.takeIf { it > 0 }?.let { add("فصل‌ها" to "$it فصل") }
    availabilityLabel(series.isDubbed, series.hasSubtitle)?.let { add("امکانات" to it) }
    series.imdbId?.takeIf { it.isNotBlank() }?.let { add("IMDb" to it) }
}

/**
 * The newest episode that can play, with its subtitled mirror first (dubbed only
 * when that is all there is) — «تماشای آخرین قسمت».
 */
internal fun latestEpisodeStream(seasons: List<SeasonDto>): Pair<EpisodeDto, String>? {
    val episode = seasons
        .sortedByDescending { it.seasonNumber }
        .firstNotNullOfOrNull { season ->
            season.episodes
                .sortedByDescending { it.episodeNumber }
                .firstOrNull { resolveEpisodeStreamUrl(it) != null }
        } ?: return null
    val links = episode.streamLinks.filter { it.url.isNotBlank() }
    val url = links.firstOrNull { it.kind == "softsub" }?.url
        ?: links.firstOrNull { it.kind != "dubbed" }?.url
        ?: resolveEpisodeStreamUrl(episode)
        ?: return null
    return episode to url
}

/** Resolve the best available online stream URL for an episode. */
fun resolveEpisodeStreamUrl(episode: EpisodeDto): String? {
    episode.videoUrl?.takeIf { it.isNotBlank() }?.let { return it }
    episode.streamLinks
        .firstOrNull { it.kind.equals("stream", ignoreCase = true) && it.url.isNotBlank() }
        ?.let { return it.url }
    return episode.streamLinks.firstOrNull { it.url.isNotBlank() }?.url
}
