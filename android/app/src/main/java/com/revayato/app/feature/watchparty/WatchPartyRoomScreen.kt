package com.revayato.app.feature.watchparty

import android.app.Activity
import android.content.Context
import android.content.pm.ActivityInfo
import android.media.AudioManager
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.systemBars
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.automirrored.rounded.Send
import androidx.compose.material.icons.automirrored.rounded.VolumeUp
import androidx.compose.material.icons.rounded.Brightness6
import androidx.compose.material.icons.rounded.ChatBubbleOutline
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.ClosedCaption
import androidx.compose.material.icons.rounded.ContentCopy
import androidx.compose.material.icons.rounded.Forward10
import androidx.compose.material.icons.rounded.Fullscreen
import androidx.compose.material.icons.rounded.FullscreenExit
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.Mood
import androidx.compose.material.icons.rounded.Pause
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Replay10
import androidx.compose.material.icons.rounded.Speed
import androidx.compose.material.icons.rounded.Sync
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.BgSurface
import com.revayato.app.core.theme.BrandGreen
import com.revayato.app.core.theme.BrandMint
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.data.model.ChatMessageDto
import com.revayato.app.data.model.RoomMemberDto
import com.revayato.app.feature.player.SubtitleAppearance
import com.revayato.app.feature.player.SubtitleFont
import com.revayato.app.feature.player.SubtitleSize
import com.revayato.app.feature.player.applyAppearance
import com.revayato.app.feature.player.loadSubtitleAppearance
import com.revayato.app.feature.player.saveSubtitleAppearance
import com.revayato.app.ui.components.ErrorState
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.SharedFlow
import kotlin.math.abs
import kotlin.math.roundToInt

// Chat surfaces drawn over the black video need their own opaque-ish palette so
// bubbles stay legible whatever frame is behind them.
private val ChatOverlayBg = Color(0xF2121316)
private val ChatBubbleOverlay = Color(0x24FFFFFF)

// The reaction palette MUST stay in lock-step with the backend consumer's
// ALLOWED_REACTIONS allowlist — anything outside it is dropped server-side.
private val ReactionEmojis = listOf("❤️", "😂", "😮", "😢", "👏", "🔥", "🎉", "👍")

private val PlaybackSpeeds = listOf(0.5f, 0.75f, 1f, 1.25f, 1.5f, 2f)

/** Which vertical-drag gesture is active, plus its 0..1 level for the bubble. */
private data class GestureFeedback(val brightness: Boolean, val level: Float)

@androidx.annotation.OptIn(androidx.media3.common.util.UnstableApi::class)
@Composable
fun WatchPartyRoomScreen(
    code: String,
    onBack: () -> Unit,
    onOpenPlayer: (contentType: String, id: Int, slug: String, title: String, url: String, positionMs: Long, episodeId: Int, subtitlesEncoded: String, qualitiesEncoded: String) -> Unit = { _, _, _, _, _, _, _, _, _ -> },
    viewModel: WatchPartyRoomViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    LaunchedEffect(code) { viewModel.start(code) }

    val leave = {
        viewModel.leave()
        onBack()
    }

    // --- Layout / chat state shared by both portrait and fullscreen modes ---
    var fullscreen by remember { mutableStateOf(false) }
    var chatOpen by remember { mutableStateOf(false) }
    var controlsVisible by remember { mutableStateOf(true) }
    var lastSeenCount by remember { mutableIntStateOf(0) }
    var localNotice by remember { mutableStateOf<String?>(null) }

    // Bottom-sheet toggles, hoisted so both modes summon the same sheets.
    var speedSheet by remember { mutableStateOf(false) }
    var subtitleSheet by remember { mutableStateOf(false) }

    val context = LocalContext.current
    var subtitleAppearance by remember { mutableStateOf(loadSubtitleAppearance(context)) }

    // Keep the display awake for the whole session.
    val view = LocalView.current
    DisposableEffect(Unit) {
        view.keepScreenOn = true
        onDispose { view.keepScreenOn = false }
    }

    // Enter/exit immersive landscape as fullscreen toggles; always restore on leave.
    val activity = context as? Activity
    DisposableEffect(fullscreen) {
        val window = activity?.window
        val controller = window?.let { WindowInsetsControllerCompat(it, view) }
        if (fullscreen) {
            activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
            controller?.apply {
                systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                hide(WindowInsetsCompat.Type.systemBars())
            }
        } else {
            activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_USER
            controller?.show(WindowInsetsCompat.Type.systemBars())
        }
        onDispose {
            controller?.show(WindowInsetsCompat.Type.systemBars())
            activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
            // Never leave the screen dimmed/brightened from a drag gesture.
            activity?.window?.let { w ->
                val lp = w.attributes
                lp.screenBrightness = android.view.WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE
                w.attributes = lp
            }
        }
    }

    // Unread badge: count messages that arrive while the chat isn't visible. In
    // portrait the chat is always on screen; in fullscreen only while the panel is open.
    LaunchedEffect(state.messages.size, chatOpen, fullscreen) {
        if (!fullscreen || chatOpen) lastSeenCount = state.messages.size
    }
    val unread = (state.messages.size - lastSeenCount).coerceAtLeast(0)

    // Auto-hide the fullscreen controls while playing (chat panel stays independent).
    LaunchedEffect(controlsVisible, state.playing, fullscreen) {
        if (fullscreen && controlsVisible && state.playing) {
            delay(3800)
            controlsVisible = false
        }
    }

    // Transient notice pill (copy confirmation + playback/socket toasts).
    val notice = state.toast ?: localNotice
    LaunchedEffect(notice) {
        if (notice != null) {
            delay(2600)
            if (state.toast != null) viewModel.consumeToast() else localNotice = null
        }
    }

    // Back priority: close sheet → close chat → exit fullscreen → leave room.
    BackHandler {
        when {
            speedSheet -> speedSheet = false
            subtitleSheet -> subtitleSheet = false
            chatOpen -> chatOpen = false
            fullscreen -> fullscreen = false
            else -> leave()
        }
    }

    val clipboard = LocalClipboardManager.current
    val copyInvite = {
        state.room?.inviteCode?.takeIf { it.isNotBlank() }?.let {
            clipboard.setText(AnnotatedString(it))
            localNotice = "کد دعوت کپی شد"
        }
        Unit
    }

    if (state.error != null && !state.connected) {
        Column(Modifier.fillMaxSize().background(BgSurface)) {
            RoomTopBar(
                title = state.content?.title ?: "تماشای گروهی",
                inviteCode = state.room?.inviteCode,
                onBack = leave,
                onCopyInvite = copyInvite,
                onlineCount = 0,
                latencyMs = null,
            )
            ErrorState(message = state.error!!, modifier = Modifier.fillMaxSize())
        }
        return
    }

    Box(Modifier.fillMaxSize().background(if (fullscreen) Color.Black else BgSurface)) {
        if (fullscreen) {
            FullscreenBody(
                state = state,
                player = viewModel.player,
                subtitleAppearance = subtitleAppearance,
                reactions = viewModel.reactions,
                controlsVisible = controlsVisible,
                chatOpen = chatOpen,
                unread = unread,
                onToggleControls = { controlsVisible = !controlsVisible },
                onExitFullscreen = { fullscreen = false },
                onToggleChat = { chatOpen = !chatOpen },
                onCloseChat = { chatOpen = false },
                onPlayPause = viewModel::togglePlay,
                onSeek = viewModel::seekTo,
                onRewind = { viewModel.seekBy(-10_000) },
                onForward = { viewModel.seekBy(10_000) },
                onOpenSpeed = { speedSheet = true },
                onOpenSubtitles = { subtitleSheet = true },
                onResync = viewModel::resyncToHost,
                onReact = viewModel::sendReaction,
                onRetry = viewModel::retryPlayback,
                draft = state.chatDraft,
                onDraftChange = viewModel::onChatDraftChange,
                onSend = viewModel::sendChat,
            )
        } else {
            PortraitBody(
                state = state,
                player = viewModel.player,
                subtitleAppearance = subtitleAppearance,
                reactions = viewModel.reactions,
                onBack = leave,
                onCopyInvite = copyInvite,
                onEnterFullscreen = {
                    controlsVisible = true
                    fullscreen = true
                },
                onPlayPause = viewModel::togglePlay,
                onSeek = viewModel::seekTo,
                onOpenSpeed = { speedSheet = true },
                onOpenSubtitles = { subtitleSheet = true },
                onResync = viewModel::resyncToHost,
                onReact = viewModel::sendReaction,
                onRetry = viewModel::retryPlayback,
                onDraftChange = viewModel::onChatDraftChange,
                onSend = viewModel::sendChat,
            )
        }

        // Notice pill (bottom-center), above everything in either mode.
        AnimatedVisibility(
            visible = notice != null,
            enter = fadeIn(tween(150)),
            exit = fadeOut(tween(250)),
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .windowInsetsPadding(WindowInsets.systemBars)
                .padding(bottom = 20.dp),
        ) {
            Text(
                notice.orEmpty(),
                color = Color.White,
                style = MaterialTheme.typography.labelLarge,
                modifier = Modifier
                    .background(Color(0xE6101012), CircleShape)
                    .padding(horizontal = 18.dp, vertical = 10.dp),
            )
        }
    }

    if (speedSheet) {
        SpeedSheet(
            current = state.playbackSpeed,
            onPick = { viewModel.setSpeed(it); speedSheet = false },
            onDismiss = { speedSheet = false },
        )
    }
    if (subtitleSheet) {
        SubtitleSheet(
            subtitles = state.subtitles,
            activeIndex = state.activeSubtitleIndex,
            appearance = subtitleAppearance,
            onSelectTrack = viewModel::selectSubtitle,
            onAppearanceChange = {
                subtitleAppearance = it
                saveSubtitleAppearance(context, it)
            },
            onDismiss = { subtitleSheet = false },
        )
    }
}

/* ============================= Shared player surface ============================= */
@androidx.annotation.OptIn(androidx.media3.common.util.UnstableApi::class)
@Composable
private fun PartyPlayerSurface(
    player: androidx.media3.exoplayer.ExoPlayer,
    appearance: SubtitleAppearance,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    AndroidView(
        factory = { ctx ->
            PlayerView(ctx).apply {
                useController = false
                this.player = player
                setShowBuffering(PlayerView.SHOW_BUFFERING_NEVER)
                resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
                subtitleView?.applyAppearance(ctx, appearance)
            }
        },
        // Re-apply the viewer's subtitle look whenever it changes.
        update = { it.subtitleView?.applyAppearance(context, appearance) },
        // Detach the shared player when this surface leaves composition (e.g. on a
        // fullscreen toggle) so the video output moves cleanly to the new surface.
        onRelease = { it.player = null },
        modifier = modifier,
    )
}

/* ================================= PORTRAIT ================================= */
@Composable
private fun PortraitBody(
    state: RoomUiState,
    player: androidx.media3.exoplayer.ExoPlayer,
    subtitleAppearance: SubtitleAppearance,
    reactions: SharedFlow<ReactionBurst>,
    onBack: () -> Unit,
    onCopyInvite: () -> Unit,
    onEnterFullscreen: () -> Unit,
    onPlayPause: () -> Unit,
    onSeek: (Long) -> Unit,
    onOpenSpeed: () -> Unit,
    onOpenSubtitles: () -> Unit,
    onResync: () -> Unit,
    onReact: (String) -> Unit,
    onRetry: () -> Unit,
    onDraftChange: (String) -> Unit,
    onSend: () -> Unit,
) {
    Column(Modifier.fillMaxSize()) {
        RoomTopBar(
            title = state.content?.title ?: "تماشای گروهی",
            inviteCode = state.room?.inviteCode,
            onBack = onBack,
            onCopyInvite = onCopyInvite,
            onlineCount = state.members.count { it.isOnline },
            latencyMs = state.latencyMs,
            modifier = Modifier.statusBarsPadding(),
        )

        // ---- Video with overlaid actions + floating reactions ----
        Box(
            Modifier
                .fillMaxWidth()
                .aspectRatio(16f / 9f)
                .background(Color.Black),
            contentAlignment = Alignment.Center,
        ) {
            PartyPlayerSurface(player, subtitleAppearance, Modifier.fillMaxSize())
            ReactionOverlay(reactions, Modifier.fillMaxSize())

            if (state.buffering || state.loading) {
                CircularProgressIndicator(color = BrandMint, strokeWidth = 2.dp)
            }
            if (state.playerError != null) {
                PlayerErrorOverlay(message = state.playerError, onRetry = onRetry)
            }

            // Top-right quick actions: subtitle + (host) speed.
            Row(
                Modifier.align(Alignment.TopEnd).padding(6.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                if (state.subtitles.isNotEmpty()) {
                    OverlayCircleButton(Icons.Rounded.ClosedCaption, "زیرنویس", onOpenSubtitles)
                }
                if (state.isHost) {
                    OverlayCircleButton(Icons.Rounded.Speed, "سرعت پخش", onOpenSpeed)
                }
            }

            IconButton(
                onClick = onEnterFullscreen,
                modifier = Modifier
                    .align(Alignment.BottomEnd)
                    .padding(6.dp)
                    .size(38.dp)
                    .background(Color(0x66000000), CircleShape),
            ) {
                Icon(Icons.Rounded.Fullscreen, contentDescription = "تمام‌صفحه", tint = Color.White, modifier = Modifier.size(22.dp))
            }
        }

        PlaybackBar(
            isHost = state.isHost,
            playing = state.playing,
            positionMs = state.positionMs,
            durationMs = state.durationMs,
            speed = state.playbackSpeed,
            onToggle = onPlayPause,
            onSeek = onSeek,
            onResync = onResync,
        )

        ReactionBar(onReact = onReact, modifier = Modifier.fillMaxWidth())

        MembersStrip(members = state.members)

        ChatMessages(
            messages = state.messages,
            translucent = false,
            modifier = Modifier.weight(1f).fillMaxWidth(),
        )
        ChatInput(
            draft = state.chatDraft,
            translucent = false,
            onDraftChange = onDraftChange,
            onSend = onSend,
            modifier = Modifier.navigationBarsPadding().imePadding(),
        )
    }
}

@Composable
private fun RoomTopBar(
    title: String,
    inviteCode: String?,
    onBack: () -> Unit,
    onCopyInvite: () -> Unit,
    onlineCount: Int,
    latencyMs: Long?,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier
            .fillMaxWidth()
            .background(BgElevated)
            .padding(horizontal = 8.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = onBack) {
            Icon(Icons.AutoMirrored.Rounded.ArrowForward, contentDescription = "خروج از اتاق")
        }
        Column(Modifier.weight(1f)) {
            Text(
                title,
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (onlineCount > 0) {
                    Box(Modifier.size(6.dp).background(BrandGreen, CircleShape))
                    Text("$onlineCount آنلاین", style = MaterialTheme.typography.labelSmall, color = TextMuted)
                } else {
                    Text("تماشای گروهی", style = MaterialTheme.typography.labelSmall, color = TextMuted)
                }
            }
        }
        if (!inviteCode.isNullOrBlank()) {
            Row(
                Modifier
                    .clip(RoundedCornerShape(999.dp))
                    .background(BgSurface)
                    .clickable(onClick = onCopyInvite)
                    .padding(start = 12.dp, end = 8.dp, top = 6.dp, bottom = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Text(inviteCode, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold, color = BrandMint)
                Icon(Icons.Rounded.ContentCopy, contentDescription = "کپی کد دعوت", tint = TextSecondary, modifier = Modifier.size(15.dp))
            }
        }
        if (latencyMs != null) {
            Text(
                "${latencyMs}ms",
                style = MaterialTheme.typography.labelSmall,
                color = if (latencyMs < 200) BrandGreen else TextMuted,
                modifier = Modifier.padding(horizontal = 8.dp),
            )
        }
    }
}

@Composable
private fun PlaybackBar(
    isHost: Boolean,
    playing: Boolean,
    positionMs: Long,
    durationMs: Long,
    speed: Float,
    onToggle: () -> Unit,
    onSeek: (Long) -> Unit,
    onResync: () -> Unit,
) {
    Column(Modifier.fillMaxWidth().background(BgElevated).padding(horizontal = 12.dp, vertical = 6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onToggle, enabled = isHost) {
                Icon(
                    if (playing) Icons.Rounded.Pause else Icons.Rounded.PlayArrow,
                    contentDescription = if (playing) "توقف" else "پخش",
                    tint = if (isHost) BrandMint else TextMuted,
                )
            }
            SeekBar(
                positionMs = positionMs,
                durationMs = durationMs,
                enabled = isHost,
                onSeek = onSeek,
                modifier = Modifier.weight(1f),
            )
            if (speed != 1f) {
                Text(
                    "${formatSpeed(speed)}x",
                    style = MaterialTheme.typography.labelSmall,
                    color = BrandMint,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(start = 6.dp),
                )
            }
        }
        if (!isHost) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                modifier = Modifier.padding(start = 12.dp, bottom = 4.dp),
            ) {
                Icon(Icons.Rounded.Lock, contentDescription = null, tint = TextMuted, modifier = Modifier.size(14.dp))
                Text("کنترل پخش در دست میزبان است", style = MaterialTheme.typography.labelSmall, color = TextMuted)
                Spacer(Modifier.weight(1f))
                Row(
                    Modifier
                        .clip(RoundedCornerShape(999.dp))
                        .clickable(onClick = onResync)
                        .background(BgSurface)
                        .padding(horizontal = 10.dp, vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Icon(Icons.Rounded.Sync, contentDescription = null, tint = BrandMint, modifier = Modifier.size(13.dp))
                    Text("هماهنگ‌سازی", style = MaterialTheme.typography.labelSmall, color = BrandMint)
                }
            }
        }
    }
}

/** LTR-forced timeline (elapsed left, total right) even in the RTL UI. */
@Composable
private fun SeekBar(
    positionMs: Long,
    durationMs: Long,
    enabled: Boolean,
    onSeek: (Long) -> Unit,
    modifier: Modifier = Modifier,
    light: Boolean = false,
) {
    androidx.compose.runtime.CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        Row(modifier, verticalAlignment = Alignment.CenterVertically) {
            Text(
                formatTime(positionMs),
                style = MaterialTheme.typography.labelSmall,
                color = if (light) Color.White else TextSecondary,
            )
            val dur = durationMs.coerceAtLeast(1)
            Slider(
                value = positionMs.coerceIn(0, dur).toFloat(),
                onValueChange = { if (enabled) onSeek(it.toLong()) },
                valueRange = 0f..dur.toFloat(),
                enabled = enabled,
                colors = SliderDefaults.colors(
                    thumbColor = BrandMint,
                    activeTrackColor = BrandMint,
                    inactiveTrackColor = if (light) Color(0x55FFFFFF) else Color(0x33FFFFFF),
                ),
                modifier = Modifier.weight(1f).padding(horizontal = 8.dp),
            )
            Text(
                formatTime(durationMs),
                style = MaterialTheme.typography.labelSmall,
                color = if (light) Color.White else TextSecondary,
            )
        }
    }
}

@Composable
private fun MembersStrip(members: List<RoomMemberDto>) {
    Row(
        Modifier
            .fillMaxWidth()
            .background(BgSurface)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        val online = members.count { it.isOnline }
        Text("$online آنلاین", style = MaterialTheme.typography.labelMedium, color = BrandGreen)
        Spacer(Modifier.size(4.dp))
        members.take(8).forEach { member -> MemberAvatar(member) }
    }
}

@Composable
private fun MemberAvatar(member: RoomMemberDto, size: androidx.compose.ui.unit.Dp = 30.dp) {
    val initial = member.user?.displayName?.trim()?.firstOrNull()?.toString() ?: "؟"
    Box(
        Modifier
            .size(size)
            .background(if (member.role == "host") BrandGreen else BgElevated, CircleShape)
            .border(
                width = 1.5.dp,
                color = if (member.isOnline) BrandMint else OutlineSoft,
                shape = CircleShape,
            ),
        contentAlignment = Alignment.Center,
    ) {
        Text(initial, color = if (member.role == "host") OnBrand else TextSecondary, fontSize = 13.sp)
    }
}

/* ================================ FULLSCREEN ================================ */
@androidx.annotation.OptIn(androidx.media3.common.util.UnstableApi::class)
@Composable
private fun FullscreenBody(
    state: RoomUiState,
    player: androidx.media3.exoplayer.ExoPlayer,
    subtitleAppearance: SubtitleAppearance,
    reactions: SharedFlow<ReactionBurst>,
    controlsVisible: Boolean,
    chatOpen: Boolean,
    unread: Int,
    onToggleControls: () -> Unit,
    onExitFullscreen: () -> Unit,
    onToggleChat: () -> Unit,
    onCloseChat: () -> Unit,
    onPlayPause: () -> Unit,
    onSeek: (Long) -> Unit,
    onRewind: () -> Unit,
    onForward: () -> Unit,
    onOpenSpeed: () -> Unit,
    onOpenSubtitles: () -> Unit,
    onResync: () -> Unit,
    onReact: (String) -> Unit,
    onRetry: () -> Unit,
    draft: String,
    onDraftChange: (String) -> Unit,
    onSend: () -> Unit,
) {
    val context = LocalContext.current
    val activity = context as? Activity
    val audioManager = remember { context.getSystemService(Context.AUDIO_SERVICE) as AudioManager }
    val maxVolume = remember { audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1) }

    var gesture by remember { mutableStateOf<GestureFeedback?>(null) }
    var seekTotal by remember { mutableIntStateOf(0) }
    var seekForward by remember { mutableStateOf(true) }

    // Auto-dismiss the volume/brightness bubble shortly after the drag stops.
    LaunchedEffect(gesture) {
        if (gesture != null) { delay(650); gesture = null }
    }
    // Collapse the double-tap seek ripple once taps stop accumulating.
    LaunchedEffect(seekTotal, seekForward) {
        if (seekTotal != 0) { delay(700); seekTotal = 0 }
    }

    Box(
        Modifier
            .fillMaxSize()
            .background(Color.Black)
            // Tap toggles controls; double-tap on a side seeks (host only).
            .pointerInput(state.isHost) {
                detectTapGestures(
                    onTap = { onToggleControls() },
                    onDoubleTap = { pos ->
                        if (state.isHost) {
                            val fwd = pos.x > size.width / 2f
                            seekForward = fwd
                            seekTotal = if (fwd) seekTotal + 10 else seekTotal + 10
                            if (fwd) onForward() else onRewind()
                        } else {
                            onToggleControls()
                        }
                    },
                )
            }
            // Vertical drag: left half = brightness, right half = volume.
            .pointerInput(Unit) {
                var isLeft = false
                var accVol = 0f
                var accBright = 0.5f
                detectVerticalDragGestures(
                    onDragStart = { off ->
                        isLeft = off.x < size.width / 2f
                        accVol = audioManager.getStreamVolume(AudioManager.STREAM_MUSIC).toFloat()
                        val cur = activity?.window?.attributes?.screenBrightness ?: 0.5f
                        accBright = if (cur < 0f) 0.5f else cur
                    },
                    onVerticalDrag = { change, dragAmount ->
                        change.consume()
                        val frac = -dragAmount / size.height.toFloat()
                        if (isLeft) {
                            accBright = (accBright + frac).coerceIn(0.02f, 1f)
                            activity?.window?.let { w ->
                                val lp = w.attributes
                                lp.screenBrightness = accBright
                                w.attributes = lp
                            }
                            gesture = GestureFeedback(brightness = true, level = accBright)
                        } else {
                            accVol = (accVol + frac * maxVolume).coerceIn(0f, maxVolume.toFloat())
                            audioManager.setStreamVolume(AudioManager.STREAM_MUSIC, accVol.roundToInt(), 0)
                            gesture = GestureFeedback(brightness = false, level = accVol / maxVolume)
                        }
                    },
                )
            },
    ) {
        PartyPlayerSurface(player, subtitleAppearance, Modifier.fillMaxSize())
        ReactionOverlay(reactions, Modifier.fillMaxSize())

        if (state.buffering || state.loading) {
            CircularProgressIndicator(color = BrandMint, strokeWidth = 2.dp, modifier = Modifier.align(Alignment.Center))
        }

        // Double-tap seek ripple (host only).
        if (seekTotal != 0) {
            SeekRipple(
                forward = seekForward,
                seconds = seekTotal,
                modifier = Modifier
                    .align(if (seekForward) Alignment.CenterEnd else Alignment.CenterStart)
                    .padding(horizontal = 40.dp),
            )
        }

        // Volume / brightness bubble.
        gesture?.let { GestureBubble(it, Modifier.align(Alignment.Center)) }

        if (state.playerError != null) {
            PlayerErrorOverlay(message = state.playerError, onRetry = onRetry, modifier = Modifier.align(Alignment.Center))
        }

        // ---- Controls overlay (auto-hiding) ----
        AnimatedVisibility(
            visible = controlsVisible,
            enter = fadeIn(),
            exit = fadeOut(),
            modifier = Modifier.fillMaxSize(),
        ) {
            FullscreenControls(
                state = state,
                unread = unread,
                onExitFullscreen = onExitFullscreen,
                onToggleChat = onToggleChat,
                onPlayPause = onPlayPause,
                onSeek = onSeek,
                onRewind = onRewind,
                onForward = onForward,
                onOpenSpeed = onOpenSpeed,
                onOpenSubtitles = onOpenSubtitles,
                onResync = onResync,
            )
        }

        // ---- Persistent reaction launcher clinging to the left edge ----
        ReactionLauncher(
            onReact = onReact,
            modifier = Modifier
                .align(Alignment.CenterStart)
                .windowInsetsPadding(WindowInsets.systemBars),
        )

        // ---- Persistent chat opener tab (visible whenever the panel is closed) ----
        AnimatedVisibility(
            visible = !chatOpen,
            enter = fadeIn(),
            exit = fadeOut(),
            modifier = Modifier
                .align(Alignment.CenterEnd)
                .windowInsetsPadding(WindowInsets.systemBars),
        ) {
            ChatOpenerTab(unread = unread, onClick = onToggleChat)
        }

        // ---- Sliding chat side panel (video keeps playing beside it) ----
        val ltr = LocalLayoutDirection.current == LayoutDirection.Ltr
        AnimatedVisibility(
            visible = chatOpen,
            enter = slideInHorizontally(tween(240)) { w -> if (ltr) w else -w } + fadeIn(tween(200)),
            exit = slideOutHorizontally(tween(200)) { w -> if (ltr) w else -w } + fadeOut(tween(160)),
            modifier = Modifier.align(Alignment.CenterEnd),
        ) {
            ChatSidePanel(
                messages = state.messages,
                draft = draft,
                onDraftChange = onDraftChange,
                onSend = onSend,
                onClose = onCloseChat,
            )
        }
    }
}

@Composable
private fun FullscreenControls(
    state: RoomUiState,
    unread: Int,
    onExitFullscreen: () -> Unit,
    onToggleChat: () -> Unit,
    onPlayPause: () -> Unit,
    onSeek: (Long) -> Unit,
    onRewind: () -> Unit,
    onForward: () -> Unit,
    onOpenSpeed: () -> Unit,
    onOpenSubtitles: () -> Unit,
    onResync: () -> Unit,
) {
    Box(
        Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    0f to Color(0x99000000),
                    0.25f to Color.Transparent,
                    0.72f to Color.Transparent,
                    1f to Color(0x99000000),
                ),
            )
            .windowInsetsPadding(WindowInsets.safeDrawing),
    ) {
        // Top bar
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onExitFullscreen) {
                Icon(Icons.Rounded.FullscreenExit, contentDescription = "خروج از تمام‌صفحه", tint = Color.White, modifier = Modifier.size(26.dp))
            }
            Column(Modifier.weight(1f).padding(start = 6.dp)) {
                Text(
                    state.content?.title ?: "تماشای گروهی",
                    style = MaterialTheme.typography.titleMedium,
                    color = Color.White,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                val online = state.members.count { it.isOnline }
                Text("$online آنلاین", style = MaterialTheme.typography.labelSmall, color = Color(0xCCFFFFFF))
            }
            if (state.subtitles.isNotEmpty()) {
                IconButton(onClick = onOpenSubtitles) {
                    Icon(Icons.Rounded.ClosedCaption, contentDescription = "زیرنویس", tint = Color.White, modifier = Modifier.size(24.dp))
                }
            }
            if (state.isHost) {
                IconButton(onClick = onOpenSpeed) {
                    Icon(Icons.Rounded.Speed, contentDescription = "سرعت پخش", tint = Color.White, modifier = Modifier.size(24.dp))
                }
            }
            ChatIconButton(unread = unread, onClick = onToggleChat)
        }

        // Center transport — host only; guests see the host-lock hint + a resync tap.
        if (state.isHost) {
            Row(
                Modifier.align(Alignment.Center),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(34.dp),
            ) {
                CircleControl(onRewind, 50.dp) {
                    Icon(Icons.Rounded.Replay10, contentDescription = "۱۰ ثانیه عقب", tint = Color.White, modifier = Modifier.size(32.dp))
                }
                CircleControl(onPlayPause, 74.dp, Color(0x33FFFFFF)) {
                    Icon(
                        if (state.playing) Icons.Rounded.Pause else Icons.Rounded.PlayArrow,
                        contentDescription = "پخش/توقف",
                        tint = Color.White,
                        modifier = Modifier.size(46.dp),
                    )
                }
                CircleControl(onForward, 50.dp) {
                    Icon(Icons.Rounded.Forward10, contentDescription = "۱۰ ثانیه جلو", tint = Color.White, modifier = Modifier.size(32.dp))
                }
            }
        } else {
            Row(
                Modifier
                    .align(Alignment.Center)
                    .clip(CircleShape)
                    .clickable(onClick = onResync)
                    .background(Color(0x66000000))
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Icon(Icons.Rounded.Sync, contentDescription = null, tint = Color.White, modifier = Modifier.size(16.dp))
                Text("هماهنگ‌سازی با میزبان", color = Color.White, style = MaterialTheme.typography.labelMedium)
            }
        }

        // Bottom seek bar
        SeekBar(
            positionMs = state.positionMs,
            durationMs = state.durationMs,
            enabled = state.isHost,
            onSeek = onSeek,
            light = true,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 10.dp),
        )
    }
}

/* ============================= Gesture feedback ============================= */
@Composable
private fun GestureBubble(feedback: GestureFeedback, modifier: Modifier = Modifier) {
    Column(
        modifier
            .background(Color(0xCC101012), RoundedCornerShape(16.dp))
            .padding(horizontal = 20.dp, vertical = 16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Icon(
            if (feedback.brightness) Icons.Rounded.Brightness6 else Icons.AutoMirrored.Rounded.VolumeUp,
            contentDescription = null,
            tint = Color.White,
            modifier = Modifier.size(26.dp),
        )
        Box(
            Modifier
                .size(width = 120.dp, height = 4.dp)
                .clip(CircleShape)
                .background(Color(0x44FFFFFF)),
        ) {
            Box(
                Modifier
                    .fillMaxHeight()
                    .fillMaxWidth(feedback.level.coerceIn(0f, 1f))
                    .clip(CircleShape)
                    .background(BrandMint),
            )
        }
        Text("${(feedback.level * 100).roundToInt()}٪", color = Color.White, fontSize = 12.sp)
    }
}

@Composable
private fun SeekRipple(forward: Boolean, seconds: Int, modifier: Modifier = Modifier) {
    Column(
        modifier
            .background(Color(0x55000000), CircleShape)
            .padding(20.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(
            if (forward) Icons.Rounded.Forward10 else Icons.Rounded.Replay10,
            contentDescription = null,
            tint = Color.White,
            modifier = Modifier.size(34.dp),
        )
        Text("$seconds ثانیه", color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold)
    }
}

/* ============================= Live reactions ============================= */
/** Emoji that rise and fade over the video, one per burst broadcast to the room. */
@Composable
private fun ReactionOverlay(reactions: SharedFlow<ReactionBurst>, modifier: Modifier = Modifier) {
    val active = remember { mutableStateListOf<ReactionBurst>() }
    LaunchedEffect(Unit) {
        reactions.collect { burst ->
            active.add(burst)
            if (active.size > 24) active.removeAt(0)
        }
    }
    BoxWithConstraints(modifier) {
        val density = LocalDensity.current
        val heightPx = with(density) { maxHeight.toPx() }
        val widthPx = with(density) { maxWidth.toPx() }
        active.forEach { burst ->
            androidx.compose.runtime.key(burst.id) {
                FloatingReaction(burst, heightPx, widthPx) { active.remove(burst) }
            }
        }
    }
}

@Composable
private fun FloatingReaction(
    burst: ReactionBurst,
    heightPx: Float,
    widthPx: Float,
    onDone: () -> Unit,
) {
    val progress = remember { Animatable(0f) }
    // Random-ish lane and drift so simultaneous reactions don't overlap perfectly.
    val lane = remember(burst.id) { 0.10f + kotlin.random.Random.nextFloat() * 0.45f }
    val drift = remember(burst.id) { (kotlin.random.Random.nextFloat() - 0.5f) * 0.14f }
    LaunchedEffect(burst.id) {
        progress.animateTo(1f, tween(2600, easing = LinearEasing))
        onDone()
    }
    val p = progress.value
    Column(
        Modifier.graphicsLayer {
            translationY = heightPx * (0.92f - 0.80f * p)
            translationX = widthPx * lane + widthPx * drift * p
            alpha = (1f - p * p).coerceIn(0f, 1f)
            val pop = (p / 0.18f).coerceIn(0f, 1f)
            val s = 0.5f + 0.55f * pop
            scaleX = s
            scaleY = s
        },
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(burst.emoji, fontSize = 34.sp)
        if (burst.displayName.isNotBlank()) {
            Text(
                burst.displayName,
                color = Color.White,
                fontSize = 10.sp,
                modifier = Modifier
                    .background(Color(0x66000000), CircleShape)
                    .padding(horizontal = 6.dp, vertical = 1.dp),
            )
        }
    }
}

/** Portrait: an always-visible row of tappable reaction emojis. */
@Composable
private fun ReactionBar(onReact: (String) -> Unit, modifier: Modifier = Modifier) {
    Row(
        modifier
            .background(BgElevated)
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = 10.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        ReactionEmojis.forEach { emoji ->
            Box(
                Modifier
                    .size(38.dp)
                    .clip(CircleShape)
                    .background(BgSurface)
                    .clickable { onReact(emoji) },
                contentAlignment = Alignment.Center,
            ) {
                Text(emoji, fontSize = 20.sp)
            }
        }
    }
}

/** Fullscreen: a left-edge launcher that expands into a reaction picker. */
@Composable
private fun ReactionLauncher(onReact: (String) -> Unit, modifier: Modifier = Modifier) {
    var open by remember { mutableStateOf(false) }
    // Fold the picker away if it sits idle so it doesn't block the frame.
    LaunchedEffect(open) {
        if (open) { delay(4200); open = false }
    }
    Row(modifier.padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier
                .padding(start = 6.dp)
                .clip(CircleShape)
                .background(Color(0xCC101012))
                .clickable { open = !open }
                .padding(10.dp),
            contentAlignment = Alignment.Center,
        ) {
            Icon(Icons.Rounded.Mood, contentDescription = "واکنش", tint = Color.White, modifier = Modifier.size(24.dp))
        }
        AnimatedVisibility(
            visible = open,
            enter = fadeIn(tween(160)) + slideInHorizontally(tween(200)) { -it / 2 },
            exit = fadeOut(tween(140)) + slideOutHorizontally(tween(160)) { -it / 2 },
        ) {
            Row(
                Modifier
                    .padding(start = 6.dp)
                    .clip(RoundedCornerShape(999.dp))
                    .background(Color(0xE6101012))
                    .horizontalScroll(rememberScrollState())
                    .padding(horizontal = 8.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                ReactionEmojis.forEach { emoji ->
                    Box(
                        Modifier
                            .size(38.dp)
                            .clip(CircleShape)
                            .clickable { onReact(emoji) },
                        contentAlignment = Alignment.Center,
                    ) {
                        Text(emoji, fontSize = 22.sp)
                    }
                }
            }
        }
    }
}

/* ============================= Player error ============================= */
@Composable
private fun PlayerErrorOverlay(message: String, onRetry: () -> Unit, modifier: Modifier = Modifier) {
    Column(
        modifier
            .background(Color(0xCC000000), RoundedCornerShape(16.dp))
            .padding(horizontal = 22.dp, vertical = 18.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(message, color = Color.White, style = MaterialTheme.typography.bodyMedium)
        Row(
            Modifier
                .clip(RoundedCornerShape(999.dp))
                .background(BrandMint)
                .clickable(onClick = onRetry)
                .padding(horizontal = 18.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Icon(Icons.Rounded.Refresh, contentDescription = null, tint = OnBrand, modifier = Modifier.size(18.dp))
            Text("تلاش دوباره", color = OnBrand, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelLarge)
        }
    }
}

/* ============================= Bottom sheets ============================= */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SpeedSheet(current: Float, onPick: (Float) -> Unit, onDismiss: () -> Unit) {
    val sheet = rememberModalBottomSheetState()
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheet, containerColor = BgElevated) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 28.dp)) {
            Text("سرعت پخش", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = TextPrimary)
            Spacer(Modifier.size(6.dp))
            Text("برای همه در اتاق اعمال می‌شود", style = MaterialTheme.typography.labelSmall, color = TextMuted)
            Spacer(Modifier.size(10.dp))
            PlaybackSpeeds.forEach { s ->
                SheetOptionRow(
                    label = if (s == 1f) "عادی" else "${formatSpeed(s)}x",
                    selected = abs(s - current) < 0.01f,
                    onClick = { onPick(s) },
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SubtitleSheet(
    subtitles: List<PartySubtitle>,
    activeIndex: Int,
    appearance: SubtitleAppearance,
    onSelectTrack: (Int) -> Unit,
    onAppearanceChange: (SubtitleAppearance) -> Unit,
    onDismiss: () -> Unit,
) {
    val sheet = rememberModalBottomSheetState()
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheet, containerColor = BgElevated) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 28.dp)) {
            Text("زیرنویس", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = TextPrimary)
            Spacer(Modifier.size(10.dp))
            SheetOptionRow(label = "خاموش", selected = activeIndex < 0, onClick = { onSelectTrack(-1) })
            subtitles.forEachIndexed { index, sub ->
                SheetOptionRow(label = sub.label, selected = index == activeIndex, onClick = { onSelectTrack(index) })
            }

            if (subtitles.isNotEmpty()) {
                Spacer(Modifier.size(16.dp))
                Text("فونت", style = MaterialTheme.typography.labelMedium, color = TextSecondary)
                Spacer(Modifier.size(8.dp))
                Row(
                    Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    SubtitleFont.entries.forEach { font ->
                        AppearanceChip(
                            label = font.title,
                            selected = font == appearance.font,
                            onClick = { onAppearanceChange(appearance.copy(font = font)) },
                        )
                    }
                }
                Spacer(Modifier.size(14.dp))
                Text("اندازه", style = MaterialTheme.typography.labelMedium, color = TextSecondary)
                Spacer(Modifier.size(8.dp))
                Row(
                    Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    SubtitleSize.entries.forEach { size ->
                        AppearanceChip(
                            label = size.title,
                            selected = size == appearance.size,
                            onClick = { onAppearanceChange(appearance.copy(size = size)) },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun SheetOptionRow(label: String, selected: Boolean, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .clickable(onClick = onClick)
            .background(if (selected) BrandMint.copy(alpha = 0.14f) else Color.Transparent)
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            label,
            style = MaterialTheme.typography.bodyLarge,
            color = if (selected) BrandMint else TextPrimary,
            fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
            modifier = Modifier.weight(1f),
        )
        if (selected) {
            Icon(Icons.Rounded.Check, contentDescription = null, tint = BrandMint, modifier = Modifier.size(18.dp))
        }
    }
}

@Composable
private fun AppearanceChip(label: String, selected: Boolean, onClick: () -> Unit) {
    Box(
        Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(if (selected) BrandMint else BgSurface)
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 8.dp),
    ) {
        Text(
            label,
            style = MaterialTheme.typography.labelLarge,
            color = if (selected) OnBrand else TextSecondary,
            fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
        )
    }
}

/* ============================= Small shared bits ============================= */
@Composable
private fun OverlayCircleButton(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, onClick: () -> Unit) {
    IconButton(
        onClick = onClick,
        modifier = Modifier.size(38.dp).background(Color(0x66000000), CircleShape),
    ) {
        Icon(icon, contentDescription = label, tint = Color.White, modifier = Modifier.size(20.dp))
    }
}

/** Slim tab clinging to the edge that opens chat without summoning full controls. */
@Composable
private fun ChatOpenerTab(unread: Int, onClick: () -> Unit) {
    Box(contentAlignment = Alignment.TopEnd) {
        Row(
            Modifier
                .padding(vertical = 8.dp)
                .clip(RoundedCornerShape(topStart = 20.dp, bottomStart = 20.dp))
                .background(Color(0xCC101012))
                .clickable(onClick = onClick)
                .padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Icon(Icons.Rounded.ChatBubbleOutline, contentDescription = "باز کردن گفتگو", tint = Color.White, modifier = Modifier.size(22.dp))
        }
        if (unread > 0) UnreadDot(unread)
    }
}

/** Chat icon in the top bar, with an unread badge. */
@Composable
private fun ChatIconButton(unread: Int, onClick: () -> Unit) {
    Box(contentAlignment = Alignment.TopEnd) {
        IconButton(onClick = onClick) {
            Icon(Icons.Rounded.ChatBubbleOutline, contentDescription = "گفتگو", tint = Color.White, modifier = Modifier.size(24.dp))
        }
        if (unread > 0) UnreadDot(unread)
    }
}

@Composable
private fun UnreadDot(count: Int) {
    Box(
        Modifier
            .padding(top = 2.dp, end = 2.dp)
            .size(18.dp)
            .background(Color(0xFFE23B4E), CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            if (count > 9) "9+" else "$count",
            color = Color.White,
            fontSize = 10.sp,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
private fun ChatSidePanel(
    messages: List<ChatMessageDto>,
    draft: String,
    onDraftChange: (String) -> Unit,
    onSend: () -> Unit,
    onClose: () -> Unit,
) {
    Column(
        Modifier
            .fillMaxHeight()
            .fillMaxWidth(0.5f)
            .widthIn(min = 260.dp, max = 400.dp)
            .background(ChatOverlayBg)
            .windowInsetsPadding(WindowInsets.systemBars)
            .imePadding(),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(start = 16.dp, end = 8.dp, top = 10.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Rounded.ChatBubbleOutline, contentDescription = null, tint = BrandMint, modifier = Modifier.size(18.dp))
            Spacer(Modifier.size(8.dp))
            Text("گفتگوی زنده", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = Color.White, modifier = Modifier.weight(1f))
            IconButton(onClick = onClose) {
                Icon(Icons.Rounded.Close, contentDescription = "بستن گفتگو", tint = Color.White, modifier = Modifier.size(20.dp))
            }
        }
        ChatMessages(messages = messages, translucent = true, modifier = Modifier.weight(1f).fillMaxWidth())
        ChatInput(draft = draft, translucent = true, onDraftChange = onDraftChange, onSend = onSend)
    }
}

/* ============================= Shared chat pieces ============================= */
@Composable
private fun ChatMessages(
    messages: List<ChatMessageDto>,
    translucent: Boolean,
    modifier: Modifier = Modifier,
) {
    if (messages.isEmpty()) {
        Box(modifier, contentAlignment = Alignment.Center) {
            Text(
                "هنوز پیامی نیست؛ اولین نفر باش!",
                style = MaterialTheme.typography.bodySmall,
                color = if (translucent) Color(0x99FFFFFF) else TextMuted,
            )
        }
        return
    }
    val listState = rememberLazyListState()
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.size - 1)
    }
    LazyColumn(
        state = listState,
        modifier = modifier.padding(horizontal = 12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 8.dp),
    ) {
        items(messages, key = { it.id }) { msg -> ChatBubble(msg, translucent) }
    }
}

@Composable
private fun ChatBubble(msg: ChatMessageDto, translucent: Boolean) {
    Column {
        Text(
            msg.user?.displayName ?: "کاربر",
            style = MaterialTheme.typography.labelSmall,
            color = BrandMint,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.size(2.dp))
        Box(
            Modifier
                .background(if (translucent) ChatBubbleOverlay else BgElevated, RoundedCornerShape(12.dp))
                .padding(horizontal = 12.dp, vertical = 8.dp),
        ) {
            Text(
                msg.message,
                style = MaterialTheme.typography.bodyMedium,
                color = if (translucent) Color.White else MaterialTheme.colorScheme.onSurface,
            )
        }
    }
}

@Composable
private fun ChatInput(
    draft: String,
    translucent: Boolean,
    onDraftChange: (String) -> Unit,
    onSend: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier
            .fillMaxWidth()
            .background(if (translucent) Color(0xF21A1B1E) else BgElevated)
            .padding(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        OutlinedTextField(
            value = draft,
            onValueChange = onDraftChange,
            modifier = Modifier.weight(1f),
            placeholder = { Text("پیام بنویس…", color = if (translucent) Color(0x99FFFFFF) else TextMuted) },
            maxLines = 3,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
            keyboardActions = KeyboardActions(onSend = { onSend() }),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = BrandMint,
                cursorColor = BrandMint,
                focusedTextColor = if (translucent) Color.White else MaterialTheme.colorScheme.onSurface,
                unfocusedTextColor = if (translucent) Color.White else MaterialTheme.colorScheme.onSurface,
                unfocusedBorderColor = if (translucent) Color(0x44FFFFFF) else OutlineSoft,
            ),
        )
        IconButton(onClick = onSend) {
            Icon(Icons.AutoMirrored.Rounded.Send, contentDescription = "ارسال", tint = BrandMint)
        }
    }
}

@Composable
private fun CircleControl(
    onClick: () -> Unit,
    size: androidx.compose.ui.unit.Dp,
    background: Color = Color.Transparent,
    content: @Composable () -> Unit,
) {
    Box(
        Modifier
            .size(size)
            .background(background, CircleShape)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) { content() }
}

private fun formatTime(ms: Long): String {
    if (ms <= 0) return "0:00"
    val totalSec = ms / 1000
    val h = totalSec / 3600
    val m = (totalSec % 3600) / 60
    val s = totalSec % 60
    return if (h > 0) "%d:%02d:%02d".format(h, m, s) else "%d:%02d".format(m, s)
}

/** Trim a trailing ".0" so 1.0→"1" but 0.75 stays "0.75". */
private fun formatSpeed(speed: Float): String =
    if (speed % 1f == 0f) speed.toInt().toString() else speed.toString()
