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
import com.revayato.app.data.model.MovieDetailDto
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

data class MovieDetailState(
    val content: UiState<MovieDetailDto> = UiState.Loading,
    val similar: List<CatalogCardDto> = emptyList(),
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
class MovieDetailViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val catalogRepository: CatalogRepository,
    private val engagementRepository: EngagementRepository,
    private val watchPartyRepository: WatchPartyRepository,
    private val authRepository: AuthRepository,
    private val downloadsManager: DownloadsManager,
) : ViewModel() {

    private val slug: String = savedStateHandle["slug"] ?: ""

    private val _state = MutableStateFlow(MovieDetailState())
    val state: StateFlow<MovieDetailState> = _state.asStateFlow()

    init {
        load()
        observeDownloadEvents()
    }

    /** Turn download-engine signals into accurate alerts for *this* title only. */
    private fun observeDownloadEvents() {
        viewModelScope.launch {
            downloadsManager.events.collect { event ->
                val movie = (_state.value.content as? UiState.Success)?.data ?: return@collect
                if (event.title != movie.title) return@collect
                val message = when (event) {
                    is DownloadEvent.Rejected ->
                        "لینک این نسخه معتبر نیست؛ کیفیت دیگری را امتحان کن"
                    is DownloadEvent.Started ->
                        if (event.toFile) "دانلود فایل در حافظهٔ گوشی آغاز شد"
                        else "دانلود برای تماشای آفلاین آغاز شد"
                    is DownloadEvent.Completed ->
                        if (event.toFile) "دانلود فایل کامل شد ✓"
                        else "دانلود آفلاین «${movie.title}» کامل شد ✓"
                    is DownloadEvent.Failed ->
                        if (event.toFile) "دانلود فایل ناموفق بود؛ دوباره تلاش کن"
                        else "دانلود ناموفق بود؛ کیفیت دیگری را امتحان کن"
                }
                _state.value = _state.value.copy(actionMessage = message)
            }
        }
    }

    fun load() {
        _state.value = _state.value.copy(content = UiState.Loading)
        viewModelScope.launch {
            val loggedIn = authRepository.isLoggedIn.first()
            val detailDef = async { catalogRepository.movieDetail(slug) }
            val similarDef = async { catalogRepository.movieSimilar(slug) }

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
            when (val res = engagementRepository.ratingSummary("movie", id)) {
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
        if (!_state.value.isLoggedIn) {
            _state.value = _state.value.copy(actionMessage = "برای ثبت نظر باید وارد شوی")
            return
        }
        _state.value = _state.value.copy(ratings = _state.value.ratings.copy(submitting = true))
        viewModelScope.launch {
            when (val res = engagementRepository.rate("movie", id, score, review.ifBlank { null }, isSpoiler)) {
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

    private fun currentId(): Int? = (_state.value.content as? UiState.Success)?.data?.id

    fun toggleWatchlist() {
        val id = currentId() ?: return
        if (!_state.value.isLoggedIn) {
            _state.value = _state.value.copy(actionMessage = "برای این کار باید وارد شوی")
            return
        }
        viewModelScope.launch {
            engagementRepository.toggleWatchlist("movie", id).let { res ->
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
        if (!_state.value.isLoggedIn) {
            _state.value = _state.value.copy(actionMessage = "برای این کار باید وارد شوی")
            return
        }
        viewModelScope.launch {
            engagementRepository.toggleLike("movie", id).let { res ->
                if (res is ApiResult.Success) {
                    _state.value = _state.value.copy(liked = res.data)
                }
            }
        }
    }

    fun createWatchParty() {
        val id = currentId() ?: return
        if (!_state.value.isLoggedIn) {
            _state.value = _state.value.copy(actionMessage = "برای تماشای گروهی باید وارد شوی")
            return
        }
        if (_state.value.creatingRoom) return
        _state.value = _state.value.copy(creatingRoom = true)
        viewModelScope.launch {
            when (val res = watchPartyRepository.createRoom("movie", id)) {
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

    /** Download for in-app offline playback (kept inside the app's cache).
     *  The started/failed/completed alert is driven by [observeDownloadEvents]. */
    fun downloadOffline(url: String) {
        val movie = (_state.value.content as? UiState.Success)?.data ?: return
        downloadsManager.enqueueOffline("movie", movie.id, movie.title, url)
        emitDownloadEvent(movie, url)
    }

    /** Save a shareable copy to the phone's public Downloads folder. */
    fun downloadFile(url: String) {
        val movie = (_state.value.content as? UiState.Success)?.data ?: return
        downloadsManager.enqueueFile(movie.title, url)
        emitDownloadEvent(movie, url)
    }

    /** Fire real download telemetry (platform = android) for the staff panel.
     *  Quality is resolved from the matching download link when known. */
    private fun emitDownloadEvent(movie: MovieDetailDto, url: String) {
        val link = movie.downloadLinks.firstOrNull { it.url == url }
        val quality = (link?.quality?.ifBlank { link.label } ?: "").trim()
        viewModelScope.launch {
            engagementRepository.trackDownload(
                titleId = movie.id,
                slug = movie.slug.ifBlank { slug },
                contentType = "movie",
                quality = quality,
                sourcePage = "/movies/${movie.slug.ifBlank { slug }}",
            )
        }
    }

    /** Open the «گزارش خطا» sheet. Reporting requires an account (the support
     *  inbox is per-user), so gate it the same way as the other actions. */
    fun openReport() {
        if (currentId() == null) return
        if (!_state.value.isLoggedIn) {
            _state.value = _state.value.copy(actionMessage = "برای گزارش خطا باید وارد شوی")
            return
        }
        _state.value = _state.value.copy(showReportSheet = true)
    }

    fun dismissReport() {
        if (_state.value.reportSubmitting) return
        _state.value = _state.value.copy(showReportSheet = false)
    }

    fun submitReport(reason: String) {
        val movie = (_state.value.content as? UiState.Success)?.data ?: return
        val trimmed = reason.trim()
        if (trimmed.length < 10 || _state.value.reportSubmitting) return
        _state.value = _state.value.copy(reportSubmitting = true)
        viewModelScope.launch {
            val url = "https://revayato.com/movies/${movie.slug}"
            when (val res = engagementRepository.reportProblem(movie.title, movie.releaseYear, url, trimmed)) {
                is ApiResult.Success -> _state.value = _state.value.copy(
                    reportSubmitting = false,
                    showReportSheet = false,
                    actionMessage = "گزارش تو ثبت شد. ممنون! کد پیگیری: ${res.data.trackingCode}",
                )
                is ApiResult.Error -> _state.value = _state.value.copy(
                    reportSubmitting = false,
                    actionMessage = res.message,
                )
            }
        }
    }

    fun consumeRoomCode() {
        _state.value = _state.value.copy(pendingRoomCode = null)
    }

    fun consumeMessage() {
        _state.value = _state.value.copy(actionMessage = null)
    }
}
