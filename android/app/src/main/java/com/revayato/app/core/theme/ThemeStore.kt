package com.revayato.app.core.theme

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

/** How the app picks light or dark. [SYSTEM] follows the phone's own setting. */
enum class ThemeMode { SYSTEM, LIGHT, DARK }

private val Context.themeDataStore by preferencesDataStore(name = "revayato_theme")

/** Remembers the viewer's light/dark choice on the device. */
@Singleton
class ThemeStore @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val key = stringPreferencesKey("theme_mode")

    val mode: Flow<ThemeMode> = context.themeDataStore.data.map { prefs ->
        prefs[key]?.let { stored -> ThemeMode.entries.firstOrNull { it.name == stored } } ?: ThemeMode.SYSTEM
    }

    suspend fun set(mode: ThemeMode) {
        context.themeDataStore.edit { it[key] = mode.name }
    }
}

/** What screens need to read and flip the theme: the stored mode, the resolved darkness, and a setter. */
@androidx.compose.runtime.Immutable
data class ThemeController(
    val mode: ThemeMode,
    val isDark: Boolean,
    val setMode: (ThemeMode) -> Unit,
)

val LocalThemeController = androidx.compose.runtime.staticCompositionLocalOf {
    ThemeController(mode = ThemeMode.SYSTEM, isDark = true, setMode = {})
}
