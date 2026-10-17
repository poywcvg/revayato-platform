package com.revayato.app.feature.player

import android.app.Activity
import android.content.Context
import android.content.pm.ActivityInfo
import android.media.AudioManager
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.PlaylistPlay
import androidx.compose.material.icons.rounded.AspectRatio
import androidx.compose.material.icons.rounded.BrightnessHigh
import androidx.compose.material.icons.rounded.Brush
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.ClosedCaption
import androidx.compose.material.icons.rounded.FastForward
import androidx.compose.material.icons.rounded.Flag
import androidx.compose.material.icons.rounded.GraphicEq
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.LockOpen
import androidx.compose.material.icons.rounded.Pause
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Replay
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.SkipNext
import androidx.compose.material.icons.rounded.VolumeUp
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.PointerEventType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView
import com.revayato.app.core.theme.AccentYellow
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.Brand
import com.revayato.app.core.theme.NeutralSurface
import com.revayato.app.core.theme.OnPlayAccent
import com.revayato.app.core.theme.PlayAccent
import com.revayato.app.core.theme.PlayAccentSoft
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.ui.components.NetworkImage
import kotlin.math.roundToInt
import kotlinx.coroutines.delay

private enum class GestureKind { VOLUME, BRIGHTNESS }

/** Transient double-tap seek indicator: which side, how many seconds accumulated. */
private data class SeekFeedback(val forward: Boolean, val seconds: Int, val tick: Int)

@OptIn(ExperimentalMaterial3Api::class, androidx.media3.common.util.UnstableApi::class)
@Composable
fun PlayerScreen(
    args: PlayerArgs,
    onBack: () -> Unit,
    viewModel: PlayerViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    LaunchedEffect(args.id) { viewModel.setup(args) }

    // Full-screen landscape cinema mode: lock orientation + hide system bars,
    // keep the screen awake, and restore everything on exit.
    val view = LocalView.current
    val context = LocalContext.current
    val activity = context as? Activity
    DisposableEffect(Unit) {
        view.keepScreenOn = true
        val originalOrientation = activity?.requestedOrientation
        activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        val window = activity?.window
        val controller = window?.let { WindowInsetsControllerCompat(it, view) }
        controller?.apply {
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            hide(WindowInsetsCompat.Type.systemBars())
        }
        // Enter the player at full screen brightness so the picture is never dim —
        // the fix for "نور کم است حتی روی ۱۰۰٪". The right-edge slider lowers it.
        window?.let { w -> w.attributes = w.attributes.apply { screenBrightness = 1f } }
        onDispose {
            view.keepScreenOn = false
            controller?.show(WindowInsetsCompat.Type.systemBars())
            // Hand brightness control back to the system when leaving the player.
            window?.attributes = window?.attributes?.apply { screenBrightness = -1f }
            originalOrientation?.let { activity.requestedOrientation = it }
        }
    }

    // --- Audio (system media stream) + screen brightness gesture state ---
    val audioManager = remember { context.getSystemService(Context.AUDIO_SERVICE) as AudioManager }
    val maxVolume = remember { audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1) }
    var volumeFraction by remember {
        mutableFloatStateOf(audioManager.getStreamVolume(AudioManager.STREAM_MUSIC).toFloat() / maxVolume)
    }
    // Start at full brightness to match the applied window value above.
    var brightness by remember { mutableFloatStateOf(1f) }
    // Which edge slider is currently on screen (null = none). The volume/brightness
    // sliders appear ONLY while the viewer is changing that value, then fade out.
    var adjust by remember { mutableStateOf<GestureKind?>(null) }
    // Bumped on every volume/brightness change so the single shared deadline below
    // restarts — the slider stays up while dragging and hides ~1.2s after it stops.
    var adjustTick by remember { mutableIntStateOf(0) }
    var seek by remember { mutableStateOf<SeekFeedback?>(null) }

    // One deadline for both sliders, reset by each change via [adjustTick].
    LaunchedEffect(adjustTick) {
        if (adjust != null) {
            delay(1200)
            adjust = null
        }
    }

    // Auto-dismiss the double-tap seek ripple; the key includes tick so rapid
    // repeat taps keep it alive and accumulating (+10s, +20s, …).
    LaunchedEffect(seek?.tick) {
        if (seek != null) {
            delay(700)
            seek = null
        }
    }

    fun applyBrightness(target: Float) {
        val clamped = target.coerceIn(0.02f, 1f)
        brightness = clamped
        activity?.window?.let { w ->
            w.attributes = w.attributes.apply { screenBrightness = clamped }
        }
        adjust = GestureKind.BRIGHTNESS
        adjustTick++
    }

    fun applyVolume(target: Float) {
        val clamped = target.coerceIn(0f, 1f)
        volumeFraction = clamped
        audioManager.setStreamVolume(
            AudioManager.STREAM_MUSIC,
            (clamped * maxVolume).roundToInt(),
            0,
        )
        adjust = GestureKind.VOLUME
        adjustTick++
    }

    var controlsVisible by remember { mutableStateOf(true) }
    var locked by remember { mutableStateOf(false) }
    // Aspect fit → zoom (crop) → stretch, cycled by the ⛶ control.
    var resizeModeIndex by remember { mutableStateOf(0) }
    var showSubtitleSheet by remember { mutableStateOf(false) }
    var showSettingsSheet by remember { mutableStateOf(false) }
    var showAudioSheet by remember { mutableStateOf(false) }
    var showEpisodesSheet by remember { mutableStateOf(false) }
    var showReportSheet by remember { mutableStateOf(false) }
    // Viewer-chosen subtitle typeface + size, restored from the last session and
    // re-applied to the SubtitleView whenever it changes.
    var subtitleAppearance by remember { mutableStateOf(loadSubtitleAppearance(context)) }

    // Any touch restarts the hide countdown, and nothing hides while a finger is
    // still down (mid-scrub, mid-press) — the controls used to vanish in the middle
    // of using them, 3.5s after they first appeared.
    var interactionTick by remember { mutableIntStateOf(0) }
    var touching by remember { mutableStateOf(false) }

    // Auto-hide controls after inactivity while playing.
    LaunchedEffect(controlsVisible, state.isPlaying, interactionTick, touching) {
        if (controlsVisible && state.isPlaying && !touching) {
            delay(3500)
            controlsVisible = false
        }
    }

    BackHandler(onBack = onBack)

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black)
            // Watch every touch on its way down (Initial pass, never consumed) just
            // to keep the controls awake; the gestures themselves live on their own
            // layer below the controls.
            .pointerInput(Unit) {
                awaitPointerEventScope {
                    while (true) {
                        val event = awaitPointerEvent(PointerEventPass.Initial)
                        // Only finger down/up — moves would recompose the whole
                        // screen every frame of a drag for no gain.
                        if (event.type == PointerEventType.Press || event.type == PointerEventType.Release) {
                            touching = event.changes.any { it.pressed }
                            interactionTick++
                        }
                    }
                }
            },
    ) {
        AndroidView(
            modifier = Modifier.fillMaxSize(),
            factory = { ctx ->
                PlayerView(ctx).apply {
                    useController = false
                    player = viewModel.player
                    setShowBuffering(PlayerView.SHOW_BUFFERING_NEVER)
                    resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
                }
            },
            // Re-apply the viewer's font/size and the chosen aspect mode on change.
            update = { view ->
                view.subtitleView?.applyAppearance(context, subtitleAppearance)
                view.resizeMode = when (resizeModeIndex) {
                    1 -> AspectRatioFrameLayout.RESIZE_MODE_ZOOM
                    2 -> AspectRatioFrameLayout.RESIZE_MODE_FILL
                    else -> AspectRatioFrameLayout.RESIZE_MODE_FIT
                }
            },
        )

        // Screen gestures sit on their own layer *under* the controls, not on the
        // root Box: a sibling on top wins the hit test, so a button press can never
        // be stolen by the brightness/volume drag or delayed by double-tap detection.
        Box(
            modifier = Modifier
                .fillMaxSize()
                // Tap toggles controls; double-tap seeks ±10s. Disabled while locked so
                // stray touches can't disturb playback (only the unlock button responds).
                .pointerInput(locked) {
                    if (locked) {
                        detectTapGestures(onTap = { controlsVisible = !controlsVisible })
                        return@pointerInput
                    }
                    detectTapGestures(
                        onTap = { controlsVisible = !controlsVisible },
                        onDoubleTap = { offset ->
                            val forward = offset.x >= size.width / 2f
                            viewModel.seekBy(if (forward) 10_000 else -10_000)
                            // Accumulate when tapping the same side again in quick succession.
                            val prev = seek
                            val seconds = if (prev != null && prev.forward == forward) prev.seconds + 10 else 10
                            seek = SeekFeedback(forward, seconds, (prev?.tick ?: 0) + 1)
                            // Keep the ripple clean — don't pop the full controls open.
                            controlsVisible = false
                        },
                    )
                }
                // Vertical drag: left half = brightness, right half = volume.
                .pointerInput(locked) {
                    if (locked) return@pointerInput
                    var leftSide = false
                    detectVerticalDragGestures(
                        onDragStart = { offset -> leftSide = offset.x < size.width / 2f },
                        onVerticalDrag = { change, dragAmount ->
                            change.consume()
                            val h = size.height.coerceAtLeast(1)
                            // Drag up (negative dragAmount) increases the value.
                            val deltaFraction = -dragAmount / h
                            if (leftSide) applyBrightness(brightness + deltaFraction)
                            else applyVolume(volumeFraction + deltaFraction)
                        },
                    )
                },
        )

        if (state.isBuffering && state.error == null) {
            CircularProgressIndicator(
                color = Brand,
                modifier = Modifier.align(Alignment.Center).size(52.dp),
            )
        }

        // Status pill (top-center): subtitle import, or a codec/source auto-recovery
        // notice while the player swaps to a device-compatible mirror.
        SubtitleStatusPill(
            loading = state.subtitleLoading || state.recovering,
            notice = state.recoveryNotice ?: state.subtitleNotice,
            modifier = Modifier.align(Alignment.TopCenter),
        )

        // Brightness slider (left edge) — appears only while the viewer is changing
        // brightness (a left-side drag) and fades out on the shared deadline, so it
        // never clutters the frame or overlaps the rest of the controls.
        AnimatedVisibility(
            visible = adjust == GestureKind.BRIGHTNESS,
            enter = fadeIn(tween(120)),
            exit = fadeOut(tween(220)),
            modifier = Modifier.align(Alignment.CenterStart),
        ) {
            VerticalControlSlider(
                fraction = brightness,
                onFraction = { applyBrightness(it) },
                icon = Icons.Rounded.BrightnessHigh,
                fill = Color(0xFFFFD54F),
                modifier = Modifier.padding(start = 10.dp).fillMaxHeight(0.52f),
            )
        }
        // Volume slider (right edge) — shown for a right-side drag, same transience.
        AnimatedVisibility(
            visible = adjust == GestureKind.VOLUME,
            enter = fadeIn(tween(120)),
            exit = fadeOut(tween(220)),
            modifier = Modifier.align(Alignment.CenterEnd),
        ) {
            VerticalControlSlider(
                fraction = volumeFraction,
                onFraction = { applyVolume(it) },
                icon = Icons.Rounded.VolumeUp,
                fill = Brand,
                modifier = Modifier.padding(end = 10.dp).fillMaxHeight(0.52f),
            )
        }

        // Error overlay with retry.
        state.error?.let { message ->
            ErrorOverlay(
                message = message,
                onRetry = viewModel::retry,
                onBack = onBack,
                modifier = Modifier.align(Alignment.Center),
            )
        }

        // End-of-episode card: offer the next episode (auto-advance) or a replay.
        if (state.ended && state.error == null && state.nextEpisodeId != null) {
            NextEpisodeOverlay(
                label = state.nextEpisodeLabel ?: "قسمت بعد",
                onNext = { state.nextEpisodeId?.let { viewModel.selectEpisode(it) } },
                onReplay = viewModel::replay,
                modifier = Modifier.align(Alignment.Center),
            )
        }

        AnimatedVisibility(
            visible = controlsVisible && state.error == null && !locked,
            enter = fadeIn(),
            exit = fadeOut(),
            modifier = Modifier.fillMaxSize(),
        ) {
            PlayerControls(
                state = state,
                onBack = onBack,
                onPlayPause = viewModel::playPause,
                onSeek = viewModel::seekTo,
                onSettings = { showSettingsSheet = true },
                onSubtitles = { showSubtitleSheet = true },
                onAudio = { showAudioSheet = true },
                hasEpisodes = state.seasons.isNotEmpty(),
                onEpisodes = { showEpisodesSheet = true },
                onReport = {
                    viewModel.resetContentReport()
                    showReportSheet = true
                },
                resizeModeIndex = resizeModeIndex,
                onCycleResize = { resizeModeIndex = (resizeModeIndex + 1) % 3 },
                onLock = {
                    locked = true
                    controlsVisible = false
                },
                onCycleSpeed = { viewModel.setSpeed(nextSpeed(state.playbackSpeed)) },
                appearance = subtitleAppearance,
                onAppearanceChange = { updated ->
                    subtitleAppearance = updated
                    saveSubtitleAppearance(context, updated)
                },
            )
        }

        // Locked: everything is inert except a single unlock affordance that appears
        // briefly on tap, so the viewer can't nudge playback by accident.
        AnimatedVisibility(
            visible = locked && controlsVisible && state.error == null,
            enter = fadeIn(),
            exit = fadeOut(),
            modifier = Modifier.align(Alignment.CenterStart),
        ) {
            LockToggle(
                locked = true,
                onClick = {
                    locked = false
                    controlsVisible = true
                },
                modifier = Modifier.padding(24.dp),
            )
        }

        // Double-tap seek ripple (topmost, above controls) — YouTube-style flowing
        // chevrons with an accumulating counter on the tapped side.
        AnimatedVisibility(
            visible = seek != null,
            enter = fadeIn(tween(120)),
            exit = fadeOut(tween(260)),
            modifier = Modifier.fillMaxSize(),
        ) {
            seek?.let { SeekRipple(it) }
        }
    }

    if (showSettingsSheet) {
        ModalBottomSheet(
            onDismissRequest = { showSettingsSheet = false },
            containerColor = BgElevated,
        ) {
            SettingsSheet(
                state = state,
                onSpeed = { viewModel.setSpeed(it) },
                onQuality = { viewModel.selectQuality(it) },
                onSubtitleSync = { viewModel.nudgeSubtitleOffset(it) },
            )
        }
    }
    if (showSubtitleSheet) {
        ModalBottomSheet(onDismissRequest = { showSubtitleSheet = false }) {
            SubtitleSheet(
                subtitles = state.subtitles.map { it.label },
                activeIndex = state.activeSubtitleIndex,
                loading = state.subtitleLoading,
                onSelect = {
                    viewModel.selectSubtitleByUser(it)
                    showSubtitleSheet = false
                },
            )
        }
    }
    if (showAudioSheet) {
        ModalBottomSheet(
            onDismissRequest = { showAudioSheet = false },
            containerColor = BgElevated,
        ) {
            AudioSheet(
                tracks = state.audioTracks,
                activeIndex = state.activeAudioIndex,
                onSelect = {
                    viewModel.selectAudioTrack(it)
                    showAudioSheet = false
                },
            )
        }
    }
    if (showEpisodesSheet) {
        ModalBottomSheet(
            onDismissRequest = { showEpisodesSheet = false },
            containerColor = BgElevated,
        ) {
            EpisodesSheet(
                seasons = state.seasons,
                currentEpisodeId = state.currentEpisodeId,
                onSelect = {
                    viewModel.selectEpisode(it)
                    showEpisodesSheet = false
                },
            )
        }
    }
    if (showReportSheet) {
        PlayerReportSheet(
            isSeries = state.isSeries,
            submitting = state.reportSubmitting,
            done = state.reportDone,
            message = state.reportMessage,
            onSubmit = { problemType, detail ->
                viewModel.submitContentReport(problemType, detail)
            },
            onDismiss = {
                showReportSheet = false
                viewModel.resetContentReport()
            },
        )
    }
}

@Composable
private fun SubtitleStatusPill(loading: Boolean, notice: String?, modifier: Modifier = Modifier) {
    val text = when {
        loading -> notice ?: "در حال یافتن زیرنویس…"
        notice != null -> notice
        else -> null
    } ?: return
    // The user can close any in-player notification. Reset the dismissal
    // whenever the message text changes so a fresh notice always shows.
    var dismissed by remember(text) { mutableStateOf(false) }
    if (dismissed) return
    val topInset = WindowInsets.safeDrawing.asPaddingValues().calculateTopPadding()
    Row(
        modifier = modifier
            .padding(top = topInset + 12.dp)
            .background(Color(0xCC101012), CircleShape)
            .padding(start = 16.dp, end = 6.dp, top = 6.dp, bottom = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        if (loading) {
            CircularProgressIndicator(color = Brand, strokeWidth = 2.dp, modifier = Modifier.size(16.dp))
        }
        Text(text, color = Color.White, style = MaterialTheme.typography.labelLarge)
        IconButton(
            onClick = { dismissed = true },
            modifier = Modifier.size(28.dp),
        ) {
            Icon(
                imageVector = Icons.Rounded.Close,
                contentDescription = "بستن",
                tint = Color.White,
                modifier = Modifier.size(18.dp),
            )
        }
    }
}

@Composable
private fun ErrorOverlay(
    message: String,
    onRetry: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .padding(24.dp)
            .background(Color(0xEE151517), RoundedCornerShape(20.dp))
            .padding(horizontal = 28.dp, vertical = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(message, color = Color.White, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Button(
                onClick = onRetry,
                colors = ButtonDefaults.buttonColors(containerColor = Brand, contentColor = Color.Black),
            ) {
                Icon(Icons.Rounded.Refresh, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.size(8.dp))
                Text("تلاش دوباره", fontWeight = FontWeight.Bold)
            }
            Button(
                onClick = onBack,
                colors = ButtonDefaults.buttonColors(containerColor = Color(0x33FFFFFF), contentColor = Color.White),
            ) {
                Text("بازگشت")
            }
        }
    }
}

/**
 * The full control overlay, laid out to match the reference design exactly:
 *   • top bar — exit (خروج) on the left, تنظیمات gear centred, subtitle/audio (and
 *     episodes) chips on the right;
 *   • a single central play/pause button;
 *   • a bottom-left cluster (lock / aspect / speed) and a bottom-right subtitle
 *     appearance cluster (A↑ A↓ A⁻ A⁺ Aa 🖌);
 *   • a full-width seek bar with elapsed − total times.
 *
 * The whole overlay is forced LTR so every manual alignment below is *visual*
 * (left means left, right means right) and lands where the mock-up shows it,
 * regardless of the app's ambient RTL direction. Persian glyphs inside each
 * [Text] still shape themselves correctly.
 */
@Composable
private fun PlayerControls(
    state: PlayerUiState,
    onBack: () -> Unit,
    onPlayPause: () -> Unit,
    onSeek: (Long) -> Unit,
    onSettings: () -> Unit,
    onSubtitles: () -> Unit,
    onAudio: () -> Unit,
    hasEpisodes: Boolean,
    onEpisodes: () -> Unit,
    onReport: () -> Unit,
    resizeModeIndex: Int,
    onCycleResize: () -> Unit,
    onLock: () -> Unit,
    onCycleSpeed: () -> Unit,
    appearance: SubtitleAppearance,
    onAppearanceChange: (SubtitleAppearance) -> Unit,
) {
    val insets = WindowInsets.safeDrawing.asPaddingValues()
    androidx.compose.runtime.CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                // Lighter scrim: just enough at the top and bottom edges to keep the
                // controls legible, leaving the picture clear through the middle.
                .background(
                    Brush.verticalGradient(
                        0f to Color(0x99000000),
                        0.28f to Color.Transparent,
                        0.72f to Color.Transparent,
                        1f to Color(0x99000000),
                    ),
                ),
        ) {
            // --- Top bar: exit (left) · settings (centre) · subtitle/audio (right) ---
            val topPad = Modifier
                .fillMaxWidth()
                .padding(top = insets.calculateTopPadding())
                .padding(horizontal = 12.dp, vertical = 8.dp)
            Box(modifier = topPad.align(Alignment.TopCenter)) {
                // Exit — left edge.
                TopChip(
                    icon = Icons.Rounded.Close,
                    text = "خروج",
                    onClick = onBack,
                    modifier = Modifier.align(Alignment.CenterStart),
                )
                // Settings + report — centred pair.
                Row(
                    modifier = Modifier.align(Alignment.Center),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    TopChip(
                        icon = Icons.Rounded.Settings,
                        text = "تنظیمات",
                        onClick = onSettings,
                    )
                    TopChip(
                        icon = Icons.Rounded.Flag,
                        text = "گزارش خطا",
                        onClick = onReport,
                        tint = AccentYellow,
                    )
                }
                // Subtitle / audio / episodes — right edge.
                Row(
                    modifier = Modifier.align(Alignment.CenterEnd),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    if (hasEpisodes) {
                        TopChip(
                            icon = Icons.AutoMirrored.Rounded.PlaylistPlay,
                            text = "قسمت‌ها",
                            onClick = onEpisodes,
                        )
                    }
                    TopChip(
                        icon = Icons.Rounded.ClosedCaption,
                        text = "${state.subtitles.size} زیرنویس",
                        onClick = onSubtitles,
                        tint = if (state.activeSubtitleIndex >= 0) Brand else Color.White,
                    )
                    TopChip(
                        icon = Icons.Rounded.GraphicEq,
                        text = "${state.audioTracks.size.coerceAtLeast(1)} صدا",
                        onClick = onAudio,
                    )
                }
            }

            // --- Centre: single play / pause ---
            CircleControl(
                onClick = onPlayPause,
                size = 82.dp,
                background = Color(0x33FFFFFF),
                modifier = Modifier.align(Alignment.Center),
            ) {
                Icon(
                    imageVector = if (state.playWhenReady && !state.ended) Icons.Rounded.Pause else Icons.Rounded.PlayArrow,
                    contentDescription = "پخش/توقف",
                    tint = Color.White,
                    modifier = Modifier.size(50.dp),
                )
            }

            // --- Bottom: clusters + seek bar ---
            Column(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .padding(bottom = insets.calculateBottomPadding())
                    .padding(horizontal = 16.dp, vertical = 10.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    // Bottom-left cluster: lock · aspect · speed.
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        LockToggle(locked = false, onClick = onLock)
                        PlayerGlyphButton(
                            icon = Icons.Rounded.AspectRatio,
                            label = "نسبت تصویر",
                            onClick = onCycleResize,
                            tint = if (resizeModeIndex == 0) Color.White else Brand,
                        )
                        Box(
                            modifier = Modifier
                                .clip(CircleShape)
                                .clickable(onClick = onCycleSpeed)
                                .padding(horizontal = 8.dp, vertical = 6.dp),
                            contentAlignment = Alignment.Center,
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                Icon(
                                    Icons.Rounded.FastForward,
                                    contentDescription = "سرعت پخش",
                                    tint = if (state.playbackSpeed == 1f) Color.White else Brand,
                                    modifier = Modifier.size(24.dp),
                                )
                                if (state.playbackSpeed != 1f) {
                                    Text(
                                        "${formatSpeed(state.playbackSpeed)}×",
                                        color = Brand,
                                        style = MaterialTheme.typography.labelMedium,
                                        fontWeight = FontWeight.Bold,
                                    )
                                }
                            }
                        }
                    }
                    Spacer(Modifier.weight(1f))
                    // Bottom-right cluster: subtitle appearance controls.
                    SubtitleAppearanceCluster(
                        appearance = appearance,
                        onAppearanceChange = onAppearanceChange,
                    )
                }

                // Timeline, left-to-right like every player (elapsed left, total right).
                SeekTimeline(
                    positionMs = state.positionMs,
                    durationMs = state.durationMs,
                    bufferedMs = state.bufferedMs,
                    onSeek = onSeek,
                )
            }
        }
    }
}

/**
 * The player timeline: a thin track (played · buffered · rest) with a small
 * thumb, elapsed time on the left and total on the right.
 *
 * The finger drives a local scrub position and the player seeks **once**, on
 * release. (The old Slider seeked on every drag frame: the stream re-buffered at
 * each step and the thumb snapped back to the stale position under the finger.)
 * A tap anywhere on the track jumps there. While scrubbing the track thickens,
 * the thumb grows, and a time bubble rides above it, so the target is readable
 * without lifting the finger. The touch area is far taller than the drawn line.
 */
@Composable
private fun SeekTimeline(
    positionMs: Long,
    durationMs: Long,
    bufferedMs: Long,
    onSeek: (Long) -> Unit,
) {
    val seekable = durationMs > 0
    var scrub by remember { mutableStateOf<Float?>(null) }
    val played = scrub ?: if (seekable) (positionMs.toFloat() / durationMs).coerceIn(0f, 1f) else 0f
    val buffered = if (seekable) (bufferedMs.toFloat() / durationMs).coerceIn(0f, 1f) else 0f
    val active = scrub != null
    val trackHeight by animateDpAsState(if (active) 6.dp else 4.dp, tween(120), label = "track")
    val thumbRadius by animateDpAsState(if (active) 9.dp else 6.dp, tween(120), label = "thumb")
    val shownMs = if (seekable) (played * durationMs).toLong() else positionMs
    val timeStyle = MaterialTheme.typography.labelMedium.copy(
        fontFeatureSettings = "tnum",
        fontWeight = FontWeight.Bold,
    )

    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(
            formatTime(shownMs),
            color = if (active) Brand else Color.White,
            style = timeStyle,
            modifier = Modifier.widthIn(min = 44.dp),
        )
        BoxWithConstraints(
            modifier = Modifier
                .weight(1f)
                .padding(horizontal = 10.dp)
                .height(36.dp)
                .pointerInput(seekable, durationMs) {
                    if (!seekable) return@pointerInput
                    awaitEachGesture {
                        val down = awaitFirstDown()
                        down.consume()
                        val width = size.width.toFloat().coerceAtLeast(1f)
                        scrub = (down.position.x / width).coerceIn(0f, 1f)
                        var released = false
                        while (true) {
                            val event = awaitPointerEvent()
                            val change = event.changes.firstOrNull { it.id == down.id } ?: break
                            if (!change.pressed) {
                                change.consume()
                                released = true
                                break
                            }
                            scrub = (change.position.x / width).coerceIn(0f, 1f)
                            change.consume()
                        }
                        val target = scrub
                        scrub = null
                        // A cancelled gesture (e.g. a system swipe) doesn't seek.
                        if (released && target != null) onSeek((target * durationMs).toLong())
                    }
                },
            contentAlignment = Alignment.CenterStart,
        ) {
            val trackWidth = maxWidth
            val playedColor = Brand
            Canvas(Modifier.fillMaxWidth().height(thumbRadius * 2)) {
                val h = trackHeight.toPx()
                val y = size.height / 2f
                val r = CornerRadius(h / 2f, h / 2f)
                val top = Offset(0f, y - h / 2f)
                drawRoundRect(Color(0x40FFFFFF), top, Size(size.width, h), r)
                drawRoundRect(Color(0x66FFFFFF), top, Size(size.width * buffered, h), r)
                drawRoundRect(playedColor, top, Size(size.width * played, h), r)
                drawCircle(Color.White, thumbRadius.toPx(), Offset(size.width * played, y))
            }
            if (active) {
                // Time bubble above the thumb, kept inside the track's width.
                val bubbleWidth = 64.dp
                val x = (trackWidth * played - bubbleWidth / 2)
                    .coerceIn(0.dp, (trackWidth - bubbleWidth).coerceAtLeast(0.dp))
                Box(
                    modifier = Modifier
                        .offset(x = x, y = (-30).dp)
                        .width(bubbleWidth)
                        .clip(RoundedCornerShape(8.dp))
                        .background(Color(0xE6000000))
                        .padding(vertical = 4.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(formatTime(shownMs), color = Color.White, style = timeStyle)
                }
            }
        }
        Text(
            formatTime(durationMs),
            color = Color.White.copy(alpha = 0.8f),
            style = timeStyle,
            textAlign = TextAlign.End,
            modifier = Modifier.widthIn(min = 44.dp),
        )
    }
}

/** A rounded pill (icon + short label) used across the player's top bar. */
@Composable
private fun TopChip(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    tint: Color = Color.White,
) {
    Row(
        modifier = modifier
            .clip(RoundedCornerShape(999.dp))
            .background(Color(0x40000000))
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Icon(icon, contentDescription = text, tint = tint, modifier = Modifier.size(18.dp))
        Text(text, color = tint, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold)
    }
}

/** A bare icon button used inside the bottom clusters. */
@Composable
private fun PlayerGlyphButton(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    onClick: () -> Unit,
    tint: Color = Color.White,
) {
    Box(
        modifier = Modifier
            .clip(CircleShape)
            .clickable(onClick = onClick)
            .padding(8.dp),
        contentAlignment = Alignment.Center,
    ) {
        Icon(icon, contentDescription = label, tint = tint, modifier = Modifier.size(24.dp))
    }
}

/**
 * A thin vertical track the viewer drags to set volume / brightness, with the icon
 * below and the live 0–100 value above. The fill grows from the bottom. Dragging
 * reads the absolute touch position so the value tracks the finger exactly; the
 * parent clamps the fraction into range.
 */
@Composable
private fun VerticalControlSlider(
    fraction: Float,
    onFraction: (Float) -> Unit,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    fill: Color,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.width(40.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(
            "${(fraction * 100).roundToInt()}",
            color = Color.White,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.Bold,
        )
        Box(
            modifier = Modifier
                .weight(1f)
                .width(6.dp)
                .clip(CircleShape)
                .background(Color(0x55FFFFFF))
                .pointerInput(Unit) {
                    detectVerticalDragGestures { change, _ ->
                        change.consume()
                        val h = size.height.coerceAtLeast(1)
                        onFraction(1f - change.position.y / h)
                    }
                },
            contentAlignment = Alignment.BottomCenter,
        ) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .fillMaxHeight(fraction.coerceIn(0f, 1f))
                    .clip(CircleShape)
                    .background(fill),
            )
        }
        Icon(icon, contentDescription = null, tint = Color.White, modifier = Modifier.size(22.dp))
    }
}

/** The lock / unlock affordance. Shown open in the bar, closed when locked. */
@Composable
private fun LockToggle(locked: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .clip(CircleShape)
            .background(if (locked) Color(0x66000000) else Color.Transparent)
            .clickable(onClick = onClick)
            .padding(if (locked) 12.dp else 8.dp),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            imageVector = if (locked) Icons.Rounded.Lock else Icons.Rounded.LockOpen,
            contentDescription = if (locked) "باز کردن قفل" else "قفل کردن",
            tint = Color.White,
            modifier = Modifier.size(24.dp),
        )
    }
}

/**
 * Bottom-right subtitle-appearance cluster (the design's «تنظیمات زیرنویس»):
 * A↑ / A↓ raise & lower the caption on screen, A⁻ / A⁺ shrink & grow it, Aa cycles
 * the typeface and 🖌 the colour. Every change is applied live and persisted.
 */
@Composable
private fun SubtitleAppearanceCluster(
    appearance: SubtitleAppearance,
    onAppearanceChange: (SubtitleAppearance) -> Unit,
) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // A↑ / A↓ — move the caption up / down.
        SubtitleGlyphButton("A↑") {
            onAppearanceChange(
                appearance.copy(bottomPaddingFraction = (appearance.bottomPaddingFraction + 0.03f).coerceIn(0.04f, 0.45f)),
            )
        }
        SubtitleGlyphButton("A↓") {
            onAppearanceChange(
                appearance.copy(bottomPaddingFraction = (appearance.bottomPaddingFraction - 0.03f).coerceIn(0.04f, 0.45f)),
            )
        }
        // A⁻ / A⁺ — smaller / larger.
        SubtitleGlyphButton("A⁻") { onAppearanceChange(appearance.copy(size = appearance.size.smaller())) }
        SubtitleGlyphButton("A⁺") { onAppearanceChange(appearance.copy(size = appearance.size.larger())) }
        // Aa — cycle typeface.
        SubtitleGlyphButton("Aa") { onAppearanceChange(appearance.copy(font = appearance.font.next())) }
        // 🖌 — cycle colour, tinted to the current choice so it doubles as a swatch.
        Box(
            modifier = Modifier
                .clip(CircleShape)
                .clickable { onAppearanceChange(appearance.copy(color = appearance.color.next())) }
                .padding(8.dp),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                Icons.Rounded.Brush,
                contentDescription = "رنگ زیرنویس",
                tint = Color(appearance.color.fg),
                modifier = Modifier.size(22.dp),
            )
        }
    }
}

/** A compact text-glyph button (e.g. "A↑") for the subtitle-appearance cluster. */
@Composable
private fun SubtitleGlyphButton(glyph: String, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .clip(CircleShape)
            .clickable(onClick = onClick)
            .padding(horizontal = 8.dp, vertical = 6.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(glyph, color = Color.White, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun CircleControl(
    onClick: () -> Unit,
    size: androidx.compose.ui.unit.Dp,
    background: Color = Color.Transparent,
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    Box(
        modifier = modifier
            .size(size)
            .background(background, CircleShape)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) { content() }
}

/**
 * The «تنظیمات» sheet reached from the top-bar gear: playback speed, quality
 * mirror, and — most importantly — the manual subtitle-sync nudger that dials out
 * any lead/lag ("جلو/عقب بودن زیرنویس") in ±0.5s steps, showing the live offset.
 */
@Composable
private fun SettingsSheet(
    state: PlayerUiState,
    onSpeed: (Float) -> Unit,
    onQuality: (String) -> Unit,
    onSubtitleSync: (Long) -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 20.dp)
            .padding(bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        Text("تنظیمات", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)

        // --- Subtitle sync ---
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("هماهنگی زیرنویس", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            Text(
                "اگر زیرنویس جلو یا عقب است، آن را دقیق تنظیم کنید.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                SyncStepButton("−۰٫۵ ثانیه") { onSubtitleSync(-500L) }
                Text(
                    text = formatOffset(state.subtitleOffsetMs),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = if (state.subtitleOffsetMs == 0L) MaterialTheme.colorScheme.onSurface else Brand,
                    modifier = Modifier.weight(1f),
                )
                SyncStepButton("+۰٫۵ ثانیه") { onSubtitleSync(500L) }
            }
        }

        // --- Playback speed ---
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("سرعت پخش", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(listOf(0.5f, 0.75f, 1f, 1.25f, 1.5f, 2f), key = { it }) { speed ->
                    SelectableChip(
                        label = if (speed == 1f) "عادی" else "${formatSpeed(speed)}×",
                        selected = speed == state.playbackSpeed,
                        onClick = { onSpeed(speed) },
                    )
                }
            }
        }

        // --- Quality mirror (only when there is a real choice) ---
        if (state.qualities.size > 1) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("کیفیت پخش", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(state.qualities, key = { it.url }) { quality ->
                        SelectableChip(
                            label = quality.label,
                            selected = quality.url == state.activeQualityUrl,
                            onClick = { onQuality(quality.url) },
                        )
                    }
                }
            }
        }
    }
}

/** A filled step button for the ±0.5s subtitle-sync nudger. */
@Composable
private fun SyncStepButton(label: String, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(12.dp))
            .background(NeutralSurface)
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurface)
    }
}

/** The embedded-audio («صدا») track picker. */
@Composable
private fun AudioSheet(
    tracks: List<PlayerAudioTrack>,
    activeIndex: Int,
    onSelect: (Int) -> Unit,
) {
    Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
        Text("صدا", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Spacer(Modifier.size(8.dp))
        if (tracks.isEmpty()) {
            Text(
                "این نسخه فقط یک صدا دارد.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(vertical = 12.dp),
            )
        }
        tracks.forEachIndexed { index, track ->
            SubtitleOption(track.label, activeIndex == index) { onSelect(index) }
        }
    }
}

/** Track-selection-only subtitle picker (appearance lives on the player overlay). */
@Composable
private fun SubtitleSheet(
    subtitles: List<String>,
    activeIndex: Int,
    loading: Boolean,
    onSelect: (Int) -> Unit,
) {
    Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("زیرنویس", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            if (loading) CircularProgressIndicator(color = Brand, strokeWidth = 2.dp, modifier = Modifier.size(16.dp))
        }
        Spacer(Modifier.size(8.dp))
        SubtitleOption("خاموش", activeIndex == -1) { onSelect(-1) }
        subtitles.forEachIndexed { index, label ->
            SubtitleOption(label, activeIndex == index) { onSelect(index) }
        }
        if (subtitles.isEmpty() && loading) {
            LinearProgressIndicator(
                color = Brand,
                trackColor = Color(0x33FFFFFF),
                modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
            )
            Text(
                "در حال دریافت زیرنویس فارسی از سرور…",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(vertical = 12.dp),
            )
        }
    }
}

/** A pill toggle used for the subtitle font/size choices. */
@Composable
private fun SelectableChip(label: String, selected: Boolean, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(if (selected) PlayAccentSoft else NeutralSurface)
            .then(if (selected) Modifier.border(1.dp, PlayAccent, RoundedCornerShape(999.dp)) else Modifier)
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 9.dp),
    ) {
        Text(
            label,
            style = MaterialTheme.typography.labelLarge,
            color = if (selected) PlayAccent else MaterialTheme.colorScheme.onSurface,
            fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
        )
    }
}

@Composable
private fun SubtitleOption(label: String, active: Boolean, onClick: () -> Unit) {
    Text(
        text = label,
        style = MaterialTheme.typography.bodyLarge,
        color = if (active) Brand else MaterialTheme.colorScheme.onSurface,
        fontWeight = if (active) FontWeight.Bold else FontWeight.Normal,
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(vertical = 12.dp),
    )
}

/**
 * In-player episode switcher: season pills across the top, a scrollable episode
 * list below. The episode on screen is marked "در حال پخش" in the play accent so
 * the viewer always sees where they are; tapping any other episode swaps to it.
 */
@Composable
private fun EpisodesSheet(
    seasons: List<PlayerSeason>,
    currentEpisodeId: Int,
    onSelect: (Int) -> Unit,
) {
    val initialSeason = remember(seasons, currentEpisodeId) {
        seasons.indexOfFirst { s -> s.episodes.any { it.id == currentEpisodeId } }.coerceAtLeast(0)
    }
    var selectedSeason by remember(seasons) { mutableStateOf(initialSeason) }
    val season = seasons.getOrNull(selectedSeason) ?: seasons.firstOrNull() ?: return

    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 20.dp)
            .padding(bottom = 20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text(
            "قسمت‌ها",
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onSurface,
        )
        if (seasons.size > 1) {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(seasons.indices.toList(), key = { it }) { index ->
                    val selected = index == selectedSeason
                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(999.dp))
                            .background(if (selected) PlayAccentSoft else NeutralSurface)
                            .clickable { selectedSeason = index }
                            .padding(horizontal = 16.dp, vertical = 8.dp),
                    ) {
                        Text(
                            text = seasons[index].title,
                            style = MaterialTheme.typography.labelMedium,
                            color = if (selected) PlayAccent else MaterialTheme.colorScheme.onSurface,
                            fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
                        )
                    }
                }
            }
        }
        LazyColumn(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(max = 320.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(season.episodes, key = { it.id }) { ep ->
                EpisodeSheetRow(
                    episode = ep,
                    isCurrent = ep.id == currentEpisodeId,
                    onClick = { if (ep.playable) onSelect(ep.id) },
                )
            }
        }
    }
}

@Composable
private fun EpisodeSheetRow(
    episode: PlayerEpisode,
    isCurrent: Boolean,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(if (isCurrent) PlayAccentSoft else NeutralSurface)
            .then(
                if (isCurrent) Modifier.border(1.dp, PlayAccent, RoundedCornerShape(14.dp)) else Modifier,
            )
            .clickable(enabled = episode.playable, onClick = onClick)
            .padding(8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(
            modifier = Modifier
                .width(104.dp)
                .aspectRatio(16f / 9f)
                .clip(RoundedCornerShape(8.dp)),
        ) {
            NetworkImage(
                url = episode.poster,
                contentDescription = episode.title,
                fallbackText = "قسمت ${episode.episodeNumber}",
                modifier = Modifier.fillMaxSize(),
            )
            if (isCurrent) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(Color(0x66000000)),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        Icons.Rounded.PlayArrow,
                        contentDescription = null,
                        tint = PlayAccent,
                        modifier = Modifier.size(26.dp),
                    )
                }
            }
        }
        Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(
                text = "${episode.episodeNumber}. ${episode.title}",
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.SemiBold,
                color = if (episode.playable) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            when {
                isCurrent -> Text(
                    "در حال پخش",
                    style = MaterialTheme.typography.labelSmall,
                    color = PlayAccent,
                    fontWeight = FontWeight.Bold,
                )
                !episode.playable -> Text(
                    "لینک پخش موجود نیست",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

/** Netflix-style end card: jump straight to the next episode or replay this one. */
@Composable
private fun NextEpisodeOverlay(
    label: String,
    onNext: () -> Unit,
    onReplay: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .padding(24.dp)
            .background(Color(0xEE151517), RoundedCornerShape(20.dp))
            .padding(horizontal = 28.dp, vertical = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("این قسمت تمام شد", color = Color.White, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        Text("بعدی: $label", color = TextSecondary, style = MaterialTheme.typography.bodyMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Button(
                onClick = onNext,
                colors = ButtonDefaults.buttonColors(containerColor = PlayAccent, contentColor = OnPlayAccent),
            ) {
                Icon(Icons.Rounded.SkipNext, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.size(8.dp))
                Text("قسمت بعد", fontWeight = FontWeight.Bold)
            }
            Button(
                onClick = onReplay,
                colors = ButtonDefaults.buttonColors(containerColor = Color(0x33FFFFFF), contentColor = Color.White),
            ) {
                Icon(Icons.Rounded.Replay, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.size(8.dp))
                Text("تکرار")
            }
        }
    }
}

/**
 * YouTube-style double-tap seek feedback: a soft side-vignette with three chevrons
 * that flow toward the seek direction and an accumulating "N ثانیه" counter.
 */
@Composable
private fun SeekRipple(feedback: SeekFeedback) {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = if (feedback.forward) Alignment.CenterEnd else Alignment.CenterStart,
    ) {
        Column(
            modifier = Modifier
                .fillMaxHeight()
                .fillMaxWidth(0.42f)
                .background(
                    Brush.horizontalGradient(
                        colors = if (feedback.forward) {
                            listOf(Color.Transparent, Color(0x2E000000), Color(0x66000000))
                        } else {
                            listOf(Color(0x66000000), Color(0x2E000000), Color.Transparent)
                        },
                    ),
                ),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            val transition = rememberInfiniteTransition(label = "seekChevrons")
            val phase by transition.animateFloat(
                initialValue = 0f,
                targetValue = 3f,
                animationSpec = infiniteRepeatable(tween(820), RepeatMode.Restart),
                label = "chevronPhase",
            )
            Row(horizontalArrangement = Arrangement.spacedBy((-8).dp)) {
                repeat(3) { i ->
                    // Cascade the highlight in the seek direction.
                    val order = if (feedback.forward) i else (2 - i)
                    val active = order <= phase
                    Icon(
                        imageVector = Icons.Rounded.PlayArrow,
                        contentDescription = null,
                        tint = Color.White.copy(alpha = if (active) 1f else 0.3f),
                        modifier = Modifier
                            .size(26.dp)
                            .graphicsLayer { if (!feedback.forward) scaleX = -1f },
                    )
                }
            }
            Spacer(Modifier.size(6.dp))
            Text(
                "${feedback.seconds} ثانیه",
                color = Color.White,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

private fun formatTime(ms: Long): String {
    if (ms <= 0) return "0:00"
    val totalSec = ms / 1000
    val h = totalSec / 3600
    val m = (totalSec % 3600) / 60
    val s = totalSec % 60
    return if (h > 0) "%d:%02d:%02d".format(h, m, s) else "%d:%02d".format(m, s)
}

/** Ordered speed ring cycled by the bottom-left ►► control. */
private val SPEED_STEPS = listOf(0.75f, 1f, 1.25f, 1.5f, 2f)

/** Next speed in the ring after [cur] (wraps); defaults to 1.25× off an odd value. */
private fun nextSpeed(cur: Float): Float {
    val i = SPEED_STEPS.indexOfFirst { kotlin.math.abs(it - cur) < 0.01f }
    return if (i < 0) 1.25f else SPEED_STEPS[(i + 1) % SPEED_STEPS.size]
}

/** Trim a speed to a clean label: 1, 1.25, 1.5, 2 (no trailing zeros). */
private fun formatSpeed(speed: Float): String =
    if (speed % 1f == 0f) speed.toInt().toString() else speed.toString().trimEnd('0').trimEnd('.')

/** Human subtitle-sync offset, e.g. "همگام", "+۱٫۵ ثانیه", "−۰٫۵ ثانیه". */
private fun formatOffset(offsetMs: Long): String {
    if (offsetMs == 0L) return "همگام"
    val sign = if (offsetMs > 0) "+" else "−"
    val secs = kotlin.math.abs(offsetMs) / 1000.0
    val label = if (secs % 1.0 == 0.0) secs.toInt().toString() else secs.toString().trimEnd('0').trimEnd('.')
    return "$sign$label ثانیه"
}
