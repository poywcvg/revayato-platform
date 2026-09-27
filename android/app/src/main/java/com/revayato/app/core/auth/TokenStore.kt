package com.revayato.app.core.auth

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.authDataStore by preferencesDataStore(name = "revayato_auth")

/**
 * Persists the JWT access/refresh pair. Access tokens are short-lived (~1h);
 * the refresh token rotates on every use, so we always write both together.
 */
@Singleton
class TokenStore @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val accessKey = stringPreferencesKey("access")
    private val refreshKey = stringPreferencesKey("refresh")

    val isLoggedIn: Flow<Boolean> =
        context.authDataStore.data.map { !it[refreshKey].isNullOrBlank() }

    suspend fun accessToken(): String? = context.authDataStore.data.first()[accessKey]

    suspend fun refreshToken(): String? = context.authDataStore.data.first()[refreshKey]

    suspend fun save(access: String, refresh: String?) {
        context.authDataStore.edit { prefs ->
            prefs[accessKey] = access
            if (!refresh.isNullOrBlank()) prefs[refreshKey] = refresh
        }
    }

    suspend fun clear() {
        context.authDataStore.edit { it.clear() }
    }
}
