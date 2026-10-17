package com.revayato.app.feature.profile

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material.icons.rounded.Verified
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
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.AccentYellow
import com.revayato.app.core.theme.BrandDeep
import com.revayato.app.core.theme.Brand
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.data.model.ProfileReviewDto
import com.revayato.app.data.model.ProfileStatsDto
import com.revayato.app.ui.components.NetworkImage

/** Big circular avatar: image if present, otherwise a branded initial. */
@Composable
fun ProfileAvatar(avatar: String?, name: String, size: Int = 84, modifier: Modifier = Modifier) {
    Box(
        modifier
            .size(size.dp)
            .clip(CircleShape)
            .background(Brush.linearGradient(listOf(BrandDeep, Brand))),
        contentAlignment = Alignment.Center,
    ) {
        if (!avatar.isNullOrBlank()) {
            NetworkImage(avatar, null, Modifier.fillMaxWidth().aspectRatio(1f))
        } else {
            Text(
                name.trim().take(1).uppercase().ifBlank { "?" },
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Black,
                color = OnBrand,
            )
        }
    }
}

/** Name + verified tick + @username + optional bio + join line. */
@Composable
fun ProfileIdentity(
    displayName: String,
    username: String,
    isVerified: Boolean,
    bio: String,
    memberSince: String?,
    modifier: Modifier = Modifier,
) {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(
                displayName.ifBlank { username },
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Black,
                color = TextPrimary,
            )
            if (isVerified) {
                Icon(Icons.Rounded.Verified, contentDescription = "تأییدشده", tint = Brand, modifier = Modifier.size(20.dp))
            }
        }
        if (username.isNotBlank()) {
            Text("@$username", style = MaterialTheme.typography.bodyMedium, color = TextMuted)
        }
        if (bio.isNotBlank()) {
            Text(
                bio,
                style = MaterialTheme.typography.bodyMedium,
                color = TextSecondary,
                modifier = Modifier.padding(top = 6.dp),
            )
        }
        memberSince?.take(4)?.takeIf { it.length == 4 }?.let {
            Text("عضو از $it", style = MaterialTheme.typography.labelMedium, color = TextMuted, modifier = Modifier.padding(top = 2.dp))
        }
    }
}

/** Three real-number stat tiles: collections / ratings / likes. */
@Composable
fun ProfileStatsRow(stats: ProfileStatsDto, modifier: Modifier = Modifier) {
    Row(
        modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(MaterialTheme.colorScheme.surface)
            .padding(vertical = 16.dp),
        horizontalArrangement = Arrangement.SpaceEvenly,
    ) {
        StatTile(stats.collections, "کالکشن")
        StatDivider()
        StatTile(stats.ratings, "امتیاز")
        StatDivider()
        StatTile(stats.likes ?: stats.publicTitles, if (stats.likes != null) "پسند" else "عنوان")
    }
}

@Composable
private fun StatTile(value: Int, label: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(value.toString(), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Black, color = TextPrimary)
        Text(label, style = MaterialTheme.typography.labelMedium, color = TextMuted)
    }
}

@Composable
private fun StatDivider() {
    Box(Modifier.width(1.dp).height(34.dp).background(OutlineSoft))
}

/** Section title used across profile screens. */
@Composable
fun ProfileSectionTitle(title: String, modifier: Modifier = Modifier, action: (@Composable () -> Unit)? = null) {
    Row(
        modifier.fillMaxWidth().padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = TextPrimary, modifier = Modifier.weight(1f))
        action?.invoke()
    }
}

/** A public review card: poster + title + score + text (spoiler-masked). */
@Composable
fun ReviewCard(
    review: ProfileReviewDto,
    onOpenTitle: (contentType: String, slug: String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val card = review.content
    Row(
        modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(MaterialTheme.colorScheme.surface)
            .let { if (card != null) it.clickable { onOpenTitle(review.contentType, card.slug) } else it }
            .padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        NetworkImage(
            url = card?.poster,
            contentDescription = card?.title,
            modifier = Modifier
                .width(54.dp)
                .aspectRatio(2f / 3f)
                .clip(RoundedCornerShape(8.dp)),
            fallbackText = card?.title ?: "",
        )
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                card?.title ?: "عنوان حذف‌شده",
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.Bold,
                color = TextPrimary,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                Icon(Icons.Rounded.Star, contentDescription = null, tint = AccentYellow, modifier = Modifier.size(14.dp))
                Text(
                    formatScore(review.score),
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                    color = AccentYellow,
                )
            }
            if (review.review.isNotBlank()) {
                Text(
                    if (review.isSpoiler) "⚠️ این نقد اسپویل دارد — برای دیدن باز کن" else review.review,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (review.isSpoiler) TextMuted else TextSecondary,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

private fun formatScore(score: Double): String =
    if (score % 1.0 == 0.0) score.toInt().toString() else String.format("%.1f", score)
