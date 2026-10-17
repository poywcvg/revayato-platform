package com.revayato.app.feature.detail

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.download.DownloadEvent
import com.revayato.app.core.download.DownloadsManager
import com.revayato.app.core.network.ApiResult
import com.revayato.app.core.network.orNull
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.CatalogCardDto
import com.revayato.app.data.model.EpisodeDto
import com.revayato.app.data.model.SeriesDetailDto
import com.revayato.app.data.repository.AuthRepository
import com.revayato.app.data.repository.CatalogRepository
import com.revayato.app.data.repository.EngagementRepository
import com.revayato.app.data.repository.WatchPartyRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import javax.inject.Inject

data class SeriesDetailState(
    val content: UiState<SeriesDetailDto> = UiState.Loading,
    val similar: List<CatalogCardDto> = emptyList(),
    val selectedSeasonIndex: Int = 0,
    val isLoggedIn: Boolean = false,
    val inWatchlist: Boolean = false,
    val liked: Boolean = false,
    val actionMessage: String? = null,
    val creatingRoom: Boolean = false,
    val pendingRoomCode: String? = null,
    val showReportSheet: Boolean = false,
    val reportSubmitting: Boolean = false,
    val ratings: RatingsUi = RatingsUi(),
)

@HiltViewModel
class SeriesDetailViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val catalogRepository: CatalogRepository,
    private val engagementRepository: EngagementRepository,
    private val watchPartyRepository: WatchPartyRepository,
    private val authRepository: AuthRepository,
    private val downloadsManager: DownloadsManager,
) : ViewModel() {

    private val slug: String = savedStateHandle["slug"] ?: ""

    private val _state = MutableStateFlow(SeriesDetailState())
    val state: StateFlow<SeriesDetailState> = _state.asStateFlow()

    // Episode titles this screen has queued, so download events raised for an
    // unrelated title (e.g. a movie downloaded elsewhere) don't alert here.
    private val enqueuedTitles = mutableSetOf<String>()

    init {
        load()
        observeDownloadEvents()
    }

    /** Turn download-engine signals into accurate alerts for episodes queued here. */
    private fun observeDownloadEvents() {
        viewModelScope.launch {
            downloadsManager.events.collect { event ->
                if (event.title !in enqueuedTitles) return@collect
                val message = when (event) {
                    is DownloadEvent.Rejected ->
                        "لینک این نسخه معتبر نیست؛ کیفیت دیگری را امتحان کن"
                    is DownloadEvent.Started ->
                        if (event.toFile) "دانلود فایل «${event.title}» آغاز شد"
                        else "دانلود آفلاین «${event.title}» آغاز شد"
                    is DownloadEvent.Completed ->
                        if (event.toFile) "دانلود فایل «${event.title}» کامل شد ✓"
                        else "دانلود آفلاین «${event.title}» کامل شد ✓"
                    is DownloadEvent.Failed ->
                        "دانلود «${event.title}» ناموفق بود؛ دوباره تلاش کن"
                }
                _state.value = _state.value.copy(actionMessage = message)
            }
        }
    }

    fun load() {
        _state.value = _state.value.copy(content = UiState.Loading)
        viewModelScope.launch {
            val loggedIn = authRepository.isLoggedIn.first()
            val detailDef = async { catalogRepository.seriesDetail(slug) }
            val similarDef = async { catalogRepository.seriesSimilar(slug) }
            when (val detail = detailDef.await()) {
                is ApiResult.Success -> {
                    _state.value = _state.value.copy(
                        content = UiState.Success(detail.data),
                        similar = similarDef.await().orNull().orEmpty(),
                        isLoggedIn = loggedIn,
                    )
                    loadRatings(detail.data.id)
                }
                is ApiResult.Error -> _state.value = _state.value.copy(
                    content = UiState.Error(detail.message),
                    isLoggedIn = loggedIn,
                )
            }
        }
    }

    private fun loadRatings(id: Int) {
        _state.value = _state.value.copy(ratings = _state.value.ratings.copy(loading = true))
        viewModelScope.launch {
            when (val res = engagementRepository.ratingSummary("series", id)) {
                is ApiResult.Success -> _state.value =
                    _state.value.copy(ratings = RatingsUi.from(res.data))
                is ApiResult.Error -> _state.value =
                    _state.value.copy(ratings = _state.value.ratings.copy(loading = false))
            }
        }
    }

    /** Submit or update the signed-in user's rating + review, then refresh the list. */
    fun submitRating(score: Double, review: String, isSpoiler: Boolean) {
        val id = currentId() ?: return
        if (!requireLogin()) return
        _state.value = _state.value.copy(ratings = _state.value.ratings.copy(submitting = true))
        viewModelScope.launch {
            when (val res = engagementRepository.rate("series", id, score, review.ifBlank { null }, isSpoiler)) {
                is ApiResult.Success -> {
                    loadRatings(id)
                    _state.value = _state.value.copy(actionMessage = "نظر شما ثبت شد ✓")
                }
                is ApiResult.Error -> _state.value = _state.value.copy(
                    ratings = _state.value.ratings.copy(submitting = false),
                    actionMessage = res.message,
                )
            }
        }
    }

    fun selectSeason(index: Int) {
        _state.value = _state.value.copy(selectedSeasonIndex = index)
    }

    private fun currentId(): Int? = (_state.value.content as? UiState.Success)?.data?.id

    fun toggleWatchlist() {
        val id = currentId() ?: return
        if (!requireLogin()) return
        viewModelScope.launch {
            engagementRepository.toggleWatchlist("series", id).let { res ->
                if (res is ApiResult.Success) {
                    _state.value = _state.value.copy(
                        inWatchlist = res.data,
                        actionMessage = if (res.data) MSG_ADDED_TO_WATCHLIST else "از لیست تماشا حذف شد",
                    )
                }
            }
        }
    }

    fun toggleLike() {
        val id = currentId() ?: return
        if (!requireLogin()) return
        viewModelScope.launch {
            engagementRepository.toggleLike("series", id).let { res ->
                if (res is ApiResult.Success) _state.value = _state.value.copy(liked = res.data)
            }
        }
    }

    fun createWatchParty(episodeId: Int) {
        if (!requireLogin()) return
        if (_state.value.creatingRoom) return
        _state.value = _state.value.copy(creatingRoom = true)
        viewModelScope.launch {
            when (val res = watchPartyRepository.createRoom("episode", episodeId)) {
                is ApiResult.Success -> _state.value = _state.value.copy(
                    creatingRoom = false,
                    pendingRoomCode = res.data.inviteCode,
                )
                is ApiResult.Error -> _state.value = _state.value.copy(
                    creatingRoom = false,
                    actionMessage = res.message,
                )
            }
        }
    }

    /** Download an episode for in-app offline playback. Alert is driven by events. */
    fun downloadEpisodeOffline(episode: EpisodeDto, url: String) {
        enqueuedTitles += episode.title
        downloadsManager.enqueueOffline("episode", episode.id, episode.title, url)
        emitDownloadEvent(episode, url)
    }

    /** Save an episode as a shareable file in the phone's Downloads folder. */
    fun downloadEpisodeFile(episode: EpisodeDto, url: String) {
        enqueuedTitles += episode.title
        downloadsManager.enqueueFile(episode.title, url)
        emitDownloadEvent(episode, url)
    }

    /** Fire real download telemetry (platform = android) for the staff panel.
     *  Episodes roll up to their parent series title; quality is resolved from
     *  the matching episode stream link when known. */
    private fun emitDownloadEvent(episode: EpisodeDto, url: String) {
        val series = (_state.value.content as? UiState.Success)?.data ?: return
        val link = episode.streamLinks.firstOrNull { it.url == url }
        val quality = (link?.quality?.ifBlank { link.label } ?: "").trim()
        viewModelScope.launch {
            engagementRepository.trackDownload(
                titleId = series.id,
                slug = series.slug.ifBlank { slug },
                contentType = "series",
                quality = quality,
                sourcePage = "/series/${series.slug.ifBlank { slug }}",
            )
        }
    }

    /** Open the «گزارش خطا» sheet (login-gated, per-user support inbox). */
    fun openReport() {
        if (currentId() == null) return
        if (!requireLogin()) return
        _state.value = _state.value.copy(showReportSheet = true)
    }

    fun dismissReport() {
        if (_state.value.reportSubmitting) return
        _state.value = _state.value.copy(showReportSheet = false)
    }

    fun submitReport(reason: String) {
        val series = (_state.value.content as? UiState.Success)?.data ?: return
        val trimmed = reason.trim()
        if (trimmed.length < 10 || _state.value.reportSubmitting) return
        _state.value = _state.value.copy(reportSubmitting = true)
        viewModelScope.launch {
            // Same structured engine as movie + web player (see MovieDetailViewModel).
            val problemType = inferStructuredProblemType(trimmed, isSeries = true)
            when (val res = catalogRepository.reportContentIssue(
                contentType = "series",
                problemType = problemType,
                objectId = series.id,
                slug = series.slug,
                detail = trimmed,
            )) {
                is ApiResult.Success -> {
                    val code = res.data.trackingCode.trim()
                    val msg = if (code.isNotBlank()) {
                        "گزارش تو ثبت شد و خودکار بررسی می‌شود. ممنون! کد پیگیری: $code"
                    } else {
                        "گزارش تو ثبت شد و خودکار بررسی می‌شود. ممنون!"
                    }
                    _state.value = _state.value.copy(
                        reportSubmitting = false,
                        showReportSheet = false,
                        actionMessage = msg,
                    )
                }
                is ApiResult.Error -> {
                    val url = "https://revayato.com/series/${series.slug}"
                    when (val fallback = engagementRepository.reportProblem(series.title, series.startYear, url, trimmed)) {
                        is ApiResult.Success -> _state.value = _state.value.copy(
                            reportSubmitting = false,
                            showReportSheet = false,
                            actionMessage = "گزارش تو ثبت شد. ممنون! کد پیگیری: ${fallback.data.trackingCode}",
                        )
                        is ApiResult.Error -> _state.value = _state.value.copy(
                            reportSubmitting = false,
                            actionMessage = res.message,
                        )
                    }
                }
            }
        }
    }

    private fun requireLogin(): Boolean {
        if (!_state.value.isLoggedIn) {
            _state.value = _state.value.copy(actionMessage = "برای این کار باید وارد شوی")
            return false
        }
        return true
    }

    fun consumeRoomCode() {
        _state.value = _state.value.copy(pendingRoomCode = null)
    }

    fun consumeMessage() {
        _state.value = _state.value.copy(actionMessage = null)
    }
}
