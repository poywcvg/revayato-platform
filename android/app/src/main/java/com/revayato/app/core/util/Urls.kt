package com.revayato.app.core.util

import com.revayato.app.BuildConfig

/**
 * Backend serializers already emit absolute media/CDN URLs, but a few nested
 * payloads can still carry a relative object key. Resolve those against the API
 * origin so Coil / ExoPlayer never receive a path-only source.
 */
fun String?.toAbsoluteUrl(): String? {
    val raw = this?.trim().orEmpty()
    if (raw.isEmpty()) return null
    if (raw.startsWith("http://") || raw.startsWith("https://")) return raw
    if (raw.startsWith("//")) return "https:$raw"
    val base = BuildConfig.API_BASE_URL.trimEnd('/')
    return if (raw.startsWith("/")) "$base$raw" else "$base/$raw"
}
