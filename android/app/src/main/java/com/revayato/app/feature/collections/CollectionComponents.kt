package com.revayato.app.feature.collections

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Layers
import androidx.compose.material.icons.rounded.Link
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.Public
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.revayato.app.core.theme.NeutralSurface
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.data.model.UserCollectionDto
import com.revayato.app.ui.components.NetworkImage


/** Parse a `#RRGGBB` accent into a Compose [Color], falling back to brand violet. */
fun parseAccent(hex: String?): Color = runCatching {
    val clean = hex?.removePrefix("#")?.takeIf { it.length == 6 } ?: return@runCatching Color(0xFFE8A04E)
    Color(("FF$clean").toLong(16))
}.getOrDefault(Color(0xFFE8A04E))

/**
 * A collection's cover: up to four poster tiles arranged as a collage over the
 * collection's accent colour. Falls back to an accent gradient with a stacked-cards
 * glyph when the collection is empty, so a fresh collection still looks designed.
 */
@Composable
fun CollectionCover(
    covers: List<String>,
    accent: Color,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(18.dp))
            .background(
                Brush.linearGradient(
                    listOf(accent.copy(alpha = 0.85f), accent.copy(alpha = 0.35f)),
                ),
            ),
    ) {
        when {
            covers.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Icon(
                    Icons.Rounded.Layers,
                    contentDescription = null,
                    tint = Color.White.copy(alpha = 0.85f),
                    modifier = Modifier.size(34.dp),
                )
            }

            covers.size == 1 -> NetworkImage(
                url = covers[0],
                contentDescription = null,
                modifier = Modifier.fillMaxSize(),
            )

            else -> {
                // 2×2 collage (uses whatever is available, 2–4 posters).
                val four = covers.take(4)
                Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Row(Modifier.fillMaxWidth().weight(1f), horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                        CoverTile(four.getOrNull(0), Modifier.weight(1f).fillMaxHeight())
                        CoverTile(four.getOrNull(1), Modifier.weight(1f).fillMaxHeight())
                    }
                    if (four.size > 2) {
                        Row(Modifier.fillMaxWidth().weight(1f), horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                            CoverTile(four.getOrNull(2), Modifier.weight(1f).fillMaxHeight())
                            CoverTile(four.getOrNull(3), Modifier.weight(1f).fillMaxHeight())
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CoverTile(url: String?, modifier: Modifier) {
    if (url == null) {
        Box(modifier.background(Color.Black.copy(alpha = 0.18f)))
    } else {
        NetworkImage(url = url, contentDescription = null, modifier = modifier)
    }
}

/** Small pill showing a collection's visibility with a matching icon. */
@Composable
fun VisibilityBadge(visibility: String, modifier: Modifier = Modifier, onImage: Boolean = true) {
    // Over artwork the pill stays white-on-glass; on a plain surface it follows the theme.
    val fill = if (onImage) Color.White.copy(alpha = 0.10f) else NeutralSurface
    val ink = if (onImage) Color.White.copy(alpha = 0.9f) else TextSecondary
    val (icon, label) = when (visibility) {
        "public" -> Icons.Rounded.Public to "عمومی"
        "unlisted" -> Icons.Rounded.Link to "با لینک"
        else -> Icons.Rounded.Lock to "خصوصی"
    }
    Row(
        modifier = modifier
            .clip(RoundedCornerShape(999.dp))
            .background(fill)
            .padding(horizontal = 8.dp, vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Icon(icon, contentDescription = null, tint = ink, modifier = Modifier.size(12.dp))
        Text(
            label,
            style = MaterialTheme.typography.labelSmall,
            color = ink,
        )
    }
}

/**
 * A collection tile for grids/rails: collage cover + title + item count, with the
 * accent as a thin framing edge so each collection reads as its own object.
 */
@Composable
fun CollectionCard(
    collection: UserCollectionDto,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    showOwner: Boolean = false,
) {
    val accent = parseAccent(collection.accent)
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(18.dp))
            .clickable(onClick = onClick),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Box {
            CollectionCover(
                covers = collection.covers,
                accent = accent,
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(1f)
                    .border(1.dp, accent.copy(alpha = 0.55f), RoundedCornerShape(18.dp)),
            )
            VisibilityBadge(
                visibility = collection.visibility,
                modifier = Modifier.align(Alignment.TopEnd).padding(8.dp),
            )
        }
        Text(
            collection.title,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onSurface,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Box(Modifier.size(6.dp).clip(RoundedCornerShape(999.dp)).background(accent))
            Text(
                if (showOwner && collection.owner.username.isNotBlank())
                    "${collection.itemCount} عنوان · ${collection.owner.username}"
                else
                    "${collection.itemCount} عنوان",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

/** Horizontal collection tile (used in the compact profile rail). */
@Composable
fun CollectionWideRow(
    collection: UserCollectionDto,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val accent = parseAccent(collection.accent)
    Row(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(MaterialTheme.colorScheme.surface)
            .clickable(onClick = onClick)
            .padding(10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        CollectionCover(
            covers = collection.covers,
            accent = accent,
            modifier = Modifier.size(64.dp),
        )
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                collection.title,
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onSurface,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                "${collection.itemCount} عنوان",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        VisibilityBadge(visibility = collection.visibility, onImage = false)
        Spacer(Modifier.width(2.dp))
    }
}
