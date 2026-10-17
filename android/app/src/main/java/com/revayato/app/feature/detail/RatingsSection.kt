package com.revayato.app.feature.detail

import com.revayato.app.core.theme.BgSoft
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material.icons.rounded.StarBorder
import androidx.compose.material.icons.rounded.Verified
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.draw.clip
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.Brand
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.StarGold
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.NeutralSurface
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.data.model.RatingDto
import com.revayato.app.data.model.RatingSummaryDto
import kotlin.math.roundToInt

/** UI state for the comments & ratings panel, shared by movie and series detail. */
data class RatingsUi(
    val loading: Boolean = false,
    val average: Double? = null,
    val count: Int = 0,
    val myScore: Double? = null,
    val myReview: String? = null,
    val reviews: List<RatingDto> = emptyList(),
    val submitting: Boolean = false,
) {
    companion object {
        fun from(dto: RatingSummaryDto): RatingsUi = RatingsUi(
            average = dto.average,
            count = dto.count,
            myScore = dto.myRating?.score,
            myReview = dto.myRating?.review,
            reviews = dto.reviews,
        )
    }
}

/**
 * Comments & ratings block shown at the bottom of every movie and series detail
 * screen (replaces the old inline episodes list on series). Signed-in users pick
 * a 1–10 score, optionally write a review and flag it as a spoiler; everyone sees
 * the community average and other users' reviews.
 */
@Composable
fun RatingsAndComments(
    ui: RatingsUi,
    isLoggedIn: Boolean,
    onSubmit: (score: Double, review: String, isSpoiler: Boolean) -> Unit,
    onRequireLogin: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth().padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            SectionTitle("نظرات و امتیازها")
            val comments = maxOf(ui.count, ui.reviews.size)
            if (comments > 0) {
                Box(
                    Modifier
                        .padding(top = 8.dp)
                        .clip(RoundedCornerShape(999.dp))
                        .background(NeutralSurface)
                        .padding(horizontal = 8.dp, vertical = 2.dp),
                ) {
                    Text(
                        toPersianDigits(comments.toString()),
                        style = MaterialTheme.typography.labelMedium,
                        color = TextSecondary,
                    )
                }
            }
        }

        AverageRatingCard(average = ui.average, count = ui.count)

        if (isLoggedIn) {
            RateComposer(
                initialScore = ui.myScore,
                initialReview = ui.myReview,
                submitting = ui.submitting,
                onSubmit = onSubmit,
            )
        } else {
            LoginPrompt(onRequireLogin = onRequireLogin)
        }

        when {
            ui.loading -> Box(
                Modifier.fillMaxWidth().padding(vertical = 20.dp),
                contentAlignment = Alignment.Center,
            ) { CircularProgressIndicator(color = Brand, strokeWidth = 2.dp) }

            ui.reviews.isEmpty() -> Text(
                text = "هنوز نظری ثبت نشده — اولین نفر باش!",
                style = MaterialTheme.typography.bodyMedium,
                color = TextMuted,
                modifier = Modifier.padding(vertical = 8.dp),
            )

            else -> ui.reviews.forEach { review ->
                ReviewCard(review)
            }
        }
    }
}

@Composable
private fun AverageRatingCard(average: Double?, count: Int) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(BgElevated, RoundedCornerShape(18.dp))
            .border(1.dp, OutlineSoft, RoundedCornerShape(18.dp))
            .padding(horizontal = 18.dp, vertical = 16.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Icon(Icons.Rounded.Star, contentDescription = null, tint = StarGold, modifier = Modifier.size(30.dp))
        Column {
            Text(
                text = if (average != null) "${trimScore(average)} از ۱۰" else "بدون امتیاز",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onSurface,
            )
            Text(
                text = if (count > 0) "$count نظر کاربران" else "امتیاز کاربران روایتو",
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted,
            )
        }
    }
}

@Composable
private fun RateComposer(
    initialScore: Double?,
    initialReview: String?,
    submitting: Boolean,
    onSubmit: (Double, String, Boolean) -> Unit,
) {
    var score by remember(initialScore) { mutableFloatStateOf(initialScore?.toFloat() ?: 0f) }
    var review by remember(initialReview) { mutableStateOf(initialReview.orEmpty()) }
    var spoiler by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(BgElevated, RoundedCornerShape(18.dp))
            .border(1.dp, OutlineSoft, RoundedCornerShape(18.dp))
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = if (initialScore != null) "امتیاز شما" else "امتیاز خود را ثبت کن",
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onSurface,
        )
        StarRow(score = score.roundToInt(), onScore = { score = it.toFloat() })

        OutlinedTextField(
            value = review,
            onValueChange = { review = it.take(4000) },
            modifier = Modifier.fillMaxWidth().height(110.dp),
            placeholder = { Text("نظرت را بنویس… (اختیاری)") },
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Default),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = Brand,
                cursorColor = Brand,
            ),
        )

        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier
                .clickable { spoiler = !spoiler }
                .padding(vertical = 2.dp),
        ) {
            Box(
                Modifier
                    .size(20.dp)
                    .background(
                        if (spoiler) Brand else Color.Transparent,
                        RoundedCornerShape(5.dp),
                    )
                    .border(1.5.dp, if (spoiler) Brand else OutlineSoft, RoundedCornerShape(5.dp)),
                contentAlignment = Alignment.Center,
            ) {
                if (spoiler) Text("✓", color = OnBrand, fontSize = 13.sp, fontWeight = FontWeight.Bold)
            }
            Spacer(Modifier.width(8.dp))
            Text("این نظر اسپویلر دارد", style = MaterialTheme.typography.bodyMedium, color = TextSecondary)
        }

        val canSubmit = score >= 1f && !submitting
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(
                    if (canSubmit) Brand else OutlineSoft,
                    RoundedCornerShape(14.dp),
                )
                .clickable(enabled = canSubmit) {
                    onSubmit(score.toDouble(), review.trim(), spoiler)
                }
                .padding(vertical = 13.dp),
            contentAlignment = Alignment.Center,
        ) {
            if (submitting) {
                CircularProgressIndicator(color = OnBrand, strokeWidth = 2.dp, modifier = Modifier.size(20.dp))
            } else {
                Text(
                    text = if (initialScore != null) "به‌روزرسانی نظر" else "ثبت نظر",
                    color = if (canSubmit) OnBrand else TextMuted,
                    fontWeight = FontWeight.Bold,
                )
            }
        }
    }
}

@Composable
private fun StarRow(score: Int, onScore: (Int) -> Unit) {
    // Ten stars map directly onto the site's 0–10 scale — tapping a star sets that
    // score. Kept in an LTR row so 1 is on the left and 10 on the right regardless
    // of the surrounding RTL layout.
    Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
        (1..10).forEach { value ->
            Icon(
                imageVector = if (value <= score) Icons.Rounded.Star else Icons.Rounded.StarBorder,
                contentDescription = "امتیاز $value",
                tint = if (value <= score) StarGold else TextMuted,
                modifier = Modifier
                    .size(28.dp)
                    .clickable { onScore(value) },
            )
        }
    }
}

@Composable
private fun LoginPrompt(onRequireLogin: () -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .background(BgElevated, RoundedCornerShape(18.dp))
            .border(1.dp, OutlineSoft, RoundedCornerShape(18.dp))
            .clickable { onRequireLogin() }
            .padding(vertical = 16.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = "برای ثبت نظر و امتیاز وارد شوید",
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Bold,
            color = Brand,
        )
    }
}

@Composable
private fun ReviewCard(review: RatingDto) {
    var revealed by remember(review.id) { mutableStateOf(!review.isSpoiler) }
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(BgElevated, RoundedCornerShape(16.dp))
            .border(
                1.dp,
                if (review.isFeatured) Brand.copy(alpha = 0.55f) else OutlineSoft,
                RoundedCornerShape(16.dp),
            )
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        if (review.isFeatured) {
            Row(
                modifier = Modifier
                    .background(Brand.copy(alpha = 0.14f), RoundedCornerShape(999.dp))
                    .padding(horizontal = 9.dp, vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Icon(
                    Icons.Rounded.AutoAwesome,
                    contentDescription = null,
                    tint = Brand,
                    modifier = Modifier.size(13.dp),
                )
                Text("نقد برگزیده", color = Brand, fontWeight = FontWeight.Bold, fontSize = 11.sp)
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier.size(34.dp).background(Brand, CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    text = (review.username?.firstOrNull() ?: '؟').uppercaseChar().toString(),
                    color = OnBrand,
                    fontWeight = FontWeight.Bold,
                )
            }
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    text = review.username ?: "کاربر روایتو",
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                review.createdAt?.take(10)?.let {
                    Text(text = it, style = MaterialTheme.typography.labelSmall, color = TextMuted)
                }
            }
            ScoreBadge(review.score)
        }

        val text = review.review?.takeIf { it.isNotBlank() }
        if (text != null) {
            Box {
                Text(
                    text = text,
                    style = MaterialTheme.typography.bodyMedium,
                    // Masked like the web: solid tone, transparent ink. No blur.
                    color = if (revealed) TextSecondary else Color.Transparent,
                    modifier = if (revealed) Modifier else Modifier
                        .clip(RoundedCornerShape(6.dp))
                        .background(BgSoft),
                )
                if (!revealed) {
                    Box(
                        Modifier
                            .matchParentSize()
                            .clickable { revealed = true },
                        contentAlignment = Alignment.Center,
                    ) {
                        Text(
                            text = "⚠ اسپویلر — برای نمایش لمس کن",
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Bold,
                            color = StarGold,
                            textAlign = TextAlign.Center,
                        )
                    }
                }
            }
        }

        // «پاسخ روایتو» — a public reply the روایتو team posted under this review.
        review.adminReply?.takeIf { it.isNotBlank() }?.let { reply ->
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(Brand.copy(alpha = 0.08f), RoundedCornerShape(12.dp))
                    .border(1.dp, Brand.copy(alpha = 0.32f), RoundedCornerShape(12.dp))
                    .padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Icon(
                        Icons.Rounded.Verified,
                        contentDescription = null,
                        tint = Brand,
                        modifier = Modifier.size(16.dp),
                    )
                    Text(
                        "پاسخ روایتو",
                        color = Brand,
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.labelLarge,
                    )
                    review.adminReplyByName?.takeIf { it.isNotBlank() }?.let {
                        Text("· $it", color = TextMuted, style = MaterialTheme.typography.labelSmall)
                    }
                }
                Text(reply, style = MaterialTheme.typography.bodyMedium, color = TextSecondary)
                review.adminReplyAt?.take(10)?.let {
                    Text(toPersianDigits(it), style = MaterialTheme.typography.labelSmall, color = TextMuted)
                }
            }
        }
    }
}

/** "2026-09-19" → "۲۰۲۶-۰۹-۱۹" — Persian digits, punctuation untouched. */
private fun toPersianDigits(value: String): String =
    value.map { ch -> if (ch.isDigit()) '۰' + (ch - '0') else ch }.joinToString("")

@Composable
private fun ScoreBadge(score: Double) {
    Row(
        modifier = Modifier
            .background(StarGold.copy(alpha = 0.16f), RoundedCornerShape(9.dp))
            .padding(horizontal = 9.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        Icon(Icons.Rounded.Star, contentDescription = null, tint = StarGold, modifier = Modifier.size(15.dp))
        Text(
            text = trimScore(score),
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.Bold,
            color = StarGold,
        )
    }
}

/** "8.0" → "۸", "7.5" → "۷.۵" — drops a trailing .0 and shows Persian digits. */
private fun trimScore(value: Double): String {
    val rounded = (value * 10).roundToInt() / 10.0
    val raw = if (rounded % 1.0 == 0.0) rounded.toInt().toString() else rounded.toString()
    return raw.map { ch -> if (ch.isDigit()) '۰' + (ch - '0') else ch }.joinToString("")
}
