package com.revayato.app.feature.watchparty

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Groups
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.BgMain
import com.revayato.app.core.theme.Brand
import com.revayato.app.core.theme.ErrorRed
import com.revayato.app.core.theme.NeutralSurface
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.feature.collection.BackTopBar

@Composable
fun WatchPartyLandingScreen(
    isLoggedIn: Boolean,
    onEnterRoom: (String) -> Unit,
    onRequireLogin: () -> Unit,
    onBack: () -> Unit,
    onBrowseTitles: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: WatchPartyLandingViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    LaunchedEffect(state.navigateToCode) {
        state.navigateToCode?.let {
            onEnterRoom(it)
            viewModel.consumeNavigation()
        }
    }
    LaunchedEffect(state.requireLogin) {
        if (state.requireLogin) {
            onRequireLogin()
            viewModel.consumeRequireLogin()
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(BgMain)
            .navigationBarsPadding(),
    ) {
        BackTopBar(title = "تماشای گروهی", onBack = onBack)
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .imePadding()
                .padding(horizontal = 20.dp)
                .padding(top = 6.dp, bottom = 28.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Box(
                    modifier = Modifier
                        .size(54.dp)
                        .clip(RoundedCornerShape(17.dp))
                        .background(Brand.copy(alpha = 0.14f)),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        imageVector = Icons.Rounded.Groups,
                        contentDescription = null,
                        tint = Brand,
                        modifier = Modifier.size(29.dp),
                    )
                }
                Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(
                        text = "با هم ببینیم",
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = "یک اتاق، یک فیلم، یک گفت‌وگوی زنده",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextSecondary,
                    )
                }
            }

            if (!isLoggedIn) {
                Text(
                    text = "برای ساختن یا پیوستن به اتاق، ابتدا وارد حساب شو.",
                    style = MaterialTheme.typography.bodySmall,
                    color = TextMuted,
                )
            }

            // Join an existing room by invite code.
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(20.dp))
                    .background(BgElevated)
                    .border(1.dp, OutlineSoft.copy(alpha = 0.65f), RoundedCornerShape(20.dp))
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(11.dp),
            ) {
                Text(
                    text = "پیوستن به اتاق",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = "کد دعوتی که دوستت فرستاده را وارد کن.",
                    style = MaterialTheme.typography.bodySmall,
                    color = TextSecondary,
                )
                OutlinedTextField(
                    value = state.code,
                    onValueChange = viewModel::onCodeChange,
                    modifier = Modifier.fillMaxWidth(),
                    placeholder = { Text("کد دعوت") },
                    singleLine = true,
                    isError = state.error != null,
                    shape = RoundedCornerShape(13.dp),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Go),
                    keyboardActions = KeyboardActions(onGo = { viewModel.join() }),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = Brand,
                        cursorColor = Brand,
                    ),
                )
                if (state.error != null) {
                    Text(
                        text = state.error!!,
                        color = ErrorRed,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                Button(
                    onClick = viewModel::join,
                    enabled = !state.joining,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(50.dp),
                    shape = RoundedCornerShape(13.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Brand,
                        contentColor = OnBrand,
                    ),
                ) {
                    if (state.joining) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(21.dp),
                            strokeWidth = 2.dp,
                            color = OnBrand,
                        )
                    } else {
                        Text("پیوستن به اتاق", fontWeight = FontWeight.Bold)
                    }
                }
            }

            // Creation needs a title (and, for a series, an episode), so the clear
            // path is to pick one first instead of inventing a room without content.
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(20.dp))
                    .background(NeutralSurface)
                    .border(1.dp, Brand.copy(alpha = 0.34f), RoundedCornerShape(20.dp))
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Icon(
                        imageVector = Icons.Rounded.Add,
                        contentDescription = null,
                        tint = Brand,
                        modifier = Modifier.size(20.dp),
                    )
                    Text(
                        text = "اتاق تازه بساز",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                    )
                }
                Text(
                    text = "یک فیلم یا قسمت را باز کن و روی «تماشای گروهی» بزن. دکمهٔ آن در قهرمان صفحهٔ هر عنوان، همیشه در دسترس است.",
                    style = MaterialTheme.typography.bodySmall,
                    color = TextSecondary,
                )
                Button(
                    onClick = onBrowseTitles,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(48.dp),
                    shape = RoundedCornerShape(13.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Brand,
                        contentColor = OnBrand,
                    ),
                ) {
                    Icon(
                        imageVector = Icons.Rounded.PlayArrow,
                        contentDescription = null,
                        modifier = Modifier.size(19.dp),
                    )
                    Spacer(Modifier.size(7.dp))
                    Text("انتخاب فیلم یا سریال", fontWeight = FontWeight.Bold)
                }
            }

            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(18.dp))
                    .background(BgElevated)
                    .border(1.dp, OutlineSoft.copy(alpha = 0.55f), RoundedCornerShape(18.dp))
                    .padding(horizontal = 14.dp, vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Text(
                    text = "در اتاق چه خبر است؟",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(bottom = 2.dp),
                )
                FeatureRow("پخش هماهنگ برای همهٔ اعضا")
                FeatureRow("گفت‌وگوی زنده حین تماشا")
                FeatureRow("کنترل پخش در دست میزبان")
            }

            if (!isLoggedIn) {
                OutlinedButton(
                    onClick = onRequireLogin,
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(13.dp),
                    colors = ButtonDefaults.outlinedButtonColors(
                        contentColor = MaterialTheme.colorScheme.onSurface,
                    ),
                ) {
                    Text("ورود به حساب", fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun FeatureRow(text: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Box(
            modifier = Modifier
                .size(22.dp)
                .clip(CircleShape)
                .background(Brand.copy(alpha = 0.13f)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = Icons.Rounded.CheckCircle,
                contentDescription = null,
                tint = Brand,
                modifier = Modifier.size(15.dp),
            )
        }
        Text(
            text = text,
            style = MaterialTheme.typography.bodyMedium,
            color = TextMuted,
        )
    }
}
