package com.revayato.app.core.download

import android.content.Context
import androidx.annotation.OptIn
import androidx.media3.common.util.UnstableApi
import androidx.media3.database.DatabaseProvider
import androidx.media3.database.StandaloneDatabaseProvider
import androidx.media3.datasource.DataSource
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.cache.Cache
import androidx.media3.datasource.cache.CacheDataSource
import androidx.media3.datasource.cache.NoOpCacheEvictor
import androidx.media3.datasource.cache.SimpleCache
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.offline.DefaultDownloadIndex
import androidx.media3.exoplayer.offline.DefaultDownloaderFactory
import androidx.media3.exoplayer.offline.DownloadManager
import androidx.media3.exoplayer.offline.DownloadNotificationHelper
import okhttp3.OkHttpClient
import java.io.File
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * Process-wide singletons for Media3 offline downloads. [RevayatoDownloadService]
 * is instantiated by the framework and cannot receive Hilt injections, so the
 * download manager, cache and notification helper live here behind lazy getters.
 */
@OptIn(UnstableApi::class)
object DownloadUtil {

    const val DOWNLOAD_NOTIFICATION_CHANNEL_ID = "revayato_downloads"
    private const val DOWNLOAD_CONTENT_DIRECTORY = "revayato_downloads"

    // Many third-party file hosts (starsdl, etc.) reset the connection unless the
    // request looks like a real browser. The web player works precisely because
    // the browser sends a desktop UA + a revayato Referer; mirror that here so
    // ExoPlayer streams (and offline downloads) are not blocked at the TLS/HTTP
    // layer. Without this, online playback simply fails to start.
    //
    // Public so the system-DownloadManager path ([DownloadsManager.enqueueFile])
    // can send the *same* browser-mimicking headers — otherwise a "ذخیره فایل"
    // request goes out with Android's default UA and no Referer, the CDN resets
    // the connection, and the download fails silently with no error surfaced.
    const val STREAM_USER_AGENT =
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

    val STREAM_REQUEST_HEADERS = mapOf(
        "Referer" to "https://revayato.com/",
        "Accept" to "*/*",
        "Accept-Language" to "fa,en;q=0.9",
    )

    private var databaseProvider: DatabaseProvider? = null
    private var downloadCache: Cache? = null
    private var downloadManager: DownloadManager? = null
    private var notificationHelper: DownloadNotificationHelper? = null

    // A dedicated client keeps download traffic off the REST call-timeout budget.
    // Generous timeouts so a slow CDN never trips a premature failure, and both
    // redirect follows on so http↔https and CDN edge hops resolve transparently.
    private val httpClient: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .followRedirects(true)
            .followSslRedirects(true)
            .retryOnConnectionFailure(true)
            .build()
    }

    /** Browser-mimicking HTTP source shared by streaming and offline downloads. */
    private fun streamingHttpFactory(): OkHttpDataSource.Factory =
        OkHttpDataSource.Factory(httpClient)
            .setUserAgent(STREAM_USER_AGENT)
            .setDefaultRequestProperties(STREAM_REQUEST_HEADERS)

    @Synchronized
    fun getDatabaseProvider(context: Context): DatabaseProvider =
        databaseProvider ?: StandaloneDatabaseProvider(context.applicationContext).also { databaseProvider = it }

    @Synchronized
    fun getDownloadCache(context: Context): Cache {
        downloadCache?.let { return it }
        val dir = File(context.applicationContext.filesDir, DOWNLOAD_CONTENT_DIRECTORY)
        return SimpleCache(dir, NoOpCacheEvictor(), getDatabaseProvider(context)).also { downloadCache = it }
    }

    @Synchronized
    fun getDownloadManager(context: Context): DownloadManager {
        downloadManager?.let { return it }
        val upstream = DefaultDataSource.Factory(
            context.applicationContext,
            streamingHttpFactory(),
        )
        val manager = DownloadManager(
            context.applicationContext,
            DefaultDownloadIndex(getDatabaseProvider(context)),
            DefaultDownloaderFactory(
                CacheDataSource.Factory()
                    .setCache(getDownloadCache(context))
                    .setUpstreamDataSourceFactory(upstream),
                Executors.newFixedThreadPool(3),
            ),
        ).apply {
            maxParallelDownloads = 2
        }
        downloadManager = manager
        return manager
    }

    @Synchronized
    fun getNotificationHelper(context: Context): DownloadNotificationHelper =
        notificationHelper ?: DownloadNotificationHelper(
            context.applicationContext,
            DOWNLOAD_NOTIFICATION_CHANNEL_ID,
        ).also { notificationHelper = it }

    /** Cache-backed source factory so a downloaded title plays fully offline. */
    fun getCacheDataSourceFactory(context: Context): DataSource.Factory {
        val upstream = DefaultDataSource.Factory(
            context.applicationContext,
            streamingHttpFactory(),
        )
        return CacheDataSource.Factory()
            .setCache(getDownloadCache(context))
            .setUpstreamDataSourceFactory(upstream)
            .setFlags(CacheDataSource.FLAG_IGNORE_CACHE_ON_ERROR)
    }
}
