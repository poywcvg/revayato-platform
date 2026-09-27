package com.revayato.app.feature.player

import android.content.Context
import androidx.annotation.OptIn
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.DefaultRenderersFactory
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import com.revayato.app.core.network.ApiResult
import com.revayato.app.core.playback.WatchProgressEntry
import com.revayato.app.core.playback.WatchProgressStore
import com.revayato.app.core.util.toAbsoluteUrl
import com.revayato.app.data.model.DownloadLinkDto
import com.revayato.app.data.model.EpisodeDto
import com.revayato.app.data.model.PlaybackSubtitleEnsureRequest
import com.revayato.app.data.model.SubtitleTrackDto
import com.revayato.app.data.repository.CatalogRepository
import com.revayato.app.data.repository.EngagementRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class PlayerUiState(
    val isPlaying: Boolean = false,
    val isBuffering: Boolean = true,
    val positionMs: Long = 0,
    val durationMs: Long = 0,
    val bufferedMs: Long = 0,
    val playbackSpeed: Float = 1f,
    val subtitles: List<PlayerSubtitle> = emptyList(),
    val activeSubtitleIndex: Int = -1, // -1 = off
    // Manual subtitle sync offset in ms (+ later, - earlier).
    val subtitleOffsetMs: Long = 0L,
    val qualities: List<PlayerQuality> = emptyList(),
    val activeQualityUrl: String = "",
    // Embedded audio tracks (languages) and the active one.
    val audioTracks: List<PlayerAudioTrack> = emptyList(),
    val activeAudioIndex: Int = 0,
    val title: String = "",
    val error: String? = null,
    // Transient: the player is silently switching to a device-compatible mirror
    // after a decoder/source failure (shows a pill, not a blocking error).
    val recovering: Boolean = false,
    val recoveryNotice: String? = null,
    val ended: Boolean = false,
    val subtitleLoading: Boolean = false,
    val subtitleNotice: String? = null,
    // Series episode switcher (empty for movies / offline episodes).
    val seasons: List<PlayerSeason> = emptyList(),
    val currentEpisodeId: Int = 0,
    val nextEpisodeId: Int? = null,
    val nextEpisodeLabel: String? = null,
    // Whether this title is a series (gates the «قسمت اشتباه» report option).
    val isSeries: Boolean = false,
    // «گزارش خطا» structured problem report.
    val reportSubmitting: Boolean = false,
    val reportDone: Boolean = false,
    val reportMessage: String? = null,
)

@OptIn(UnstableApi::class)
@HiltViewModel
class PlayerViewModel @Inject constructor(
    @ApplicationContext private val context: Context,
    private val engagementRepository: EngagementRepository,
    private val catalogRepository: CatalogRepository,
    private val watchProgressStore: WatchProgressStore,
) : ViewModel() {

    private val _state = MutableStateFlow(PlayerUiState())
    val state: StateFlow<PlayerUiState> = _state.asStateFlow()

    private var contentId: Int = 0
    private var contentType: String = "movie"
    private var titleSlug: String = ""
    private var episodeId: Int = 0
    private var currentMediaUrl: String = ""

    // Continue-Watching bookkeeping. [titleId] stays fixed at the *title* id even
    // when [contentId] follows the active episode, so a series keeps one shelf
    // entry that tracks whichever episode is playing.
    private var titleId: Int = 0
    private var titleForCard: String = ""
    private var posterForCard: String = ""
    private var episodeLabelForCard: String = ""

    // Episode switcher state: the full episode map (id → source) and their play
    // order across seasons, used to jump around and to auto-advance at the end.
    private var episodesById: Map<Int, EpisodeDto> = emptyMap()
    private var orderedEpisodeIds: List<Int> = emptyList()

    // Audio-gain booster so quiet Persian dubs are loud even at system max volume
    // (the fix for "صدا کم است حتی روی ۱۰۰٪"). Attached to the player's audio
    // session as soon as one is assigned; boost is applied gently to avoid clipping.
    private var loudnessEnhancer: android.media.audiofx.LoudnessEnhancer? = null

    // Manual subtitle sync. offset in ms (+ = later), plus per-URL rewritten-file
    // overrides so a nudged sidecar is fed to the player instead of the original.
    private var subtitleOffsetMs: Long = 0L
    private val subtitleOverrides = HashMap<String, android.net.Uri>()

    // Codec-aware auto-fallback: every mirror we could switch to (raw URLs), the
    // ones already tried, and a guard so a genuinely unplayable title still stops
    // after exhausting the candidates instead of looping forever.
    private var candidateSources: List<PlayerQuality> = emptyList()
    private val triedSourceUrls = HashSet<String>()
    private var reportedPlaybackGap = false

    val player: ExoPlayer by lazy {
        // Cache-backed so a title downloaded for offline plays without the network.
        val dataSourceFactory = com.revayato.app.core.download.DownloadUtil.getCacheDataSourceFactory(context)
        // Buffer far ahead (up to ~2 min) into the cache so playback stays smooth at
        // the highest quality, while a short bufferForPlayback keeps startup snappy.
        val loadControl = androidx.media3.exoplayer.DefaultLoadControl.Builder()
            .setBufferDurationsMs(
                50_000,   // minBufferMs — keep a healthy reservoir
                120_000,  // maxBufferMs — pull ~2 min ahead into cache
                1_000,    // bufferForPlaybackMs — start fast
                3_000,    // bufferForPlaybackAfterRebufferMs
            )
            .setPrioritizeTimeOverSizeThresholds(true)
            .setBackBuffer(30_000, true) // keep 30s behind so short rewinds don't re-fetch
            .build()
        // Allow ExoPlayer to fall back to a secondary (often software) decoder when
        // the primary hardware decoder fails to initialise — recovers a large class
        // of "پخش نمی‌شه روی بعضی گوشی‌ها" cases where the HW HEVC/AVC decoder is
        // missing or busy, instead of dying with ERROR_CODE_DECODER_INIT_FAILED.
        val renderersFactory = DefaultRenderersFactory(context)
            .setEnableDecoderFallback(true)
        ExoPlayer.Builder(context, renderersFactory)
            .setMediaSourceFactory(DefaultMediaSourceFactory(dataSourceFactory))
            .setLoadControl(loadControl)
            .setSeekBackIncrementMs(10_000)
            .setSeekForwardIncrementMs(10_000)
            .build()
            .also {
                it.setPlaybackSpeed(1f)
                it.volume = 1f
                it.addListener(playerListener)
            }
    }

    private val playerListener = object : Player.Listener {
        override fun onIsPlayingChanged(isPlaying: Boolean) {
            _state.value = _state.value.copy(isPlaying = isPlaying)
            // Pausing (incl. leaving the app / backgrounding) is the moment we most
            // want a fresh resume point saved.
            if (!isPlaying) persistProgress()
        }

        override fun onPlaybackStateChanged(playbackState: Int) {
            _state.value = _state.value.copy(
                isBuffering = playbackState == Player.STATE_BUFFERING,
                ended = playbackState == Player.STATE_ENDED,
                durationMs = player.duration.coerceAtLeast(0),
                // Once the swapped-in mirror is playable, drop the "finding a
                // compatible version" pill.
                recovering = if (playbackState == Player.STATE_READY) false else _state.value.recovering,
                recoveryNotice = if (playbackState == Player.STATE_READY) null else _state.value.recoveryNotice,
            )
            // A finished title should drop off the Continue Watching shelf.
            if (playbackState == Player.STATE_ENDED) watchProgressStore.remove(contentType, titleId)
        }

        override fun onPlayerError(error: androidx.media3.common.PlaybackException) {
            // Before blocking the viewer with an error, try to auto-switch to a
            // device-compatible mirror: many failures here are an HEVC/AV1/10-bit
            // encode this phone can't decode, or a dead source host. Falling back to
            // another rung (H.264 first) plays the film transparently.
            if (isRecoverablePlaybackError(error)) {
                if (tryAutoFallback(error)) return
                // Every mirror was tried and none decodes on this device — we've
                // already asked the backend to fetch a compatible encode.
                _state.value = _state.value.copy(
                    error = "این نسخه روی این دستگاه قابل پخش نیست. نسخهٔ سازگار به‌صورت خودکار در حال آماده‌سازی است؛ کمی بعد دوباره تلاش کنید.",
                    recovering = false,
                    recoveryNotice = null,
                )
                return
            }
            _state.value = _state.value.copy(
                error = "پخش با خطا مواجه شد: ${error.errorCodeName}",
                recovering = false,
                recoveryNotice = null,
            )
        }

        // Attach (or re-attach) the loudness booster whenever the audio session is
        // (re)assigned — e.g. after a source swap — so the +gain survives quality
        // and episode changes.
        override fun onAudioSessionIdChanged(audioSessionId: Int) {
            attachLoudnessEnhancer(audioSessionId)
        }

        // Keep the audio-track list in sync with what the media actually exposes.
        override fun onTracksChanged(tracks: androidx.media3.common.Tracks) {
            refreshAudioTracks(tracks)
        }
    }

    /** Build/refresh a [LoudnessEnhancer] on the given session with a gentle boost. */
    private fun attachLoudnessEnhancer(sessionId: Int) {
        if (sessionId == androidx.media3.common.C.AUDIO_SESSION_ID_UNSET) return
        runCatching {
            loudnessEnhancer?.release()
            loudnessEnhancer = android.media.audiofx.LoudnessEnhancer(sessionId).apply {
                // ~+6 dB. LoudnessEnhancer is dynamics-aware, so this lifts quiet
                // dubs noticeably without hard-clipping already-loud passages.
                setTargetGain(AUDIO_BOOST_MB)
                enabled = true
            }
        }
    }

    /** Read the media's audio groups into a selectable list for the "صدا" picker. */
    private fun refreshAudioTracks(tracks: androidx.media3.common.Tracks) {
        val audioGroups = tracks.groups.filter { it.type == androidx.media3.common.C.TRACK_TYPE_AUDIO }
        val list = ArrayList<PlayerAudioTrack>()
        var activeIndex = 0
        audioGroups.forEachIndexed { gi, group ->
            for (ti in 0 until group.length) {
                val fmt = group.getTrackFormat(ti)
                val label = fmt.label
                    ?: fmt.language?.let { audioLanguageLabel(it) }
                    ?: "صدای ${list.size + 1}"
                if (group.isTrackSelected(ti)) activeIndex = list.size
                list.add(PlayerAudioTrack(label = label, groupOrdinal = gi, trackIndex = ti))
            }
        }
        _state.value = _state.value.copy(audioTracks = list, activeAudioIndex = activeIndex)
    }

    private fun audioLanguageLabel(code: String): String = when (code.lowercase().take(2)) {
        "fa", "pe" -> "فارسی"
        "en" -> "انگلیسی"
        "ar" -> "عربی"
        else -> code
    }

    fun setup(args: PlayerArgs) {
        if (contentId == args.id && player.currentMediaItem != null) return
        contentId = args.id
        contentType = args.contentType
        titleSlug = args.slug
        episodeId = args.episodeId
        titleId = args.id
        titleForCard = args.title
        posterForCard = ""
        episodeLabelForCard = ""

        val subtitles = args.subtitles
        // Prefer a codec THIS device can actually decode as the auto-play default.
        // Providers list the x265/HEVC/10-bit encode as the top "quality", so a
        // pure resolution sort makes it the default — and a phone without an HEVC
        // decoder then fails to play. Every rung stays selectable in the menu.
        candidateSources = args.qualities
        triedSourceUrls.clear()
        reportedPlaybackGap = false
        val startUrl = chooseCompatibleStartUrl(args.url, args.qualities)
        triedSourceUrls.add(startUrl)

        _state.value = _state.value.copy(
            title = args.title,
            subtitles = subtitles,
            qualities = args.qualities,
            activeQualityUrl = startUrl,
            isSeries = !contentType.equals("movie", ignoreCase = true),
            recovering = false,
            recoveryNotice = null,
        )

        val url = startUrl.toAbsoluteUrl() ?: run {
            _state.value = _state.value.copy(error = "لینک پخش نامعتبر است")
            return
        }
        currentMediaUrl = url

        // Resume from where the viewer left off. An explicit startPositionMs from a
        // deep-link wins; otherwise fall back to the locally-saved position for this
        // exact title+episode, but only when it's a meaningful mid-watch spot.
        val resumeMs = if (args.startPositionMs > 0) {
            args.startPositionMs
        } else {
            watchProgressStore.get(contentType, titleId)
                ?.takeIf {
                    it.episodeId == episodeId &&
                        it.durationMs > RESUME_MIN_DURATION_MS &&
                        it.positionMs in RESUME_MIN_POSITION_MS..(it.durationMs - RESUME_TAIL_MS)
                }
                ?.positionMs ?: 0L
        }

        player.setMediaItem(buildMediaItem(url, subtitles), resumeMs)
        player.prepare()
        player.playWhenReady = true
        if (subtitles.isNotEmpty()) selectSubtitle(0)
        startProgressLoop()

        // For a movie we won't hit loadSeriesEpisodes(), so fetch a poster once so
        // the Continue Watching card has artwork (best-effort, offline-safe).
        if (contentType.equals("movie", ignoreCase = true) && titleSlug.isNotBlank()) {
            viewModelScope.launch {
                (catalogRepository.movieDetail(titleSlug) as? ApiResult.Success)?.data?.let { detail ->
                    posterForCard = detail.poster.orEmpty()
                    if (titleForCard.isBlank()) titleForCard = detail.title
                }
            }
        }

        // Kick off the backend auto-subtitle import for online streams that have
        // no embedded/attached Persian track yet — but only for the versions where
        // that makes sense (see gateSubtitleImport: dubbed/hardsub are skipped).
        if (args.isRemote && titleSlug.isNotBlank()) {
            gateSubtitleImport(hadSubtitles = subtitles.isNotEmpty())
        }

        // For a series, load the full season/episode tree so the viewer can jump
        // between episodes without leaving the player.
        if (!contentType.equals("movie", ignoreCase = true) && titleSlug.isNotBlank()) {
            _state.value = _state.value.copy(currentEpisodeId = episodeId)
            loadSeriesEpisodes()
        }
    }

    /** Fetch the series' seasons/episodes for the in-player switcher (best-effort). */
    private fun loadSeriesEpisodes() {
        viewModelScope.launch {
            val res = catalogRepository.seriesDetail(titleSlug)
            if (res !is ApiResult.Success) return@launch
            // Keep the series-level title/poster for the Continue Watching card so a
            // series shows its own artwork rather than a single episode's.
            posterForCard = res.data.poster.orEmpty()
            if (res.data.title.isNotBlank()) titleForCard = res.data.title
            val map = LinkedHashMap<Int, EpisodeDto>()
            val order = ArrayList<Int>()
            val seasons = res.data.seasons.map { season ->
                PlayerSeason(
                    seasonNumber = season.seasonNumber,
                    title = season.title.ifBlank { "فصل ${season.seasonNumber}" },
                    episodes = season.episodes.map { ep ->
                        map[ep.id] = ep
                        order += ep.id
                        PlayerEpisode(
                            id = ep.id,
                            seasonNumber = season.seasonNumber,
                            episodeNumber = ep.episodeNumber,
                            title = ep.title.ifBlank { "قسمت ${ep.episodeNumber}" },
                            poster = ep.poster,
                            playable = episodeStreamUrl(ep) != null,
                        )
                    },
                )
            }
            episodesById = map
            orderedEpisodeIds = order
            _state.value = _state.value.copy(seasons = seasons, currentEpisodeId = episodeId)
            recomputeNext()
        }
    }

    /**
     * Jump to another episode of the same series in place: swaps the source,
     * subtitles and quality list, restarts from the top and re-runs the subtitle
     * import — all without tearing down the player or leaving the screen.
     */
    fun selectEpisode(id: Int) {
        if (id == episodeId && player.currentMediaItem != null) return
        val ep = episodesById[id] ?: return
        val raw = episodeStreamUrl(ep) ?: return
        val subtitles = toPlayerSubtitles(ep.subtitleTracks)
        val qualities = decodeQualities(encodeQualities(buildQualitiesFromLinks(ep.streamLinks)), raw)

        // New content → reset codec-fallback bookkeeping and start on a mirror this
        // device can decode (see chooseCompatibleStartUrl / setup).
        candidateSources = qualities
        triedSourceUrls.clear()
        reportedPlaybackGap = false
        val startRaw = chooseCompatibleStartUrl(raw, qualities)
        triedSourceUrls.add(startRaw)
        val abs = startRaw.toAbsoluteUrl() ?: return

        // New content → drop any subtitle sync offset from the previous episode.
        subtitleOffsetMs = 0L
        subtitleOverrides.clear()

        episodeId = ep.id
        contentId = ep.id
        currentMediaUrl = abs
        player.setMediaItem(buildMediaItem(abs, subtitles), 0L)
        player.prepare()
        player.playWhenReady = true

        _state.value = _state.value.copy(
            title = ep.title.ifBlank { "قسمت ${ep.episodeNumber}" },
            subtitles = subtitles,
            activeSubtitleIndex = -1,
            qualities = qualities,
            activeQualityUrl = startRaw,
            currentEpisodeId = ep.id,
            positionMs = 0,
            subtitleOffsetMs = 0L,
            isBuffering = true,
            ended = false,
            error = null,
            recovering = false,
            recoveryNotice = null,
            subtitleLoading = false,
            subtitleNotice = null,
        )
        if (subtitles.isNotEmpty()) selectSubtitle(0)
        recomputeNext()

        if (abs.startsWith("http", ignoreCase = true) && titleSlug.isNotBlank()) {
            // Classify from this episode's own links — no extra fetch needed.
            gateSubtitleImport(hadSubtitles = subtitles.isNotEmpty(), knownLinks = ep.streamLinks)
        }
    }

    /** Restart the current episode/movie from the beginning. */
    fun replay() {
        player.seekTo(0)
        player.playWhenReady = true
        _state.value = _state.value.copy(ended = false)
    }

    /** Recompute the "next episode" pointer for auto-advance from where we are. */
    private fun recomputeNext() {
        val idx = orderedEpisodeIds.indexOf(episodeId)
        val nextId = if (idx >= 0) orderedEpisodeIds.getOrNull(idx + 1) else null
        val nextEp = nextId?.let { episodesById[it] }
        _state.value = _state.value.copy(
            nextEpisodeId = nextId,
            nextEpisodeLabel = nextEp?.let { it.title.ifBlank { "قسمت ${it.episodeNumber}" } },
        )
    }

    /** Best online/offline source URL for an episode (mirrors the detail screen). */
    private fun episodeStreamUrl(ep: EpisodeDto): String? {
        ep.videoUrl?.takeIf { it.isNotBlank() }?.let { return it }
        ep.streamLinks.firstOrNull { it.kind.equals("stream", ignoreCase = true) && it.url.isNotBlank() }
            ?.let { return it.url }
        return ep.streamLinks.firstOrNull { it.url.isNotBlank() }?.url
    }

    private fun toPlayerSubtitles(tracks: List<SubtitleTrackDto>): List<PlayerSubtitle> =
        tracks.mapNotNull { t ->
            val url = t.src.ifBlank { t.sourceUrl.orEmpty() }
            if (url.isBlank()) return@mapNotNull null
            PlayerSubtitle(
                label = t.label.ifBlank { t.language.ifBlank { "زیرنویس" } },
                url = url,
                language = t.language.ifBlank { "fa" },
            )
        }

    private fun buildMediaItem(url: String, subtitles: List<PlayerSubtitle>): MediaItem {
        val builder = MediaItem.Builder().setUri(url)
        if (subtitles.isNotEmpty()) {
            builder.setSubtitleConfigurations(
                subtitles.map { sub ->
                    // A sync-shifted local file (if any) replaces the original sidecar.
                    val uri = subtitleOverrides[sub.url]
                        ?: android.net.Uri.parse(sub.url.toAbsoluteUrl() ?: sub.url)
                    MediaItem.SubtitleConfiguration.Builder(uri)
                        .setMimeType(guessSubtitleMime(sub.url))
                        .setLanguage(sub.language)
                        .setLabel(sub.label)
                        .setSelectionFlags(androidx.media3.common.C.SELECTION_FLAG_DEFAULT)
                        .build()
                },
            )
        }
        return builder.build()
    }

    /**
     * Gate the subtitle auto-importer by the version of the mirror now playing.
     *
     * Per product rule: the importer must NOT act on **dubbed** (دوبله) online
     * playback — the audio is already Persian, so fetching a subtitle there is both
     * unwanted and wrong. A burned-in **hardsub** already carries its subtitle in the
     * picture, so there is nothing to import either. The importer runs only for
     * **soft-subtitled** (زیرنویس) and untagged **original** mirrors, which is exactly
     * where a missing Persian sidecar should be carefully fetched and synced.
     *
     * The version is decided with the same classifier the download/play pickers use,
     * matched against the title's own links, so it stays consistent with what the
     * user picked. [knownLinks] lets the episode switcher skip the extra fetch.
     */
    private fun gateSubtitleImport(hadSubtitles: Boolean, knownLinks: List<DownloadLinkDto>? = null) {
        viewModelScope.launch {
            val kind = currentPlaybackVersion(knownLinks)
            when (kind) {
                PlaybackVersionKind.DUBBED, PlaybackVersionKind.HARDSUB -> {
                    // Nothing to import; clear any stale "finding subtitle" state.
                    _state.value = _state.value.copy(subtitleLoading = false, subtitleNotice = null)
                }
                // SOFTSUB, ORIGINAL, or an unmatched URL → ensure a subtitle exists.
                // Pass the resolved version so the backend picks the precise lane.
                else -> ensureSubtitles(hadSubtitles, versionToken = kind.backendToken)
            }
        }
    }

    /**
     * Best-effort classification of the mirror currently on screen. Matches
     * [currentMediaUrl] against the title's own download/stream links and runs the
     * shared [classifyPlaybackVersion]. When no link matches (deep links, ad-hoc
     * URLs) it still inspects the bare URL so an obvious «دوبله»/dub link is caught;
     * a hint-free URL falls through to ORIGINAL, preserving the import behaviour.
     */
    private suspend fun currentPlaybackVersion(knownLinks: List<DownloadLinkDto>?): PlaybackVersionKind {
        val links = knownLinks ?: fetchCurrentLinks()
        val match = links.firstOrNull { link ->
            val abs = link.url.toAbsoluteUrl() ?: link.url
            abs == currentMediaUrl || link.url == currentMediaUrl
        }
        // Fall back to classifying the bare URL so dubbed links are still caught.
        return classifyPlaybackVersion(match ?: DownloadLinkDto(url = currentMediaUrl))
    }

    /** Fetch the download/stream links for the title or episode now playing. */
    private suspend fun fetchCurrentLinks(): List<DownloadLinkDto> =
        if (contentType.equals("movie", ignoreCase = true)) {
            (catalogRepository.movieDetail(titleSlug) as? ApiResult.Success)?.data?.downloadLinks.orEmpty()
        } else {
            episodesById[episodeId]?.streamLinks
                ?: (catalogRepository.seriesDetail(titleSlug) as? ApiResult.Success)?.data
                    ?.seasons?.asSequence()?.flatMap { it.episodes.asSequence() }
                    ?.firstOrNull { it.id == episodeId }?.streamLinks
                ?: emptyList()
        }

    /**
     * Report the missing subtitle to the backend (which extracts the embedded
     * Persian track and falls back to SubtitleStar → Subzone), then poll until
     * the synced cues are attached and swap them onto the running player.
     */
    private fun ensureSubtitles(hadSubtitles: Boolean, versionToken: String = "") {
        viewModelScope.launch {
            _state.value = _state.value.copy(
                subtitleLoading = true,
                subtitleNotice = if (hadSubtitles) null else "در حال یافتن زیرنویس فارسی…",
            )
            val ensureType = if (contentType.equals("movie", ignoreCase = true)) "movie" else "series"
            val request = PlaybackSubtitleEnsureRequest(
                contentType = ensureType,
                slug = titleSlug,
                episodeId = episodeId,
                version = versionToken,
                sourceUrl = currentMediaUrl,
                sync = true,
            )
            var reportId: Int? = null
            when (val res = catalogRepository.ensurePlaybackSubtitles(request)) {
                is ApiResult.Success -> {
                    reportId = res.data.reportId
                    if (res.data.subtitleTracks.isNotEmpty()) {
                        applySubtitleTracks(res.data.subtitleTracks)
                        _state.value = _state.value.copy(subtitleLoading = false, subtitleNotice = null)
                        return@launch
                    }
                    if (stopSubtitleHunt(res.data.status)) return@launch
                }
                is ApiResult.Error -> {
                    // Silent: subtitles are best-effort, playback continues regardless.
                    _state.value = _state.value.copy(subtitleLoading = false, subtitleNotice = null)
                    if (hadSubtitles) return@launch
                }
            }

            // Poll the cheap status endpoint until the worker finishes extraction.
            // The urgent embedded-subtitle worker runs ffmpeg on the server and can
            // take a couple of minutes, while the sync lane only tries fast provider
            // sidecars. Polling for just 30s used to strand the player on "loading"
            // and miss the precisely-synced embedded track once it landed, so we keep
            // watching for up to ~2.5 minutes with a gentle back-off.
            var waitedMs = 0L
            val maxWaitMs = 150_000L
            while (waitedMs < maxWaitMs) {
                val stepMs = if (waitedMs < 30_000L) 3_000L else 6_000L
                delay(stepMs)
                waitedMs += stepMs
                val poll = catalogRepository.playbackSubtitleStatus(
                    contentType = ensureType,
                    slug = titleSlug,
                    episodeId = episodeId,
                    reportId = reportId,
                )
                if (poll is ApiResult.Success && poll.data.subtitleTracks.isNotEmpty()) {
                    applySubtitleTracks(poll.data.subtitleTracks)
                    _state.value = _state.value.copy(subtitleLoading = false, subtitleNotice = null)
                    return@launch
                }
                if (poll is ApiResult.Success && stopSubtitleHunt(poll.data.status)) return@launch
            }
            _state.value = _state.value.copy(
                subtitleLoading = false,
                subtitleNotice = if (_state.value.subtitles.isEmpty()) "زیرنویسی برای این نسخه یافت نشد" else null,
            )
        }
    }

    /**
     * The server's final word on a hunt: `not_needed` (dubbed stream or a
     * Persian-language title) ends it silently, `exhausted` (every crawler came
     * back empty for this file) ends it with a notice instead of polling on.
     */
    private fun stopSubtitleHunt(status: String): Boolean {
        val notice = when (status) {
            "not_needed" -> null
            "exhausted" -> if (_state.value.subtitles.isEmpty()) "زیرنویسی برای این نسخه یافت نشد" else null
            else -> return false
        }
        _state.value = _state.value.copy(subtitleLoading = false, subtitleNotice = notice)
        return true
    }

    /** Merge newly-found tracks into the player and auto-select the first one. */
    private fun applySubtitleTracks(tracks: List<SubtitleTrackDto>) {
        val incoming = toPlayerSubtitles(tracks)
        if (incoming.isEmpty()) return

        val merged = (_state.value.subtitles + incoming)
            .distinctBy { it.url }
        if (merged.size == _state.value.subtitles.size) return // nothing new

        // Point at the first freshly-imported (precisely-synced) track, which may
        // sit after any tracks that were already attached before the import.
        val freshIndex = merged.indexOfFirst { m -> incoming.any { it.url == m.url } }
            .coerceAtLeast(0)

        val pos = player.currentPosition
        val wasPlaying = player.playWhenReady
        player.setMediaItem(buildMediaItem(currentMediaUrl, merged), pos)
        player.prepare()
        player.playWhenReady = wasPlaying
        _state.value = _state.value.copy(subtitles = merged)
        // Auto-enable the freshly imported Persian track.
        selectSubtitle(freshIndex)
    }

    private fun startProgressLoop() {
        viewModelScope.launch {
            var lastReport = 0L
            var lastPersist = 0L
            while (true) {
                if (player.isPlaying) {
                    val pos = player.currentPosition
                    val dur = player.duration.coerceAtLeast(1)
                    _state.value = _state.value.copy(
                        positionMs = pos,
                        durationMs = dur,
                        bufferedMs = player.bufferedPosition,
                    )
                    // Report progress to the backend every ~15s.
                    if (pos - lastReport > 15_000) {
                        lastReport = pos
                        engagementRepository.reportProgress(
                            titleId = contentId,
                            slug = titleSlug,
                            contentType = contentType,
                            progressPercent = pos * 100.0 / dur,
                            sourcePage = "android_player",
                        )
                    }
                    // Save a local resume point every ~5s (cheap, survives crashes).
                    if (kotlin.math.abs(pos - lastPersist) > 5_000) {
                        lastPersist = pos
                        persistProgress()
                    }
                }
                delay(500)
            }
        }
    }

    /**
     * Persist (or clear) this title's local resume point. A near-finished title is
     * dropped from the shelf instead of being saved; anything meaningfully mid-watch
     * is upserted with everything the player needs to relaunch straight back into it.
     */
    private fun persistProgress() {
        if (titleId == 0 || currentMediaUrl.isBlank()) return
        val pos = player.currentPosition
        val dur = player.duration
        if (dur <= RESUME_MIN_DURATION_MS) return
        if (pos < RESUME_MIN_POSITION_MS) return
        if (pos >= dur - RESUME_TAIL_MS) {
            watchProgressStore.remove(contentType, titleId)
            return
        }
        val isSeries = !contentType.equals("movie", ignoreCase = true)
        watchProgressStore.upsert(
            WatchProgressEntry(
                contentType = contentType,
                id = titleId,
                slug = titleSlug,
                title = titleForCard.ifBlank { _state.value.title },
                poster = posterForCard,
                episodeId = episodeId,
                episodeLabel = if (isSeries) _state.value.title else "",
                url = currentMediaUrl,
                subtitlesEncoded = encodePlayerSubtitles(_state.value.subtitles),
                qualitiesEncoded = encodeQualities(_state.value.qualities),
                positionMs = pos,
                durationMs = dur,
                updatedAt = System.currentTimeMillis(),
            ),
        )
    }

    fun playPause() {
        if (player.isPlaying) player.pause() else player.play()
    }

    fun seekTo(positionMs: Long) {
        player.seekTo(positionMs.coerceIn(0, player.duration.coerceAtLeast(0)))
    }

    fun seekBy(deltaMs: Long) {
        seekTo(player.currentPosition + deltaMs)
    }

    fun setSpeed(speed: Float) {
        player.setPlaybackSpeed(speed)
        _state.value = _state.value.copy(playbackSpeed = speed)
    }

    /**
     * Switch to a different quality mirror without losing the viewer's place.
     * Position, play/pause, speed and the attached subtitle tracks all carry over
     * to the new source. [rawUrl] is the un-resolved URL as listed in the menu.
     */
    fun selectQuality(rawUrl: String) {
        if (rawUrl.isBlank() || rawUrl == _state.value.activeQualityUrl) return
        val abs = rawUrl.toAbsoluteUrl() ?: return
        val pos = player.currentPosition
        val wasPlaying = player.playWhenReady
        val speed = _state.value.playbackSpeed
        val subtitleIndex = _state.value.activeSubtitleIndex
        // A deliberate manual pick re-opens the auto-fallback cycle so a later
        // failure can still hop to another mirror.
        triedSourceUrls.clear()
        triedSourceUrls.add(rawUrl)
        reportedPlaybackGap = false
        currentMediaUrl = abs
        player.setMediaItem(buildMediaItem(abs, _state.value.subtitles), pos)
        player.prepare()
        player.playWhenReady = wasPlaying
        player.setPlaybackSpeed(speed)
        _state.value = _state.value.copy(
            activeQualityUrl = rawUrl,
            error = null,
            recovering = false,
            recoveryNotice = null,
        )
        if (subtitleIndex >= 0) selectSubtitle(subtitleIndex)
    }

    /**
     * Pick the source to auto-play. Honours [preferredRaw] when this device can
     * decode its codec; otherwise falls to the highest-resolution mirror the
     * device *can* decode (H.264 first). Keeps HEVC/AV1 rungs in the menu for
     * phones that support them — this only moves the default off an unplayable one.
     */
    private fun chooseCompatibleStartUrl(preferredRaw: String, qualities: List<PlayerQuality>): String {
        if (preferredRaw.isBlank()) return preferredRaw
        val preferredLabel = qualities.firstOrNull { it.url == preferredRaw }?.label
        if (!codecLikelyUnsupported(preferredRaw, preferredLabel)) return preferredRaw
        val compatible = qualities
            .filter { it.url.isNotBlank() && !codecLikelyUnsupported(it.url, it.label) }
            .maxByOrNull { resolutionRank(it.label) }
        return compatible?.url ?: preferredRaw
    }

    /** Next untried mirror to fall back to, device-decodable codecs first. */
    private fun nextFallbackSource(): PlayerQuality? =
        candidateSources
            .filter { it.url.isNotBlank() && it.url !in triedSourceUrls }
            .sortedWith(
                compareByDescending<PlayerQuality> { deviceCodecRank(it.url, it.label) }
                    .thenByDescending { resolutionRank(it.label) },
            )
            .firstOrNull()

    /** Whether an [error] is the kind another mirror could plausibly fix. */
    private fun isRecoverablePlaybackError(error: androidx.media3.common.PlaybackException): Boolean =
        when (error.errorCode) {
            // Source/IO (dead host, network) · container/manifest unsupported ·
            // decoder init/decode failures (missing/incapable HEVC/AV1 decoder).
            in 2000..2999, in 3001..3004, in 4001..4005 -> true
            else -> false
        }

    /**
     * Silently swap to the next device-compatible mirror after a decoder/source
     * failure, keeping the viewer's place. Returns false (and files a background
     * self-heal report) once no untried, decodable mirror remains.
     */
    private fun tryAutoFallback(error: androidx.media3.common.PlaybackException): Boolean {
        triedSourceUrls.add(_state.value.activeQualityUrl)
        val next = nextFallbackSource() ?: run {
            reportPlaybackGapOnce()
            return false
        }
        val abs = next.url.toAbsoluteUrl() ?: run {
            triedSourceUrls.add(next.url)
            return tryAutoFallback(error)
        }
        val pos = player.currentPosition
        val wasPlaying = player.playWhenReady
        val speed = _state.value.playbackSpeed
        val subtitleIndex = _state.value.activeSubtitleIndex
        triedSourceUrls.add(next.url)
        currentMediaUrl = abs
        player.setMediaItem(buildMediaItem(abs, _state.value.subtitles), pos)
        player.prepare()
        player.playWhenReady = wasPlaying
        player.setPlaybackSpeed(speed)
        _state.value = _state.value.copy(
            activeQualityUrl = next.url,
            error = null,
            recovering = true,
            recoveryNotice = "در حال یافتن نسخهٔ سازگار برای پخش…",
            isBuffering = true,
        )
        if (subtitleIndex >= 0) selectSubtitle(subtitleIndex)
        return true
    }

    /**
     * Ask the backend (once per title/episode) to re-crawl a device-safe H.264
     * MP4/HLS mirror when this device has no playable source. Best-effort and
     * silent — it self-heals the catalog for the next viewer.
     */
    private fun reportPlaybackGapOnce() {
        if (reportedPlaybackGap) return
        if (titleSlug.isBlank() && titleId == 0) return
        reportedPlaybackGap = true
        val reportType = if (contentType.equals("movie", ignoreCase = true)) "movie" else "series"
        viewModelScope.launch {
            runCatching {
                catalogRepository.reportContentIssue(
                    contentType = reportType,
                    problemType = "playback",
                    objectId = titleId,
                    slug = titleSlug,
                    episodeId = episodeId,
                    sourceUrl = currentMediaUrl,
                    detail = "auto: decoder/source failure on device; no compatible mirror found",
                )
            }
        }
    }

    /** Numeric resolution rank of a quality label so higher resolutions sort first. */
    private fun resolutionRank(label: String): Int =
        Regex("(\\d{3,4})\\s*p", RegexOption.IGNORE_CASE).find(label)?.groupValues?.get(1)?.toIntOrNull() ?: 0

    /**
     * User-initiated subtitle track change from the picker. Resets any manual sync
     * offset (it belonged to the previous track) before selecting the new one.
     */
    fun selectSubtitleByUser(index: Int) {
        if (index != _state.value.activeSubtitleIndex) resetSubtitleSync()
        selectSubtitle(index)
    }

    /** Clear the manual sync offset and any rewritten sidecar files. */
    private fun resetSubtitleSync() {
        if (subtitleOffsetMs == 0L && subtitleOverrides.isEmpty()) return
        subtitleOffsetMs = 0L
        subtitleOverrides.clear()
        _state.value = _state.value.copy(subtitleOffsetMs = 0L)
        rebuildPreservingPosition()
    }

    /**
     * Nudge the active subtitle's timing by [deltaMs] (+ later, - earlier). Rewrites
     * the sidecar's cue timestamps and swaps the shifted file onto the player so the
     * viewer can dial out any drift ("جلو/عقب بودن زیرنویس").
     */
    fun nudgeSubtitleOffset(deltaMs: Long) {
        val idx = _state.value.activeSubtitleIndex
        if (idx < 0) {
            _state.value = _state.value.copy(subtitleNotice = "ابتدا یک زیرنویس را روشن کنید")
            return
        }
        val sub = _state.value.subtitles.getOrNull(idx) ?: return
        val newOffset = (subtitleOffsetMs + deltaMs).coerceIn(-60_000L, 60_000L)
        subtitleOffsetMs = newOffset
        _state.value = _state.value.copy(subtitleOffsetMs = newOffset)
        viewModelScope.launch {
            val absUrl = sub.url.toAbsoluteUrl() ?: sub.url
            val shifted = SubtitleSync.shiftedFile(context, absUrl, newOffset)
            if (shifted != null) subtitleOverrides[sub.url] = shifted else subtitleOverrides.remove(sub.url)
            rebuildPreservingPosition()
            selectSubtitle(idx)
        }
    }

    /** Rebuild the media item from [currentMediaUrl] keeping position + play state. */
    private fun rebuildPreservingPosition() {
        if (currentMediaUrl.isBlank()) return
        val pos = player.currentPosition
        val wasPlaying = player.playWhenReady
        val speed = _state.value.playbackSpeed
        player.setMediaItem(buildMediaItem(currentMediaUrl, _state.value.subtitles), pos)
        player.prepare()
        player.playWhenReady = wasPlaying
        player.setPlaybackSpeed(speed)
    }

    /** Switch the embedded audio track (language) by index into [state.audioTracks]. */
    fun selectAudioTrack(index: Int) {
        val target = _state.value.audioTracks.getOrNull(index) ?: return
        val audioGroups = player.currentTracks.groups
            .filter { it.type == androidx.media3.common.C.TRACK_TYPE_AUDIO }
        val group = audioGroups.getOrNull(target.groupOrdinal) ?: return
        val params = player.trackSelectionParameters.buildUpon()
            .setOverrideForType(
                androidx.media3.common.TrackSelectionOverride(
                    group.mediaTrackGroup,
                    target.trackIndex,
                ),
            )
            .build()
        player.trackSelectionParameters = params
        _state.value = _state.value.copy(activeAudioIndex = index)
    }

    fun selectSubtitle(index: Int) {
        val params = player.trackSelectionParameters.buildUpon()
        if (index < 0) {
            params.setPreferredTextLanguage(null)
            params.setSelectUndeterminedTextLanguage(false)
            params.setTrackTypeDisabled(androidx.media3.common.C.TRACK_TYPE_TEXT, true)
        } else {
            val lang = _state.value.subtitles.getOrNull(index)?.language
            // Never leave the text renderer disabled from a previous "off" — otherwise
            // a freshly-attached track would stay hidden even when selected. Prefer the
            // track's language and accept undetermined tags so sideloaded fa cues win.
            params.setTrackTypeDisabled(androidx.media3.common.C.TRACK_TYPE_TEXT, false)
            params.setPreferredTextLanguage(lang)
            params.setSelectUndeterminedTextLanguage(true)
        }
        player.trackSelectionParameters = params.build()
        _state.value = _state.value.copy(activeSubtitleIndex = index)
    }

    fun retry() {
        _state.value = _state.value.copy(error = null, recovering = false, recoveryNotice = null)
        // A manual retry re-opens the self-heal report so a fresh exhaustion can
        // ping the backend again.
        reportedPlaybackGap = false
        if (currentMediaUrl.isNotBlank()) {
            player.setMediaItem(buildMediaItem(currentMediaUrl, _state.value.subtitles), player.currentPosition)
            player.prepare()
            player.playWhenReady = true
        }
    }

    /**
     * File a structured «گزارش خطا» for the title/episode now playing. The backend
     * auto-remediation engine dispatches the fix by [problemType]
     * (subtitle / wrong_title / wrong_episode / playback / audio / other):
     * re-running the subtitle pipeline, re-crawling playback sources, or stripping
     * a contaminated link and re-importing. Best-effort — a failure only surfaces a
     * gentle notice and never disrupts playback.
     */
    fun submitContentReport(problemType: String, detail: String) {
        if (_state.value.reportSubmitting) return
        if (contentId == 0 && titleSlug.isBlank()) return
        _state.value = _state.value.copy(reportSubmitting = true, reportMessage = null)
        viewModelScope.launch {
            // Classify the mirror on screen so the backend can scope a wrong-version
            // strip to the exact lane the viewer is watching (best-effort).
            val versionToken = runCatching { currentPlaybackVersion(null).backendToken }.getOrDefault("")
            val reportType = if (contentType.equals("movie", ignoreCase = true)) "movie" else "series"
            val res = catalogRepository.reportContentIssue(
                contentType = reportType,
                problemType = problemType,
                objectId = titleId,
                slug = titleSlug,
                episodeId = episodeId,
                version = versionToken,
                sourceUrl = currentMediaUrl,
                detail = detail,
            )
            _state.value = when (res) {
                is ApiResult.Success -> _state.value.copy(
                    reportSubmitting = false,
                    reportDone = true,
                    reportMessage = if (res.data.auto) {
                        "گزارشت ثبت شد؛ سیستم در حال بررسی و رفع خودکار مشکل است."
                    } else {
                        "گزارشت ثبت شد و برای بررسی به تیم روایتو رسید. ممنون!"
                    },
                )
                is ApiResult.Error -> _state.value.copy(
                    reportSubmitting = false,
                    reportDone = false,
                    reportMessage = "ارسال گزارش ناموفق بود؛ لطفاً دوباره تلاش کن.",
                )
            }
        }
    }

    /** Reset the report sheet's transient state (called when it is reopened/closed). */
    fun resetContentReport() {
        if (!_state.value.reportDone && _state.value.reportMessage == null && !_state.value.reportSubmitting) return
        _state.value = _state.value.copy(reportSubmitting = false, reportDone = false, reportMessage = null)
    }

    override fun onCleared() {
        // Final flush so exiting the player always leaves an accurate resume point.
        persistProgress()
        runCatching { loudnessEnhancer?.release() }
        loudnessEnhancer = null
        player.release()
        super.onCleared()
    }

    private companion object {
        const val RESUME_MIN_POSITION_MS = 10_000L   // ignore the first few seconds
        const val RESUME_MIN_DURATION_MS = 60_000L   // don't track very short clips
        const val RESUME_TAIL_MS = 60_000L           // treat the last minute as "finished"
        const val AUDIO_BOOST_MB = 600               // audio gain in millibels (+6 dB)
    }
}

@OptIn(UnstableApi::class)
private fun guessSubtitleMime(url: String): String = when {
    url.endsWith(".srt", ignoreCase = true) -> MimeTypes.APPLICATION_SUBRIP
    url.endsWith(".ass", ignoreCase = true) || url.endsWith(".ssa", ignoreCase = true) -> MimeTypes.TEXT_SSA
    url.endsWith(".ttml", ignoreCase = true) || url.endsWith(".xml", ignoreCase = true) -> MimeTypes.APPLICATION_TTML
    else -> MimeTypes.TEXT_VTT
}
