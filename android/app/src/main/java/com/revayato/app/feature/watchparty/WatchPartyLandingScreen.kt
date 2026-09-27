package com.revayato.app.feature.watchparty

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Groups
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.BrandGreen
import com.revayato.app.core.theme.BrandMint
import com.revayato.app.core.theme.ErrorRed
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextSecondary

@Composable
fun WatchPartyLandingScreen(
    isLoggedIn: Boolean,
    onEnterRoom: (String) -> Unit,
    onRequireLogin: () -> Unit,
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
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(
            Icons.Rounded.Groups,
            contentDescription = null,
            tint = BrandMint,
            modifier = Modifier.size(64.dp),
        )
        Spacer(Modifier.height(16.dp))
        Text(
            "تماشای گروهی",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(8.dp))
        Text(
            "کد دعوت دوستت رو وارد کن تا با هم و کاملاً هماهنگ تماشا کنید. برای ساختن اتاق جدید، از صفحهٔ هر فیلم یا قسمت روی «تماشای گروهی» بزن.",
            style = MaterialTheme.typography.bodyMedium,
            color = TextSecondary,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(28.dp))
        OutlinedTextField(
            value = state.code,
            onValueChange = viewModel::onCodeChange,
            modifier = Modifier.fillMaxWidth(),
            placeholder = { Text("کد دعوت") },
            singleLine = true,
            isError = state.error != null,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Go),
            keyboardActions = KeyboardActions(onGo = { viewModel.join() }),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = BrandMint,
                cursorColor = BrandMint,
            ),
        )
        if (state.error != null) {
            Spacer(Modifier.height(8.dp))
            Text(
                state.error!!,
                color = ErrorRed,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        Spacer(Modifier.height(20.dp))
        Button(
            onClick = viewModel::join,
            enabled = !state.joining,
            modifier = Modifier
                .fillMaxWidth()
                .height(52.dp),
            shape = RoundedCornerShape(14.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = BrandMint,
                contentColor = OnBrand,
            ),
        ) {
            if (state.joining) {
                CircularProgressIndicator(
                    modifier = Modifier.size(22.dp),
                    strokeWidth = 2.dp,
                    color = OnBrand,
                )
            } else {
                Text("پیوستن به اتاق", fontWeight = FontWeight.Bold)
            }
        }
        Spacer(Modifier.height(24.dp))
        FeatureRow("پخش کاملاً هماهنگ برای همه اعضا")
        FeatureRow("گفتگوی زنده حین تماشا")
        FeatureRow("کنترل پخش در دست میزبان")
    }
}

@Composable
private fun FeatureRow(text: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Spacer(
            Modifier
                .size(7.dp)
                .background(BrandGreen, RoundedCornerShape(4.dp)),
        )
        Spacer(Modifier.size(10.dp))
        Text(text, style = MaterialTheme.typography.bodyMedium, color = TextMuted)
    }
}
