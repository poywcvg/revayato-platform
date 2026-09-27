package com.revayato.app.feature.player

import android.content.Context
import android.net.Uri
import com.revayato.app.core.download.DownloadUtil
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

/**
 * Manual subtitle synchronisation. ExoPlayer/Media3 has no built-in per-track
 * timing offset, so when the viewer nudges the sync we download the sidecar once,
 * re-time every cue by the chosen delay, and hand a rewritten local file back to
 * the player. Positive offset = subtitles appear later (video is ahead of the
 * text); negative = earlier. Keeps a tiny in-memory cache of the raw text so
 * repeated nudges never re-hit the network.
 */
object SubtitleSync {

    private val client: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .followRedirects(true)
            .followSslRedirects(true)
            .build()
    }

    // url -> original subtitle text. Bounded implicitly by how many distinct
    // subtitles a single viewing session touches (a handful).
    private val rawCache = HashMap<String, String>()

    /**
     * Return a local file [Uri] holding [absUrl]'s cues shifted by [offsetMs], or
     * null when no shift is needed / the fetch fails (caller then uses [absUrl]).
     */
    suspend fun shiftedFile(context: Context, absUrl: String, offsetMs: Long): Uri? {
        if (offsetMs == 0L || absUrl.isBlank()) return null
        return withContext(Dispatchers.IO) {
            runCatching {
                val text = rawCache[absUrl] ?: fetch(absUrl).also { rawCache[absUrl] = it }
                val shifted = shift(text, offsetMs)
                val ext = when {
                    absUrl.endsWith(".vtt", true) || text.trimStart().startsWith("WEBVTT") -> "vtt"
                    absUrl.endsWith(".ass", true) || absUrl.endsWith(".ssa", true) -> return@runCatching null
                    else -> "srt"
                }
                val dir = File(context.cacheDir, "subsync").apply { mkdirs() }
                val file = File(dir, "${hash(absUrl)}_$offsetMs.$ext")
                if (!file.exists()) file.writeText(shifted)
                Uri.fromFile(file)
            }.getOrNull()
        }
    }

    private fun fetch(url: String): String {
        val req = Request.Builder()
            .url(url)
            .header("User-Agent", DownloadUtil.STREAM_USER_AGENT)
            .apply { DownloadUtil.STREAM_REQUEST_HEADERS.forEach { (k, v) -> header(k, v) } }
            .build()
        client.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) error("HTTP ${resp.code}")
            return resp.body?.string().orEmpty()
        }
    }

    // Matches SRT (00:01:02,500) and VTT (00:01:02.500 or 01:02.500) timestamps,
    // preserving the original separator so the rewritten file stays valid.
    private val timeRe =
        Regex("""(?:(\d{1,2}):)?(\d{1,2}):(\d{2})([,.])(\d{1,3})""")

    private fun shift(text: String, offsetMs: Long): String =
        timeRe.replace(text) { m ->
            val h = m.groupValues[1].ifEmpty { "0" }.toLong()
            val min = m.groupValues[2].toLong()
            val sec = m.groupValues[3].toLong()
            val sep = m.groupValues[4]
            val millis = m.groupValues[5].padEnd(3, '0').take(3).toLong()
            val total = (((h * 60 + min) * 60 + sec) * 1000 + millis + offsetMs)
                .coerceAtLeast(0L)
            val hh = total / 3_600_000
            val mm = (total % 3_600_000) / 60_000
            val ss = (total % 60_000) / 1000
            val ms = total % 1000
            "%02d:%02d:%02d%s%03d".format(hh, mm, ss, sep, ms)
        }

    private fun hash(s: String): String =
        MessageDigest.getInstance("MD5").digest(s.toByteArray())
            .joinToString("") { "%02x".format(it) }
            .take(16)
}
