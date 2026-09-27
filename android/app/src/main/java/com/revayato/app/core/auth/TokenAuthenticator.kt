package com.revayato.app.core.auth

import com.revayato.app.BuildConfig
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.Route
import javax.inject.Inject
import javax.inject.Singleton

/**
 * On a 401, exchanges the rotating refresh token for a fresh access token and
 * replays the failed request. A dedicated bare OkHttpClient performs the refresh
 * so it never re-enters this authenticator (which would loop).
 */
@Singleton
class TokenAuthenticator @Inject constructor(
    private val tokenStore: TokenStore,
    private val sessionEvents: SessionEvents,
) : okhttp3.Authenticator {

    private val json = Json { ignoreUnknownKeys = true }
    private val bareClient by lazy { OkHttpClient.Builder().build() }
    private val jsonMedia = "application/json; charset=utf-8".toMediaType()

    override fun authenticate(route: Route?, response: Response): Request? {
        // Give up after a couple of retries to avoid hammering a dead session.
        if (responseCount(response) >= 2) return null

        synchronized(this) {
            val currentAccess = runBlocking { tokenStore.accessToken() }
            val failedAccess = response.request.header("Authorization")?.removePrefix("Bearer ")

            // Another thread may have already refreshed; retry with the new token.
            if (currentAccess != null && currentAccess != failedAccess) {
                return response.request.newBuilder()
                    .header("Authorization", "Bearer $currentAccess")
                    .build()
            }

            val refresh = runBlocking { tokenStore.refreshToken() } ?: return null
            val newAccess = refreshTokens(refresh) ?: run {
                runBlocking { tokenStore.clear() }
                sessionEvents.notifyLoggedOut()
                return null
            }
            return response.request.newBuilder()
                .header("Authorization", "Bearer $newAccess")
                .build()
        }
    }

    private fun refreshTokens(refresh: String): String? {
        val body = buildJsonObject { put("refresh", refresh) }.toString()
            .toRequestBody(jsonMedia)
        val request = Request.Builder()
            .url("${BuildConfig.API_BASE_URL}/api/auth/token/refresh/")
            .post(body)
            .build()
        return try {
            bareClient.newCall(request).execute().use { resp ->
                if (!resp.isSuccessful) return null
                val payload = resp.body?.string().orEmpty()
                val obj = json.parseToJsonElement(payload).jsonObject
                val access = obj["access"]?.jsonPrimitive?.content ?: return null
                val newRefresh = obj["refresh"]?.jsonPrimitive?.content
                runBlocking { tokenStore.save(access, newRefresh ?: refresh) }
                access
            }
        } catch (_: Exception) {
            null
        }
    }

    private fun responseCount(response: Response): Int {
        var count = 1
        var prior = response.priorResponse
        while (prior != null) {
            count++
            prior = prior.priorResponse
        }
        return count
    }
}
