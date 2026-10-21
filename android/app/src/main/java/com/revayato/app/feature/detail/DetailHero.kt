package com.revayato.app.feature.detail

import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.ClosedCaption
import androidx.compose.material.icons.rounded.Download
import androidx.compose.material.icons.rounded.Favorite
import androidx.compose.material.icons.rounded.FavoriteBorder
import androidx.compose.material.icons.rounded.Mic
import androidx.compose.material.icons.rounded.People
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.PlayCircle
import androidx.compose.material.icons.rounded.PlaylistAdd
import androidx.compose.material.icons.rounded.SkipNext
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.BgMain
import com.revayato.app.core.theme.Brand
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.RevayatoMotion
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.core.theme.motionScale
import com.revayato.app.core.theme.rememberedPressScale
import com.revayato.app.data.model.DownloadLinkDto
import com.revayato.app.data.model.GenreDto
import com.revayato.app.data.model.RatingSourceDto
import com.revayato.app.ui.components.NetworkImage
import java.util.Locale
import kotlin.math.roundToInt

/** Everything the detail hero needs, independent of movie/series response types. */
@Immutable
data class DetailHeroData(
    val isSeries: Boolean,
    val title: String,
    val englishTitle: String,
    val year: Int?,
    val posterUrl: String?,
    val backdropUrl: String?,
    val genres: List<GenreDto>,
    val ageRating: String?,
    val facts: List<String>,
    val freshPills: List<String>,
    val hasSubtitle: Boolean,
    val isDubbed: Boolean,
    val canPlay: Boolean,
    val trailerUrl: String?,
    val ratings: List<RatingSourceDto>,
    val imdbRating: Double?,
    val siteRating: Double?,
    val siteRatingCount: Int,
    val imdbRank: Int?,
) {
    val kindWord: String get() = if (isSeries) "سریال" else "فیلم"
    val hasEnglish: Boolean get() = englishTitle.isNotBlank() && englishTitle != title
}

/** User actions shown as a scrollable row of circular controls. */
class DetailHeroActions(
    val onPlay: () -> Unit,
    val onPlayLatest: (() -> Unit)?,
    val onDownload: (() -> Unit)?,
    val onToggleWatchlist: () -> Unit,
    val onToggleLike: () -> Unit,
    val onWatchTogether: () -> Unit,
    val onAddToCollection: () -> Unit,
    val onGenreClick: (GenreDto) -> Unit,
    val onRate: () -> Unit,
)

/**
 * A full-bleed backdrop, not a poster floating in a card. Kept as a public
 * composable because the detail screens use it as their own fallback canvas.
 */
@Composable
fun DetailBackdrop(
    backdropUrl: String?,
    title: String,
    modifier: Modifier = Modifier,
) {
    Box(modifier = modifier.background(BgElevated)) {
        NetworkImage(
            url = backdropUrl,
            contentDescription = title,
            fallbackText = title,
            modifier = Modifier.fillMaxSize(),
        )
        Box(
            Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        0f to Color.Black.copy(alpha = 0.34f),
                        0.46f to Color.Transparent,
                        0.74f to BgMain.copy(alpha = 0.68f),
                        1f to BgMain,
                    ),
                ),
        )
    }
}

/**
 * Netflix-style RTL hero: the artwork owns the top of the page, the title and
 * actions sit on the bottom scrim, and everything below is quiet. The backdrop
 * breathes in slowly once per title; content rises a few pixels after it, so
 * opening a detail page feels like a reveal rather than a route swap.
 */
@Composable
fun DetailHero(
    data: DetailHeroData,
    inWatchlist: Boolean,
    liked: Boolean,
    actions: DetailHeroActions,
    modifier: Modifier = Modifier,
) {
    val uriHandler = LocalUriHandler.current
    val openTrailer: (() -> Unit)? = data.trailerUrl
        ?.takeIf { it.isNotBlank() }
        ?.let { url -> { runCatching { uriHandler.openUri(url) } } }

    var revealed by remember(data.title) { mutableStateOf(false) }
    LaunchedEffect(data.title) { revealed = true }
    val backdropScale by animateFloatAsState(
        targetValue = if (revealed) 1f else 1.065f,
        animationSpec = tween(durationMillis = 1_350, easing = RevayatoMotion.Decelerate),
        label = "heroBackdropScale",
    )
    val contentAlpha by animateFloatAsState(
        targetValue = if (revealed) 1f else 0f,
        animationSpec = tween(durationMillis = 560, delayMillis = 90, easing = RevayatoMotion.Decelerate),
        label = "heroContentAlpha",
    )
    val contentLift by animateDpAsState(
        targetValue = if (revealed) 0.dp else 24.dp,
        animationSpec = tween(durationMillis = 620, delayMillis = 70, easing = RevayatoMotion.Decelerate),
        label = "heroContentLift",
    )

    BoxWithConstraints(modifier = modifier.fillMaxWidth()) {
        val heroHeight = (maxWidth * 1.18f).coerceIn(400.dp, 520.dp)

        Box(
            Modifier
                .fillMaxWidth()
                .height(heroHeight)
                .background(BgElevated),
        ) {
            DetailBackdrop(
                backdropUrl = data.backdropUrl ?: data.posterUrl,
                title = data.title,
                modifier = Modifier
                    .fillMaxSize()
                    .graphicsLayer {
                        scaleX = backdropScale
                        scaleY = backdropScale
                    },
            )
            // Small extra top scrim so status bar icons and the floating back /
            // report buttons always have contrast on bright stills.
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(96.dp)
                    .background(
                        Brush.verticalGradient(
                            0f to Color.Black.copy(alpha = 0.52f),
                            1f to Color.Transparent,
                        ),
                    ),
            )

            Column(
                modifier = Modifier
                    .align(Alignment.BottomStart)
                    .fillMaxWidth()
                    .padding(horizontal = 20.dp)
                    .padding(bottom = 18.dp)
                    .graphicsLayer {
                        alpha = contentAlpha
                        translationY = contentLift.toPx()
                    },
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                if (data.freshPills.isNotEmpty()) {
                    FreshPill(data.freshPills.first())
                }

                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(
                        text = data.kindWord,
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        color = Color.White.copy(alpha = 0.92f),
                    )
                    data.year?.let {
                        MetaDot()
                        Text(
                            text = toFaDigits(it.toString()),
                            style = MaterialTheme.typography.labelMedium,
                            color = Color.White.copy(alpha = 0.82f),
                        )
                    }
                    data.ageRating?.takeIf { it.isNotBlank() }?.let {
                        Text(
                            text = it,
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.SemiBold,
                            color = Color.White,
                            modifier = Modifier
                                .clip(RoundedCornerShape(4.dp))
                                .border(1.dp, Color.White.copy(alpha = 0.42f), RoundedCornerShape(4.dp))
                                .padding(horizontal = 6.dp, vertical = 2.dp),
                        )
                    }
                    if (data.facts.isNotEmpty()) {
                        MetaDot()
                        Text(
                            text = data.facts.take(3).joinToString(" · "),
                            style = MaterialTheme.typography.labelMedium,
                            color = Color.White.copy(alpha = 0.82f),
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }

                Text(
                    text = data.title.ifBlank { data.englishTitle },
                    style = MaterialTheme.typography.headlineMedium.copy(
                        fontSize = 30.sp,
                        lineHeight = 38.sp,
                    ),
                    fontWeight = FontWeight.Bold,
                    color = Color.White,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                if (data.hasEnglish) {
                    Text(
                        text = data.englishTitle,
                        style = MaterialTheme.typography.labelLarge,
                        color = Color.White.copy(alpha = 0.68f),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }

                if (data.genres.isNotEmpty()) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        data.genres.take(5).forEach { genre ->
                            GenrePill(genre = genre, onClick = { actions.onGenreClick(genre) })
                        }
                    }
                }

                HeroRatings(data = data, onRate = actions.onRate)

                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    if (data.hasSubtitle) {
                        FormatBadge("زیرنویس", Icons.Rounded.ClosedCaption)
                    }
                    if (data.isDubbed) {
                        FormatBadge("دوبله", Icons.Rounded.Mic)
                    }
                }

                Spacer(Modifier.height(2.dp))
                HeroPrimaryButton(
                    data = data,
                    onPlay = {
                        when {
                            data.canPlay -> actions.onPlay()
                            openTrailer != null -> openTrailer.invoke()
                        }
                    },
                )
                Spacer(Modifier.height(2.dp))
                HeroActionRow(
                    data = data,
                    inWatchlist = inWatchlist,
                    liked = liked,
                    actions = actions,
                    onTrailer = openTrailer,
                )
            }
        }
    }
}

@Composable
private fun FreshPill(text: String) {
    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(Color.Black.copy(alpha = 0.34f))
            .border(1.dp, Brand.copy(alpha = 0.48f), RoundedCornerShape(999.dp))
            .padding(horizontal = 10.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Box(
            Modifier
                .size(6.dp)
                .clip(CircleShape)
                .background(Brand),
        )
        Text(
            text = text,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.SemiBold,
            color = Color.White.copy(alpha = 0.92f),
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun MetaDot() {
    Box(
        Modifier
            .size(3.dp)
            .clip(CircleShape)
            .background(Color.White.copy(alpha = 0.48f)),
    )
}

@Composable
private fun FormatBadge(text: String, icon: ImageVector) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Icon(
            imageVector = icon,
            contentDescription = null,
            tint = Color.White.copy(alpha = 0.78f),
            modifier = Modifier.size(14.dp),
        )
        Text(
            text = text,
            style = MaterialTheme.typography.labelSmall,
            color = Color.White.copy(alpha = 0.78f),
        )
    }
}

@Composable
private fun GenrePill(genre: GenreDto, onClick: () -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    val scale = rememberedPressScale(interaction, pressedScale = 0.94f)
    Box(
        modifier = Modifier
            .motionScale(scale)
            .clip(RoundedCornerShape(999.dp))
            .background(Color.White.copy(alpha = 0.12f))
            .border(1.dp, Color.White.copy(alpha = 0.17f), RoundedCornerShape(999.dp))
            .clickable(interactionSource = interaction, indication = null, onClick = onClick)
            .padding(horizontal = 9.dp, vertical = 4.dp),
    ) {
        Text(
            text = genre.title,
            style = MaterialTheme.typography.labelSmall,
            color = Color.White.copy(alpha = 0.88f),
            maxLines = 1,
        )
    }
}

@Composable
private fun HeroRatings(data: DetailHeroData, onRate: () -> Unit) {
    val imdb = data.imdbRating?.takeIf { it > 0 }
    val site = data.siteRating?.takeIf { it > 0 }
    val rank = data.imdbRank?.takeIf { it in 1..250 }
    if (imdb == null && site == null && rank == null) return

    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(9.dp))
            .clickable(onClick = onRate)
            .padding(vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        imdb?.let {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                ImdbBadge()
                Text(
                    text = formatScore(it),
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                    color = Color.White,
                )
            }
        }
        if (site != null) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                Icon(
                    Icons.Rounded.Star,
                    contentDescription = null,
                    tint = Color(0xFFFFC857),
                    modifier = Modifier.size(15.dp),
                )
                Text(
                    text = "${formatScore(site)} از ۵",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = Color.White.copy(alpha = 0.88f),
                )
            }
        }
        if (rank != null) {
            Text(
                text = "Top ${toFaDigits(rank.toString())}",
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.Bold,
                color = Color(0xFFFFC857),
                modifier = Modifier
                    .clip(RoundedCornerShape(4.dp))
                    .background(Color.Black.copy(alpha = 0.28f))
                    .padding(horizontal = 5.dp, vertical = 2.dp),
            )
        }
    }
}

@Composable
private fun ImdbBadge() {
    Text(
        text = "IMDb",
        fontSize = 10.sp,
        fontWeight = FontWeight.Black,
        color = Color(0xFF0B0B0C),
        modifier = Modifier
            .clip(RoundedCornerShape(3.dp))
            .background(Color(0xFFF5C518))
            .padding(horizontal = 4.dp, vertical = 2.dp),
    )
}

@Composable
private fun HeroPrimaryButton(data: DetailHeroData, onPlay: () -> Unit) {
    val enabled = data.canPlay || !data.trailerUrl.isNullOrBlank()
    val interaction = remember { MutableInteractionSource() }
    val scale = rememberedPressScale(interaction, pressedScale = 0.975f)
    val label = when {
        data.canPlay && data.isSeries -> "پخش"
        data.canPlay -> "پخش فیلم"
        !data.trailerUrl.isNullOrBlank() -> "تماشای تریلر"
        else -> "به‌زودی"
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .height(52.dp)
            .motionScale(scale)
            .clip(RoundedCornerShape(13.dp))
            .background(if (enabled) Brand else Color.White.copy(alpha = 0.13f))
            .clickable(
                interactionSource = interaction,
                indication = null,
                enabled = enabled,
                onClick = onPlay,
            ),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center,
    ) {
        Icon(
            imageVector = Icons.Rounded.PlayArrow,
            contentDescription = null,
            tint = if (enabled) OnBrand else Color.White.copy(alpha = 0.55f),
            modifier = Modifier.size(25.dp),
        )
        Spacer(Modifier.width(6.dp))
        Text(
            text = label,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
            color = if (enabled) OnBrand else Color.White.copy(alpha = 0.55f),
        )
    }
}

@Composable
private fun HeroActionRow(
    data: DetailHeroData,
    inWatchlist: Boolean,
    liked: Boolean,
    actions: DetailHeroActions,
    onTrailer: (() -> Unit)?,
) {
    val items = buildList<HeroActionButtonModel> {
        actions.onPlayLatest?.let {
            add(HeroActionButtonModel("آخرین قسمت", Icons.Rounded.SkipNext, false, it))
        }
        actions.onDownload?.let {
            add(HeroActionButtonModel("دانلود", Icons.Rounded.Download, false, it))
        }
        add(
            HeroActionButtonModel(
                label = "لیست من",
                icon = if (inWatchlist) Icons.Rounded.Check else Icons.Rounded.Add,
                active = inWatchlist,
                onClick = actions.onToggleWatchlist,
            ),
        )
        add(
            HeroActionButtonModel(
                label = "پسندیدم",
                icon = if (liked) Icons.Rounded.Favorite else Icons.Rounded.FavoriteBorder,
                active = liked,
                onClick = actions.onToggleLike,
            ),
        )
        add(HeroActionButtonModel("تماشای گروهی", Icons.Rounded.People, false, actions.onWatchTogether))
        add(HeroActionButtonModel("کالکشن", Icons.Rounded.PlaylistAdd, false, actions.onAddToCollection))
        if (onTrailer != null) {
            add(HeroActionButtonModel("تریلر", Icons.Rounded.PlayCircle, false, onTrailer))
        }
    }

    LazyRow(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        items(items, key = { it.label }) { action ->
            HeroActionButton(action)
        }
    }
}

@Composable
private fun HeroActionButton(action: HeroActionButtonModel) {
    val interaction = remember { MutableInteractionSource() }
    val scale = rememberedPressScale(interaction, pressedScale = 0.92f)
    Column(
        modifier = Modifier
            .width(72.dp)
            .motionScale(scale)
            .clip(RoundedCornerShape(14.dp))
            .clickable(interactionSource = interaction, indication = null, onClick = action.onClick)
            .padding(vertical = 2.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        Box(
            modifier = Modifier
                .size(46.dp)
                .clip(CircleShape)
                .background(if (action.active) Brand else Color.Black.copy(alpha = 0.36f))
                .border(
                    width = 1.dp,
                    color = if (action.active) Brand else Color.White.copy(alpha = 0.18f),
                    shape = CircleShape,
                ),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = action.icon,
                contentDescription = action.label,
                tint = if (action.active) OnBrand else Color.White.copy(alpha = 0.94f),
                modifier = Modifier.size(22.dp),
            )
        }
        Text(
            text = action.label,
            style = MaterialTheme.typography.labelSmall,
            color = Color.White.copy(alpha = 0.86f),
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

private data class HeroActionButtonModel(
    val label: String,
    val icon: ImageVector,
    val active: Boolean,
    val onClick: () -> Unit,
)

private fun formatScore(value: Double): String =
    String.format(Locale.US, "%.1f", value).removeSuffix(".0")

internal fun toFaDigits(value: String): String = buildString(value.length) {
    value.forEach { ch ->
        append(if (ch in '0'..'9') '۰' + (ch - '0') else ch)
    }
}

// ---- Hero content builders shared by the movie and series screens ----

private fun twoDigits(value: Int): String = toFaDigits(value.toString().padStart(2, '0'))

private fun newestEpisode(links: List<DownloadLinkDto>): DownloadLinkDto? =
    links.filter { (it.episodeNumber ?: 0) > 0 }
        .maxByOrNull { (it.seasonNumber ?: 1) * 10_000 + (it.episodeNumber ?: 0) }

/** «فصل ۰۴ - قسمت ۰۹ اضافه شد» and friends, from the links actually on the page. */
internal fun freshPills(isSeries: Boolean, links: List<DownloadLinkDto>): List<String> = buildList {
    if (isSeries) {
        newestEpisode(links.filter { it.kind != "dubbed" })?.let {
            add("فصل ${twoDigits(it.seasonNumber ?: 1)} - قسمت ${twoDigits(it.episodeNumber ?: 0)} اضافه شد")
        }
        newestEpisode(links.filter { it.kind == "dubbed" })?.let {
            add("دوبله فصل ${twoDigits(it.seasonNumber ?: 1)} - قسمت ${twoDigits(it.episodeNumber ?: 0)} اضافه شد")
        }
    } else {
        if (links.any { it.kind == "dubbed" }) add("نسخهٔ دوبله فارسی اضافه شد")
        if (links.any { it.kind == "softsub" || it.kind == "hardsub" }) add("زیرنویس فارسی اضافه شد")
    }
}

/** Duration or season count, then the countries. */
internal fun heroFacts(durationMinutes: Int?, seasonCount: Int?, countries: List<String>): List<String> = buildList {
    durationMinutes?.takeIf { it > 0 }?.let { add("${toFaDigits(it.toString())} دقیقه") }
    seasonCount?.takeIf { it > 0 }?.let { add("${toFaDigits(it.toString())} فصل") }
    countries.filter { it.isNotBlank() }.take(2).takeIf { it.isNotEmpty() }?.let { add(it.joinToString("، ")) }
}
