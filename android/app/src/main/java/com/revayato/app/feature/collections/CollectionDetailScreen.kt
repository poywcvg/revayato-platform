package com.revayato.app.feature.collections

import com.revayato.app.ui.components.FlatSnackbar
import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.ContentCopy
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.Edit
import androidx.compose.material.icons.rounded.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
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
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.CollectionItemDto
import com.revayato.app.data.model.UserCollectionDto
import com.revayato.app.feature.collection.BackTopBar
import com.revayato.app.ui.components.ErrorState
import com.revayato.app.ui.components.LoadingState
import com.revayato.app.ui.components.NetworkImage

private const val SITE_BASE = "https://revayato.com"

@Composable
fun CollectionDetailScreen(
    source: CollectionSource,
    onBack: () -> Unit,
    onOpenTitle: (contentType: String, slug: String) -> Unit,
    onOpenProfile: (username: String) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: CollectionDetailViewModel = hiltViewModel(),
) {
    LaunchedEffect(source) { viewModel.load(source) }
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    val clipboard = LocalClipboardManager.current
    val context = LocalContext.current
    var confirmDelete by remember { mutableStateOf(false) }

    LaunchedEffect(state.deleted) { if (state.deleted) onBack() }
    LaunchedEffect(state.message) {
        state.message?.let { snackbar.showSnackbar(it); viewModel.consumeMessage() }
    }

    Scaffold(
        modifier = modifier.fillMaxSize(),
        containerColor = MaterialTheme.colorScheme.background,
        topBar = { BackTopBar(title = "کالکشن", onBack = onBack) },
        snackbarHost = { SnackbarHost(snackbar) { FlatSnackbar(it) } },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when (val s = state.content) {
                is UiState.Loading -> LoadingState(Modifier.fillMaxSize())
                is UiState.Error -> ErrorState(s.message, Modifier.fillMaxSize(), onRetry = { viewModel.load(source) })
                is UiState.Success -> {
                    val collection = s.data
                    val shareLink = SITE_BASE + collection.shareUrl
                    val doShare = {
                        val text = "«${collection.title}» را در روایتو ببین:\n$shareLink"
                        val intent = Intent(Intent.ACTION_SEND).apply {
                            type = "text/plain"
                            putExtra(Intent.EXTRA_TEXT, text)
                        }
                        context.startActivity(Intent.createChooser(intent, "اشتراک کالکشن"))
                    }
                    val doCopy = {
                        clipboard.setText(AnnotatedString(shareLink))
                        viewModel.showMessage("لینک کالکشن کپی شد")
                    }

                    LazyVerticalGrid(
                        columns = GridCells.Fixed(3),
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = PaddingValues(16.dp, 0.dp, 16.dp, 32.dp),
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                        verticalArrangement = Arrangement.spacedBy(16.dp),
                    ) {
                        item(span = { GridItemSpan(3) }) {
                            CollectionHeader(
                                collection = collection,
                                canEdit = collection.isMine,
                                onShare = doShare,
                                onCopy = doCopy,
                                onEdit = viewModel::startEditing,
                                onDelete = { confirmDelete = true },
                                onOpenProfile = { onOpenProfile(collection.owner.username) },
                            )
                        }
                        if (collection.items.isEmpty()) {
                            item(span = { GridItemSpan(3) }) {
                                Box(Modifier.fillMaxWidth().padding(top = 40.dp), contentAlignment = Alignment.Center) {
                                    Text(
                                        if (collection.isMine) "هنوز عنوانی اضافه نکردی — از صفحهٔ هر فیلم یا سریال با «افزودن به کالکشن» اضافه کن."
                                        else "این کالکشن هنوز عنوانی ندارد.",
                                        color = TextMuted,
                                        style = MaterialTheme.typography.bodyMedium,
                                    )
                                }
                            }
                        } else {
                            items(collection.items, key = { "${it.contentType}-${it.id}" }) { item ->
                                CollectionItemCell(
                                    item = item,
                                    canEdit = collection.isMine,
                                    onClick = { onOpenTitle(item.contentType, item.slug) },
                                    onRemove = { viewModel.removeItem(item.contentType, item.id) },
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    if (state.editing) {
        val current = (state.content as? UiState.Success)?.data
        if (current != null) {
            CollectionEditDialog(
                title = "ویرایش کالکشن",
                confirmLabel = "ذخیره",
                initialName = current.title,
                initialDescription = current.description,
                initialVisibility = current.visibility,
                busy = false,
                error = state.editError,
                onDismiss = viewModel::stopEditing,
                onConfirm = { name, desc, vis -> viewModel.updateMeta(name, desc, vis) },
            )
        }
    }

    if (confirmDelete) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            title = { Text("حذف کالکشن؟", fontWeight = FontWeight.Bold) },
            text = { Text("این کالکشن و ترتیب عنوان‌هایش حذف می‌شود. خود فیلم‌ها و سریال‌ها حذف نمی‌شوند.") },
            confirmButton = {
                TextButton(onClick = {
                    confirmDelete = false
                    viewModel.delete(onDeleted = onBack)
                }) { Text("حذف", color = MaterialTheme.colorScheme.error, fontWeight = FontWeight.Bold) }
            },
            dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text("انصراف") } },
        )
    }
}

@Composable
private fun CollectionHeader(
    collection: UserCollectionDto,
    canEdit: Boolean,
    onShare: () -> Unit,
    onCopy: () -> Unit,
    onEdit: () -> Unit,
    onDelete: () -> Unit,
    onOpenProfile: () -> Unit,
) {
    val accent = parseAccent(collection.accent)
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        // Banner: collage behind an accent scrim, with the title overlaid.
        Box(
            Modifier
                .fillMaxWidth()
                .height(150.dp)
                .clip(RoundedCornerShape(20.dp)),
        ) {
            CollectionCover(covers = collection.covers, accent = accent, modifier = Modifier.fillMaxSize())
            Box(
                Modifier
                    .fillMaxSize()
                    .background(
                        Brush.verticalGradient(
                            listOf(Color.Transparent, Color.Black.copy(alpha = 0.75f)),
                        ),
                    ),
            )
            Column(
                Modifier.align(Alignment.BottomStart).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                VisibilityBadge(visibility = collection.visibility)
                Text(
                    collection.title,
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Black,
                    color = Color.White,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }

        // Owner + count.
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(
                Modifier.size(30.dp).clip(CircleShape).background(accent.copy(alpha = 0.3f)),
                contentAlignment = Alignment.Center,
            ) {
                if (collection.owner.avatar != null) {
                    NetworkImage(collection.owner.avatar, null, Modifier.fillMaxSize())
                } else {
                    Text(
                        collection.owner.username.take(1).uppercase(),
                        color = Color.White, fontWeight = FontWeight.Bold,
                    )
                }
            }
            Text(
                collection.owner.username,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Bold,
                color = TextSecondary,
                modifier = Modifier.clickable(onClick = onOpenProfile),
            )
            Text("·", color = TextMuted)
            Text("${collection.itemCount} عنوان", style = MaterialTheme.typography.bodyMedium, color = TextMuted)
        }

        if (collection.description.isNotBlank()) {
            Text(
                collection.description,
                style = MaterialTheme.typography.bodyMedium,
                color = TextSecondary,
            )
        }

        // Actions.
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            HeaderAction(icon = Icons.Rounded.Share, label = "اشتراک", accent = accent, onClick = onShare, modifier = Modifier.weight(1f))
            HeaderAction(icon = Icons.Rounded.ContentCopy, label = "کپی لینک", accent = accent, onClick = onCopy, modifier = Modifier.weight(1f))
            if (canEdit) {
                HeaderAction(icon = Icons.Rounded.Edit, label = "ویرایش", accent = accent, onClick = onEdit, modifier = Modifier.weight(1f))
                HeaderAction(icon = Icons.Rounded.Delete, label = "حذف", accent = MaterialTheme.colorScheme.error, onClick = onDelete, modifier = Modifier.weight(1f))
            }
        }
        Spacer(Modifier.height(2.dp))
    }
}

@Composable
private fun HeaderAction(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    accent: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(14.dp))
            .background(accent.copy(alpha = 0.12f))
            .clickable(onClick = onClick)
            .padding(vertical = 10.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Icon(icon, contentDescription = label, tint = accent, modifier = Modifier.size(20.dp))
        Text(label, style = MaterialTheme.typography.labelSmall, color = accent, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun CollectionItemCell(
    item: CollectionItemDto,
    canEdit: Boolean,
    onClick: () -> Unit,
    onRemove: () -> Unit,
) {
    Column(
        Modifier.clickable(onClick = onClick),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Box {
            NetworkImage(
                url = item.poster,
                contentDescription = item.title,
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(2f / 3f)
                    .clip(RoundedCornerShape(12.dp))
                    .background(MaterialTheme.colorScheme.surface),
                fallbackText = item.title,
            )
            if (canEdit) {
                Box(
                    Modifier
                        .align(Alignment.TopEnd)
                        .padding(4.dp)
                        .size(26.dp)
                        .clip(CircleShape)
                        .background(Color.Black.copy(alpha = 0.6f))
                        .clickable(onClick = onRemove),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(Icons.Rounded.Close, contentDescription = "حذف از کالکشن", tint = Color.White, modifier = Modifier.size(16.dp))
                }
            }
        }
        Text(
            item.title,
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurface,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        item.year?.let {
            Text(it.toString(), style = MaterialTheme.typography.labelSmall, color = TextMuted)
        }
    }
}
