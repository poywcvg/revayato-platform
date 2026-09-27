package com.revayato.app.core.di

import android.content.Context
import com.revayato.app.BuildConfig
import com.revayato.app.core.auth.AuthInterceptor
import com.revayato.app.core.auth.TokenAuthenticator
import com.revayato.app.core.network.OfflineCacheInterceptor
import com.revayato.app.data.remote.ApiService
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import kotlinx.serialization.json.Json
import okhttp3.Cache
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.io.File
import java.util.concurrent.TimeUnit
import javax.inject.Named
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun json(): Json = Json {
        ignoreUnknownKeys = true
        coerceInputValues = true
        isLenient = true
        explicitNulls = false
    }

    @Provides
    @Singleton
    @Named("api")
    fun okHttpClient(
        @ApplicationContext context: Context,
        authInterceptor: AuthInterceptor,
        authenticator: TokenAuthenticator,
        offlineCacheInterceptor: OfflineCacheInterceptor,
    ): OkHttpClient {
        val logging = HttpLoggingInterceptor().apply {
            level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BASIC
            else HttpLoggingInterceptor.Level.NONE
        }
        // Disk cache for the JSON API. The catalog endpoints send
        // `public, max-age=...`, so re-browsing (back, re-open, return home)
        // is served from here with no network hit; user-specific endpoints send
        // `no-store` and are never cached. See OfflineCacheInterceptor for the
        // offline/stale fallback that rides on top of this.
        val httpCache = Cache(File(context.cacheDir, "http_cache"), HTTP_CACHE_BYTES)
        return OkHttpClient.Builder()
            .cache(httpCache)
            // Application interceptor: sits above the cache so it can retry a
            // failed GET against cached bytes when the device is offline.
            .addInterceptor(offlineCacheInterceptor)
            .addInterceptor(authInterceptor)
            .authenticator(authenticator)
            .addInterceptor(logging)
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .callTimeout(60, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()
    }

    /**
     * A bare client for fetching the update APK. Deliberately not the API
     * client: an installer must not carry the user's bearer token, and a 3.4 MB
     * body would evict the whole JSON response cache on its way through.
     * Generous call timeout — this is one large file on a phone connection.
     */
    @Provides
    @Singleton
    @Named("apk")
    fun apkClient(): OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .callTimeout(15, TimeUnit.MINUTES)
        .retryOnConnectionFailure(true)
        .build()

    @Provides
    @Singleton
    fun retrofit(@Named("api") client: OkHttpClient, json: Json): Retrofit {
        val contentType = "application/json".toMediaType()
        return Retrofit.Builder()
            .baseUrl("${BuildConfig.API_BASE_URL.trimEnd('/')}/")
            .client(client)
            .addConverterFactory(json.asConverterFactory(contentType))
            .build()
    }

    @Provides
    @Singleton
    fun apiService(retrofit: Retrofit): ApiService = retrofit.create(ApiService::class.java)

    private const val HTTP_CACHE_BYTES = 25L * 1024 * 1024
}
