package com.revayato.app.core.update

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.first
import javax.inject.Inject
import javax.inject.Singleton

private val Context.updateDataStore by preferencesDataStore(name = "revayato_update")

/**
 * What the user has already said about updating, so the app asks once and then
 * stays quiet. Kept out of the auth store on purpose: signing out must not make
 * a dismissed update reappear.
 */
@Singleton
class UpdateStore @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val skippedKey = intPreferencesKey("skipped_version_code")
    private val promptedAtKey = longPreferencesKey("prompted_at")

    /** The newest build the user has tapped «بعداً» on, or 0. */
    suspend fun skippedVersionCode(): Int =
        context.updateDataStore.data.first()[skippedKey] ?: 0

    /** Epoch millis of the last time we showed the sheet, or 0. */
    suspend fun promptedAt(): Long =
        context.updateDataStore.data.first()[promptedAtKey] ?: 0L

    suspend fun rememberPrompt(now: Long) {
        context.updateDataStore.edit { it[promptedAtKey] = now }
    }

    suspend fun skip(versionCode: Int) {
        context.updateDataStore.edit { it[skippedKey] = versionCode }
    }
}
