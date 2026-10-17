package com.revayato.app.feature.detail

import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
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
