package com.revayato.app.core.download

import android.app.DownloadManager as SystemDownloadManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.Uri
import android.os.Environment
import androidx.annotation.OptIn
import androidx.core.content.ContextCompat
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.offline.Download
import androidx.media3.exoplayer.offline.DownloadManager
import androidx.media3.exoplayer.offline.DownloadRequest
import androidx.media3.exoplayer.offline.DownloadService
import com.revayato.app.core.util.toAbsoluteUrl
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.concurrent.ConcurrentHashMap
import javax.inject.Inject
import javax.inject.Singleton

/** A downloaded (or downloading) title, projected for the UI. */
data class DownloadItem(
    val id: String,
    val title: String,
    val contentType: String,
    val contentId: Int,
    val uri: String,
    val state: Int,
    val percentDownloaded: Float,
    val bytesDownloaded: Long,
) {
    val isComplete: Boolean get() = state == Download.STATE_COMPLETED
}

/**
 * A one-shot download lifecycle signal, surfaced so screens can raise an accurate
 * alert instead of the old fire-and-forget "started" message that lied when a
 * download later failed. [title] identifies which title the event is about so a
 * detail screen can filter to its own downloads.
 */
sealed interface DownloadEvent {
    val title: String

    /** The URL was missing/invalid, so nothing was ever queued. */
    data class Rejected(override val title: String) : DownloadEvent
    /** Successfully handed to the download engine. */
    data class Started(override val title: String, val toFile: Boolean) : DownloadEvent
    /** Finished writing to cache / the Downloads folder. */
    data class Completed(override val title: String, val toFile: Boolean) : DownloadEvent
    /** The download engine reported a failure (network, CDN reset, disk, …). */
    data class Failed(override val title: String, val toFile: Boolean) : DownloadEvent
}

/**
 * Bridges the app to two download mechanisms:
 *  - Media3 offline cache → in-app offline playback ([enqueueOffline]).
 *  - Android system DownloadManager → a shareable file in /Download ([enqueueFile]).
 *
 * Both paths now (a) send the same browser-mimicking headers the CDNs demand,
 * (b) validate the URL up-front and report back whether the request was accepted,
 * and (c) emit terminal [DownloadEvent]s so the UI can alert on real success or
 * failure rather than optimistically claiming success the moment a button is tapped.
 */
@OptIn(UnstableApi::class)
@Singleton
class DownloadsManager @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val manager: DownloadManager = DownloadUtil.getDownloadManager(context)

    private val _downloads = MutableStateFlow<List<DownloadItem>>(emptyList())
    val downloads: StateFlow<List<DownloadItem>> = _downloads.asStateFlow()

    private val _events = MutableSharedFlow<DownloadEvent>(
        replay = 0,
        extraBufferCapacity = 16,
    )
    val events: SharedFlow<DownloadEvent> = _events.asSharedFlow()

    // Offline (Media3) download ids we've already reported a terminal event for,
    // so a repeated onDownloadChanged callback doesn't double-fire an alert.
    private val reportedOffline = ConcurrentHashMap<String, Int>()
    // System DownloadManager id → title, so the completion receiver can name the file.
    private val fileTitles = ConcurrentHashMap<Long, String>()

    init {
        manager.addListener(object : DownloadManager.Listener {
            override fun onDownloadChanged(dm: DownloadManager, download: Download, e: Exception?) {
                val title = decodeMeta(String(download.request.data)).title
                    .ifBlank { download.request.id }
                when (download.state) {
                    Download.STATE_COMPLETED ->
                        if (reportedOffline.put(download.request.id, download.state) != download.state) {
                            _events.tryEmit(DownloadEvent.Completed(title, toFile = false))
                        }
                    Download.STATE_FAILED ->
                        if (reportedOffline.put(download.request.id, download.state) != download.state) {
                            _events.tryEmit(DownloadEvent.Failed(title, toFile = false))
                        }
                    else -> Unit
                }
                refresh()
            }

            override fun onDownloadRemoved(dm: DownloadManager, download: Download) {
                reportedOffline.remove(download.request.id)
                refresh()
            }
        })
        registerFileCompletionReceiver()
        refresh()
    }

    fun refresh() {
        val items = buildList {
            manager.downloadIndex.getDownloads().use { cursor ->
                while (cursor.moveToNext()) add(cursor.download.toItem())
            }
        }
        _downloads.value = items
    }

    /**
     * Queue an in-app offline download keyed by a stable content id.
     * @return true when the request was accepted; false when the URL was unusable.
     */
    fun enqueueOffline(contentType: String, contentId: Int, title: String, url: String): Boolean {
        val resolved = url.toAbsoluteUrl()
        if (resolved.isNullOrBlank()) {
            _events.tryEmit(DownloadEvent.Rejected(title))
            return false
        }
        val id = keyOf(contentType, contentId)
        reportedOffline.remove(id)
        val request = DownloadRequest.Builder(id, Uri.parse(resolved))
            .setData(encodeMeta(title, contentType, contentId).toByteArray())
            .build()
        DownloadService.sendAddDownload(
            context, RevayatoDownloadService::class.java, request, /* foreground= */ false,
        )
        _events.tryEmit(DownloadEvent.Started(title, toFile = false))
        return true
    }

    fun removeOffline(id: String) {
        DownloadService.sendRemoveDownload(
            context, RevayatoDownloadService::class.java, id, /* foreground= */ false,
        )
    }

    fun pauseAll() {
        DownloadService.sendPauseDownloads(context, RevayatoDownloadService::class.java, false)
    }

    fun resumeAll() {
        DownloadService.sendResumeDownloads(context, RevayatoDownloadService::class.java, false)
    }

    /**
     * Save a shareable copy to the public Downloads folder via the OS.
     * @return true when the request was accepted; false when the URL was unusable.
     */
    fun enqueueFile(title: String, url: String): Boolean {
        val resolved = url.toAbsoluteUrl()
        if (resolved.isNullOrBlank()) {
            _events.tryEmit(DownloadEvent.Rejected(title))
            return false
        }
        val system = context.getSystemService(Context.DOWNLOAD_SERVICE) as SystemDownloadManager
        val safeName = title.replace(Regex("[^\\p{L}\\p{N} ._-]"), "").trim().ifBlank { "revayato" }
        val fileName = "$safeName${guessExtension(resolved)}"
        val request = SystemDownloadManager.Request(Uri.parse(resolved))
            .setTitle(title)
            .setDescription("دانلود از روایتو")
            .setNotificationVisibility(SystemDownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName)
            .setAllowedOverMetered(true)
            .setAllowedOverRoaming(true)
            // Without a browser UA + Referer the provider CDNs reset the connection,
            // which was the root cause of "ذخیره فایل" downloads dying with no error.
            .addRequestHeader("User-Agent", DownloadUtil.STREAM_USER_AGENT)
        DownloadUtil.STREAM_REQUEST_HEADERS.forEach { (k, v) -> request.addRequestHeader(k, v) }

        val id = try {
            system.enqueue(request)
        } catch (e: Exception) {
            _events.tryEmit(DownloadEvent.Failed(title, toFile = true))
            return false
        }
        fileTitles[id] = title
        _events.tryEmit(DownloadEvent.Started(title, toFile = true))
        return true
    }

    /**
     * The system DownloadManager only reports terminal status via a broadcast, so
     * listen for it and translate the OS status into a [DownloadEvent] — this is
     * how "ذخیره فایل" downloads finally get real success/failure feedback.
     */
    private fun registerFileCompletionReceiver() {
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(ctx: Context, intent: Intent) {
                val id = intent.getLongExtra(SystemDownloadManager.EXTRA_DOWNLOAD_ID, -1L)
                if (id == -1L) return
                val title = fileTitles.remove(id) ?: return
                val system = ctx.getSystemService(Context.DOWNLOAD_SERVICE) as SystemDownloadManager
                val status = system.query(SystemDownloadManager.Query().setFilterById(id)).use { c ->
                    if (c != null && c.moveToFirst()) {
                        c.getInt(c.getColumnIndexOrThrow(SystemDownloadManager.COLUMN_STATUS))
                    } else {
                        SystemDownloadManager.STATUS_FAILED
                    }
                }
                if (status == SystemDownloadManager.STATUS_SUCCESSFUL) {
                    _events.tryEmit(DownloadEvent.Completed(title, toFile = true))
                } else {
                    _events.tryEmit(DownloadEvent.Failed(title, toFile = true))
                }
            }
        }
        ContextCompat.registerReceiver(
            context,
            receiver,
            IntentFilter(SystemDownloadManager.ACTION_DOWNLOAD_COMPLETE),
            ContextCompat.RECEIVER_EXPORTED,
        )
    }

    private fun Download.toItem(): DownloadItem {
        val meta = decodeMeta(String(request.data))
        return DownloadItem(
            id = request.id,
            title = meta.title.ifBlank { request.id },
            contentType = meta.contentType,
            contentId = meta.contentId,
            uri = request.uri.toString(),
            state = state,
            percentDownloaded = percentDownloaded.coerceIn(0f, 100f),
            bytesDownloaded = bytesDownloaded,
        )
    }

    private data class Meta(val title: String, val contentType: String, val contentId: Int)

    private fun encodeMeta(title: String, contentType: String, contentId: Int): String =
        "$contentType|$contentId|$title"

    private fun decodeMeta(raw: String): Meta {
        val parts = raw.split("|", limit = 3)
        return if (parts.size == 3) {
            Meta(parts[2], parts[0], parts[1].toIntOrNull() ?: 0)
        } else {
            Meta(raw, "movie", 0)
        }
    }

    private fun guessExtension(url: String): String {
        val path = Uri.parse(url).lastPathSegment.orEmpty()
        val dot = path.lastIndexOf('.')
        return if (dot in 0..path.length - 2) path.substring(dot) else ".mp4"
    }

    companion object {
        fun keyOf(contentType: String, contentId: Int) = "$contentType-$contentId"
    }
}
