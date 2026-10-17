package com.revayato.app.feature.auth

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
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
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material.icons.rounded.AlternateEmail
import androidx.compose.material.icons.rounded.Bookmarks
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Devices
import androidx.compose.material.icons.rounded.ErrorOutline
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.MarkEmailRead
import androidx.compose.material.icons.rounded.Person
import androidx.compose.material.icons.rounded.RadioButtonUnchecked
import androidx.compose.material.icons.rounded.StarRate
import androidx.compose.material.icons.rounded.Visibility
import androidx.compose.material.icons.rounded.VisibilityOff
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.getValue
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.R
import com.revayato.app.core.theme.IsDarkTheme
import com.revayato.app.core.theme.AccentYellow
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.BgMain
import com.revayato.app.core.theme.Brand
import com.revayato.app.core.theme.ErrorRed
import com.revayato.app.core.theme.NeutralSurface
import com.revayato.app.core.theme.NeutralSurfaceActive
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.core.theme.TextSecondary

/*
 * Login / signup / reset. One calm layout for all three: the روایتو mark on a
 * warm hearth wash, a ورود | ثبت‌نام switch, then a single card with the
 * fields. Errors sit under the field they are about (or in the card when the
 * server sends them) and stay until the user edits, instead of a toast that
 * vanishes before it is read. One amber button per screen, no glow, no
 * entrance animation between the user and the first field.
 */

private enum class AuthMode { LOGIN, REGISTER }

@Composable
fun LoginScreen(
    onBack: () -> Unit,
    onLoggedIn: () -> Unit,
    onRegister: () -> Unit,
    onForgotPassword: () -> Unit,
    viewModel: AuthViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val focus = LocalFocusManager.current
    LaunchedEffect(state.done) {
        if (state.done) {
            viewModel.consumeDone()
            onLoggedIn()
        }
    }
    val submit = {
        focus.clearFocus()
        viewModel.login()
    }
    AuthScaffold(
        title = "خوش برگشتی",
        subtitle = "وارد حسابت شو تا تماشا را از همان‌جا که ماندی ادامه بدهی.",
        onBack = onBack,
        mode = AuthMode.LOGIN,
        onSwitchMode = onRegister,
    ) {
        AuthField(
            value = state.identifier,
            onChange = viewModel::onIdentifierChange,
            label = "ایمیل یا نام کاربری",
            icon = Icons.Rounded.Person,
            keyboardType = KeyboardType.Email,
            error = state.fieldError(AuthInput.IDENTIFIER),
        )
        PasswordField(
            value = state.password,
            onChange = viewModel::onPasswordChange,
            label = "رمز عبور",
            error = state.fieldError(AuthInput.PASSWORD),
            onDone = submit,
        )
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            TextButton(onClick = onForgotPassword) {
                Text("رمز عبور را فراموش کردی؟", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
            }
        }
        FormNotice(state.generalError())
        AuthButton(text = "ورود", loadingText = "در حال ورود…", loading = state.loading, onClick = submit)
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
    val focus = LocalFocusManager.current
    LaunchedEffect(state.done) {
        if (state.done) {
            viewModel.consumeDone()
            onRegistered()
        }
    }
    val submit = {
        focus.clearFocus()
        viewModel.register()
    }
    AuthScaffold(
        title = "به روایتو بپیوند",
        subtitle = "ساخت حساب رایگان است و کمتر از یک دقیقه طول می‌کشد.",
        onBack = onBack,
        mode = AuthMode.REGISTER,
        onSwitchMode = onLogin,
        extra = { RegisterPerks() },
    ) {
        AuthField(
            value = state.email,
            onChange = viewModel::onEmailChange,
            label = "ایمیل",
            icon = Icons.Rounded.AlternateEmail,
            keyboardType = KeyboardType.Email,
            placeholder = "name@mail.com",
            error = state.fieldError(AuthInput.EMAIL),
        )
        AuthField(
            value = state.username,
            onChange = viewModel::onUsernameChange,
            label = "نام کاربری",
            icon = Icons.Rounded.Person,
            keyboardType = KeyboardType.Ascii,
            hint = "با همین نام در پروفایل و نظرها دیده می‌شوی.",
            error = state.fieldError(AuthInput.USERNAME),
        )
        PasswordField(
            value = state.password,
            onChange = viewModel::onPasswordChange,
            label = "رمز عبور",
            error = state.fieldError(AuthInput.PASSWORD),
            onDone = submit,
        )
        PasswordChecklist(password = state.password)
        FormNotice(state.generalError())
        AuthButton(text = "ساخت حساب", loadingText = "در حال ساخت حساب…", loading = state.loading, onClick = submit)
    }
}

@Composable
fun ForgotPasswordScreen(
    onBack: () -> Unit,
    viewModel: AuthViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val focus = LocalFocusManager.current
    val submit = {
        focus.clearFocus()
        viewModel.requestReset()
    }
    AuthScaffold(
        title = "بازیابی رمز عبور",
        subtitle = "ایمیل حسابت را بنویس؛ لینک ساخت رمز تازه را برایت می‌فرستیم.",
        onBack = onBack,
    ) {
        val info = state.info
        if (info != null) {
            ResetSent(message = info, onBack = onBack)
        } else {
            AuthField(
                value = state.email,
                onChange = viewModel::onEmailChange,
                label = "ایمیل",
                icon = Icons.Rounded.AlternateEmail,
                keyboardType = KeyboardType.Email,
                placeholder = "name@mail.com",
                imeAction = ImeAction.Send,
                onImeAction = submit,
                error = state.fieldError(AuthInput.EMAIL),
            )
            FormNotice(state.generalError())
            AuthButton(text = "ارسال لینک بازیابی", loadingText = "در حال ارسال…", loading = state.loading, onClick = submit)
        }
    }
}

private fun AuthFormState.fieldError(field: AuthInput): String? = error?.takeIf { errorField == field }

private fun AuthFormState.generalError(): String? = error?.takeIf { errorField == null }

@Composable
private fun AuthScaffold(
    title: String,
    subtitle: String,
    onBack: () -> Unit,
    mode: AuthMode? = null,
    onSwitchMode: () -> Unit = {},
    extra: (@Composable () -> Unit)? = null,
    content: @Composable () -> Unit,
) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(BgMain)
            // A low warm wash behind the mark, the logo's hearth colour fading into
            // the app background. Quiet on purpose: no glow, no motion.
            .background(
                Brush.verticalGradient(
                    0f to if (IsDarkTheme) Color(0xFF2B1A12) else Color(0xFFF3E6D6),
                    0.42f to BgMain,
                ),
            ),
    ) {
        Column(
            Modifier
                .fillMaxSize()
                .statusBarsPadding()
                .navigationBarsPadding()
                .imePadding()
                .verticalScroll(rememberScrollState()),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Row(Modifier.fillMaxWidth().padding(8.dp)) {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Rounded.ArrowForward, contentDescription = "بازگشت", tint = TextPrimary)
                }
            }

            Column(
                Modifier
                    .widthIn(max = 460.dp)
                    .fillMaxWidth()
                    .padding(horizontal = 20.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Image(
                    painter = painterResource(R.drawable.brand_logo),
                    contentDescription = "روایتو",
                    modifier = Modifier.size(width = 52.dp, height = 65.dp),
                )
                Spacer(Modifier.height(18.dp))
                Text(
                    title,
                    style = MaterialTheme.typography.headlineSmall,
                    color = TextPrimary,
                    textAlign = TextAlign.Center,
                )
                Spacer(Modifier.height(8.dp))
                Text(
                    subtitle,
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextSecondary,
                    textAlign = TextAlign.Center,
                )
                extra?.let {
                    Spacer(Modifier.height(16.dp))
                    it()
                }
                Spacer(Modifier.height(24.dp))

                if (mode != null) {
                    ModeSwitch(mode = mode, onSwitch = onSwitchMode)
                    Spacer(Modifier.height(12.dp))
                }

                Column(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(20.dp))
                        .background(BgElevated)
                        .border(BorderStroke(1.dp, OutlineSoft), RoundedCornerShape(20.dp))
                        .padding(horizontal = 18.dp, vertical = 20.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    content()
                }

                Spacer(Modifier.height(12.dp))
                TextButton(onClick = onBack) {
                    Text("فعلاً بدون حساب ادامه می‌دهم", color = TextMuted, style = MaterialTheme.typography.labelLarge)
                }
                Spacer(Modifier.height(24.dp))
            }
        }
    }
}

/** «ورود | ثبت‌نام» segmented switch; the other tab swaps to its screen. */
@Composable
private fun ModeSwitch(mode: AuthMode, onSwitch: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(NeutralSurface)
            .padding(4.dp)
            .selectableGroup(),
    ) {
        listOf(AuthMode.LOGIN to "ورود", AuthMode.REGISTER to "ثبت‌نام").forEach { (tab, label) ->
            val selected = tab == mode
            Box(
                Modifier
                    .weight(1f)
                    .height(42.dp)
                    .clip(RoundedCornerShape(10.dp))
                    .background(if (selected) NeutralSurfaceActive else Color.Transparent)
                    .selectable(
                        selected = selected,
                        role = Role.Tab,
                        onClick = { if (!selected) onSwitch() },
                    ),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    label,
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = if (selected) FontWeight.Bold else FontWeight.Medium,
                    color = if (selected) TextPrimary else TextMuted,
                )
            }
        }
    }
}

/** What an account gets you, said once above the signup form. */
@Composable
private fun RegisterPerks() {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Perk(Icons.Rounded.Devices, "ادامهٔ تماشا روی همهٔ دستگاه‌ها")
        Perk(Icons.Rounded.Bookmarks, "لیست تماشا و کالکشن‌های خودت")
        Perk(Icons.Rounded.StarRate, "امتیاز و نظر دربارهٔ فیلم‌ها")
    }
}

@Composable
private fun Perk(icon: ImageVector, text: String) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Icon(icon, contentDescription = null, tint = Brand, modifier = Modifier.size(18.dp))
        Text(text, style = MaterialTheme.typography.bodySmall, color = TextSecondary)
    }
}

@Composable
private fun AuthField(
    value: String,
    onChange: (String) -> Unit,
    label: String,
    icon: ImageVector,
    keyboardType: KeyboardType = KeyboardType.Text,
    imeAction: ImeAction = ImeAction.Next,
    onImeAction: (() -> Unit)? = null,
    placeholder: String? = null,
    hint: String? = null,
    error: String? = null,
    trailingIcon: (@Composable () -> Unit)? = null,
    visualTransformation: VisualTransformation = VisualTransformation.None,
) {
    val supporting = error ?: hint
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        placeholder = placeholder?.let { { Text(it, color = TextMuted, style = LocalTextStyle.current.copy(textDirection = TextDirection.Ltr)) } },
        leadingIcon = { Icon(icon, contentDescription = null, modifier = Modifier.size(20.dp)) },
        trailingIcon = trailingIcon,
        supportingText = supporting?.let { { Text(it) } },
        isError = error != null,
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        // Emails, usernames and passwords are Latin: type them left-to-right even
        // inside the right-to-left form.
        textStyle = LocalTextStyle.current.copy(textDirection = TextDirection.ContentOrLtr),
        visualTransformation = visualTransformation,
        keyboardOptions = KeyboardOptions(keyboardType = keyboardType, imeAction = imeAction),
        keyboardActions = KeyboardActions(
            onDone = { onImeAction?.invoke() },
            onSend = { onImeAction?.invoke() },
        ),
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = Brand,
            unfocusedBorderColor = OutlineSoft,
            focusedLabelColor = Brand,
            unfocusedLabelColor = TextMuted,
            cursorColor = Brand,
            focusedTextColor = TextPrimary,
            unfocusedTextColor = TextPrimary,
            focusedLeadingIconColor = Brand,
            unfocusedLeadingIconColor = TextMuted,
            focusedSupportingTextColor = TextMuted,
            unfocusedSupportingTextColor = TextMuted,
            errorBorderColor = ErrorRed,
            errorLabelColor = ErrorRed,
            errorLeadingIconColor = ErrorRed,
            errorSupportingTextColor = ErrorRed,
            errorCursorColor = ErrorRed,
            focusedContainerColor = Color.Transparent,
            unfocusedContainerColor = Color.Transparent,
        ),
    )
}

@Composable
private fun PasswordField(
    value: String,
    onChange: (String) -> Unit,
    label: String,
    error: String?,
    onDone: () -> Unit,
) {
    var visible by rememberSaveable { mutableStateOf(false) }
    AuthField(
        value = value,
        onChange = onChange,
        label = label,
        icon = Icons.Rounded.Lock,
        keyboardType = KeyboardType.Password,
        imeAction = ImeAction.Done,
        onImeAction = onDone,
        error = error,
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

/**
 * Signup password guidance: a three-step strength bar and the three rules
 * behind it, each ticking off as it is met, so the user sees what to add
 * rather than only a verdict.
 */
@Composable
private fun PasswordChecklist(password: String) {
    val rules = listOf(
        "حداقل ۸ کاراکتر" to (password.length >= 8),
        "هم حرف، هم عدد" to (password.any { it.isDigit() } && password.any { it.isLetter() }),
        "یک نماد یا ۱۲ کاراکتر به بالا" to (password.any { !it.isLetterOrDigit() } || password.length >= 12),
    )
    val score = rules.count { it.second }
    val (label, color) = when {
        password.isEmpty() -> "" to OutlineSoft
        score <= 1 -> "ضعیف" to ErrorRed
        score == 2 -> "متوسط" to AccentYellow
        else -> "قوی" to Brand
    }
    Column(
        Modifier
            .fillMaxWidth()
            .semantics { contentDescription = if (label.isEmpty()) "قدرت رمز" else "قدرت رمز: $label" },
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
            repeat(3) { index ->
                Box(
                    Modifier
                        .weight(1f)
                        .height(4.dp)
                        .clip(CircleShape)
                        .background(if (password.isNotEmpty() && index < score) color else OutlineSoft),
                )
            }
            if (label.isNotEmpty()) {
                Text(label, style = MaterialTheme.typography.labelSmall, color = color, modifier = Modifier.padding(start = 4.dp))
            }
        }
        rules.forEach { (rule, met) ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Icon(
                    if (met) Icons.Rounded.CheckCircle else Icons.Rounded.RadioButtonUnchecked,
                    contentDescription = null,
                    tint = if (met) Brand else TextMuted,
                    modifier = Modifier.size(16.dp),
                )
                Text(rule, style = MaterialTheme.typography.labelSmall, color = if (met) TextSecondary else TextMuted)
            }
        }
    }
}

/** A server or network error, shown in the card until the user edits a field. */
@Composable
private fun FormNotice(message: String?) {
    if (message.isNullOrBlank()) return
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(ErrorRed.copy(alpha = 0.12f))
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Icon(Icons.Rounded.ErrorOutline, contentDescription = null, tint = ErrorRed, modifier = Modifier.size(20.dp))
        Text(message, color = TextPrimary, style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
    }
}

@Composable
private fun ResetSent(message: String, onBack: () -> Unit) {
    Column(
        Modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(
            Modifier
                .size(56.dp)
                .clip(CircleShape)
                .background(Brand.copy(alpha = 0.14f)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(Icons.Rounded.MarkEmailRead, contentDescription = null, tint = Brand, modifier = Modifier.size(28.dp))
        }
        Text("ایمیلت را ببین", style = MaterialTheme.typography.titleMedium, color = TextPrimary)
        Text(message, style = MaterialTheme.typography.bodyMedium, color = TextSecondary, textAlign = TextAlign.Center)
        Text(
            "اگر تا چند دقیقه نرسید، پوشهٔ اسپم را هم نگاه کن.",
            style = MaterialTheme.typography.bodySmall,
            color = TextMuted,
            textAlign = TextAlign.Center,
        )
        AuthButton(text = "بازگشت به ورود", loadingText = "", loading = false, onClick = onBack)
    }
}

/** The one filled button on each auth screen: flat brand amber, ink text. */
@Composable
private fun AuthButton(text: String, loadingText: String, loading: Boolean, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        enabled = !loading,
        modifier = Modifier.fillMaxWidth().height(52.dp),
        shape = RoundedCornerShape(14.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = Brand,
            contentColor = OnBrand,
            disabledContainerColor = Brand.copy(alpha = 0.55f),
            disabledContentColor = OnBrand,
        ),
        elevation = null,
    ) {
        if (loading) {
            CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp, color = OnBrand)
            Spacer(Modifier.size(10.dp))
            Text(loadingText, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleSmall)
        } else {
            Text(text, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleSmall)
        }
    }
}
