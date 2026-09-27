package com.revayato.app.feature.downloads

import androidx.lifecycle.ViewModel
import com.revayato.app.core.download.DownloadItem
import com.revayato.app.core.download.DownloadsManager
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.StateFlow
import javax.inject.Inject

@HiltViewModel
class DownloadsViewModel @Inject constructor(
    private val downloadsManager: DownloadsManager,
) : ViewModel() {

    val downloads: StateFlow<List<DownloadItem>> = downloadsManager.downloads

    fun refresh() = downloadsManager.refresh()

    fun remove(id: String) = downloadsManager.removeOffline(id)

    fun resumeAll() = downloadsManager.resumeAll()
}
