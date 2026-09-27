package com.revayato.app.feature.detail

import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Bookmark
import androidx.compose.material.icons.rounded.BookmarkBorder
import androidx.compose.material.icons.rounded.Download
import androidx.compose.material.icons.rounded.Favorite
import androidx.compose.material.icons.rounded.FavoriteBorder
import androidx.compose.material.icons.rounded.Groups
import androidx.compose.material.icons.rounded.LibraryAdd
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.revayato.app.core.theme.AccentBlue
import com.revayato.app.core.theme.AccentBlueSoft
import com.revayato.app.core.theme.AccentRed
import com.revayato.app.core.theme.AccentRedSoft
import com.revayato.app.core.theme.AccentYellow
import com.revayato.app.core.theme.AccentYellowSoft
import com.revayato.app.core.theme.BgMain
import com.revayato.app.core.theme.BrandGreen
import com.revayato.app.core.theme.BrandMint
import com.revayato.app.core.theme.DownloadAccent
import com.revayato.app.core.theme.DownloadAccentSoft
import com.revayato.app.core.theme.NeutralSurface
import com.revayato.app.core.theme.NeutralSurfaceActive
import com.revayato.app.core.theme.OnPlayAccent
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.PlayAccent
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.data.model.CastMemberDto
import com.revayato.app.data.model.GenreDto
import com.revayato.app.data.model.PersonDto
import com.revayato.app.ui.components.NetworkImage
import com.revayato.app.ui.components.RatingBadge

/**
 * Adds a spring-driven press-shrink to any interactive element (uiverse-style
 * tactile feedback). Pair with a no-ripple [clickable] using the same
 * interaction source so the whole tile reacts to touch as one object.
 */
@Composable
private fun Modifier.pressScale(pressed: Boolean, min: Float = 0.93f): Modifier {
    val scale by animateFloatAsState(
        targetValue = if (pressed) min else 1f,
        animationSpec = spring(dampingRatio = 0.55f, stiffness = 600f),
        label = "pressScale",
    )
    return this.graphicsLayer { scaleX = scale; scaleY = scale }
}

/**
 * A cinematic backdrop with a slow, endless Ken-Burns drift and a brand-toned
 * vertical scrim that melts the image into the page background so the title and
 * meta below read cleanly over it.
 */
@Composable
fun DetailBackdrop(
    backdropUrl: String?,
    posterUrl: String?,
    title: String,
    modifier: Modifier = Modifier,
) {
    val drift = rememberInfiniteTransition(label = "backdropDrift")
    val zoom by drift.animateFloat(
        initialValue = 1f,
        targetValue = 1.08f,
        animationSpec = infiniteRepeatable(
            animation = tween(16000, easing = LinearEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "zoom",
    )
    Box(modifier = modifier.fillMaxWidth()) {
        NetworkImage(
            url = backdropUrl,
            contentDescription = title,
            fallbackText = title,
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(16f / 9f)
                .graphicsLayer { scaleX = zoom; scaleY = zoom },
        )
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(16f / 9f)
                .background(
                    Brush.verticalGradient(
                        0.0f to Color.Transparent,
                        0.55f to BgMain.copy(alpha = 0.35f),
                        1f to BgMain,
                    ),
                ),
        )
    }
}

/**
 * Cinematic hero header: a rounded, floating poster card that overlaps the
 * backdrop, with the title, secondary title and meta line rising in beside it.
 * The whole block eases in once on first composition for a polished entrance.
 */
@Composable
fun PosterHeader(
    posterUrl: String?,
    title: String,
    secondaryTitle: String?,
    year: Int?,
    rating: Double?,
    durationMinutes: Int?,
    ageRating: String?,
    modifier: Modifier = Modifier,
) {
    var shown by remember { mutableStateOf(false) }
    androidx.compose.runtime.LaunchedEffect(Unit) { shown = true }
    val reveal by animateFloatAsState(
        targetValue = if (shown) 1f else 0f,
        animationSpec = tween(520, easing = FastOutSlowInEasing),
        label = "heroReveal",
    )
    Row(
        modifier = modifier
            .fillMaxWidth()
            .graphicsLayer {
                alpha = reveal
                translationY = (1f - reveal) * 40f
            },
        horizontalArrangement = Arrangement.spacedBy(14.dp),
        verticalAlignment = Alignment.Bottom,
    ) {
        NetworkImage(
            url = posterUrl,
            contentDescription = title,
            fallbackText = title,
            modifier = Modifier
                .width(104.dp)
                .aspectRatio(2f / 3f)
                .shadow(18.dp, RoundedCornerShape(14.dp), clip = false)
                .clip(RoundedCornerShape(14.dp)),
        )
        Column(
            modifier = Modifier.weight(1f).padding(bottom = 4.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                color = TextPrimary,
            )
            secondaryTitle?.takeIf { it.isNotBlank() }?.let {
                Text(
                    text = it,
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextMuted,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            MetaRow(
                year = year,
                rating = rating,
                durationMinutes = durationMinutes,
                ageRating = ageRating,
            )
        }
    }
}

@Composable
fun MetaRow(
    year: Int?,
    rating: Double?,
    durationMinutes: Int?,
    ageRating: String?,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier,
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        rating?.takeIf { it > 0 }?.let { RatingBadge(it) }
        year?.let { MetaText(it.toString()) }
        durationMinutes?.takeIf { it > 0 }?.let { MetaText("${it} دقیقه") }
        ageRating?.takeIf { it.isNotBlank() }?.let {
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(4.dp))
                    .background(NeutralSurfaceActive)
                    .padding(horizontal = 6.dp, vertical = 2.dp),
            ) { MetaText(it) }
        }
    }
}

@Composable
private fun MetaText(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.labelMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

// The home accent trio, cycled across genre chips to give the row a lively,
// branded rhythm (mirrors the web discovery shelves).
private val GenreAccents = listOf(
    AccentYellow to AccentYellowSoft,
    AccentRed to AccentRedSoft,
    AccentBlue to AccentBlueSoft,
)

@Composable
fun GenreChips(
    genres: List<GenreDto>,
    modifier: Modifier = Modifier,
    onGenreClick: ((GenreDto) -> Unit)? = null,
) {
    if (genres.isEmpty()) return
    LazyRow(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items(genres, key = { it.id }) { g ->
            val (fg, bg) = GenreAccents[g.id % GenreAccents.size]
            val interaction = remember { MutableInteractionSource() }
            val pressed by interaction.collectIsPressedAsState()
            var base = Modifier
                .clip(RoundedCornerShape(999.dp))
                .background(bg)
                .then(
                    if (onGenreClick != null) {
                        Modifier.clickable(
                            interactionSource = interaction,
                            indication = null,
                        ) { onGenreClick(g) }
                    } else Modifier,
                )
                .padding(horizontal = 14.dp, vertical = 7.dp)
            if (onGenreClick != null) base = base.pressScale(pressed)
            Box(modifier = base) {
                Text(
                    text = g.title,
                    style = MaterialTheme.typography.labelMedium,
                    color = fg,
                    fontWeight = FontWeight.SemiBold,
                )
            }
        }
    }
}

/**
 * Snackbar text shown after a title is added to the watchlist. Shared by the movie
 * and series detail view-models (which set it) and their screens (which, on this
 * exact message, attach a «مشاهده» action that jumps to the library tab). Keeping it
 * a single const means the screen's match can never silently drift from the VM's text.
 */
internal const val MSG_ADDED_TO_WATCHLIST = "به لیست تماشا اضافه شد"

@Composable
fun PrimaryActions(
    canPlay: Boolean,
    inWatchlist: Boolean,
    liked: Boolean,
    hasDownloads: Boolean,
    onPlay: () -> Unit,
    onToggleWatchlist: () -> Unit,
    onToggleLike: () -> Unit,
    onDownload: () -> Unit,
    onWatchTogether: () -> Unit,
    onAddToCollection: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        // The two primary actions get two deliberately different, meaning-bound
        // accents: emerald for online play ("go"), azure for download (offline).
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            PlayButton(
                canPlay = canPlay,
                onPlay = onPlay,
                modifier = Modifier.weight(1f),
            )
            if (hasDownloads) {
                val interaction = remember { MutableInteractionSource() }
                val pressed by interaction.collectIsPressedAsState()
                Row(
                    modifier = Modifier
                        .height(52.dp)
                        .clip(RoundedCornerShape(14.dp))
                        .background(DownloadAccentSoft)
                        .clickable(interactionSource = interaction, indication = null, onClick = onDownload)
                        .pressScale(pressed)
                        .padding(horizontal = 20.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.Rounded.Download, contentDescription = null, tint = DownloadAccent)
                    Spacer(Modifier.width(8.dp))
                    Text(
                        text = "دانلود",
                        color = DownloadAccent,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                    )
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            ActionChip(
                icon = if (inWatchlist) Icons.Rounded.Bookmark else Icons.Rounded.BookmarkBorder,
                label = "لیست من",
                active = inWatchlist,
                onClick = onToggleWatchlist,
                modifier = Modifier.weight(1f),
            )
            ActionChip(
                icon = if (liked) Icons.Rounded.Favorite else Icons.Rounded.FavoriteBorder,
                label = "پسندیدن",
                active = liked,
                onClick = onToggleLike,
                modifier = Modifier.weight(1f),
            )
            ActionChip(
                icon = Icons.Rounded.Groups,
                label = "گروهی",
                active = false,
                onClick = onWatchTogether,
                modifier = Modifier.weight(1f),
            )
            ActionChip(
                icon = Icons.Rounded.LibraryAdd,
                label = "کالکشن",
                active = false,
                onClick = onAddToCollection,
                modifier = Modifier.weight(1f),
            )
        }
    }
}

/**
 * The hero play button. When playable it wears a living brand gradient with a
 * soft sheen that sweeps across it (uiverse-inspired), so the primary action
 * always draws the eye; disabled it collapses to a quiet neutral surface.
 */
@Composable
private fun PlayButton(
    canPlay: Boolean,
    onPlay: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val shimmer = rememberInfiniteTransition(label = "playShimmer")
    val sweep by shimmer.animateFloat(
        initialValue = -1f,
        targetValue = 2f,
        animationSpec = infiniteRepeatable(
            animation = tween(2600, easing = LinearEasing),
            repeatMode = RepeatMode.Restart,
        ),
        label = "sweep",
    )
    val shape = RoundedCornerShape(14.dp)
    val background = if (canPlay) {
        Modifier.background(Brush.horizontalGradient(listOf(PlayAccent, BrandMint, BrandGreen)))
    } else {
        Modifier.background(NeutralSurface)
    }
    Row(
        modifier = modifier
            .height(52.dp)
            .clip(shape)
            .then(background)
            .then(
                if (canPlay) {
                    Modifier.drawWithContent {
                        drawContent()
                        // A narrow diagonal highlight that travels left→right.
                        val x = size.width * sweep
                        drawRect(
                            brush = Brush.horizontalGradient(
                                colors = listOf(
                                    Color.Transparent,
                                    Color.White.copy(alpha = 0.28f),
                                    Color.Transparent,
                                ),
                                startX = x - size.width * 0.25f,
                                endX = x + size.width * 0.25f,
                            ),
                            blendMode = BlendMode.SrcOver,
                        )
                    }
                } else Modifier,
            )
            .clickable(
                interactionSource = interaction,
                indication = null,
                enabled = canPlay,
                onClick = onPlay,
            )
            .pressScale(pressed)
            .padding(horizontal = 20.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.Center,
    ) {
        Icon(
            Icons.Rounded.PlayArrow,
            contentDescription = null,
            tint = if (canPlay) OnPlayAccent else TextMuted,
        )
        Spacer(Modifier.width(8.dp))
        Text(
            text = if (canPlay) "پخش آنلاین" else "لینک پخش موجود نیست",
            color = if (canPlay) OnPlayAccent else TextMuted,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun ActionChip(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    active: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(12.dp))
            .background(if (active) NeutralSurfaceActive else NeutralSurface)
            .clickable(interactionSource = interaction, indication = null, onClick = onClick)
            .pressScale(pressed)
            .padding(vertical = 10.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Icon(
            imageVector = icon,
            contentDescription = label,
            tint = if (active) TextPrimary else MaterialTheme.colorScheme.onSurface,
            modifier = Modifier.size(22.dp),
        )
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = if (active) TextPrimary else MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
fun ExpandableText(
    text: String,
    modifier: Modifier = Modifier,
    collapsedLines: Int = 4,
) {
    var expanded by remember { mutableStateOf(false) }
    Column(
        modifier = modifier
            .fillMaxWidth()
            .clickable { expanded = !expanded }
            .animateContentSize(),
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            maxLines = if (expanded) Int.MAX_VALUE else collapsedLines,
            overflow = TextOverflow.Ellipsis,
        )
        if (!expanded) {
            Text(
                text = "بیشتر",
                style = MaterialTheme.typography.labelMedium,
                color = BrandMint,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
    }
}

/**
 * Horizontal cast strip. Each face is a tappable tile that opens the actor's
 * page when a slug is available.
 */
@Composable
fun CastRow(
    cast: List<CastMemberDto>,
    modifier: Modifier = Modifier,
    onActorClick: ((slug: String) -> Unit)? = null,
) {
    if (cast.isEmpty()) return
    LazyRow(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        items(cast, key = { it.id }) { member ->
            val slug = member.actor?.slug
            val interaction = remember { MutableInteractionSource() }
            val pressed by interaction.collectIsPressedAsState()
            val clickable = onActorClick != null && !slug.isNullOrBlank()
            Column(
                modifier = Modifier
                    .width(76.dp)
                    .then(
                        if (clickable) {
                            Modifier
                                .clip(RoundedCornerShape(12.dp))
                                .clickable(interactionSource = interaction, indication = null) {
                                    onActorClick!!(slug!!)
                                }
                                .pressScale(pressed)
                        } else Modifier,
                    )
                    .padding(vertical = 4.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                NetworkImage(
                    url = member.actor?.profileUrl ?: member.actor?.photo,
                    contentDescription = member.actor?.name,
                    fallbackText = member.actor?.name,
                    modifier = Modifier
                        .size(66.dp)
                        .clip(CircleShape),
                )
                Text(
                    text = member.actor?.name.orEmpty(),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurface,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                if (member.role.isNotBlank()) {
                    Text(
                        text = member.role,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
    }
}

/**
 * A tappable pill for a single crew credit (director/writer). Shows a small
 * round photo when available and opens the person's page on tap.
 */
@Composable
fun PeoplePills(
    people: List<PersonDto>,
    modifier: Modifier = Modifier,
    onPersonClick: ((slug: String) -> Unit)? = null,
) {
    if (people.isEmpty()) return
    LazyRow(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        items(people, key = { it.id }) { person ->
            val interaction = remember { MutableInteractionSource() }
            val pressed by interaction.collectIsPressedAsState()
            val clickable = onPersonClick != null && person.slug.isNotBlank()
            Row(
                modifier = Modifier
                    .clip(RoundedCornerShape(999.dp))
                    .background(NeutralSurface)
                    .then(
                        if (clickable) {
                            Modifier
                                .clickable(interactionSource = interaction, indication = null) {
                                    onPersonClick!!(person.slug)
                                }
                                .pressScale(pressed)
                        } else Modifier,
                    )
                    .padding(start = 6.dp, end = 14.dp, top = 6.dp, bottom = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                NetworkImage(
                    url = person.profileUrl ?: person.photo,
                    contentDescription = person.name,
                    fallbackText = person.name,
                    modifier = Modifier
                        .size(30.dp)
                        .clip(CircleShape),
                )
                Text(
                    text = person.name,
                    style = MaterialTheme.typography.labelMedium,
                    color = TextSecondary,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

/**
 * A quiet «مشخصات» facts card: label→value rows (country, language, format,
 * IMDb id, view count …). Only non-empty rows are passed in, so the card never
 * shows blanks.
 */
@Composable
fun DetailFacts(
    facts: List<Pair<String, String>>,
    modifier: Modifier = Modifier,
) {
    if (facts.isEmpty()) return
    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(NeutralSurface)
            .padding(horizontal = 16.dp, vertical = 4.dp),
    ) {
        facts.forEachIndexed { index, (label, value) ->
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(16.dp),
                verticalAlignment = Alignment.Top,
            ) {
                Text(
                    text = label,
                    style = MaterialTheme.typography.labelMedium,
                    color = TextMuted,
                    modifier = Modifier.width(88.dp),
                )
                Text(
                    text = value,
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextPrimary,
                    modifier = Modifier.weight(1f),
                )
            }
            if (index != facts.lastIndex) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(1.dp)
                        .background(OutlineSoft.copy(alpha = 0.5f)),
                )
            }
        }
    }
}
