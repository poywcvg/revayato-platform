package com.revayato.app.feature.detail

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ReportProblem
import androidx.compose.material.icons.rounded.Send
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.revayato.app.core.theme.AccentYellow
import com.revayato.app.core.theme.AccentYellowSoft
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.core.theme.TextSecondary

/** Minimum characters the backend accepts for a support-ticket body. */
private const val MIN_REPORT_LEN = 10

/** Dark text drawn on the amber submit button. */
private val OnAccentYellow = Color(0xFF241A00)

/**
 * A distinct, amber-accented sheet for reporting a problem with a title. Kept
 * deliberately apart from the azure download sheet and the play flow so «گزارش خطا»
 * reads as its own thing. The user picks a quick reason and/or types details; the
 * report is filed as a "bug" support ticket and reaches the admin inbox.
 *
 * [contentLabel] is a short noun for the title in the prompt, e.g. «این فیلم» / «این سریال».
 */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun ReportProblemSheet(
    contentLabel: String,
    submitting: Boolean,
    onSubmit: (reason: String) -> Unit,
    onDismiss: () -> Unit,
) {
    // Quick reasons; each is ≥10 chars so a single tap already satisfies the
    // minimum, while the user can still edit or add detail before sending.
    val quickReasons = remember {
        listOf(
            "این عنوان پخش نمی‌شود",
            "زیرنویس ندارد یا خراب است",
            "مشکل در صدا یا دوبله",
            "کیفیت یا نسخهٔ اشتباه است",
            "لینک دانلود کار نمی‌کند",
            "اطلاعات صفحه اشتباه است",
        )
    }
    var reason by remember { mutableStateOf("") }
    val trimmedLen = reason.trim().length
    val canSubmit = trimmedLen >= MIN_REPORT_LEN && !submitting

    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = { if (!submitting) onDismiss() },
        sheetState = sheetState,
        containerColor = BgElevated,
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .imePadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
                .padding(top = 4.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            SheetHeader(
                icon = Icons.Rounded.ReportProblem,
                accent = AccentYellow,
                accentSoft = AccentYellowSoft,
                title = "گزارش خطا",
                subtitle = "اگر مشکلی در $contentLabel دیدی، کوتاه توضیح بده تا برای تیم روایتو فرستاده شود.",
            )

            Text(
                "یکی را انتخاب کن یا خودت بنویس:",
                style = MaterialTheme.typography.labelMedium,
                color = TextSecondary,
            )
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                quickReasons.forEach { preset ->
                    val selected = reason.trim() == preset
                    Text(
                        preset,
                        style = MaterialTheme.typography.labelLarge,
                        color = if (selected) OnAccentYellow else TextPrimary,
                        modifier = Modifier
                            .clip(RoundedCornerShape(999.dp))
                            .background(if (selected) AccentYellow else AccentYellowSoft)
                            .border(
                                1.dp,
                                if (selected) AccentYellow else OutlineSoft,
                                RoundedCornerShape(999.dp),
                            )
                            .clickable(enabled = !submitting) { reason = preset }
                            .padding(horizontal = 14.dp, vertical = 9.dp),
                    )
                }
            }

            OutlinedTextField(
                value = reason,
                onValueChange = { if (it.length <= 5000) reason = it },
                enabled = !submitting,
                modifier = Modifier.fillMaxWidth(),
                minLines = 3,
                maxLines = 6,
                textStyle = MaterialTheme.typography.bodyMedium,
                placeholder = { Text("توضیح مشکل…", color = TextMuted) },
                shape = RoundedCornerShape(16.dp),
                supportingText = {
                    Text(
                        if (trimmedLen in 1 until MIN_REPORT_LEN) {
                            "کمی بیشتر توضیح بده (حداقل ۱۰ نویسه)"
                        } else {
                            "توضیح دقیق‌تر به رفع سریع‌تر مشکل کمک می‌کند."
                        },
                        style = MaterialTheme.typography.labelSmall,
                        color = TextMuted,
                    )
                },
                colors = TextFieldDefaults.colors(
                    focusedContainerColor = Color(0x14FFFFFF),
                    unfocusedContainerColor = Color(0x14FFFFFF),
                    disabledContainerColor = Color(0x0AFFFFFF),
                    focusedIndicatorColor = AccentYellow,
                    unfocusedIndicatorColor = OutlineSoft,
                    cursorColor = AccentYellow,
                    focusedTextColor = TextPrimary,
                    unfocusedTextColor = TextPrimary,
                ),
            )

            // Amber filled submit; disabled until the reason is long enough.
            Row(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(14.dp))
                    .background(if (canSubmit) AccentYellow else AccentYellowSoft)
                    .clickable(enabled = canSubmit) { onSubmit(reason) }
                    .padding(vertical = 14.dp),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (submitting) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(18.dp),
                        strokeWidth = 2.dp,
                        color = OnAccentYellow,
                    )
                    Spacer(Modifier.size(10.dp))
                    Text(
                        "در حال ارسال…",
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.Bold,
                        color = OnAccentYellow,
                    )
                } else {
                    Icon(
                        Icons.Rounded.Send,
                        contentDescription = null,
                        tint = if (canSubmit) OnAccentYellow else TextMuted,
                        modifier = Modifier.size(18.dp),
                    )
                    Spacer(Modifier.size(10.dp))
                    Text(
                        "ارسال گزارش",
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.Bold,
                        color = if (canSubmit) OnAccentYellow else TextMuted,
                    )
                }
            }
        }
    }
}

/**
 * The minimal top-of-page trigger: a compact pill with a warning glyph and label,
 * subtle enough to sit over artwork without competing with the poster or the play
 * button. Shared by the movie and series detail screens.
 */
@Composable
fun ReportProblemButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier
            .clip(RoundedCornerShape(999.dp))
            .background(Color(0x66000000))
            .border(1.dp, Color(0x33FFFFFF), RoundedCornerShape(999.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            Icons.Rounded.ReportProblem,
            contentDescription = "گزارش خطا",
            tint = AccentYellow,
            modifier = Modifier.size(15.dp),
        )
        Spacer(Modifier.size(6.dp))
        Text(
            "گزارش خطا",
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.SemiBold,
            color = TextPrimary,
        )
    }
}
