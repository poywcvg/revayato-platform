package com.revayato.app.ui.components

import androidx.compose.animation.core.InfiniteRepeatableSpec
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import coil.compose.AsyncImage
import coil.compose.AsyncImagePainter
import coil.request.ImageRequest
import com.revayato.app.core.util.toAbsoluteUrl

/**
 * Coil-backed image with a shimmering placeholder and a graceful text fallback
 * when the source is missing or fails.
 *
 * Uses [AsyncImage] (not `rememberAsyncImagePainter`) on purpose: AsyncImage
 * measures its layout bounds and decodes the bitmap at the *display* size, so a
 * 2:3 poster shown at ~132dp never inflates a full-resolution bitmap into
 * memory. That single change is what keeps rails/grids scrolling smoothly and
 * slashes GC churn — the painter variant would decode at Size.ORIGINAL.
 */
@Composable
fun NetworkImage(
    url: String?,
    contentDescription: String?,
    modifier: Modifier = Modifier,
    contentScale: ContentScale = ContentScale.Crop,
    fallbackText: String? = null,
) {
    val resolved = url.toAbsoluteUrl()
    var state by remember(resolved) {
        mutableStateOf<AsyncImagePainter.State>(AsyncImagePainter.State.Empty)
    }
    Box(modifier = modifier.background(MaterialTheme.colorScheme.surfaceVariant)) {
        AsyncImage(
            model = ImageRequest.Builder(LocalContext.current)
                .data(resolved)
                .crossfade(true)
                .build(),
            contentDescription = contentDescription,
            contentScale = contentScale,
            modifier = Modifier.fillMaxSize(),
            onState = { state = it },
        )
        when (state) {
            is AsyncImagePainter.State.Loading -> ShimmerBox(Modifier.fillMaxSize())
            is AsyncImagePainter.State.Error -> FallbackPoster(fallbackText ?: contentDescription)
            is AsyncImagePainter.State.Empty ->
                if (resolved == null) FallbackPoster(fallbackText ?: contentDescription)
            // Success — the decoded frame already fills the box.
            else -> Unit
        }
    }
}

@Composable
private fun FallbackPoster(text: String?) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.linearGradient(
                    listOf(Color(0xFF1E1E22), Color(0xFF141414)),
                ),
            ),
        contentAlignment = Alignment.Center,
    ) {
        if (!text.isNullOrBlank()) {
            Text(
                text = text.take(24),
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxSize().background(Color.Transparent),
            )
        }
    }
}

@Composable
fun ShimmerBox(modifier: Modifier = Modifier) {
    val transition = rememberInfiniteTransition(label = "shimmer")
    val translate by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1000f,
        animationSpec = InfiniteRepeatableSpec(
            animation = tween(1200),
            repeatMode = RepeatMode.Restart,
        ),
        label = "shimmerTranslate",
    )
    val colors = listOf(
        Color(0xFF17171B),
        Color(0xFF232329),
        Color(0xFF17171B),
    )
    Box(
        modifier = modifier.drawWithContent {
            drawContent()
            val brush = Brush.linearGradient(
                colors = colors,
                start = Offset(translate - 400f, 0f),
                end = Offset(translate, size.height),
            )
            drawRect(brush = brush)
        },
    )
}
