package com.revayato.app.feature.update

import androidx.lifecycle.ViewModel
import com.revayato.app.core.update.AppUpdateManager
import com.revayato.app.core.update.UpdateUiState
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.StateFlow
import java.io.File
import javax.inject.Inject

/**
 * The Compose-facing face of [AppUpdateManager].
 *
 * Thin on purpose: the state and the in-flight download live in the manager
 * (a singleton) so the activity-level update sheet and the «بررسی بروزرسانی»
 * row in the profile are looking at the same conversation, even though Compose
 * hands each of them its own ViewModel instance.
 */
@HiltViewModel
class UpdateViewModel @Inject constructor(
    private val manager: AppUpdateManager,
) : ViewModel() {

    val state: StateFlow<UpdateUiState> = manager.state

    fun checkOnLaunch() = manager.checkOnLaunch()

    fun checkNow() = manager.checkNow()

    fun download() = manager.download()

    fun postpone() = manager.postpone()

    fun dismissUpToDate() = manager.dismissUpToDate()

    fun clearError() = manager.clearError()

    fun canInstall(): Boolean = manager.canInstall()

    fun unknownSourcesSettings() = manager.unknownSourcesSettings()

    fun installIntent(file: File) = manager.installIntent(file)
}
