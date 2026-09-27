package com.revayato.app.core.playback

import android.content.Context
import android.content.SharedPreferences
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.Serializable
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json
import javax.inject.Inject
import javax.inject.Singleton

/**
 * One resumable item on the "ادامه تماشا" (Continue Watching) shelf. Rich enough
 * to both render a poster card AND relaunch the player straight to where the
 * viewer left off — no round-trip to the backend required.
 */
@Serializable
data class WatchProgressEntry(
    val contentType: String,
    val id: Int,
    val slug: String,
    val title: String,
    val poster: String = "",
    val episodeId: Int = 0,
    val episodeLabel: String = "",
    val url: String,
    val subtitlesEncoded: String = "",
    val qualitiesEncoded: String = "",
    val positionMs: Long = 0,
    val durationMs: Long = 0,
    val updatedAt: Long = 0,
) {
    /** Fraction watched in [0f,1f], for the little progress bar on the card. */
    val progressFraction: Float
        get() = if (durationMs > 0) (positionMs.toFloat() / durationMs).coerceIn(0f, 1f) else 0f
}

/**
 * Device-local, title-level playback progress persisted across app launches.
 *
 * The player is the single writer (it upserts every few seconds and clears an
 * entry when a title finishes); the home screen observes [entries] to build the
 * Continue Watching rail. Backed by SharedPreferences holding one JSON blob so
 * reads/writes are cheap and survive process death.
 */
@Singleton
class WatchProgressStore @Inject constructor(
    @ApplicationContext context: Context,
) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

    private val _entries = MutableStateFlow(readAll())
    /** Most-recently watched first. */
    val entries: StateFlow<List<WatchProgressEntry>> = _entries.asStateFlow()

    private fun key(contentType: String, id: Int): String = "${contentType.lowercase()}:$id"

    fun get(contentType: String, id: Int): WatchProgressEntry? {
        val k = key(contentType, id)
        return _entries.value.firstOrNull { key(it.contentType, it.id) == k }
    }

    /** Insert or replace the entry for a title, keeping the list newest-first. */
    fun upsert(entry: WatchProgressEntry) {
        val k = key(entry.contentType, entry.id)
        val next = (_entries.value.filterNot { key(it.contentType, it.id) == k } + entry)
            .sortedByDescending { it.updatedAt }
            .take(MAX_ENTRIES)
        _entries.value = next
        persist(next)
    }

    /** Drop a title from the shelf (e.g. once it's been finished). */
    fun remove(contentType: String, id: Int) {
        val k = key(contentType, id)
        val next = _entries.value.filterNot { key(it.contentType, it.id) == k }
        if (next.size == _entries.value.size) return
        _entries.value = next
        persist(next)
    }

    private fun readAll(): List<WatchProgressEntry> {
        val raw = prefs.getString(KEY_ENTRIES, null) ?: return emptyList()
        return runCatching {
            json.decodeFromString(ListSerializer(WatchProgressEntry.serializer()), raw)
        }.getOrDefault(emptyList()).sortedByDescending { it.updatedAt }
    }

    private fun persist(list: List<WatchProgressEntry>) {
        val raw = runCatching {
            json.encodeToString(ListSerializer(WatchProgressEntry.serializer()), list)
        }.getOrNull() ?: return
        prefs.edit().putString(KEY_ENTRIES, raw).apply()
    }

    private companion object {
        const val PREFS_NAME = "revayato_watch_progress"
        const val KEY_ENTRIES = "entries"
        const val MAX_ENTRIES = 20
    }
}
