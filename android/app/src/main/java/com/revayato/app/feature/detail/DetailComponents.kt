package com.revayato.app.feature.detail

import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CalendarMonth
import androidx.compose.material.icons.rounded.FormatListNumbered
import androidx.compose.material.icons.rounded.HighQuality
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.LiveTv
import androidx.compose.material.icons.rounded.Movie
import androidx.compose.material.icons.rounded.Public
import androidx.compose.material.icons.rounded.Schedule
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material.icons.rounded.Subtitles
import androidx.compose.material.icons.rounded.Translate
import androidx.compose.material.icons.rounded.Visibility
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.revayato.app.core.theme.AccentBlue
import com.revayato.app.core.theme.AccentRed
import com.revayato.app.core.theme.AccentYellow
import com.revayato.app.core.theme.Brand
import com.revayato.app.core.theme.NeutralSurface
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.data.model.CastMemberDto
import com.revayato.app.data.model.PersonDto
import com.revayato.app.ui.components.NetworkImage

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
 * Snackbar text shown after a title is added to the watchlist. Shared by the movie
 * and series detail view-models (which set it) and their screens (which, on this
 * exact message, attach a «مشاهده» action that jumps to the library tab). Keeping it
 * a single const means the screen's match can never silently drift from the VM's text.
 */
internal const val MSG_ADDED_TO_WATCHLIST = "به لیست تماشا اضافه شد"

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
                color = Brand,
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
 * The «مشخصات» section as a compact, icon-led grid. Each fact gets a small
 * tinted glyph and its own tile, so the section reads as a quick at-a-glance
 * sheet rather than a spreadsheet. Only non-empty rows are passed in, so the
 * grid never shows blanks.
 */
@Composable
fun DetailFacts(
    facts: List<Pair<String, String>>,
    modifier: Modifier = Modifier,
) {
    if (facts.isEmpty()) return
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        facts.chunked(2).forEach { rowFacts ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                rowFacts.forEach { (label, value) ->
                    FactTile(
                        label = label,
                        value = value,
                        visual = factVisual(label),
                        modifier = Modifier.weight(1f),
                    )
                }
                if (rowFacts.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

private data class FactVisual(val icon: ImageVector, val tint: Color)

/** Pick a recognisable glyph and a restrained accent for each known fact. */
@Composable
private fun factVisual(label: String): FactVisual {
    val lower = label.lowercase()
    return when {
        label.contains("کشور") -> FactVisual(Icons.Rounded.Public, AccentBlue)
        label.contains("زبان") -> FactVisual(Icons.Rounded.Translate, Brand)
        label.contains("فرمت") -> FactVisual(Icons.Rounded.Movie, AccentYellow)
        label.contains("کیفیت") -> FactVisual(Icons.Rounded.HighQuality, Brand)
        label.contains("امکانات") || lower.contains("زیرنویس") ->
            FactVisual(Icons.Rounded.Subtitles, AccentYellow)
        label.contains("IMDb") || label.contains("امتیاز") ->
            FactVisual(Icons.Rounded.Star, AccentYellow)
        label.contains("سال") || label.contains("تاریخ") ->
            FactVisual(Icons.Rounded.CalendarMonth, AccentBlue)
        label.contains("فصل") -> FactVisual(Icons.Rounded.LiveTv, AccentRed)
        label.contains("قسمت") -> FactVisual(Icons.Rounded.FormatListNumbered, AccentRed)
        label.contains("مدت") || label.contains("زمان") ->
            FactVisual(Icons.Rounded.Schedule, AccentBlue)
        label.contains("بازدید") || label.contains("تماشا") ->
            FactVisual(Icons.Rounded.Visibility, Brand)
        else -> FactVisual(Icons.Rounded.Info, TextSecondary)
    }
}

@Composable
private fun FactTile(
    label: String,
    value: String,
    visual: FactVisual,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .heightIn(min = 86.dp)
            .clip(RoundedCornerShape(14.dp))
            .background(NeutralSurface)
            .border(1.dp, OutlineSoft.copy(alpha = 0.62f), RoundedCornerShape(14.dp))
            .padding(horizontal = 12.dp, vertical = 11.dp),
        verticalArrangement = Arrangement.spacedBy(7.dp),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(7.dp),
        ) {
            Box(
                modifier = Modifier
                    .size(28.dp)
                    .clip(CircleShape)
                    .background(visual.tint.copy(alpha = 0.15f)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = visual.icon,
                    contentDescription = null,
                    tint = visual.tint,
                    modifier = Modifier.size(16.dp),
                )
            }
            Text(
                text = label,
                style = MaterialTheme.typography.labelSmall,
                color = TextMuted,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            color = TextPrimary,
            fontWeight = FontWeight.Medium,
            maxLines = 3,
            overflow = TextOverflow.Ellipsis,
        )
    }
}
