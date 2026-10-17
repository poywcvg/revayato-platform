package com.revayato.app.feature.detail

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Bookmark
import androidx.compose.material.icons.rounded.BookmarkBorder
import androidx.compose.material.icons.rounded.Download
import androidx.compose.material.icons.rounded.EmojiEvents
import androidx.compose.material.icons.rounded.Favorite
import androidx.compose.material.icons.rounded.FavoriteBorder
import androidx.compose.material.icons.rounded.Groups
import androidx.compose.material.icons.rounded.LibraryAdd
import androidx.compose.material.icons.rounded.Movie
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.SkipNext
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material.icons.rounded.StarOutline
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.revayato.app.R
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.BgMain
import com.revayato.app.core.theme.Brand
import com.revayato.app.core.theme.NeutralSurface
import com.revayato.app.core.theme.NeutralSurfaceActive
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.StarGold
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.data.model.DownloadLinkDto
import com.revayato.app.data.model.GenreDto
import com.revayato.app.data.model.RatingSourceDto
import com.revayato.app.feature.support.toFaDigits
import com.revayato.app.ui.components.NetworkImage
import com.revayato.app.ui.components.PosterMarks
import java.util.Locale

/*
 * The movie / series hero, laid out like the website's: a sharp backdrop, the
 * titled poster with its subtitle/dub/play marks and a play button on it,
 * «دانلود فیلم Inception» over «تلقین (2010)», a «ژانر:» line and facts, the
 * «… اضافه شد» freshness pills, one amber play button plus square tools, and
 * the ratings cluster (IMDb, روایتو, a 10-star row, the Top 250 place).
 */

/** Everything the hero shows, built once per title by the screen. */
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

/** The hero's buttons, wired by the movie and series screens. */
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

/** A sharp, still backdrop that only darkens at its lower edge, where the poster overlaps it. */
@Composable
fun DetailBackdrop(
    backdropUrl: String?,
    title: String,
    modifier: Modifier = Modifier,
) {
    Box(modifier = modifier.fillMaxWidth().aspectRatio(16f / 9f)) {
        NetworkImage(
            url = backdropUrl,
            contentDescription = "تصویر زمینه $title",
            fallbackText = title,
            modifier = Modifier.fillMaxSize(),
        )
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        0.0f to Color.Black.copy(alpha = 0.25f),
                        0.3f to Color.Transparent,
                        0.62f to Color.Transparent,
                        1f to BgMain,
                    ),
                ),
        )
    }
}

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
        ?.takeIf { it.startsWith("http") }
        ?.let { url -> { runCatching { uriHandler.openUri(url) } } }

    // The content column starts 56dp above the backdrop's bottom edge so the
    // poster overlaps it — padding, not offset, so no gap is left underneath.
    BoxWithConstraints(modifier.fillMaxWidth()) {
        DetailBackdrop(backdropUrl = data.backdropUrl ?: data.posterUrl, title = data.title)
        Column(
            Modifier
                .fillMaxWidth()
                .padding(top = maxWidth * 9f / 16f - 56.dp)
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.Bottom) {
                HeroPoster(
                    data = data,
                    onPlay = if (data.canPlay) actions.onPlay else openTrailer,
                    playLabel = if (data.canPlay) "پخش آنلاین" else "پخش تریلر",
                )
                HeroHeading(data = data, onGenreClick = actions.onGenreClick, modifier = Modifier.weight(1f))
            }

            if (data.freshPills.isNotEmpty()) FreshPills(data.freshPills)

            HeroActions(
                canPlay = data.canPlay,
                inWatchlist = inWatchlist,
                liked = liked,
                actions = actions,
                onTrailer = openTrailer,
            )

            HeroRatings(data = data, onRate = actions.onRate)
        }
    }
}

@Composable
private fun HeroPoster(data: DetailHeroData, onPlay: (() -> Unit)?, playLabel: String) {
    Box(
        Modifier
            .width(118.dp)
            .aspectRatio(2f / 3f)
            .clip(RoundedCornerShape(12.dp))
            .border(1.dp, OutlineSoft, RoundedCornerShape(12.dp)),
    ) {
        NetworkImage(
            url = data.posterUrl,
            contentDescription = "پوستر ${data.title}",
            fallbackText = data.title,
            modifier = Modifier.fillMaxSize(),
        )
        PosterMarks(
            subtitle = data.hasSubtitle,
            dubbed = data.isDubbed,
            playable = data.canPlay,
            modifier = Modifier.align(Alignment.TopEnd).padding(6.dp),
        )
        if (onPlay != null) {
            Box(
                Modifier
                    .align(Alignment.Center)
                    .size(46.dp)
                    .clip(CircleShape)
                    .background(Color.Black.copy(alpha = 0.6f))
                    .border(1.5.dp, Color.White.copy(alpha = 0.85f), CircleShape)
                    .clickable(onClick = onPlay)
                    .semantics { contentDescription = playLabel },
                contentAlignment = Alignment.Center,
            ) {
                Icon(Icons.Rounded.PlayArrow, contentDescription = null, tint = Color.White, modifier = Modifier.size(28.dp))
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun HeroHeading(data: DetailHeroData, onGenreClick: (GenreDto) -> Unit, modifier: Modifier = Modifier) {
    Column(modifier.padding(bottom = 2.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        // «دانلود فیلم Inception» — both names, as people search for either.
        Text(
            text = buildAnnotatedString {
                withStyle(SpanStyle(color = TextSecondary, fontWeight = FontWeight.Medium, fontSize = 14.sp)) {
                    append("دانلود ${data.kindWord} ")
                }
                // LRI … PDI keeps the Latin title's own order inside the RTL line.
                append(if (data.hasEnglish) "⁦${data.englishTitle}⁩" else data.title)
            },
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold,
            color = TextPrimary,
            maxLines = 3,
            overflow = TextOverflow.Ellipsis,
        )
        val subtitle = listOfNotNull(
            data.title.takeIf { data.hasEnglish },
            data.year?.let { "⁦($it)⁩" },
        ).joinToString(" ")
        if (subtitle.isNotBlank()) {
            Text(subtitle, style = MaterialTheme.typography.bodyMedium, color = TextMuted, maxLines = 2)
        }
        if (data.genres.isNotEmpty()) {
            FlowRow(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("ژانر: ", style = MaterialTheme.typography.labelLarge, color = TextMuted)
                val shown = data.genres.take(4)
                shown.forEachIndexed { index, genre ->
                    Text(
                        text = genre.title + if (index < shown.lastIndex) "، " else "",
                        style = MaterialTheme.typography.labelLarge,
                        color = TextPrimary,
                        modifier = Modifier.clickable { onGenreClick(genre) },
                    )
                }
            }
        }
        val age = data.ageRating?.takeIf { it.isNotBlank() }
        if (age != null || data.facts.isNotEmpty()) {
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                age?.let {
                    Box(
                        Modifier
                            .clip(RoundedCornerShape(4.dp))
                            .border(1.dp, OutlineSoft, RoundedCornerShape(4.dp))
                            .padding(horizontal = 5.dp, vertical = 1.dp),
                    ) { Text(it, style = MaterialTheme.typography.labelSmall, color = TextSecondary) }
                }
                data.facts.forEach { fact ->
                    Text(fact, style = MaterialTheme.typography.labelMedium, color = TextSecondary)
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun FreshPills(pills: List<String>) {
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        pills.forEach { pill ->
            Row(
                Modifier
                    .clip(RoundedCornerShape(999.dp))
                    .background(Brand.copy(alpha = 0.12f))
                    .padding(horizontal = 10.dp, vertical = 5.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(5.dp),
            ) {
                Icon(Icons.Rounded.Refresh, contentDescription = null, tint = Brand, modifier = Modifier.size(14.dp))
                Text(pill, style = MaterialTheme.typography.labelMedium, color = TextPrimary)
            }
        }
    }
}

@Composable
private fun HeroActions(
    canPlay: Boolean,
    inWatchlist: Boolean,
    liked: Boolean,
    actions: DetailHeroActions,
    onTrailer: (() -> Unit)?,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            // The one filled button: flat brand amber, no gradient, no sheen.
            Row(
                Modifier
                    .weight(1f)
                    .height(50.dp)
                    .clip(RoundedCornerShape(14.dp))
                    .background(if (canPlay) Brand else NeutralSurface)
                    .clickable(enabled = canPlay, onClick = actions.onPlay)
                    .padding(horizontal = 14.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.Center,
            ) {
                Icon(Icons.Rounded.PlayArrow, contentDescription = null, tint = if (canPlay) OnBrand else TextMuted)
                Spacer(Modifier.width(6.dp))
                Text(
                    if (canPlay) "تماشای آنلاین" else "لینک پخش موجود نیست",
                    color = if (canPlay) OnBrand else TextMuted,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            actions.onPlayLatest?.let { onLatest ->
                Row(
                    Modifier
                        .weight(1f)
                        .height(50.dp)
                        .clip(RoundedCornerShape(14.dp))
                        .background(NeutralSurface)
                        .border(1.dp, OutlineSoft, RoundedCornerShape(14.dp))
                        .clickable(onClick = onLatest)
                        .padding(horizontal = 12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.Center,
                ) {
                    Icon(Icons.Rounded.SkipNext, contentDescription = null, tint = TextPrimary)
                    Spacer(Modifier.width(6.dp))
                    Text(
                        "تماشای آخرین قسمت",
                        color = TextPrimary,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            actions.onDownload?.let { ToolButton(Icons.Rounded.Download, "دانلود", false, it, Modifier.weight(1f)) }
            ToolButton(
                if (inWatchlist) Icons.Rounded.Bookmark else Icons.Rounded.BookmarkBorder,
                "لیست من", inWatchlist, actions.onToggleWatchlist, Modifier.weight(1f),
            )
            ToolButton(
                if (liked) Icons.Rounded.Favorite else Icons.Rounded.FavoriteBorder,
                "پسندیدن", liked, actions.onToggleLike, Modifier.weight(1f),
            )
            onTrailer?.let { ToolButton(Icons.Rounded.Movie, "تریلر", false, it, Modifier.weight(1f)) }
            ToolButton(Icons.Rounded.Groups, "گروهی", false, actions.onWatchTogether, Modifier.weight(1f))
            ToolButton(Icons.Rounded.LibraryAdd, "کالکشن", false, actions.onAddToCollection, Modifier.weight(1f))
        }
    }
}

/** A square neutral tool button with its name under the icon. */
@Composable
private fun ToolButton(
    icon: ImageVector,
    label: String,
    active: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier
            .clip(RoundedCornerShape(12.dp))
            .clickable(onClick = onClick)
            .padding(vertical = 4.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        Box(
            Modifier
                .size(46.dp)
                .clip(RoundedCornerShape(12.dp))
                .background(if (active) NeutralSurfaceActive else NeutralSurface)
                .border(1.dp, if (active) Brand.copy(alpha = 0.5f) else OutlineSoft, RoundedCornerShape(12.dp)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(icon, contentDescription = null, tint = if (active) Brand else TextPrimary, modifier = Modifier.size(22.dp))
        }
        Text(label, style = MaterialTheme.typography.labelSmall, color = TextSecondary, maxLines = 1)
    }
}

/**
 * IMDb and روایتو side by side (score + votes), the other sources small under
 * them, the community average as a 10-star row (tap → rate it below) and the
 * IMDb Top 250 place when the title has one.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun HeroRatings(data: DetailHeroData, onRate: () -> Unit) {
    val external = data.ratings.filter { it.source != "site" && it.value != null }
    val imdb = external.firstOrNull { it.source == "imdb" }
    val imdbValue = imdb?.value ?: data.imdbRating?.takeIf { it > 0 }
    val minor = external.filter { it.source != "imdb" }.take(3)
    val site = data.siteRating?.takeIf { it > 0 && data.siteRatingCount > 0 }
    val filledStars = site?.let { Math.round(it).toInt() } ?: 0
    val rank = data.imdbRank?.takeIf { it in 1..250 }

    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(BgElevated)
            .border(1.dp, OutlineSoft.copy(alpha = 0.7f), RoundedCornerShape(16.dp))
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            if (imdbValue != null) {
                RateBlock(
                    logo = { ImdbLogo() },
                    score = imdbValue,
                    caption = imdb?.voteCount?.takeIf { it > 0 }?.let { "${toFaDigits("%,d".format(Locale.US, it))} رأی" } ?: "IMDb",
                    modifier = Modifier.weight(1f),
                )
            }
            RateBlock(
                logo = {
                    Image(
                        painter = painterResource(R.drawable.brand_logo),
                        contentDescription = null,
                        modifier = Modifier.size(width = 26.dp, height = 32.dp),
                    )
                },
                score = site,
                caption = if (site != null) "${toFaDigits(data.siteRatingCount.toString())} رأی" else "هنوز رأیی نیست",
                onClick = onRate,
                modifier = Modifier.weight(1f),
            )
        }

        if (minor.isNotEmpty()) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                minor.forEach { rating ->
                    Row(
                        Modifier
                            .clip(RoundedCornerShape(8.dp))
                            .background(NeutralSurface)
                            .padding(horizontal = 8.dp, vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Text(sourceLabel(rating.source), style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, color = TextMuted)
                        Text(
                            rating.displayValue.ifBlank { formatScore(rating.value ?: 0.0) },
                            style = MaterialTheme.typography.labelMedium,
                            color = TextPrimary,
                        )
                    }
                }
            }
        }

        // Stars run left-to-right like the score they picture.
        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
            Row(
                Modifier
                    .clip(RoundedCornerShape(8.dp))
                    .clickable(onClick = onRate)
                    .semantics { contentDescription = "امتیاز بدهید — میانگین کاربران ${toFaDigits(filledStars.toString())} از ۱۰" }
                    .padding(vertical = 2.dp),
                horizontalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                repeat(10) { index ->
                    val on = index < filledStars
                    Icon(
                        if (on) Icons.Rounded.Star else Icons.Rounded.StarOutline,
                        contentDescription = null,
                        tint = if (on) StarGold else TextMuted.copy(alpha = 0.6f),
                        modifier = Modifier.size(20.dp),
                    )
                }
            }
        }

        rank?.let {
            Row(
                Modifier
                    .clip(RoundedCornerShape(999.dp))
                    .background(StarGold.copy(alpha = 0.12f))
                    .padding(horizontal = 10.dp, vertical = 5.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Icon(Icons.Rounded.EmojiEvents, contentDescription = null, tint = StarGold, modifier = Modifier.size(16.dp))
                Text(
                    buildAnnotatedString {
                        withStyle(SpanStyle(fontWeight = FontWeight.Black)) { append(toFaDigits(it.toString())) }
                        append(" جزو ۲۵۰ ${data.kindWord} برتر")
                    },
                    style = MaterialTheme.typography.labelMedium,
                    color = TextPrimary,
                )
            }
        }
    }
}

@Composable
private fun RateBlock(
    logo: @Composable () -> Unit,
    score: Double?,
    caption: String,
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
) {
    Row(
        modifier
            .clip(RoundedCornerShape(12.dp))
            .background(NeutralSurface)
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(horizontal = 10.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        logo()
        Column {
            Text(
                text = if (score == null) buildAnnotatedString { append("—") } else buildAnnotatedString {
                    withStyle(SpanStyle(fontWeight = FontWeight.Black, color = TextPrimary)) { append(formatScore(score)) }
                    withStyle(SpanStyle(color = TextMuted, fontSize = 11.sp)) { append("/10") }
                },
                style = MaterialTheme.typography.titleMedium,
                color = TextPrimary,
            )
            Text(caption, style = MaterialTheme.typography.labelSmall, color = TextMuted, maxLines = 1)
        }
    }
}

@Composable
private fun ImdbLogo() {
    Box(
        Modifier
            .clip(RoundedCornerShape(5.dp))
            .background(StarGold)
            .padding(horizontal = 5.dp, vertical = 3.dp),
    ) {
        Text("IMDb", fontSize = 12.sp, fontWeight = FontWeight.Black, color = Color(0xFF0B0B0C))
    }
}

private fun sourceLabel(source: String): String = when (source) {
    "tmdb" -> "TMDB"
    "rotten_tomatoes", "rottentomatoes" -> "Rotten Tomatoes"
    "metacritic" -> "Metacritic"
    "letterboxd" -> "Letterboxd"
    else -> source.replaceFirstChar { it.uppercase() }
}

private fun formatScore(value: Double): String =
    String.format(Locale.US, "%.1f", value).removeSuffix(".0")

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
