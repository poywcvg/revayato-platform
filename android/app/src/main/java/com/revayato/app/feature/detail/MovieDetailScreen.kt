package com.revayato.app.feature.detail

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
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.GenreDto
import com.revayato.app.data.model.MovieDetailDto
import com.revayato.app.feature.collections.AddToCollectionSheet
import com.revayato.app.feature.player.buildQualitiesFromLinks
import com.revayato.app.feature.player.encodeQualities
import com.revayato.app.feature.player.encodeSubtitles
import com.revayato.app.feature.player.groupPlaybackLinks
import com.revayato.app.ui.components.ErrorState
import com.revayato.app.ui.components.LoadingState
import com.revayato.app.ui.components.MediaRail

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MovieDetailScreen(
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
    viewModel: MovieDetailViewModel = hiltViewModel(),
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
            is UiState.Success -> MovieDetailBody(
                movie = content.data,
                state = state,
                onPlay = onPlay,
                onOpenTitle = onOpenTitle,
                onOpenPerson = onOpenPerson,
                onOpenGenre = onOpenGenre,
                onToggleWatchlist = viewModel::toggleWatchlist,
                onToggleLike = viewModel::toggleLike,
                onWatchTogether = viewModel::createWatchParty,
                onDownloadOffline = viewModel::downloadOffline,
                onDownloadFile = viewModel::downloadFile,
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
        )
    }

    if (state.showReportSheet) {
        ReportProblemSheet(
            contentLabel = "این فیلم",
            submitting = state.reportSubmitting,
            onSubmit = viewModel::submitReport,
            onDismiss = viewModel::dismissReport,
        )
    }
}

@Composable
private fun MovieDetailBody(
    movie: MovieDetailDto,
    state: MovieDetailState,
    onPlay: (String, Int, String, String, String, Long, Int, String, String) -> Unit,
    onOpenTitle: (String, String) -> Unit,
    onOpenPerson: (kind: String, slug: String) -> Unit,
    onOpenGenre: (GenreDto) -> Unit,
    onToggleWatchlist: () -> Unit,
    onToggleLike: () -> Unit,
    onWatchTogether: () -> Unit,
    onDownloadOffline: (String) -> Unit,
    onDownloadFile: (String) -> Unit,
    onSubmitRating: (Double, String, Boolean) -> Unit,
    onRequireLogin: () -> Unit,
) {
    val streamUrl = resolveMovieStreamUrl(movie)
    val subtitlesEncoded = encodeSubtitles(movie.subtitleTracks)
    val qualities = remember(movie) { buildQualitiesFromLinks(movie.downloadLinks) }
    val qualitiesEncoded = remember(qualities) { encodeQualities(qualities) }
    // Grouped version/quality mirrors drive both the online-play picker and the
    // download sheet, so dub/sub separation is consistent across the two flows.
    val playbackGroups = remember(movie) { groupPlaybackLinks(movie.downloadLinks) }
    val totalPlaybackOptions = remember(playbackGroups) { playbackGroups.sumOf { it.options.size } }
    var showDownloadSheet by remember { mutableStateOf(false) }
    var showQualitySheet by remember { mutableStateOf(false) }
    var showCollectionSheet by remember { mutableStateOf(false) }
    val hasDownloads = remember(movie, streamUrl) {
        hasDownloadableLinks(movie.downloadLinks, streamUrl)
    }

    // Launch the player on a chosen quality (or the default stream when only one
    // rendition exists).
    fun play(url: String) {
        onPlay("movie", movie.id, movie.slug, movie.title, url, 0L, 0, subtitlesEncoded, qualitiesEncoded)
    }

    // Add the gesture/navigation-bar height to the bottom padding so the last rail
    // clears the phone's system bar (this screen has no Scaffold bottom bar).
    val navBottom = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = 32.dp + navBottom),
    ) {
        item {
            DetailBackdrop(
                backdropUrl = movie.backdrop ?: movie.poster,
                posterUrl = movie.poster,
                title = movie.title,
            )
        }
        item {
            // Pull the content column up so the poster in PosterHeader overlaps the
            // lower edge of the backdrop — a cinematic, layered hero.
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .offset(y = (-48).dp)
                    .padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                PosterHeader(
                    posterUrl = movie.poster,
                    title = movie.title,
                    secondaryTitle = movie.secondaryTitle,
                    year = movie.releaseYear,
                    rating = movie.imdbRating ?: movie.ratingAverage,
                    durationMinutes = movie.durationMinutes,
                    ageRating = movie.ageRating,
                )
                GenreChips(genres = movie.genres, onGenreClick = onOpenGenre)
                PrimaryActions(
                    canPlay = streamUrl != null,
                    inWatchlist = state.inWatchlist,
                    liked = state.liked,
                    hasDownloads = hasDownloads,
                    onPlay = {
                        streamUrl?.let { url ->
                            // Offer a version/quality picker when more than one
                            // mirror exists; otherwise jump straight into the player.
                            if (totalPlaybackOptions > 1) showQualitySheet = true else play(url)
                        }
                    },
                    onToggleWatchlist = onToggleWatchlist,
                    onToggleLike = onToggleLike,
                    onDownload = { showDownloadSheet = true },
                    onWatchTogether = onWatchTogether,
                    onAddToCollection = {
                        if (state.isLoggedIn) showCollectionSheet = true else onRequireLogin()
                    },
                )
                movie.description?.takeIf { it.isNotBlank() }?.let {
                    SectionTitle("خلاصه داستان")
                    ExpandableText(text = it)
                }
                if (movie.cast.isNotEmpty()) {
                    SectionTitle("بازیگران")
                    CastRow(
                        cast = movie.cast,
                        onActorClick = { slug -> onOpenPerson("actor", slug) },
                    )
                }
                if (movie.directors.isNotEmpty()) {
                    SectionTitle("کارگردان")
                    PeoplePills(
                        people = movie.directors,
                        onPersonClick = { slug -> onOpenPerson("director", slug) },
                    )
                }
                val facts = remember(movie) { buildMovieFacts(movie) }
                if (facts.isNotEmpty()) {
                    SectionTitle("مشخصات")
                    DetailFacts(facts = facts)
                }
            }
        }
        if (state.similar.isNotEmpty()) {
            item {
                MediaRail(
                    title = "مشابه این فیلم",
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

    if (showDownloadSheet && hasDownloads) {
        DownloadOptionsSheet(
            links = movie.downloadLinks,
            fallbackStreamUrl = streamUrl,
            onOffline = onDownloadOffline,
            onFile = onDownloadFile,
            onDismiss = { showDownloadSheet = false },
        )
    }

    if (showQualitySheet) {
        QualityPickerSheet(
            links = movie.downloadLinks,
            onSelect = { url -> play(url) },
            onDismiss = { showQualitySheet = false },
        )
    }

    if (showCollectionSheet) {
        AddToCollectionSheet(
            contentType = "movie",
            objectId = movie.id,
            title = movie.title,
            onDismiss = { showCollectionSheet = false },
        )
    }
}

@Composable
fun SectionTitle(text: String, modifier: Modifier = Modifier) {
    Text(
        text = text,
        style = MaterialTheme.typography.titleMedium,
        fontWeight = FontWeight.Bold,
        color = MaterialTheme.colorScheme.onSurface,
        modifier = modifier.padding(top = 8.dp),
    )
}

@Composable
fun BackButton(onBack: () -> Unit, modifier: Modifier = Modifier) {
    IconButton(
        onClick = onBack,
        modifier = modifier.padding(8.dp),
    ) {
        Icon(
            imageVector = Icons.AutoMirrored.Rounded.ArrowForward,
            contentDescription = "بازگشت",
            tint = MaterialTheme.colorScheme.onSurface,
        )
    }
}

/** Friendly Persian label for a content-format code (falls back to the raw value). */
internal fun contentFormatLabel(code: String?): String? = when (code?.lowercase()) {
    null, "" -> null
    "animation" -> "انیمیشن"
    "live_action" -> "لایو اکشن"
    "short" -> "فیلم کوتاه"
    "documentary" -> "مستند"
    else -> code
}

/** Human «امکانات» line built from the dub/subtitle flags. */
internal fun availabilityLabel(isDubbed: Boolean, hasSubtitle: Boolean): String? {
    val parts = buildList {
        if (isDubbed) add("دوبله فارسی")
        if (hasSubtitle) add("زیرنویس فارسی")
    }
    return parts.takeIf { it.isNotEmpty() }?.joinToString(" · ")
}

/** Assemble the non-empty «مشخصات» rows for a movie detail page. */
internal fun buildMovieFacts(movie: MovieDetailDto): List<Pair<String, String>> = buildList {
    movie.countries.mapNotNull { it.name.takeIf(String::isNotBlank) }
        .takeIf { it.isNotEmpty() }?.let { add("کشور" to it.joinToString("، ")) }
    movie.language?.takeIf { it.isNotBlank() }?.let { add("زبان" to it) }
    contentFormatLabel(movie.contentFormat)?.let { add("فرمت" to it) }
    movie.quality?.takeIf { it.isNotBlank() }?.let { add("کیفیت" to it) }
    availabilityLabel(movie.isDubbed, movie.hasSubtitle)?.let { add("امکانات" to it) }
    movie.imdbId?.takeIf { it.isNotBlank() }?.let { add("IMDb" to it) }
}

/** Resolve the best available online stream URL for a movie.
 *  Prefers browser-friendly containers (mp4) over mkv, which some devices'
 *  hardware decoders stumble on for direct progressive playback. */
fun resolveMovieStreamUrl(movie: MovieDetailDto): String? {
    val candidates = buildList {
        movie.videoUrl?.takeIf { it.isNotBlank() }?.let { add(it) }
        movie.downloadLinks
            .filter { it.kind.equals("stream", ignoreCase = true) && it.url.isNotBlank() }
            .forEach { add(it.url) }
        movie.downloadLinks.filter { it.url.isNotBlank() }.forEach { add(it.url) }
    }.distinct()
    if (candidates.isEmpty()) return null
    return candidates.firstOrNull { it.substringBefore('?').endsWith(".mp4", ignoreCase = true) }
        ?: candidates.first()
}
