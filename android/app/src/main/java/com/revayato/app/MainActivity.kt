package com.revayato.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.unit.LayoutDirection
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.RevayatoTheme
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
            keepSplash = startState.loading

            RevayatoTheme {
                // The entire experience is Persian → force right-to-left layout.
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
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
