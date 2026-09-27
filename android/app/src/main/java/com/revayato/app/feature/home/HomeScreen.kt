package com.revayato.app.feature.home

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.playback.WatchProgressEntry
import com.revayato.app.core.theme.AccentBlue
import com.revayato.app.core.theme.AccentRed
import com.revayato.app.core.theme.AccentYellow
import com.revayato.app.core.theme.BrandMint
import com.revayato.app.core.theme.PlayAccent
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.CatalogCardDto
import com.revayato.app.data.model.GenreDto
import com.revayato.app.ui.components.ErrorState
import com.revayato.app.ui.components.LoadingState
import com.revayato.app.ui.components.MediaRail
import com.revayato.app.ui.components.NetworkImage
import com.revayato.app.ui.components.RatingBadge
import com.revayato.app.ui.components.SectionHeader
import kotlinx.coroutines.delay

/** Rotating shelf accents (زرد / قرمز / آبی / نعناعی) for a lively rhythm. */
private val RailAccents = listOf(AccentYellow, AccentRed, AccentBlue, PlayAccent, BrandMint)

@Composable
fun HomeScreen(
    onOpenTitle: (contentType: String, slug: String) -> Unit,
    onOpenCollection: (slug: String) -> Unit,
    onSeeAllRoute: (route: String) -> Unit,
    onResume: (WatchProgressEntry) -> Unit,
    onOpenGenre: (GenreDto) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: HomeViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    when (val s = state) {
        is UiState.Loading -> LoadingState(modifier)
        is UiState.Error -> ErrorState(s.message, modifier, onRetry = viewModel::load)
        is UiState.Success -> HomeContent(
            data = s.data,
            modifier = modifier,
            onOpenTitle = onOpenTitle,
            onSeeAllRoute = onSeeAllRoute,
            onResume = onResume,
            onOpenGenre = onOpenGenre,
        )
    }
}

@Composable
private fun HomeContent(
    data: HomeData,
    onOpenTitle: (String, String) -> Unit,
    onSeeAllRoute: (String) -> Unit,
    onResume: (WatchProgressEntry) -> Unit,
    onOpenGenre: (GenreDto) -> Unit,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = 24.dp),
    ) {
        if (data.hero.isNotEmpty()) {
            item(key = "hero") {
                HeroSlider(items = data.hero, onOpen = onOpenTitle)
            }
        }
        if (data.continueWatching.isNotEmpty()) {
            item(key = "continue") {
                ContinueWatchingRail(entries = data.continueWatching, onResume = onResume)
            }
        }
        if (data.genres.isNotEmpty()) {
            item(key = "genres") {
                GenreChipsRow(genres = data.genres, onOpenGenre = onOpenGenre)
            }
        }
        itemsIndexed(data.rails, key = { _, rail -> rail.key }) { index, rail ->
            MediaRail(
                title = rail.title,
                items = rail.items,
                accent = RailAccents[index % RailAccents.size],
                onItemClick = { onOpenTitle(it.contentType, it.slug) },
                onSeeAll = rail.seeAllRoute?.let { route -> { onSeeAllRoute(route) } },
            )
        }
    }
}

@Composable
private fun ContinueWatchingRail(
    entries: List<WatchProgressEntry>,
    onResume: (WatchProgressEntry) -> Unit,
) {
    Column(Modifier.fillMaxWidth()) {
        SectionHeader(title = "ادامه تماشا", accent = AccentRed)
        LazyRow(
            contentPadding = PaddingValues(horizontal = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            items(entries, key = { "${it.contentType}-${it.id}-${it.episodeId}" }) { entry ->
                ContinueWatchingCard(entry = entry, onClick = { onResume(entry) })
            }
        }
    }
}

@Composable
private fun ContinueWatchingCard(
    entry: WatchProgressEntry,
    onClick: () -> Unit,
) {
    Box(
        modifier = Modifier
            .width(260.dp)
            .aspectRatio(16f / 9f)
            .clip(RoundedCornerShape(14.dp))
            .clickable { onClick() },
    ) {
        NetworkImage(
            url = entry.poster.ifBlank { null },
            contentDescription = entry.title,
            fallbackText = entry.title,
            modifier = Modifier.fillMaxSize(),
        )
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        0f to Color(0x22000000),
                        0.5f to Color(0x66000000),
                        1f to Color(0xEE111111),
                    ),
                ),
        )
        // Central play affordance.
        Box(
            modifier = Modifier
                .align(Alignment.Center)
                .size(46.dp)
                .clip(CircleShape)
                .background(AccentRed),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                Icons.Rounded.PlayArrow,
                contentDescription = null,
                tint = Color.White,
                modifier = Modifier.size(26.dp),
            )
        }
        Column(
            modifier = Modifier
                .align(Alignment.BottomStart)
                .fillMaxWidth()
                .padding(start = 12.dp, end = 12.dp, top = 12.dp, bottom = 10.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text(
                text = entry.title,
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                color = Color.White,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (entry.episodeLabel.isNotBlank()) {
                Text(
                    text = entry.episodeLabel,
                    style = MaterialTheme.typography.labelSmall,
                    color = Color(0xFFCFCFCF),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            // Resume progress bar.
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(4.dp)
                    .clip(RoundedCornerShape(2.dp))
                    .background(Color(0x33FFFFFF)),
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxHeight()
                        .fillMaxWidth(entry.progressFraction.coerceIn(0.02f, 1f))
                        .clip(RoundedCornerShape(2.dp))
                        .background(AccentRed),
                )
            }
        }
    }
}

@Composable
private fun GenreChipsRow(
    genres: List<GenreDto>,
    onOpenGenre: (GenreDto) -> Unit,
) {
    val accents = listOf(AccentYellow, AccentRed, AccentBlue, PlayAccent, BrandMint)
    Column(Modifier.fillMaxWidth()) {
        SectionHeader(title = "ژانرها", accent = AccentBlue)
        LazyRow(
            contentPadding = PaddingValues(horizontal = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            itemsIndexed(genres, key = { _, g -> g.id }) { index, genre ->
                val c = accents[index % accents.size]
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(50))
                        .background(c.copy(alpha = 0.14f))
                        .border(1.dp, c.copy(alpha = 0.45f), RoundedCornerShape(50))
                        .clickable { onOpenGenre(genre) }
                        .padding(horizontal = 16.dp, vertical = 9.dp),
                ) {
                    Text(
                        text = genre.title,
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.SemiBold,
                        color = c,
                    )
                }
            }
        }
    }
}

@Composable
private fun HeroSlider(
    items: List<CatalogCardDto>,
    onOpen: (String, String) -> Unit,
) {
    val pagerState = rememberPagerState(pageCount = { items.size })

    // Gentle auto-advance.
    LaunchedEffect(items.size) {
        while (items.size > 1) {
            delay(5000)
            val next = (pagerState.currentPage + 1) % items.size
            pagerState.animateScrollToPage(next)
        }
    }

    Column {
        HorizontalPager(
            state = pagerState,
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(16f / 10f),
        ) { page ->
            HeroSlide(item = items[page], onOpen = onOpen)
        }
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 10.dp),
            horizontalArrangement = Arrangement.Center,
        ) {
            repeat(items.size) { index ->
                val active = index == pagerState.currentPage
                Box(
                    modifier = Modifier
                        .padding(horizontal = 3.dp)
                        .size(if (active) 20.dp else 6.dp, 6.dp)
                        .clip(CircleShape)
                        .background(if (active) BrandMint else Color(0x55FFFFFF)),
                )
            }
        }
    }
}

@Composable
private fun HeroSlide(
    item: CatalogCardDto,
    onOpen: (String, String) -> Unit,
) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .clickable { onOpen(item.contentType, item.slug) },
    ) {
        NetworkImage(
            url = item.backdropUrl,
            contentDescription = item.title,
            fallbackText = item.title,
            modifier = Modifier.fillMaxSize(),
        )
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        0f to Color.Transparent,
                        0.55f to Color(0x99000000),
                        1f to Color(0xF21D1C21),
                    ),
                ),
        )
        Column(
            modifier = Modifier
                .align(Alignment.BottomStart)
                .fillMaxWidth()
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(
                text = item.title,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                color = Color.White,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                item.bestRating?.takeIf { it > 0 }?.let { RatingBadge(it) }
                item.year?.let {
                    Text(
                        text = it.toString(),
                        style = MaterialTheme.typography.labelMedium,
                        color = Color(0xFFDDDDDD),
                    )
                }
                item.genres.take(2).forEach { g ->
                    Text(
                        text = "· ${g.title}",
                        style = MaterialTheme.typography.labelMedium,
                        color = Color(0xFFBBBBBB),
                    )
                }
            }
            Button(
                onClick = { onOpen(item.contentType, item.slug) },
                colors = ButtonDefaults.buttonColors(
                    containerColor = BrandMint,
                    contentColor = Color(0xFF0D0D0D),
                ),
                shape = RoundedCornerShape(12.dp),
            ) {
                Icon(Icons.Rounded.PlayArrow, contentDescription = null)
                Spacer(Modifier.size(6.dp))
                Text("تماشا کن", fontWeight = FontWeight.Bold)
            }
        }
    }
}
