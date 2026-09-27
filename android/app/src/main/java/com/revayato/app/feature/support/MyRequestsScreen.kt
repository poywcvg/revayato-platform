package com.revayato.app.feature.support

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.KeyboardArrowLeft
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Circle
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.BrandMint
import com.revayato.app.core.theme.ErrorRed
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.SurfaceSelected
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.SupportTicketListItemDto
import com.revayato.app.feature.collection.BackTopBar
import com.revayato.app.ui.components.EmptyState
import com.revayato.app.ui.components.ErrorState
import com.revayato.app.ui.components.LoadingState
import com.revayato.app.ui.components.RevayatoSpinner

/**
 * «درخواست‌های من» — the user's own support conversations with the روایتو team.
 * List of tickets (category, subject, status, unread flag) plus a «درخواست جدید»
 * composer. Mirrors the web /requests page. Admin side stays web-only.
 */
@Composable
fun MyRequestsScreen(
    isLoggedIn: Boolean,
    onBack: () -> Unit,
    onOpenRequest: (code: String) -> Unit,
    onRequireLogin: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: MyRequestsViewModel = hiltViewModel(),
) {
    if (!isLoggedIn) {
        Column(modifier.fillMaxSize()) {
            BackTopBar(title = "درخواست‌های من", onBack = onBack)
            EmptyState(
                title = "گفتگوهایت با تیم روایتو اینجاست",
                subtitle = "برای ثبت درخواست و پیگیری پاسخ‌ها وارد شو",
                actionLabel = "ورود",
                onAction = onRequireLogin,
                modifier = Modifier.fillMaxSize(),
            )
        }
        return
    }

    LaunchedEffect(Unit) { viewModel.load() }
    val state by viewModel.state.collectAsStateWithLifecycle()
    var showCompose by remember { mutableStateOf(false) }

    Scaffold(
        modifier = modifier.fillMaxSize(),
        containerColor = MaterialTheme.colorScheme.background,
        topBar = { BackTopBar(title = "درخواست‌های من", onBack = onBack) },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { showCompose = true },
                containerColor = MaterialTheme.colorScheme.primary,
                contentColor = OnBrand,
                icon = { Icon(Icons.Rounded.Add, contentDescription = null) },
                text = { Text("درخواست جدید", fontWeight = FontWeight.Bold) },
            )
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when (val s = state.list) {
                is UiState.Loading -> LoadingState(Modifier.fillMaxSize())
                is UiState.Error -> ErrorState(s.message, Modifier.fillMaxSize(), onRetry = viewModel::load)
                is UiState.Success -> {
                    if (s.data.isEmpty()) {
                        EmptyState(
                            title = "هنوز درخواستی ثبت نکردی",
                            subtitle = "با دکمهٔ «درخواست جدید» یک عنوان درخواست کن، مشکلی را گزارش بده یا با تیم روایتو در ارتباط باش.",
                            modifier = Modifier.fillMaxSize(),
                        )
                    } else {
                        LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(16.dp, 16.dp, 16.dp, 96.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            items(s.data, key = { it.id }) { item ->
                                RequestCard(item = item, onClick = { onOpenRequest(item.trackingCode) })
                            }
                        }
                    }
                }
            }
        }
    }

    if (showCompose) {
        NewRequestSheet(
            busy = state.creating,
            error = state.createError,
            onDismiss = { showCompose = false; viewModel.consumeCreateError() },
            onSubmit = { category, subject, body ->
                viewModel.create(category, subject, body) { code ->
                    showCompose = false
                    onOpenRequest(code)
                }
            },
        )
    }
}

@Composable
private fun RequestCard(item: SupportTicketListItemDto, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(BgElevated, RoundedCornerShape(16.dp))
            .border(1.dp, OutlineSoft, RoundedCornerShape(16.dp))
            .clickable(onClick = onClick)
            .padding(14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(
            Modifier
                .size(42.dp)
                .background(BrandMint.copy(alpha = 0.14f), RoundedCornerShape(12.dp)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                categoryIcon(item.category),
                contentDescription = null,
                tint = BrandMint,
                modifier = Modifier.size(22.dp),
            )
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    text = item.subject.ifBlank { item.categoryLabel.ifBlank { categoryLabelFallback(item.category) } },
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Bold,
                    color = TextPrimary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f, fill = false),
                )
                if (item.unreadByUser) {
                    Icon(
                        Icons.Rounded.Circle,
                        contentDescription = "پاسخ خوانده‌نشده",
                        tint = BrandMint,
                        modifier = Modifier.size(9.dp),
                    )
                }
            }
            Text(
                text = buildString {
                    append(item.categoryLabel.ifBlank { categoryLabelFallback(item.category) })
                    append(" · #")
                    append(item.trackingCode)
                    val stamp = item.lastMessageAt.ifBlank { item.createdAt }
                    if (stamp.isNotBlank()) {
                        append(" · ")
                        append(supportDateTime(stamp))
                    }
                },
                style = MaterialTheme.typography.labelSmall,
                color = TextMuted,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                StatusPill(status = item.status, label = item.statusLabel)
                if (item.messageCount > 0) {
                    Text(
                        text = toFaDigits("${item.messageCount} پیام"),
                        style = MaterialTheme.typography.labelSmall,
                        color = TextMuted,
                    )
                }
            }
        }
        Icon(
            Icons.AutoMirrored.Rounded.KeyboardArrowLeft,
            contentDescription = null,
            tint = TextMuted,
            modifier = Modifier.size(20.dp),
        )
    }
}

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
private fun NewRequestSheet(
    busy: Boolean,
    error: String?,
    onDismiss: () -> Unit,
    onSubmit: (category: String, subject: String, body: String) -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var category by remember { mutableStateOf(SUPPORT_CATEGORIES.first().first) }
    var subject by remember { mutableStateOf("") }
    var body by remember { mutableStateOf("") }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = MaterialTheme.colorScheme.surface,
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp)
                .padding(bottom = 24.dp)
                .imePadding(),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("درخواست جدید", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                Text(
                    "موضوع را انتخاب کن و پیامت را بنویس؛ تیم روایتو همین‌جا پاسخ می‌دهد.",
                    style = MaterialTheme.typography.bodySmall,
                    color = TextMuted,
                )
            }

            Text("موضوع درخواست", style = MaterialTheme.typography.labelLarge, color = TextSecondary, fontWeight = FontWeight.Bold)
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                SUPPORT_CATEGORIES.chunked(2).forEach { rowItems ->
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        rowItems.forEach { (code, label) ->
                            CategoryChip(
                                code = code,
                                label = label,
                                selected = category == code,
                                onSelect = { category = code },
                                modifier = Modifier.weight(1f),
                            )
                        }
                        if (rowItems.size == 1) Spacer(Modifier.weight(1f))
                    }
                }
            }

            OutlinedTextField(
                value = subject,
                onValueChange = { subject = it.take(120) },
                label = { Text("عنوان کوتاه") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
                colors = sheetFieldColors(),
            )
            OutlinedTextField(
                value = body,
                onValueChange = { body = it },
                label = { Text("متن پیام") },
                minLines = 4,
                modifier = Modifier.fillMaxWidth(),
                colors = sheetFieldColors(),
            )

            if (!error.isNullOrBlank()) {
                Text(error, color = ErrorRed, style = MaterialTheme.typography.bodySmall)
            }

            Button(
                onClick = { onSubmit(category, subject, body) },
                enabled = !busy,
                modifier = Modifier.fillMaxWidth().height(50.dp),
                shape = RoundedCornerShape(14.dp),
                colors = ButtonDefaults.buttonColors(containerColor = BrandMint, contentColor = OnBrand),
            ) {
                if (busy) {
                    RevayatoSpinner(size = 20.dp, color = OnBrand)
                } else {
                    Text("ثبت درخواست", fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun CategoryChip(
    code: String,
    label: String,
    selected: Boolean,
    onSelect: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .background(
                if (selected) BrandMint.copy(alpha = 0.16f) else SurfaceSelected.copy(alpha = 0.4f),
                RoundedCornerShape(12.dp),
            )
            .border(
                1.dp,
                if (selected) BrandMint else OutlineSoft,
                RoundedCornerShape(12.dp),
            )
            .selectable(selected = selected, onClick = onSelect)
            .padding(horizontal = 10.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(7.dp),
    ) {
        Icon(
            categoryIcon(code),
            contentDescription = null,
            tint = if (selected) BrandMint else TextMuted,
            modifier = Modifier.size(18.dp),
        )
        Text(
            label,
            fontSize = 13.sp,
            fontWeight = if (selected) FontWeight.Bold else FontWeight.Medium,
            color = if (selected) TextPrimary else TextSecondary,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
private fun sheetFieldColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = BrandMint,
    unfocusedBorderColor = OutlineSoft,
    focusedLabelColor = BrandMint,
    unfocusedLabelColor = TextMuted,
    cursorColor = BrandMint,
    focusedTextColor = TextPrimary,
    unfocusedTextColor = TextPrimary,
    focusedContainerColor = Color.Transparent,
    unfocusedContainerColor = Color.Transparent,
)
