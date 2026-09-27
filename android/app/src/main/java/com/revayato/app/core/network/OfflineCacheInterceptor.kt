package com.revayato.app.core.network

import okhttp3.CacheControl
import okhttp3.Interceptor
import okhttp3.Response
import java.io.IOException
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Keeps browsing smooth when the network is slow or gone.
 *
 * The catalog API sends `public, max-age=60, stale-while-revalidate=180`, so a
 * fresh response is served straight from the OkHttp disk cache with no network
 * round-trip while it's within its max-age window — that's what makes back
 * navigation, re-opening a detail, or returning home feel instant.
 *
 * OkHttp does not honour `stale-while-revalidate` on its own, so this
 * application interceptor adds the resilience half by hand: when a **GET**
 * fails because the device is offline (or the request times out), it retries
 * once against the cache alone, accepting content up to [MAX_STALE_DAYS] old.
 * A cached poster grid or detail page then still paints instead of an error.
 *
 * Only GETs are retried — mutations (likes, watch progress, auth) must surface
 * their real network error rather than a stale/`504` cache reply.
 */
@Singleton
class OfflineCacheInterceptor @Inject constructor() : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        return try {
            chain.proceed(request)
        } catch (error: IOException) {
            if (request.method != "GET") throw error
            val cachedOnly = request.newBuilder()
                .cacheControl(
                    CacheControl.Builder()
                        .onlyIfCached()
                        .maxStale(MAX_STALE_DAYS, TimeUnit.DAYS)
                        .build(),
                )
                .build()
            // If nothing is cached OkHttp returns an unsatisfiable 504, which the
            // caller handles as a normal error — same outcome as the original throw.
            chain.proceed(cachedOnly)
        }
    }

    private companion object {
        const val MAX_STALE_DAYS = 7
    }
}
