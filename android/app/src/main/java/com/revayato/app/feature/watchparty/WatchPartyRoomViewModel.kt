package com.revayato.app.feature.watchparty

import android.content.Context
import androidx.annotation.OptIn
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import com.revayato.app.BuildConfig
import com.revayato.app.core.auth.TokenStore
import com.revayato.app.core.network.ApiResult
import com.revayato.app.core.util.toAbsoluteUrl
import com.revayato.app.data.model.ChatMessageDto
import com.revayato.app.data.model.PlaybackFailureRequest
import com.revayato.app.data.model.PlaybackStateDto
import com.revayato.app.data.model.RoomContentDto
import com.revayato.app.data.model.RoomDto
import com.revayato.app.data.model.RoomMemberDto
import com.revayato.app.data.repository.CatalogRepository
import com.revayato.app.data.repository.WatchPartyRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Named
import kotlin.math.abs

data class RoomUiState(
    val loading: Boolean = true,
    val error: String? = null,
    val room: RoomDto? = null,
    val content: RoomContentDto? = null,
    val members: List<RoomMemberDto> = emptyList(),
    val messages: List<ChatMessageDto> = emptyList(),
    val isHost: Boolean = false,
    val connected: Boolean = false,
    val playing: Boolean = false,
    val buffering: Boolean = true,
    val positionMs: Long = 0,
    val durationMs: Long = 0,
    val chatDraft: String = "",
    val latencyMs: Long? = null,
    val toast: String? = null,
    val ended: Boolean = false,
    val playbackSpeed: Float = 1f,
    val subtitles: List<PartySubtitle> = emptyList(),
    val activeSubtitleIndex: Int = -1, // -1 = off
    val playerError: String? = null,
)

/** A soft-sub track offered to each viewer independently (subtitles aren't synced). */
data class PartySubtitle(
    val label: String,
    val language: String,
    val url: String,
)

/** One ephemeral floating reaction to animate over the video. */
data class ReactionBurst(
    val id: Long,
    val emoji: String,
    val displayName: String,
)

/** Drift tolerance before a guest hard-seeks to the host position. */
private const val DRIFT_TOLERANCE_MS = 1_800L

@OptIn(UnstableApi::class)
@HiltViewModel
class WatchPartyRoomViewModel @Inject constructor(
    @ApplicationContext private val context: Context,
    @Named("api") apiClient: OkHttpClient,
    private val tokenStore: TokenStore,
    private val watchPartyRepository: WatchPartyRepository,
    private val catalogRepository: CatalogRepository,
    private val json: Json,
) : ViewModel() {

    private val _state = MutableStateFlow(RoomUiState())
    val state: StateFlow<RoomUiState> = _state.asStateFlow()

    // Transient reaction bursts: the screen collects these and animates them,
    // rather than parking them in UI state where they'd persist across recomposes.
    private val _reactions = MutableSharedFlow<ReactionBurst>(
        extraBufferCapacity = 32,
        onBufferOverflow = BufferOverflow.DROP_OLDEST,
    )
    val reactions: SharedFlow<ReactionBurst> = _reactions.asSharedFlow()
    private var reactionSeq = 0L

    private var inviteCode: String = ""
    private var socket: WatchPartySocket? = null
    private var eventJob: Job? = null
    private var heartbeatJob: Job? = null
    private var progressJob: Job? = null

    /** server_clock - local_clock, refined via latency ping/pong. */
    private var clockOffsetMs: Long = 0
    private var pingSentAt: Long = 0
    private var applyingRemote = false
    // Auto-heal dedup: one playback-failure report per failed source, so every
    // member failing at once collapses onto the same repair instead of N crawls.
    private val healedPartyKeys = HashSet<String>()
    private var currentPartySourceUrl: String = ""

    // A long-lived socket must not inherit the REST client's 60s call timeout.
    private val socketClient: OkHttpClient = apiClient.newBuilder()
        .callTimeout(0, TimeUnit.MILLISECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .pingInterval(20, TimeUnit.SECONDS)
        .build()

    val player: ExoPlayer by lazy {
        val dataSourceFactory = DefaultDataSource.Factory(
            context,
            OkHttpDataSource.Factory(socketClient),
        )
        ExoPlayer.Builder(context)
            .setMediaSourceFactory(DefaultMediaSourceFactory(dataSourceFactory))
            .build()
            .also { it.addListener(playerListener) }
    }

    private val playerListener = object : Player.Listener {
        override fun onIsPlayingChanged(isPlaying: Boolean) {
            _state.update { it.copy(playing = isPlaying) }
        }

        override fun onPlaybackStateChanged(playbackState: Int) {
            _state.update {
                it.copy(
                    buffering = playbackState == Player.STATE_BUFFERING,
                    ended = playbackState == Player.STATE_ENDED,
                    durationMs = player.duration.coerceAtLeast(0),
                )
            }
        }

        override fun onPlayerError(error: androidx.media3.common.PlaybackException) {
            _state.update { it.copy(playerError = "پخش با خطا مواجه شد") }
            autoHealPartySource(error)
        }

        override fun onPlaybackParametersChanged(params: androidx.media3.common.PlaybackParameters) {
            _state.update { it.copy(playbackSpeed = params.speed) }
        }
    }

    fun start(code: String) {
        if (inviteCode == code && socket != null) return
        inviteCode = code
        connect()
    }

    private fun connect() {
        _state.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            // Membership must exist before the socket will accept us (consumer
            // rejects non-members with 4403), so join over REST first.
            when (val res = watchPartyRepository.joinRoom(inviteCode)) {
                is ApiResult.Error -> {
                    _state.update { it.copy(loading = false, error = res.message) }
                    return@launch
                }
                is ApiResult.Success -> applyRoom(res.data)
            }
            val token = tokenStore.accessToken()
            if (token.isNullOrBlank()) {
                _state.update { it.copy(loading = false, error = "برای تماشای گروهی باید وارد شوی") }
                return@launch
            }
            val sock = WatchPartySocket(
                baseWsUrl = BuildConfig.WS_BASE_URL,
                inviteCode = inviteCode,
                accessToken = token,
                client = socketClient,
                json = json,
            )
            socket = sock
            eventJob = viewModelScope.launch { sock.events.collect(::onEvent) }
            sock.connect()
        }
    }

    private fun onEvent(event: WsEvent) {
        when (event) {
            is WsEvent.Open -> {
                _state.update { it.copy(connected = true, loading = false) }
                startHeartbeat()
                socket?.latencyPing(System.currentTimeMillis().also { pingSentAt = it })
                socket?.requestSync()
            }
            is WsEvent.RoomState -> {
                applyRoom(event.room)
                val hostRole = event.currentMember?.role == "host"
                _state.update {
                    it.copy(
                        members = event.members,
                        messages = event.messages,
                        isHost = event.room.isHost || hostRole,
                        loading = false,
                    )
                }
                event.playback?.let { applyRemotePlayback(it, hard = true) }
            }
            is WsEvent.Playback -> {
                val hard = event.eventType != "playback.sync" && event.eventType != "playback.state"
                applyRemotePlayback(event.playback, hard = hard)
            }
            is WsEvent.SyncRequested -> {
                // The host holds the authoritative position; answer with a fresh snapshot.
                if (_state.value.isHost) broadcast("playback.sync")
            }
            is WsEvent.Chat -> _state.update { it.copy(messages = it.messages + event.message) }
            is WsEvent.Reaction ->
                _reactions.tryEmit(ReactionBurst(reactionSeq++, event.emoji, event.displayName))
            is WsEvent.MemberJoined -> _state.update { st ->
                val without = st.members.filterNot { it.user?.id == event.member.user?.id }
                st.copy(members = without + event.member)
            }
            is WsEvent.MemberLeft -> _state.update { st ->
                st.copy(
                    members = st.members.map {
                        if (it.user?.id == event.member.user?.id) it.copy(isOnline = false) else it
                    },
                )
            }
            is WsEvent.LatencyPong -> {
                val now = System.currentTimeMillis()
                val rtt = now - pingSentAt
                // Estimate server clock at the midpoint of the round trip.
                clockOffsetMs = event.serverTimeMs - (pingSentAt + rtt / 2)
                _state.update { it.copy(latencyMs = rtt) }
            }
            is WsEvent.Error -> _state.update { it.copy(toast = event.message) }
            is WsEvent.PlaybackFix -> onPlaybackFix(event)
            is WsEvent.MemberFailed -> onMemberFailed(event)
            is WsEvent.Closed -> _state.update {
                it.copy(connected = false, error = mapCloseReason(event.code, it.error))
            }
            is WsEvent.Failure -> _state.update {
                it.copy(connected = false, loading = false, toast = event.reason)
            }
        }
    }

    private fun applyRoom(room: RoomDto) {
        val content = room.content
        _state.update { it.copy(room = room, content = content, isHost = it.isHost || room.isHost) }
        content?.let { ensureMedia(it) }
    }

    private fun ensureMedia(content: RoomContentDto) {
        if (player.currentMediaItem != null) return
        val subtitles = toPartySubtitles(content.subtitleTracks)
        val item = buildMediaItemFor(content, subtitles) ?: return
        currentPartySourceUrl = resolveStreamUrl(content).orEmpty()
        _state.update { it.copy(subtitles = subtitles) }
        player.setMediaItem(item)
        player.prepare()
        // Guests wait for the host's state; playback starts on the first sync.
        player.playWhenReady = false
        // Give every viewer the first (usually Persian) track by default; they can
        // turn it off or switch from the subtitle sheet — this choice isn't synced.
        if (subtitles.isNotEmpty()) selectSubtitle(0)
        startProgressLoop()
    }

    private fun toPartySubtitles(tracks: List<com.revayato.app.data.model.SubtitleTrackDto>): List<PartySubtitle> =
        tracks.mapNotNull { track ->
            val url = track.src.ifBlank { track.sourceUrl.orEmpty() }
            if (url.isBlank()) return@mapNotNull null
            PartySubtitle(
                label = track.label.ifBlank { track.language.ifBlank { "زیرنویس" } },
                language = track.language.ifBlank { "fa" },
                url = url,
            )
        }

    /** Build a MediaItem for the room's content with all soft-sub tracks attached. */
    private fun buildMediaItemFor(
        content: RoomContentDto,
        subtitles: List<PartySubtitle> = toPartySubtitles(content.subtitleTracks),
    ): MediaItem? {
        val streamUrl = resolveStreamUrl(content)?.toAbsoluteUrl() ?: return null
        val builder = MediaItem.Builder().setUri(streamUrl)
        val subs = subtitles.mapNotNull { sub ->
            val url = sub.url.toAbsoluteUrl() ?: return@mapNotNull null
            MediaItem.SubtitleConfiguration.Builder(android.net.Uri.parse(url))
                .setMimeType(guessSubtitleMime(url))
                .setLanguage(sub.language)
                .setLabel(sub.label)
                .build()
        }
        if (subs.isNotEmpty()) builder.setSubtitleConfigurations(subs)
        return builder.build()
    }

    private fun resolveStreamUrl(content: RoomContentDto): String? {
        content.videoUrl?.takeIf { it.isNotBlank() }?.let { return it }
        content.streamLinks.firstOrNull { it.kind == "stream" }?.url?.takeIf { it.isNotBlank() }?.let { return it }
        return content.streamLinks.firstOrNull()?.url?.takeIf { it.isNotBlank() }
    }

    private fun applyRemotePlayback(pb: PlaybackStateDto, hard: Boolean) {
        applyingRemote = true
        try {
            val targetMs = projectedPositionMs(pb)
            val drift = abs(player.currentPosition - targetMs)
            if (hard || drift > DRIFT_TOLERANCE_MS) {
                player.seekTo(targetMs.coerceAtLeast(0))
            }
            if (pb.playbackRate > 0) {
                player.setPlaybackSpeed(pb.playbackRate.toFloat())
                _state.update { it.copy(playbackSpeed = pb.playbackRate.toFloat()) }
            }
            player.playWhenReady = pb.isPlaying
        } finally {
            applyingRemote = false
        }
    }

    /** Position the host is really at now, accounting for elapsed wall-clock while playing. */
    private fun projectedPositionMs(pb: PlaybackStateDto): Long {
        val base = (pb.positionSeconds * 1000).toLong()
        if (!pb.isPlaying || pb.serverTimeMs <= 0) return base
        val serverNow = System.currentTimeMillis() + clockOffsetMs
        val elapsed = (serverNow - pb.serverTimeMs).coerceAtLeast(0)
        return base + (elapsed * pb.playbackRate).toLong()
    }

    // ---- Host controls (guests' calls are ignored server-side and locally) ----
    fun togglePlay() {
        if (!_state.value.isHost) return
        if (player.isPlaying) {
            player.pause(); broadcast("playback.pause")
        } else {
            player.play(); broadcast("playback.play")
        }
    }

    fun seekTo(positionMs: Long) {
        if (!_state.value.isHost) return
        player.seekTo(positionMs.coerceAtLeast(0))
        broadcast("playback.seek")
    }

    fun seekBy(deltaMs: Long) = seekTo(player.currentPosition + deltaMs)

    /** Host-only speed change; rides the sync channel so guests match the rate. */
    fun setSpeed(speed: Float) {
        if (!_state.value.isHost) return
        player.setPlaybackSpeed(speed)
        _state.update { it.copy(playbackSpeed = speed) }
        broadcast("playback.sync")
    }

    /** Per-viewer subtitle selection (not synced). Mirrors the main player. */
    fun selectSubtitle(index: Int) {
        val params = player.trackSelectionParameters.buildUpon()
        if (index < 0) {
            params.setPreferredTextLanguage(null)
            params.setSelectUndeterminedTextLanguage(false)
            params.setTrackTypeDisabled(androidx.media3.common.C.TRACK_TYPE_TEXT, true)
        } else {
            val lang = _state.value.subtitles.getOrNull(index)?.language
            params.setTrackTypeDisabled(androidx.media3.common.C.TRACK_TYPE_TEXT, false)
            params.setPreferredTextLanguage(lang)
            params.setSelectUndeterminedTextLanguage(true)
        }
        player.trackSelectionParameters = params.build()
        _state.update { it.copy(activeSubtitleIndex = index) }
    }

    fun sendReaction(emoji: String) {
        socket?.sendReaction(emoji)
    }

    /** Guests: re-request the host's authoritative position after a stall/drift. */
    fun resyncToHost() {
        if (_state.value.isHost) return
        socket?.requestSync()
        _state.update { it.copy(toast = "در حال هماهنگی با میزبان…") }
    }

    /** Rebuild the source after a playback error, keeping the current place. */
    fun retryPlayback() {
        val content = _state.value.content ?: return
        val item = buildMediaItemFor(content) ?: return
        val pos = player.currentPosition
        _state.update { it.copy(playerError = null, buffering = true) }
        player.setMediaItem(item, pos)
        player.prepare()
        player.playWhenReady = _state.value.playing
        val active = _state.value.activeSubtitleIndex
        if (active >= 0) selectSubtitle(active)
    }

    /**
     * Automatic heal for every group-playback failure — same intake and repair
     * as the single player, filed once with room_code so the server also
     * broadcasts playback.fix to the whole room. Immediate retry when a better
     * URL already exists, background poll otherwise. Best-effort: never breaks
     * playback, one Persian notice.
     */
    private fun autoHealPartySource(error: androidx.media3.common.PlaybackException) {
        val content = _state.value.content ?: return
        val failed = currentPartySourceUrl.ifBlank { resolveStreamUrl(content).orEmpty() }
        if (failed.isBlank()) return
        val key = "$failed|${error.errorCode}"
        if (!healedPartyKeys.add(key)) return
        if (healedPartyKeys.size > 200) healedPartyKeys.clear()
        val playedMs = runCatching { player.currentPosition.coerceAtLeast(0) }.getOrDefault(0L)
        socket?.sendPlaybackFailed(
            errorCode = error.errorCode.toString(),
            sourceUrl = failed,
            playedSeconds = playedMs / 1000.0,
        )
        _state.update { it.copy(toast = "خطای پخش ثبت شد؛ داریم نسخه سالم را آماده می‌کنیم…") }
        viewModelScope.launch {
            val res = runCatching {
                catalogRepository.reportPlaybackFailure(
                    playbackFailureRequestFor(content, error, failed, playedMs),
                )
            }.getOrNull() as? ApiResult.Success ?: return@launch
            val body = res.data
            if (!body.ok) return@launch
            if (body.messageFa.isNotBlank()) _state.update { it.copy(toast = body.messageFa) }
            val fixed = body.fixedUrl.trim()
            if (body.shouldRetry && fixed.isNotBlank() && fixed != failed) {
                applyPartyFixedUrl(fixed, "پخش درست شد؛ ادامه از همین‌جا")
                return@launch
            }
            val reportId = body.reportId
            if (reportId != null && reportId > 0 && !body.shouldRetry) {
                pollPartyFixedUrl(reportId, failed)
            }
        }
    }

    private fun playbackFailureRequestFor(
        content: RoomContentDto,
        error: androidx.media3.common.PlaybackException,
        failedUrl: String,
        playedMs: Long,
    ): PlaybackFailureRequest {
        val isEpisode = content.type == "episode"
        return PlaybackFailureRequest(
            contentType = if (isEpisode) "series" else "movie",
            objectId = if (isEpisode) (content.series?.id ?: 0) else content.id,
            slug = if (isEpisode) (content.series?.slug?.ifBlank { content.slug } ?: content.slug) else content.slug,
            episodeId = if (isEpisode) content.id else 0,
            errorCode = error.errorCode.toString(),
            errorMessage = "auto heal android-party ${error.errorCodeName} cause=${error.cause?.message}".take(500),
            sourceUrl = failedUrl,
            player = "android",
            roomCode = inviteCode,
            playedSeconds = playedMs / 1000.0,
            hadPlayed = playedMs > 1000,
        )
    }

    /** Poll a filed party report until the catalog serves a better URL. */
    private fun pollPartyFixedUrl(reportId: Int, failedUrl: String) {
        viewModelScope.launch {
            val delays = longArrayOf(3000, 5000, 8000, 12000, 15000, 15000)
            for (step in delays) {
                delay(step)
                val poll = runCatching { catalogRepository.contentIssueStatus(reportId) }.getOrNull()
                val fixed = (poll as? ApiResult.Success)?.data?.fixedUrl?.trim().orEmpty()
                if (fixed.isNotBlank() && fixed != failedUrl && fixed != currentPartySourceUrl) {
                    applyPartyFixedUrl(fixed, "پخش درست شد؛ ادامه از همین‌جا")
                    return@launch
                }
                val status = (poll as? ApiResult.Success)?.data?.status.orEmpty()
                if (status == "needs_review") return@launch
            }
        }
    }

    /** Swap this viewer's player onto a healed URL, keeping position. */
    private fun applyPartyFixedUrl(fixedRaw: String, notice: String) {
        val abs = fixedRaw.toAbsoluteUrl() ?: return
        if (abs == currentPartySourceUrl) return
        val content = _state.value.content ?: return
        val subtitles = _state.value.subtitles
        val pos = runCatching { player.currentPosition.coerceAtLeast(0) }.getOrDefault(0L)
        val wasPlaying = runCatching { player.playWhenReady }.getOrDefault(false)
        val item = runCatching {
            MediaItem.Builder().setUri(abs).also { builder ->
                if (subtitles.isNotEmpty()) {
                    builder.setSubtitleConfigurations(
                        subtitles.mapNotNull { sub ->
                            val url = sub.url.toAbsoluteUrl() ?: return@mapNotNull null
                            MediaItem.SubtitleConfiguration.Builder(android.net.Uri.parse(url))
                                .setMimeType(guessSubtitleMime(url))
                                .setLanguage(sub.language)
                                .setLabel(sub.label)
                                .build()
                        },
                    )
                }
            }.build()
        }.getOrNull() ?: return
        currentPartySourceUrl = abs
        runCatching {
            player.setMediaItem(item, pos)
            player.prepare()
            player.playWhenReady = wasPlaying
        }
        _state.update { it.copy(playerError = null, buffering = true, toast = notice) }
        if (_state.value.isHost) broadcast("playback.sync")
    }

    /** A fixed URL broadcast by the server after POST api/catalog/playback-failure/. */
    private fun onPlaybackFix(event: WsEvent.PlaybackFix) {
        if (event.messageFa.isNotBlank()) _state.update { it.copy(toast = event.messageFa) }
        val fixed = event.fixedUrl.trim()
        if (fixed.isNotBlank() && fixed != currentPartySourceUrl) {
            applyPartyFixedUrl(fixed, "پخش درست شد؛ ادامه از همین‌جا")
        }
    }

    /** Another member's player broke: the host files the shared heal. */
    private fun onMemberFailed(event: WsEvent.MemberFailed) {
        if (!_state.value.isHost) {
            if (event.messageFa.isNotBlank()) _state.update { it.copy(toast = event.messageFa) }
            return
        }
        val content = _state.value.content ?: return
        val failed = event.sourceUrl.ifBlank { currentPartySourceUrl.ifBlank { resolveStreamUrl(content).orEmpty() } }
        if (failed.isBlank()) return
        if (!healedPartyKeys.add("$failed|${event.errorCode}")) return
        _state.update { st -> st.copy(toast = event.messageFa.ifBlank { "پخش یکی از اعضا قطع شد؛ داریم نسخه سالم را آماده می‌کنیم…" }) }
        viewModelScope.launch {
            val res = runCatching {
                catalogRepository.reportPlaybackFailure(
                    PlaybackFailureRequest(
                        contentType = if (content.type == "episode") "series" else "movie",
                        objectId = if (content.type == "episode") (content.series?.id ?: 0) else content.id,
                        slug = if (content.type == "episode") (content.series?.slug?.ifBlank { content.slug } ?: content.slug) else content.slug,
                        episodeId = if (content.type == "episode") content.id else 0,
                        errorCode = event.errorCode.ifBlank { "member_failed" },
                        errorMessage = "auto heal android-party member_failed".take(500),
                        sourceUrl = failed,
                        player = "android",
                        roomCode = inviteCode,
                        playedSeconds = event.playedSeconds,
                        hadPlayed = event.playedSeconds > 1,
                    ),
                )
            }.getOrNull() as? ApiResult.Success ?: return@launch
            val body = res.data
            if (!body.ok) return@launch
            val fixed = body.fixedUrl.trim()
            if (body.shouldRetry && fixed.isNotBlank() && fixed != currentPartySourceUrl) {
                applyPartyFixedUrl(fixed, "پخش درست شد؛ ادامه از همین‌جا")
                return@launch
            }
            val reportId = body.reportId
            if (reportId != null && reportId > 0 && !body.shouldRetry) {
                pollPartyFixedUrl(reportId, failed)
            }
        }
    }

    private fun broadcast(eventType: String) {
        val durationSec = player.duration.coerceAtLeast(0) / 1000.0
        socket?.sendPlayback(
            eventType = eventType,
            positionSeconds = player.currentPosition / 1000.0,
            durationSeconds = durationSec,
            playbackRate = player.playbackParameters.speed.toDouble(),
            isPlaying = player.playWhenReady,
            streamUrl = _state.value.content?.let { resolveStreamUrl(it) },
        )
    }

    // ---- Chat ----
    fun onChatDraftChange(value: String) = _state.update { it.copy(chatDraft = value) }

    fun sendChat() {
        val text = _state.value.chatDraft.trim()
        if (text.isEmpty()) return
        socket?.sendChat(text)
        _state.update { it.copy(chatDraft = "") }
    }

    fun consumeToast() = _state.update { it.copy(toast = null) }

    private fun startHeartbeat() {
        heartbeatJob?.cancel()
        heartbeatJob = viewModelScope.launch {
            while (true) {
                delay(20_000)
                socket?.heartbeat()
                socket?.latencyPing(System.currentTimeMillis().also { pingSentAt = it })
            }
        }
    }

    private fun startProgressLoop() {
        progressJob?.cancel()
        progressJob = viewModelScope.launch {
            var lastSync = System.currentTimeMillis()
            while (true) {
                _state.update {
                    it.copy(
                        positionMs = player.currentPosition,
                        durationMs = player.duration.coerceAtLeast(0),
                    )
                }
                // The host publishes a keep-alive sync every 8s so late/ drifting
                // guests converge without a manual seek.
                if (_state.value.isHost && player.isPlaying) {
                    val now = System.currentTimeMillis()
                    if (now - lastSync > 8_000) {
                        lastSync = now
                        broadcast("playback.sync")
                    }
                }
                delay(500)
            }
        }
    }

    fun leave() {
        viewModelScope.launch { watchPartyRepository.leaveRoom(inviteCode) }
        teardown()
    }

    private fun teardown() {
        heartbeatJob?.cancel()
        progressJob?.cancel()
        eventJob?.cancel()
        socket?.close()
        socket = null
    }

    private fun mapCloseReason(code: Int, existing: String?): String? = when (code) {
        4401 -> "برای تماشای گروهی باید وارد شوی"
        4403 -> "به این اتاق دسترسی نداری"
        4404 -> "اتاق پیدا نشد"
        4409 -> "این اتاق دیگر فعال نیست"
        1000 -> existing
        else -> existing
    }

    override fun onCleared() {
        teardown()
        player.release()
        super.onCleared()
    }
}

@OptIn(UnstableApi::class)
private fun guessSubtitleMime(url: String): String = when {
    url.endsWith(".srt", ignoreCase = true) -> MimeTypes.APPLICATION_SUBRIP
    url.endsWith(".ass", ignoreCase = true) || url.endsWith(".ssa", ignoreCase = true) -> MimeTypes.TEXT_SSA
    url.endsWith(".ttml", ignoreCase = true) || url.endsWith(".xml", ignoreCase = true) -> MimeTypes.APPLICATION_TTML
    else -> MimeTypes.TEXT_VTT
}
