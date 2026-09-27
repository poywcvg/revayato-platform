package com.revayato.app.core.update

import android.content.Intent
import com.revayato.app.BuildConfig
import com.revayato.app.core.network.ApiResult
import com.revayato.app.data.model.AppReleaseDto
import com.revayato.app.data.repository.AppUpdateRepository
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/** How long an optional update stays quiet after the user has seen it once. */
private const val QUIET_WINDOW_MS = 24L * 60 * 60 * 1000

/**
 * Everything the update sheet shows. One object for both entry points — the
 * silent launch check and «بررسی بروزرسانی» in the profile — because they are
 * the same conversation and must not be able to run two downloads at once.
 */
data class UpdateUiState(
    val release: AppReleaseDto? = null,
    /** The sheet is on screen. */
    val prompting: Boolean = false,
    /** Installed build is below the minimum the backend supports: no dismissing. */
    val mandatory: Boolean = false,
    val checking: Boolean = false,
    val downloading: Boolean = false,
    /** 0..100, or -1 while the server has not told us the total size. */
    val progress: Int = 0,
    /** Downloaded and checksum-verified; the sheet now offers «نصب». */
    val readyFile: File? = null,
    val error: String? = null,
    /** Only after a *manual* check: "you already have the newest build". */
    val upToDate: Boolean = false,
)

/**
 * The in-app update flow for a sideloaded app.
 *
 * Google Play In-App Updates cannot be used here — the APK is published on
 * revayato.com/downloads/, so nothing in Play knows this install exists. This
 * singleton is the replacement: ask the backend, offer the new build, fetch it,
 * verify it, hand it to the system installer.
 *
 * It is a `@Singleton` rather than a ViewModel because two unrelated pieces of
 * UI drive it (the launch check hosted by the activity, and the profile row) and
 * an in-flight download has to survive navigation between them.
 */
@Singleton
class AppUpdateManager @Inject constructor(
    private val repository: AppUpdateRepository,
    private val store: UpdateStore,
    private val installer: ApkInstaller,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    private val _state = MutableStateFlow(UpdateUiState())
    val state: StateFlow<UpdateUiState> = _state.asStateFlow()

    /** One silent check per process; relaunching is what asks again. */
    private var launchChecked = false
    private var downloadJob: Job? = null

    /**
     * The quiet check run at app start. Raises the sheet only for a build the
     * user has not already waved away — unless it is mandatory, which ignores
     * both the skip and the quiet window.
     */
    fun checkOnLaunch() {
        if (launchChecked) return
        launchChecked = true
        scope.launch {
            cleanupInstalledLeftovers()
            val release = fetch() ?: return@launch
            if (!isNewer(release)) return@launch
            val mandatory = release.mandatory || BuildConfig.VERSION_CODE < release.minSupportedVersionCode
            if (!mandatory && !shouldNag(release)) return@launch
            store.rememberPrompt(System.currentTimeMillis())
            _state.update {
                it.copy(release = release, prompting = true, mandatory = mandatory, error = null, upToDate = false)
            }
        }
    }

    /**
     * «بررسی بروزرسانی» — the user asked, so always answer: the sheet when there
     * is a newer build, an explicit "you are up to date" when there is not, and
     * the transport error when the check itself failed.
     */
    fun checkNow() {
        if (_state.value.checking || _state.value.downloading) return
        scope.launch {
            _state.update { it.copy(checking = true, error = null, upToDate = false) }
            when (val result = repository.latest(BuildConfig.VERSION_CODE)) {
                is ApiResult.Success -> {
                    val release = result.data
                    if (isNewer(release)) {
                        val mandatory = release.mandatory ||
                            BuildConfig.VERSION_CODE < release.minSupportedVersionCode
                        store.rememberPrompt(System.currentTimeMillis())
                        _state.update {
                            it.copy(checking = false, release = release, prompting = true, mandatory = mandatory)
                        }
                    } else {
                        _state.update { it.copy(checking = false, upToDate = true) }
                    }
                }
                is ApiResult.Error -> _state.update { it.copy(checking = false, error = result.message) }
            }
        }
    }

    /** Fetch the APK, verify it, and move the sheet to its «نصب» state. */
    fun download() {
        val release = _state.value.release ?: return
        if (_state.value.downloading || release.downloadUrl.isBlank()) return
        downloadJob?.cancel()
        downloadJob = scope.launch {
            _state.update { it.copy(downloading = true, progress = 0, error = null, readyFile = null) }
            try {
                val file = installer.download(
                    url = release.downloadUrl,
                    versionCode = release.versionCode,
                    expectedBytes = release.sizeBytes,
                    sha256 = release.sha256,
                ) { percent ->
                    _state.update { if (it.downloading) it.copy(progress = percent) else it }
                }
                _state.update { it.copy(downloading = false, progress = 100, readyFile = file) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _state.update {
                    it.copy(
                        downloading = false,
                        readyFile = null,
                        error = "دانلود بروزرسانی کامل نشد. اینترنت را بررسی کن و دوباره تلاش کن.",
                    )
                }
            }
        }
    }

    /** «بعداً» — remember this build so we stop asking about it. */
    fun postpone() {
        val release = _state.value.release
        downloadJob?.cancel()
        downloadJob = null
        scope.launch { release?.let { store.skip(it.versionCode) } }
        _state.update {
            it.copy(prompting = false, downloading = false, progress = 0, error = null)
        }
    }

    /** Clear the "you are up to date" note once the user has seen it. */
    fun dismissUpToDate() = _state.update { it.copy(upToDate = false) }

    fun clearError() = _state.update { it.copy(error = null) }

    fun canInstall(): Boolean = installer.canInstall()

    fun unknownSourcesSettings(): Intent = installer.unknownSourcesSettings()

    fun installIntent(file: File): Intent = installer.installIntent(file)

    // ------------------------------------------------------------------ internals

    private suspend fun fetch(): AppReleaseDto? =
        (repository.latest(BuildConfig.VERSION_CODE) as? ApiResult.Success)?.data

    /**
     * Trust our own comparison as well as the server's `update_available`: an
     * empty [AppReleaseDto.downloadUrl] means the backend found no publishable
     * build, and offering an update we cannot download is the one outcome worth
     * ruling out here.
     */
    private fun isNewer(release: AppReleaseDto): Boolean =
        release.available &&
            release.versionCode > BuildConfig.VERSION_CODE &&
            release.downloadUrl.isNotBlank()

    private suspend fun shouldNag(release: AppReleaseDto): Boolean {
        if (release.versionCode > store.skippedVersionCode()) return true
        // Already waved away — but keep a gentle reminder once a day.
        return System.currentTimeMillis() - store.promptedAt() > QUIET_WINDOW_MS
    }

    /**
     * Delete installers for builds we are already running or have moved past.
     * A pending download for a *newer* build is left alone so backgrounding the
     * app between the download and the install does not cost the bytes twice.
     */
    private fun cleanupInstalledLeftovers() {
        runCatching { installer.purgeUpTo(BuildConfig.VERSION_CODE) }
    }
}
