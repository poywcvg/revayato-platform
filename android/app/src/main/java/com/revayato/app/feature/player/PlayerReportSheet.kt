package com.revayato.app.feature.player

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.HelpOutline
import androidx.compose.material.icons.automirrored.rounded.PlaylistPlay
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.ClosedCaption
import androidx.compose.material.icons.rounded.ErrorOutline
import androidx.compose.material.icons.rounded.Flag
import androidx.compose.material.icons.rounded.GraphicEq
import androidx.compose.material.icons.rounded.Movie
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.revayato.app.core.theme.AccentYellow
import com.revayato.app.core.theme.AccentYellowSoft
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.core.theme.TextSecondary

/** Dark text drawn on the amber submit button. */
private val OnAccentYellow = Color(0xFF241A00)

/** One selectable problem type in the player report sheet. */
private data class ReportProblemOption(
    val key: String,
    val label: String,
    val hint: String,
    val icon: ImageVector,
)

/**
 * The structured «گزارش خطا» sheet reached from inside the player. Mirrors the
 * server catalogue in `apps/catalog/report_catalog.py` (served from
 * `GET /api/catalog/report-issue/options/`) so the viewer picks the exact symptom
 * the auto-remediation engine dispatches on — the same 12 buttons the web player
 * shows. `wrong_episode` only appears for series ([isSeries]).
 *
 * Submission is handled by the ViewModel: [submitting] drives the spinner,
 * [done] + [message] show the confirmation state, and a failed send surfaces
 * [message] in place without closing the sheet.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PlayerReportSheet(
    isSeries: Boolean,
    submitting: Boolean,
    done: Boolean,
    message: String?,
    onSubmit: (problemType: String, detail: String) -> Unit,
    onDismiss: () -> Unit,
) {
    val options = remember(isSeries) {
        buildList {
            add(ReportProblemOption("playback", "اصلاً پخش نمی‌شود", "ویدیو باز نمی‌شود یا خطا می‌دهد", Icons.Rounded.ErrorOutline))
            add(ReportProblemOption("buffering", "مدام قطع و وصل می‌شود", "پخش شروع می‌شود ولی مدام می‌ایستد", Icons.AutoMirrored.Rounded.PlaylistPlay))
            add(ReportProblemOption("audio_silent", "تصویر هست، صدا نیست", "فیلم پخش می‌شود ولی هیچ صدایی ندارد", Icons.Rounded.GraphicEq))
            add(ReportProblemOption("audio_desync", "صدا با تصویر هماهنگ نیست", "صدا از تصویر جلو یا عقب است", Icons.Rounded.GraphicEq))
            add(ReportProblemOption("subtitle_missing", "زیرنویس ندارد", "هیچ زیرنویس فارسی‌ای در دسترس نیست", Icons.Rounded.ClosedCaption))
            add(ReportProblemOption("subtitle_sync", "زیرنویس عقب یا جلو است", "متن با گفت‌وگو هم‌زمان نیست", Icons.Rounded.ClosedCaption))
            add(ReportProblemOption("subtitle_garbled", "زیرنویس خراب یا نامفهوم است", "حروف به‌هم‌ریخته‌اند یا متن بی‌ربط است", Icons.Rounded.ClosedCaption))
            add(ReportProblemOption("wrong_title", "فیلم با عنوان فرق دارد", "محتوای پخش‌شده با اسم صفحه یکی نیست", Icons.Rounded.Movie))
            if (isSeries) {
                add(ReportProblemOption("wrong_episode", "قسمت اشتباه است", "این ویدیو مربوط به قسمت دیگری است", Icons.AutoMirrored.Rounded.PlaylistPlay))
            }
            add(ReportProblemOption("quality", "کیفیت تصویر خیلی پایین است", "تصویر تار است یا با کیفیت انتخابی نمی‌خواند", Icons.Rounded.ErrorOutline))
            add(ReportProblemOption("download_dead", "لینک دانلود کار نمی‌کند", "دانلود شروع نمی‌شود یا نیمه‌کاره می‌ماند", Icons.AutoMirrored.Rounded.HelpOutline))
            add(ReportProblemOption("other", "مورد دیگر", "مشکلی که در این فهرست نیست", Icons.AutoMirrored.Rounded.HelpOutline))
        }
    }

    var selected by remember { mutableStateOf<String?>(null) }
    var detail by remember { mutableStateOf("") }
    val canSubmit = selected != null && !submitting

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
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            // Header.
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Box(
                    modifier = Modifier
                        .size(40.dp)
                        .clip(RoundedCornerShape(12.dp))
                        .background(AccentYellowSoft),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(Icons.Rounded.Flag, contentDescription = null, tint = AccentYellow, modifier = Modifier.size(20.dp))
                }
                Column {
                    Text("گزارش خطا", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = TextPrimary)
                    Text(
                        "مشکل را انتخاب کن تا خودکار بررسی و رفع شود.",
                        style = MaterialTheme.typography.labelMedium,
                        color = TextSecondary,
                    )
                }
            }

            if (done) {
                // Success confirmation.
                Column(
                    Modifier.fillMaxWidth().padding(vertical = 20.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Box(
                        modifier = Modifier.size(56.dp).clip(CircleShape).background(Color(0x2234D399)),
                        contentAlignment = Alignment.Center,
                    ) {
                        Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = Color(0xFFE8A04E), modifier = Modifier.size(30.dp))
                    }
                    Text(
                        message ?: "گزارشت ثبت شد.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextSecondary,
                        modifier = Modifier.padding(horizontal = 8.dp),
                    )
                    Row(
                        Modifier
                            .clip(RoundedCornerShape(12.dp))
                            .background(Color(0x14FFFFFF))
                            .clickable(onClick = onDismiss)
                            .padding(horizontal = 20.dp, vertical = 10.dp),
                    ) {
                        Text("بستن", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold, color = TextPrimary)
                    }
                }
            } else {
                Text("چه مشکلی دیدی؟", style = MaterialTheme.typography.labelMedium, color = TextSecondary)
                options.forEach { option ->
                    ReportOptionRow(
                        option = option,
                        selected = selected == option.key,
                        enabled = !submitting,
                        onClick = { selected = option.key },
                    )
                }

                OutlinedTextField(
                    value = detail,
                    onValueChange = { if (it.length <= 500) detail = it },
                    enabled = !submitting,
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 2,
                    maxLines = 5,
                    textStyle = MaterialTheme.typography.bodyMedium,
                    placeholder = { Text("توضیح اختیاری…", color = TextMuted) },
                    shape = RoundedCornerShape(16.dp),
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

                // A failed send surfaces its notice here (sheet stays open to retry).
                message?.let {
                    Text(it, style = MaterialTheme.typography.labelMedium, color = AccentYellow)
                }

                // Amber submit; disabled until a problem is picked.
                Row(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(14.dp))
                        .background(if (canSubmit) AccentYellow else AccentYellowSoft)
                        .clickable(enabled = canSubmit) { selected?.let { onSubmit(it, detail.trim()) } }
                        .padding(vertical = 14.dp),
                    horizontalArrangement = Arrangement.Center,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    if (submitting) {
                        CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp, color = OnAccentYellow)
                        Spacer(Modifier.size(10.dp))
                        Text("در حال ارسال…", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold, color = OnAccentYellow)
                    } else {
                        Icon(Icons.Rounded.Send, contentDescription = null, tint = if (canSubmit) OnAccentYellow else TextMuted, modifier = Modifier.size(18.dp))
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
}

@Composable
private fun ReportOptionRow(
    option: ReportProblemOption,
    selected: Boolean,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(if (selected) AccentYellowSoft else Color(0x0DFFFFFF))
            .border(1.dp, if (selected) AccentYellow else OutlineSoft, RoundedCornerShape(14.dp))
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(
            modifier = Modifier.size(36.dp).clip(RoundedCornerShape(10.dp)).background(Color(0x14FFFFFF)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(option.icon, contentDescription = null, tint = if (selected) AccentYellow else TextPrimary, modifier = Modifier.size(20.dp))
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(option.label, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, color = TextPrimary)
            Text(option.hint, style = MaterialTheme.typography.labelSmall, color = TextMuted)
        }
        if (selected) {
            Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = AccentYellow, modifier = Modifier.size(20.dp))
        }
    }
}
