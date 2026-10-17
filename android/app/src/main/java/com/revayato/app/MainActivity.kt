package com.revayato.app

import android.os.Bundle
import android.graphics.Color
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.unit.LayoutDirection
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.LocalThemeController
import com.revayato.app.core.theme.RevayatoTheme
import com.revayato.app.core.theme.ThemeController
import com.revayato.app.core.theme.ThemeMode
import com.revayato.app.feature.root.RootViewModel
import com.revayato.app.feature.update.AppUpdateHost
import com.revayato.app.navigation.RevayatoRoot
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    private val rootViewModel: RootViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        val splash = installSplashScreen()
        super.onCreate(savedInstanceState)

        var keepSplash = true
        splash.setKeepOnScreenCondition { keepSplash }

        enableEdgeToEdge()

        setContent {
            val startState by rootViewModel.startState.collectAsStateWithLifecycle()
            val storedMode by rootViewModel.themeMode.collectAsStateWithLifecycle()
            // Hold the splash until the stored theme is known too, so a light-mode
            // viewer never sees one dark frame first.
            keepSplash = startState.loading || storedMode == null

            val mode = storedMode ?: ThemeMode.SYSTEM
            val systemDark = isSystemInDarkTheme()
            val dark = when (mode) {
                ThemeMode.SYSTEM -> systemDark
                ThemeMode.LIGHT -> false
                ThemeMode.DARK -> true
            }

            // Status/navigation bar icons follow the theme: light icons on the
            // dark ground, dark icons on the light one.
            DisposableEffect(dark) {
                val style = if (dark) {
                    SystemBarStyle.dark(Color.TRANSPARENT)
                } else {
                    SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT)
                }
                enableEdgeToEdge(statusBarStyle = style, navigationBarStyle = style)
                onDispose {}
            }

            val controller = ThemeController(mode = mode, isDark = dark, setMode = rootViewModel::setThemeMode)

            RevayatoTheme(darkTheme = dark) {
                // The entire experience is Persian → force right-to-left layout.
                CompositionLocalProvider(
                    LocalLayoutDirection provides LayoutDirection.Rtl,
                    LocalThemeController provides controller,
                ) {
                    Surface(modifier = Modifier.fillMaxSize()) {
                        if (!startState.loading) {
                            Box(modifier = Modifier.fillMaxSize()) {
                                RevayatoRoot(
                                    isLoggedIn = startState.isLoggedIn,
                                    sessionEvents = rootViewModel.sessionEvents,
                                )
                                // Sideloaded from revayato.com — no store ever tells
                                // anyone a newer build exists, so the app asks on its
                                // own. Hosted beside the navigation graph rather than
                                // inside it: the prompt belongs to the app, not to a
                                // screen, and the graph stays exactly as it was.
                                AppUpdateHost()
                            }
                        }
                    }
                }
            }
        }
    }
}
