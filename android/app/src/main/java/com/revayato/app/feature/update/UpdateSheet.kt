package com.revayato.app.feature.update

import android.content.ActivityNotFoundException
import android.content.Intent
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Download
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.SystemUpdate
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.SheetValue
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.Brand
import com.revayato.app.core.theme.ErrorRed
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.PlayAccent
import com.revayato.app.core.theme.PlayAccentSoft
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.feature.support.toFaDigits
import java.io.File

/**
 * Hosts the in-app update prompt. Drop it beside the app's root content once;
 * it renders nothing until there is actually a newer build to offer.
 *
 * Revayato is sideloaded from revayato.com/downloads/, so no store notifies
 * anyone that a release exists — this sheet is how an installed app finds out.
 */
@Composable
fun AppUpdateHost(viewModel: UpdateViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    LaunchedEffect(Unit) { viewModel.checkOnLaunch() }

    val release = state.release
    if (state.prompting && release != null) {
        UpdateSheet(
            versionName = release.versionName,
            notes = release.notes,
            sizeBytes = release.sizeBytes,
            mandatory = state.mandatory,
            downloading = state.downloading,
            progress = state.progress,
            readyFile = state.readyFile,
            error = state.error,
            onDownload = viewModel::download,
            installIntentFor = viewModel::installIntent,
            canInstall = viewModel::canInstall,
            unknownSourcesSettings = viewModel::unknownSourcesSettings,
            onPostpone = viewModel::postpone,
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun UpdateSheet(
    versionName: String,
    notes: List<String>,
    sizeBytes: Long,
    mandatory: Boolean,
    downloading: Boolean,
    progress: Int,
    readyFile: File?,
    error: String?,
    onDownload: () -> Unit,
    installIntentFor: (File) -> Intent,
    canInstall: () -> Boolean,
    unknownSourcesSettings: () -> Intent,
    onPostpone: () -> Unit,
) {
    val context = LocalContext.current

    // Granting "install unknown apps" happens in Settings, outside our process.
    // Coming back, retry the install straight away so the user does not have to
    // find the button again.
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) {
        val file = readyFile
        if (file != null && canInstall()) {
            runCatching { context.startActivity(installIntentFor(file)) }
        }
    }

    // A required update must not be swiped away; an optional one behaves like
    // every other sheet in the app.
    val sheetState = rememberModalBottomSheetState(
        skipPartiallyExpanded = true,
        confirmValueChange = { value -> !mandatory || value != SheetValue.Hidden },
    )

    ModalBottomSheet(
        onDismissRequest = { if (!mandatory) onPostpone() },
        sheetState = sheetState,
        containerColor = BgElevated,
        dragHandle = null,
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .navigationBarsPadding()
                .padding(horizontal = 20.dp, vertical = 22.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier
                        .size(44.dp)
                        .clip(CircleShape)
                        .background(PlayAccentSoft),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        Icons.Rounded.SystemUpdate,
                        contentDescription = null,
                        tint = PlayAccent,
                        modifier = Modifier.size(24.dp),
                    )
                }
                Spacer(Modifier.size(14.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        if (mandatory) "بروزرسانی لازم است" else "نسخهٔ جدید روایتو آماده است",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Black,
                        color = TextPrimary,
                    )
                    Text(
                        buildString {
                            append("نسخهٔ ")
                            append(toFaDigits(versionName))
                            if (sizeBytes > 0) {
                                append(" · ")
                                append(readableSize(sizeBytes))
                            }
                        },
                        style = MaterialTheme.typography.labelMedium,
                        color = TextMuted,
                    )
                }
            }

            if (mandatory) {
                Spacer(Modifier.size(14.dp))
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Rounded.Lock, contentDescription = null, tint = ErrorRed, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.size(8.dp))
                    Text(
                        "نسخهٔ نصب‌شده دیگر با سرور سازگار نیست. برای ادامه، بروزرسانی کن.",
                        style = MaterialTheme.typography.bodySmall,
                        color = TextSecondary,
                    )
                }
            }

            if (notes.isNotEmpty()) {
                Spacer(Modifier.size(16.dp))
                Text(
                    "چه چیزی تازه است",
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.Bold,
                    color = TextSecondary,
                )
                Spacer(Modifier.size(8.dp))
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    notes.forEach { note ->
                        Row(verticalAlignment = Alignment.Top) {
                            Box(
                                Modifier
                                    .padding(top = 7.dp)
                                    .size(5.dp)
                                    .clip(CircleShape)
                                    .background(Brand),
                            )
                            Spacer(Modifier.size(10.dp))
                            Text(
                                note,
                                style = MaterialTheme.typography.bodyMedium,
                                color = TextSecondary,
                                modifier = Modifier.weight(1f),
                            )
                        }
                    }
                }
            }

            if (downloading) {
                Spacer(Modifier.size(18.dp))
                Text(
                    if (progress >= 0) "در حال دانلود… ${toFaDigits(progress.toString())}٪" else "در حال دانلود…",
                    style = MaterialTheme.typography.labelMedium,
                    color = TextMuted,
                )
                Spacer(Modifier.size(8.dp))
                if (progress >= 0) {
                    LinearProgressIndicator(
                        progress = { progress / 100f },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(6.dp)
                            .clip(RoundedCornerShape(3.dp)),
                        color = PlayAccent,
                        trackColor = OutlineSoft,
                    )
                } else {
                    LinearProgressIndicator(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(6.dp)
                            .clip(RoundedCornerShape(3.dp)),
                        color = PlayAccent,
                        trackColor = OutlineSoft,
                    )
                }
            }

            if (readyFile != null && error == null) {
                Spacer(Modifier.size(14.dp))
                Text(
                    "اگر پنجرهٔ «Google Play Protect» باز شد، «Scan app» را بزن؛ چند ثانیه بعد نصب ادامه پیدا می‌کند.",
                    style = MaterialTheme.typography.bodySmall,
                    color = TextSecondary,
                )
            }

            if (error != null) {
                Spacer(Modifier.size(14.dp))
                Text(error, style = MaterialTheme.typography.bodySmall, color = ErrorRed)
            }

            Spacer(Modifier.size(20.dp))
            Button(
                onClick = {
                    val file = readyFile
                    when {
                        downloading -> Unit
                        file != null && !canInstall() -> {
                            // Android 8+ needs per-app consent before any install
                            // can start; it is granted only in Settings.
                            runCatching { permissionLauncher.launch(unknownSourcesSettings()) }
                                .onFailure {
                                    Toast.makeText(
                                        context,
                                        "در تنظیمات گوشی، اجازهٔ «نصب برنامه‌های ناشناس» را برای روایتو روشن کن.",
                                        Toast.LENGTH_LONG,
                                    ).show()
                                }
                        }
                        file != null -> try {
                            context.startActivity(installIntentFor(file))
                        } catch (_: ActivityNotFoundException) {
                            Toast.makeText(context, "نصب‌کنندهٔ سیستم در دسترس نیست.", Toast.LENGTH_LONG).show()
                        }
                        else -> onDownload()
                    }
                },
                enabled = !downloading,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(50.dp),
                shape = RoundedCornerShape(14.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Brand, contentColor = OnBrand),
            ) {
                when {
                    downloading -> {
                        CircularProgressIndicator(modifier = Modifier.size(18.dp), color = OnBrand, strokeWidth = 2.dp)
                        Spacer(Modifier.size(10.dp))
                        Text("در حال دانلود…", fontWeight = FontWeight.Bold)
                    }
                    readyFile != null -> {
                        Icon(Icons.Rounded.Check, contentDescription = null, modifier = Modifier.size(20.dp))
                        Spacer(Modifier.size(8.dp))
                        Text("نصب نسخهٔ جدید", fontWeight = FontWeight.Bold)
                    }
                    else -> {
                        Icon(Icons.Rounded.Download, contentDescription = null, modifier = Modifier.size(20.dp))
                        Spacer(Modifier.size(8.dp))
                        Text("دانلود و نصب", fontWeight = FontWeight.Bold)
                    }
                }
            }

            if (!mandatory) {
                TextButton(
                    onClick = onPostpone,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text("بعداً", color = TextMuted, fontWeight = FontWeight.Medium)
                }
            }
        }
    }
}

/** Human-readable APK size in Persian digits, e.g. «۳٫۴ مگابایت». */
internal fun readableSize(bytes: Long): String {
    val megabytes = bytes / (1024.0 * 1024.0)
    if (megabytes < 1.0) {
        val kilobytes = (bytes / 1024.0).toInt().coerceAtLeast(1)
        return "${toFaDigits(kilobytes.toString())} کیلوبایت"
    }
    val whole = megabytes.toInt()
    val tenth = ((megabytes - whole) * 10).toInt()
    return "${toFaDigits("$whole٫$tenth")} مگابایت"
}
