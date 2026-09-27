package com.revayato.app.feature.auth

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.rounded.ErrorOutline
import androidx.compose.material.icons.rounded.Movie
import androidx.compose.material.icons.rounded.Visibility
import androidx.compose.material.icons.rounded.VisibilityOff
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.BgMain
import com.revayato.app.core.theme.BgSurface
import com.revayato.app.core.theme.BrandGreen
import com.revayato.app.core.theme.BrandMint
import com.revayato.app.core.theme.ErrorRed
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.core.theme.TextSecondary

@Composable
fun LoginScreen(
    onBack: () -> Unit,
    onLoggedIn: () -> Unit,
    onRegister: () -> Unit,
    onForgotPassword: () -> Unit,
    viewModel: AuthViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(state.done) {
        if (state.done) {
            viewModel.consumeDone()
            onLoggedIn()
        }
    }
    AuthScaffold(
        title = "خوش برگشتی 👋",
        subtitle = "به حساب روایتو وارد شو و تماشا را ادامه بده",
        onBack = onBack,
        notice = state.error,
    ) {
        AuthField(
            value = state.identifier,
            onChange = viewModel::onIdentifierChange,
            label = "ایمیل یا نام کاربری",
            keyboardType = KeyboardType.Text,
        )
        Spacer(Modifier.height(14.dp))
        PasswordField(
            value = state.password,
            onChange = viewModel::onPasswordChange,
            label = "رمز عبور",
            imeAction = ImeAction.Done,
        )
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            TextButton(onClick = onForgotPassword) {
                Text("رمز عبور را فراموش کردی؟", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
            }
        }
        Spacer(Modifier.height(6.dp))
        AuthButton(text = "ورود", loading = state.loading, onClick = viewModel::login)
        Spacer(Modifier.height(16.dp))
        AuthSwitchRow(prompt = "حساب نداری؟", action = "ثبت‌نام", onClick = onRegister)
    }
}

@Composable
fun RegisterScreen(
    onBack: () -> Unit,
    onRegistered: () -> Unit,
    onLogin: () -> Unit,
    viewModel: AuthViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(state.done) {
        if (state.done) {
            viewModel.consumeDone()
            onRegistered()
        }
    }
    AuthScaffold(
        title = "به روایتو بپیوند",
        subtitle = "چند ثانیه تا شروع تماشای هزاران فیلم و سریال",
        onBack = onBack,
        notice = state.error,
    ) {
        AuthField(
            value = state.email,
            onChange = viewModel::onEmailChange,
            label = "ایمیل",
            keyboardType = KeyboardType.Email,
        )
        Spacer(Modifier.height(14.dp))
        AuthField(
            value = state.username,
            onChange = viewModel::onUsernameChange,
            label = "نام کاربری",
        )
        Spacer(Modifier.height(14.dp))
        PasswordField(
            value = state.password,
            onChange = viewModel::onPasswordChange,
            label = "رمز عبور (حداقل ۸ کاراکتر)",
            imeAction = ImeAction.Done,
        )
        PasswordStrengthBar(password = state.password)
        Spacer(Modifier.height(6.dp))
        AuthButton(text = "ساخت حساب", loading = state.loading, onClick = viewModel::register)
        Spacer(Modifier.height(16.dp))
        AuthSwitchRow(prompt = "حساب داری؟", action = "ورود", onClick = onLogin)
    }
}

@Composable
fun ForgotPasswordScreen(
    onBack: () -> Unit,
    viewModel: AuthViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    AuthScaffold(
        title = "بازیابی رمز عبور",
        subtitle = "ایمیلت را وارد کن تا لینک بازیابی برایت بفرستیم",
        onBack = onBack,
        notice = state.error,
    ) {
        AuthField(
            value = state.email,
            onChange = viewModel::onEmailChange,
            label = "ایمیل",
            keyboardType = KeyboardType.Email,
            imeAction = ImeAction.Done,
        )
        AnimatedVisibility(visible = state.info != null) {
            Text(
                state.info.orEmpty(),
                color = BrandMint,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(top = 10.dp),
            )
        }
        Spacer(Modifier.height(10.dp))
        AuthButton(text = "ارسال لینک بازیابی", loading = state.loading, onClick = viewModel::requestReset)
    }
}

@Composable
private fun AuthScaffold(
    title: String,
    subtitle: String,
    onBack: () -> Unit,
    notice: String? = null,
    content: @Composable () -> Unit,
) {
    val topInset = WindowInsets.safeDrawing.asPaddingValues().calculateTopPadding()
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                // Cinematic vertical wash: deep black → brand-tinted midnight.
                Brush.verticalGradient(
                    0f to BgSurface,
                    0.45f to BgMain,
                    1f to Color(0xFF10221B),
                ),
            ),
    ) {
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState()),
        ) {
            Row(
                Modifier.fillMaxWidth().padding(top = topInset).padding(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(onClick = onBack) {
                    Icon(
                        Icons.AutoMirrored.Rounded.ArrowForward,
                        contentDescription = "بازگشت",
                        tint = TextPrimary,
                    )
                }
            }

            // Brand hero
            Column(
                Modifier.fillMaxWidth().padding(horizontal = 24.dp),
                horizontalAlignment = Alignment.Start,
            ) {
                BrandMark()
                Spacer(Modifier.height(24.dp))
                Text(
                    title,
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                    color = TextPrimary,
                )
                Spacer(Modifier.height(8.dp))
                Text(subtitle, style = MaterialTheme.typography.bodyMedium, color = TextSecondary)
            }

            Spacer(Modifier.height(24.dp))

            // Glass form card, animated in.
            var visible by remember { mutableStateOf(false) }
            LaunchedEffect(Unit) { visible = true }
            AnimatedVisibility(
                visible = visible,
                enter = fadeIn(tween(320)) + slideInVertically(tween(320)) { it / 6 },
            ) {
                Column(
                    Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp)
                        .clip(RoundedCornerShape(24.dp))
                        .background(Color(0x14FFFFFF))
                        .padding(20.dp),
                ) {
                    content()
                }
            }
            Spacer(Modifier.height(40.dp))
        }

        // Temporary error notification that slides in from the top.
        AuthTopToast(
            notice = notice,
            modifier = Modifier
                .align(Alignment.TopCenter)
                .padding(top = topInset + 8.dp, start = 16.dp, end = 16.dp),
        )
    }
}

/**
 * A transient, top-anchored error banner: whenever [notice] changes to a new
 * non-blank message it slides down, stays visible briefly, then auto-hides.
 */
@Composable
private fun AuthTopToast(notice: String?, modifier: Modifier = Modifier) {
    var shown by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(notice) {
        val text = notice?.takeIf { it.isNotBlank() }
        if (text != null) {
            message = text
            shown = true
            kotlinx.coroutines.delay(4000)
            shown = false
        } else {
            shown = false
        }
    }
    Box(modifier = modifier) {
        AnimatedVisibility(
            visible = shown,
            enter = slideInVertically(tween(260)) { -it } + fadeIn(tween(260)),
            exit = slideOutVertically(tween(220)) { -it } + fadeOut(tween(220)),
        ) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(14.dp))
                    .background(Color(0xF2331416))
                    .padding(horizontal = 16.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Icon(
                    Icons.Rounded.ErrorOutline,
                    contentDescription = null,
                    tint = ErrorRed,
                    modifier = Modifier.size(20.dp),
                )
                Text(
                    message.orEmpty(),
                    color = TextPrimary,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }
}

@Composable
private fun BrandMark() {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(
            modifier = Modifier
                .size(52.dp)
                .clip(RoundedCornerShape(16.dp))
                .background(Brush.linearGradient(listOf(BrandMint, BrandGreen))),
            contentAlignment = Alignment.Center,
        ) {
            Icon(Icons.Rounded.Movie, contentDescription = null, tint = OnBrand, modifier = Modifier.size(28.dp))
        }
        Text(
            "روایتو",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Black,
            color = TextPrimary,
        )
    }
}

@Composable
private fun AuthSwitchRow(prompt: String, action: String, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(prompt, color = TextSecondary, style = MaterialTheme.typography.bodyMedium)
        TextButton(onClick = onClick) { Text(action, color = BrandMint, fontWeight = FontWeight.Bold) }
    }
}

@Composable
private fun AuthField(
    value: String,
    onChange: (String) -> Unit,
    label: String,
    isPassword: Boolean = false,
    keyboardType: KeyboardType = KeyboardType.Text,
    imeAction: ImeAction = ImeAction.Next,
    trailingIcon: (@Composable () -> Unit)? = null,
    visualTransformation: VisualTransformation = VisualTransformation.None,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        trailingIcon = trailingIcon,
        visualTransformation = visualTransformation,
        keyboardOptions = KeyboardOptions(
            keyboardType = if (isPassword) KeyboardType.Password else keyboardType,
            imeAction = imeAction,
        ),
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = BrandMint,
            unfocusedBorderColor = OutlineSoft,
            focusedLabelColor = BrandMint,
            unfocusedLabelColor = TextMuted,
            cursorColor = BrandMint,
            focusedTextColor = TextPrimary,
            unfocusedTextColor = TextPrimary,
        ),
    )
}

@Composable
private fun PasswordField(
    value: String,
    onChange: (String) -> Unit,
    label: String,
    imeAction: ImeAction = ImeAction.Done,
) {
    var visible by remember { mutableStateOf(false) }
    AuthField(
        value = value,
        onChange = onChange,
        label = label,
        isPassword = true,
        imeAction = imeAction,
        visualTransformation = if (visible) VisualTransformation.None else PasswordVisualTransformation(),
        trailingIcon = {
            IconButton(onClick = { visible = !visible }) {
                Icon(
                    imageVector = if (visible) Icons.Rounded.VisibilityOff else Icons.Rounded.Visibility,
                    contentDescription = if (visible) "پنهان کردن رمز" else "نمایش رمز",
                    tint = TextMuted,
                )
            }
        },
    )
}

/** Lightweight inline password-strength hint (0–3 segments). */
@Composable
private fun PasswordStrengthBar(password: String) {
    if (password.isEmpty()) return
    val score = passwordScore(password)
    val (label, color) = when (score) {
        0, 1 -> "ضعیف" to ErrorRed
        2 -> "متوسط" to Color(0xFFF5C518)
        else -> "قوی" to BrandMint
    }
    Column(Modifier.fillMaxWidth().padding(top = 10.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            repeat(3) { index ->
                Box(
                    modifier = Modifier
                        .weight(1f)
                        .height(4.dp)
                        .clip(CircleShape)
                        .background(if (index < score) color else OutlineSoft),
                )
            }
        }
        Text(
            "قدرت رمز: $label",
            style = MaterialTheme.typography.labelSmall,
            color = color,
            modifier = Modifier.padding(top = 4.dp),
        )
    }
}

private fun passwordScore(password: String): Int {
    var score = 0
    if (password.length >= 8) score++
    if (password.any { it.isDigit() } && password.any { it.isLetter() }) score++
    if (password.any { !it.isLetterOrDigit() } || password.length >= 12) score++
    return score
}

@Composable
private fun AuthButton(text: String, loading: Boolean, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        enabled = !loading,
        modifier = Modifier.fillMaxWidth().height(54.dp),
        shape = RoundedCornerShape(16.dp),
        colors = ButtonDefaults.buttonColors(containerColor = BrandMint, contentColor = OnBrand),
    ) {
        if (loading) {
            CircularProgressIndicator(modifier = Modifier.size(22.dp), strokeWidth = 2.dp, color = OnBrand)
        } else {
            Text(text, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
        }
    }
}
