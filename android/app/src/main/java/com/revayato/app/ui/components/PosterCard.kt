package com.revayato.app.ui.components

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ClosedCaption
import androidx.compose.material.icons.rounded.Mic
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.foundation.layout.height
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.revayato.app.R
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.data.model.CatalogCardDto
import java.util.Locale

/**
 * The catalog's one title card, same as the website's: a framed poster with
 * subtitle / dub / play marks stacked in its corner, then the year, the
 * English title and the IMDb + روایتو ratings under it, left-to-right.
 */
@Composable
fun PosterCard(
    item: CatalogCardDto,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    showTitle: Boolean = true,
) {
    val title = item.englishTitle
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(14.dp))
            .background(BgElevated)
            .border(1.dp, OutlineSoft.copy(alpha = 0.7f), RoundedCornerShape(14.dp))
            .clickable(onClick = onClick)
            .padding(start = 6.dp, end = 6.dp, top = 6.dp, bottom = if (showTitle) 8.dp else 6.dp),
        verticalArrangement = Arrangement.spacedBy(7.dp),
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(2f / 3f)
                .clip(RoundedCornerShape(10.dp)),
        ) {
            NetworkImage(
                url = item.posterUrl,
                contentDescription = "پوستر $title",
                fallbackText = title,
                modifier = Modifier.fillMaxSize(),
            )
            item.imdbRank?.let { rank ->
                ImdbRankChip(
                    rank = rank,
                    modifier = Modifier
                        .align(Alignment.TopStart)
                        .padding(6.dp),
                )
            }
            PosterMarks(
                subtitle = item.hasSubtitle,
                dubbed = item.isDubbed,
                playable = item.hasDownloads,
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(6.dp),
            )
        }
        if (showTitle) {
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                Column(
                    Modifier.fillMaxWidth().padding(horizontal = 2.dp),
                    verticalArrangement = Arrangement.spacedBy(3.dp),
                ) {
                    // Every row always takes its space (blank when there is no data)
                    // so every card in a rail or grid is exactly the same size.
                    Text(
                        text = item.year?.let { "($it)" } ?: "",
                        style = MaterialTheme.typography.labelSmall.copy(fontSize = 10.sp, lineHeight = 14.sp),
                        color = TextMuted,
                        maxLines = 1,
                        minLines = 1,
                    )
                    // The full title, never cut: it gets a fixed three-line box
                    // (same height on every card) and steps its size down only as
                    // far as needed to fit — two lines first, three for long names.
                    FitText(
                        text = title,
                        steps = CardTitleSteps,
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = TextPrimary,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(with(LocalDensity.current) { CardTitleBoxHeight.toDp() }),
                    )
                    Box(
                        Modifier
                            .fillMaxWidth()
                            .height(with(LocalDensity.current) { 16.sp.toDp() })
                            .clipToBounds(),
                        contentAlignment = Alignment.CenterStart,
                    ) {
                        CardRatings(item)
                    }
                }
            }
        }
    }
}

/** One try for [FitText]: a font size, its line height and how many lines it may use. */
data class FitStep(val fontSize: TextUnit, val lineHeight: TextUnit, val maxLines: Int)

// Every step fits inside CardTitleBoxHeight (2 × 16sp = 3 × 12sp = 36sp max).
private val CardTitleSteps = listOf(
    FitStep(12.sp, 16.sp, 2),
    FitStep(11.5.sp, 15.5.sp, 2),
    FitStep(11.sp, 15.sp, 2),
    FitStep(10.5.sp, 12.sp, 3),
    FitStep(10.sp, 12.sp, 3),
    FitStep(9.5.sp, 12.sp, 3),
)
private val CardTitleBoxHeight = 36.sp

/**
 * Text that shows in full by trying [steps] in order (largest first) and using
 * the first one whose layout does not overflow its width or line budget. Only if
 * even the last step overflows does it ellipsize, so the box never grows.
 */
@Composable
fun FitText(
    text: String,
    steps: List<FitStep>,
    style: TextStyle,
    modifier: Modifier = Modifier,
    fontWeight: FontWeight? = null,
    color: Color = Color.Unspecified,
) {
    BoxWithConstraints(modifier) {
        val measurer = rememberTextMeasurer()
        val maxWidth = constraints.maxWidth
        val step = remember(text, style, fontWeight, maxWidth, steps) {
            steps.firstOrNull { candidate ->
                !measurer.measure(
                    text = text,
                    style = style.copy(
                        fontSize = candidate.fontSize,
                        lineHeight = candidate.lineHeight,
                        fontWeight = fontWeight ?: style.fontWeight,
                    ),
                    overflow = TextOverflow.Clip,
                    softWrap = true,
                    maxLines = candidate.maxLines,
                    constraints = Constraints(maxWidth = maxWidth),
                ).hasVisualOverflow
            } ?: steps.last()
        }
        Text(
            text = text,
            style = style.copy(fontSize = step.fontSize, lineHeight = step.lineHeight),
            fontWeight = fontWeight,
            color = color,
            maxLines = step.maxLines,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

/**
 * Columns of every poster grid, and the width of every poster card (rails use
 * the same width as a grid cell), so a title card is one size app-wide.
 */
@Composable
fun posterGridColumns(): Int {
    val width = LocalConfiguration.current.screenWidthDp
    return when {
        width >= 840 -> 6
        width >= 600 -> 4
        else -> 3
    }
}

val PosterGridPadding = 16.dp
val PosterGridGap = 12.dp

@Composable
fun posterCardWidth(): Dp {
    val columns = posterGridColumns()
    val screen = LocalConfiguration.current.screenWidthDp.dp
    return (screen - PosterGridPadding * 2 - PosterGridGap * (columns - 1)) / columns
}

/** Round subtitle / dub / play marks, stacked in the poster's top corner. */
@Composable
fun PosterMarks(
    subtitle: Boolean,
    dubbed: Boolean,
    playable: Boolean,
    modifier: Modifier = Modifier,
    size: Dp = 22.dp,
) {
    if (!subtitle && !dubbed && !playable) return
    Column(modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        if (subtitle) PosterMark(Icons.Rounded.ClosedCaption, "زیرنویس فارسی", size)
        if (dubbed) PosterMark(Icons.Rounded.Mic, "دوبله فارسی", size)
        if (playable) PosterMark(Icons.Rounded.PlayArrow, "پخش آنلاین", size)
    }
}

@Composable
private fun PosterMark(icon: ImageVector, label: String, size: Dp) {
    Box(
        Modifier
            .size(size)
            .clip(CircleShape)
            .background(Color(0xA8000000)),
        contentAlignment = Alignment.Center,
    ) {
        Icon(icon, contentDescription = label, tint = Color.White, modifier = Modifier.size(size * 0.6f))
    }
}

/** «IMDb 7.8/10» and «[روایتو] 8.2/10» — the site score only once someone has voted. */
@Composable
private fun CardRatings(item: CatalogCardDto) {
    val external = item.ratings.firstOrNull { it.source == "imdb" && it.value != null }
        ?: item.ratings.firstOrNull { it.source == "tmdb" && it.value != null }
    val externalLabel = if (external?.source == "tmdb") "TMDB" else "IMDb"
    val externalValue = external?.displayValue?.takeIf { it.isNotBlank() }
        ?: item.imdbRating?.takeIf { it > 0 }?.let { formatScore(it) }
    val community = item.siteRating?.takeIf { it > 0 && item.siteRatingCount > 0 }?.let { formatScore(it) }
    if (externalValue == null && community == null) return
    // One row, always: a second line would make this card taller than its neighbours.
    Row(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        externalValue?.let { value ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                Box(
                    Modifier
                        .clip(RoundedCornerShape(3.dp))
                        .background(if (externalLabel == "IMDb") Color(0xFFF5C518) else Color(0xFF90CEA1))
                        .padding(horizontal = 3.dp),
                ) {
                    Text(
                        externalLabel,
                        style = MaterialTheme.typography.labelSmall.copy(fontSize = 9.sp),
                        fontWeight = FontWeight.Black,
                        color = Color(0xFF0B0B0C),
                    )
                }
                ScoreText(value)
            }
        }
        community?.let { value ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                Image(
                    painter = painterResource(R.drawable.brand_logo),
                    contentDescription = "امتیاز کاربران روایتو",
                    modifier = Modifier.size(width = 11.dp, height = 14.dp),
                )
                ScoreText(value)
            }
        }
    }
}

@Composable
private fun ScoreText(value: String) {
    Text(
        text = buildAnnotatedString {
            withStyle(SpanStyle(color = TextPrimary, fontWeight = FontWeight.Bold)) { append(value) }
            withStyle(SpanStyle(color = TextMuted, fontSize = 9.sp)) { append("/10") }
        },
        style = MaterialTheme.typography.labelSmall,
        maxLines = 1,
    )
}

private fun formatScore(value: Double): String =
    String.format(Locale.US, "%.1f", value).removeSuffix(".0")

@Composable
fun RatingBadge(rating: Double, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .background(Color(0xCC0D0D0D))
            .padding(horizontal = 6.dp, vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        Icon(
            imageVector = Icons.Rounded.Star,
            contentDescription = null,
            tint = Color(0xFFF5C518),
            modifier = Modifier.size(12.dp),
        )
        Text(
            text = String.format("%.1f", rating),
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.SemiBold,
            color = Color.White,
        )
    }
}

/** «IMDb #12» — the chart position of a Top 250 title, in IMDb's own yellow. */
@Composable
fun ImdbRankChip(rank: Int, modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(6.dp))
            .background(Color(0xFFF5C518))
            .padding(horizontal = 6.dp, vertical = 2.dp),
    ) {
        Text(
            text = "IMDb #$rank",
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Black,
            color = Color(0xFF0B0B0C),
        )
    }
}
