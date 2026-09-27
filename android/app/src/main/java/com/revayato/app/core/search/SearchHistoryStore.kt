package com.revayato.app.core.search

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.searchDataStore by preferencesDataStore(name = "revayato_search_history")

/**
 * Persists the user's recent search terms on-device (most-recent first, capped at
 * [MAX_ITEMS]) so the search screen can offer one-tap re-search and a clearable
 * history. Stored as a newline-joined string to preserve order — a preferences
 * String set would not. Everything stays local; no query ever leaves the phone
 * beyond the normal search request.
 */
@Singleton
class SearchHistoryStore @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val key = stringPreferencesKey("recent_queries")

    val history: Flow<List<String>> = context.searchDataStore.data.map { prefs ->
        prefs[key].orEmpty()
            .split('\n')
            .map { it.trim() }
            .filter { it.isNotEmpty() }
    }

    /** Record a successful search term, de-duplicated and promoted to the top. */
    suspend fun record(term: String) {
        val clean = term.trim()
        if (clean.length < 2) return
        context.searchDataStore.edit { prefs ->
            val existing = prefs[key].orEmpty()
                .split('\n')
                .map { it.trim() }
                .filter { it.isNotEmpty() && !it.equals(clean, ignoreCase = true) }
            prefs[key] = (listOf(clean) + existing).take(MAX_ITEMS).joinToString("\n")
        }
    }

    suspend fun remove(term: String) {
        context.searchDataStore.edit { prefs ->
            val remaining = prefs[key].orEmpty()
                .split('\n')
                .map { it.trim() }
                .filter { it.isNotEmpty() && !it.equals(term.trim(), ignoreCase = true) }
            prefs[key] = remaining.joinToString("\n")
        }
    }

    suspend fun clear() {
        context.searchDataStore.edit { it.remove(key) }
    }

    private companion object {
        const val MAX_ITEMS = 12
    }
}
