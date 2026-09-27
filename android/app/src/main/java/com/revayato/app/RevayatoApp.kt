package com.revayato.app

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import coil.ImageLoader
import coil.ImageLoaderFactory
import coil.disk.DiskCache
import coil.memory.MemoryCache
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class RevayatoApp : Application(), ImageLoaderFactory {

    override fun onCreate() {
        super.onCreate()
        createDownloadChannel()
    }

    private fun createDownloadChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                DOWNLOAD_CHANNEL_ID,
                "دانلودها",
                NotificationManager.IMPORTANCE_LOW,
            ).apply { description = "وضعیت دانلود فیلم‌ها و سریال‌ها" }
            getSystemService(NotificationManager::class.java)?.createNotificationChannel(channel)
        }
    }

    override fun newImageLoader(): ImageLoader = ImageLoader.Builder(this)
        .crossfade(180)
        // Posters rarely change, so trust the cache instead of revalidating each
        // scroll over the network — keeps lists smooth and cuts data usage.
        .respectCacheHeaders(false)
        .memoryCache { MemoryCache.Builder(this).maxSizePercent(0.28).build() }
        .diskCache {
            DiskCache.Builder()
                .directory(cacheDir.resolve("image_cache"))
                .maxSizeBytes(200L * 1024 * 1024)
                .build()
        }
        .build()

    companion object {
        const val DOWNLOAD_CHANNEL_ID = "revayato_downloads"
        const val DOWNLOAD_NOTIFICATION_ID = 4201
    }
}
