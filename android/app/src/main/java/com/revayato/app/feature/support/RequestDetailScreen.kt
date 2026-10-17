package com.revayato.app.feature.support

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.Send
import androidx.compose.material.icons.rounded.Verified
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.Brand
import com.revayato.app.core.theme.ErrorRed
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.SurfaceSelected
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.SupportMessageDto
import com.revayato.app.data.model.SupportTicketDetailDto
import com.revayato.app.feature.collection.BackTopBar
import com.revayato.app.ui.components.ErrorState
import com.revayato.app.ui.components.LoadingState
import com.revayato.app.ui.components.RevayatoSpinner

/**
 * One support conversation: header with subject + status, the opening message and
 * every reply as chat bubbles (تیم روایتو on one side, the user on the other), and
 * a reply composer pinned to the bottom while the ticket is still open.
 */
@Composable
fun RequestDetailScreen(
    code: String,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: RequestDetailViewModel = hiltViewModel(),
) {
    LaunchedEffect(code) { viewModel.load(code) }
    val state by viewModel.state.collectAsStateWithLifecycle()

    Scaffold(
        modifier = modifier.fillMaxSize(),
        containerColor = MaterialTheme.colorScheme.background,
        topBar = { BackTopBar(title = "گفتگو با روایتو", onBack = onBack) },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when (val s = state.ticket) {
                is UiState.Loading -> LoadingState(Modifier.fillMaxSize())
                is UiState.Error -> ErrorState(s.message, Modifier.fillMaxSize(), onRetry = { viewModel.load(code) })
                is UiState.Success -> Conversation(
                    ticket = s.data,
                    sending = state.sending,
                    sendError = state.sendError,
                    onSend = { body -> viewModel.reply(code, body) {} },
                    onConsumeError = viewModel::consumeSendError,
                )
            }
        }
    }
}

@Composable
private fun Conversation(
    ticket: SupportTicketDetailDto,
    sending: Boolean,
    sendError: String?,
    onSend: (String) -> Unit,
    onConsumeError: () -> Unit,
) {
    val listState = rememberLazyListState()
    // Keep the newest message in view as the thread grows.
    LaunchedEffect(ticket.messages.size) {
        val last = ticket.messages.size // header(0) + opening(1) + messages
        if (last > 0) listState.animateScrollToItem(last + 1)
    }

    Column(Modifier.fillMaxSize()) {
        LazyColumn(
            state = listState,
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp, 16.dp, 16.dp, 20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item(key = "header") { ConversationHeader(ticket) }
            item(key = "opening") {
                MessageBubble(
                    isStaff = false,
                    body = ticket.body,
                    stamp = ticket.createdAt,
                    author = ticket.username,
                )
            }
            itemsIndexed(ticket.messages, key = { _, m -> m.id }) { _, message ->
                MessageBubble(
                    isStaff = message.isStaffReply,
                    body = message.body,
                    stamp = message.createdAt,
                    author = message.authorUsername,
                )
            }
        }

        if (ticket.isClosed) {
            Text(
                text = "این گفتگو بسته شده است. برای موضوع تازه، درخواست جدیدی ثبت کن.",
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted,
                modifier = Modifier
                    .fillMaxWidth()
                    .background(BgElevated)
                    .padding(16.dp)
                    .navigationBarsPadding(),
            )
        } else {
            ReplyComposer(
                sending = sending,
                error = sendError,
                onSend = onSend,
                onConsumeError = onConsumeError,
            )
        }
    }
}

@Composable
private fun ConversationHeader(ticket: SupportTicketDetailDto) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(BgElevated, RoundedCornerShape(16.dp))
            .border(1.dp, OutlineSoft, RoundedCornerShape(16.dp))
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(
                Modifier.size(40.dp).background(Brand.copy(alpha = 0.14f), RoundedCornerShape(11.dp)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(categoryIcon(ticket.category), contentDescription = null, tint = Brand, modifier = Modifier.size(21.dp))
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    text = ticket.subject.ifBlank { ticket.categoryLabel.ifBlank { categoryLabelFallback(ticket.category) } },
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Bold,
                    color = TextPrimary,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = toFaDigits("${ticket.categoryLabel.ifBlank { categoryLabelFallback(ticket.category) }} · #${ticket.trackingCode}"),
                    style = MaterialTheme.typography.labelSmall,
                    color = TextMuted,
                )
            }
            StatusPill(status = ticket.status, label = ticket.statusLabel)
        }
        if (ticket.relatedTitle.isNotBlank()) {
            Text(
                text = "مرتبط با: ${ticket.relatedTitle}${ticket.relatedYear?.let { " (${toFaDigits(it.toString())})" } ?: ""}",
                style = MaterialTheme.typography.labelMedium,
                color = TextSecondary,
            )
        }
    }
}

@Composable
private fun MessageBubble(isStaff: Boolean, body: String, stamp: String, author: String) {
    if (body.isBlank()) return
    val bubbleColor = if (isStaff) Brand.copy(alpha = 0.12f) else SurfaceSelected.copy(alpha = 0.5f)
    val borderColor = if (isStaff) Brand.copy(alpha = 0.32f) else OutlineSoft
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isStaff) Arrangement.Start else Arrangement.End,
    ) {
        Column(
            modifier = Modifier
                .widthIn(max = 320.dp)
                .background(bubbleColor, RoundedCornerShape(14.dp))
                .border(1.dp, borderColor, RoundedCornerShape(14.dp))
                .padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(5.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                if (isStaff) {
                    Icon(Icons.Rounded.Verified, contentDescription = null, tint = Brand, modifier = Modifier.size(14.dp))
                }
                Text(
                    text = if (isStaff) "تیم روایتو" else author.ifBlank { "شما" },
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                    color = if (isStaff) Brand else TextSecondary,
                )
            }
            Text(body, style = MaterialTheme.typography.bodyMedium, color = TextPrimary)
            if (stamp.isNotBlank()) {
                Text(supportDateTime(stamp), style = MaterialTheme.typography.labelSmall, color = TextMuted)
            }
        }
    }
}

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
private fun ReplyComposer(
    sending: Boolean,
    error: String?,
    onSend: (String) -> Unit,
    onConsumeError: () -> Unit,
) {
    var text by remember { mutableStateOf("") }
    Column(
        Modifier
            .fillMaxWidth()
            .background(BgElevated)
            .padding(horizontal = 12.dp, vertical = 10.dp)
            .imePadding()
            .navigationBarsPadding(),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        if (!error.isNullOrBlank()) {
            Text(error, color = ErrorRed, style = MaterialTheme.typography.bodySmall)
        }
        Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = text,
                onValueChange = { text = it; if (!error.isNullOrBlank()) onConsumeError() },
                placeholder = { Text("پاسخت را بنویس…") },
                modifier = Modifier.weight(1f),
                minLines = 1,
                maxLines = 5,
                keyboardOptions = KeyboardOptions.Default,
                shape = RoundedCornerShape(16.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Brand,
                    unfocusedBorderColor = OutlineSoft,
                    cursorColor = Brand,
                    focusedTextColor = TextPrimary,
                    unfocusedTextColor = TextPrimary,
                    focusedContainerColor = Color.Transparent,
                    unfocusedContainerColor = Color.Transparent,
                ),
            )
            val canSend = text.isNotBlank() && !sending
            Box(
                Modifier
                    .size(50.dp)
                    .background(if (canSend) Brand else SurfaceSelected, RoundedCornerShape(15.dp)),
                contentAlignment = Alignment.Center,
            ) {
                if (sending) {
                    RevayatoSpinner(size = 20.dp, color = OnBrand)
                } else {
                    IconButton(
                        onClick = { if (canSend) { onSend(text.trim()); text = "" } },
                        enabled = canSend,
                    ) {
                        Icon(
                            Icons.AutoMirrored.Rounded.Send,
                            contentDescription = "ارسال",
                            tint = if (canSend) OnBrand else TextMuted,
                        )
                    }
                }
            }
        }
    }
}
