package com.revayato.app.core.download

import android.app.Notification
import androidx.annotation.OptIn
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.offline.Download
import androidx.media3.exoplayer.offline.DownloadManager
import androidx.media3.exoplayer.offline.DownloadService
import androidx.media3.exoplayer.scheduler.Scheduler
import com.revayato.app.R

/** Foreground service that runs Media3 offline downloads. Registered in the manifest. */
@OptIn(UnstableApi::class)
class RevayatoDownloadService : DownloadService(
    FOREGROUND_NOTIFICATION_ID,
    DEFAULT_FOREGROUND_NOTIFICATION_UPDATE_INTERVAL,
    DownloadUtil.DOWNLOAD_NOTIFICATION_CHANNEL_ID,
    R.string.download_channel_name,
    0,
) {
    override fun getDownloadManager(): DownloadManager = DownloadUtil.getDownloadManager(this)

    override fun getScheduler(): Scheduler? = null

    override fun getForegroundNotification(
        downloads: MutableList<Download>,
        notMetRequirements: Int,
    ): Notification {
        val message = downloads.firstOrNull()?.request?.let {
            "در حال دانلود ${downloads.size} مورد"
        } ?: "آماده‌سازی دانلود"
        return DownloadUtil.getNotificationHelper(this).buildProgressNotification(
            this,
            android.R.drawable.stat_sys_download,
            null,
            message,
            downloads,
            notMetRequirements,
        )
    }

    companion object {
        private const val FOREGROUND_NOTIFICATION_ID = 42
    }
}
