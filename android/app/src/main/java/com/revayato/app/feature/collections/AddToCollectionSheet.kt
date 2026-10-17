package com.revayato.app.feature.collections

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.Brand
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.CollectionPickRowDto
import com.revayato.app.data.model.CollectionVisibility
import com.revayato.app.ui.components.ErrorState
import com.revayato.app.ui.components.LoadingState
import com.revayato.app.ui.components.RevayatoSpinner

/**
 * Bottom sheet for adding a movie/series to one or more of the viewer's
 * collections. Toggling a row adds/removes instantly; «کالکشن جدید» creates a
 * new collection with the title already in it.
 */
@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun AddToCollectionSheet(
    contentType: String,
    objectId: Int,
    title: String,
    onDismiss: () -> Unit,
    viewModel: AddToCollectionViewModel = hiltViewModel(),
) {
    LaunchedEffect(contentType, objectId) { viewModel.load(contentType, objectId) }
    val state by viewModel.state.collectAsStateWithLifecycle()
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var showCreate by remember { mutableStateOf(false) }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = MaterialTheme.colorScheme.surface,
    ) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
            Text("افزودن به کالکشن", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Text(
                title,
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = 2.dp, bottom = 14.dp),
            )

            // New collection.
            Row(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(14.dp))
                    .clickable { showCreate = true }
                    .padding(vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Box(
                    Modifier.size(40.dp).clip(CircleShape).background(Brand.copy(alpha = 0.15f)),
                    contentAlignment = Alignment.Center,
                ) { Icon(Icons.Rounded.Add, contentDescription = null, tint = Brand) }
                Text("کالکشن جدید", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyLarge)
            }

            when (val s = state.rows) {
                is UiState.Loading -> LoadingState(Modifier.fillMaxWidth().heightIn(min = 120.dp))
                is UiState.Error -> ErrorState(
                    s.message,
                    Modifier.fillMaxWidth().heightIn(min = 120.dp),
                    onRetry = { viewModel.load(contentType, objectId) },
                )
                is UiState.Success -> {
                    if (s.data.isEmpty()) {
                        Text(
                            "هنوز کالکشنی نساختی — با «کالکشن جدید» شروع کن.",
                            color = TextMuted,
                            style = MaterialTheme.typography.bodyMedium,
                            modifier = Modifier.padding(vertical = 20.dp),
                        )
                    } else {
                        LazyColumn(Modifier.fillMaxWidth().heightIn(max = 380.dp)) {
                            items(s.data, key = { it.id }) { row ->
                                PickRow(
                                    row = row,
                                    busy = state.pending.contains(row.slug),
                                    onToggle = { viewModel.toggle(row) },
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    if (showCreate) {
        CollectionEditDialog(
            title = "کالکشن جدید",
            confirmLabel = "بساز و اضافه کن",
            initialName = "",
            initialDescription = "",
            initialVisibility = CollectionVisibility.PUBLIC,
            busy = state.creating,
            error = state.createError,
            onDismiss = { showCreate = false; viewModel.consumeCreateError() },
            onConfirm = { name, desc, vis ->
                viewModel.createAndAdd(name, desc, vis)
                showCreate = false
            },
        )
    }
}

@Composable
private fun PickRow(
    row: CollectionPickRowDto,
    busy: Boolean,
    onToggle: () -> Unit,
) {
    val accent = parseAccent(row.accent)
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .clickable(enabled = !busy, onClick = onToggle)
            .padding(vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(Modifier.size(40.dp).clip(RoundedCornerShape(10.dp)).background(accent.copy(alpha = 0.85f)))
        Column(Modifier.weight(1f)) {
            Text(
                row.title,
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.bodyLarge,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                "${row.itemCount} عنوان · ${CollectionVisibility.label(row.visibility)}",
                style = MaterialTheme.typography.labelSmall,
                color = TextMuted,
            )
        }
        Box(
            Modifier
                .size(28.dp)
                .clip(CircleShape)
                .background(if (row.contains) Brand else Color.Transparent),
            contentAlignment = Alignment.Center,
        ) {
            when {
                busy -> RevayatoSpinner(size = 18.dp, color = Brand)
                row.contains -> Icon(Icons.Rounded.Check, contentDescription = "در کالکشن", tint = OnBrand, modifier = Modifier.size(18.dp))
                else -> Icon(Icons.Rounded.Add, contentDescription = "افزودن", tint = TextMuted, modifier = Modifier.size(18.dp))
            }
        }
    }
}
