package com.revayato.app.feature.collections

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.ui.UiState
import com.revayato.app.feature.collection.BackTopBar
import com.revayato.app.ui.components.EmptyState
import com.revayato.app.ui.components.ErrorState
import com.revayato.app.ui.components.LoadingState

@Composable
fun MyCollectionsScreen(
    isLoggedIn: Boolean,
    onBack: () -> Unit,
    onOpenCollection: (slug: String) -> Unit,
    onRequireLogin: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: CollectionsViewModel = hiltViewModel(),
) {
    if (!isLoggedIn) {
        Column(modifier.fillMaxSize()) {
            BackTopBar(title = "کالکشن‌های من", onBack = onBack)
            EmptyState(
                title = "کالکشن‌هایت اینجاست",
                subtitle = "برای ساختن فهرست‌های دلخواه از فیلم و سریال وارد شو",
                actionLabel = "ورود",
                onAction = onRequireLogin,
                modifier = Modifier.fillMaxSize(),
            )
        }
        return
    }

    LaunchedEffect(Unit) { viewModel.load() }
    val state by viewModel.state.collectAsStateWithLifecycle()
    var showCreate by remember { mutableStateOf(false) }

    Scaffold(
        modifier = modifier.fillMaxSize(),
        containerColor = MaterialTheme.colorScheme.background,
        topBar = { BackTopBar(title = "کالکشن‌های من", onBack = onBack) },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { showCreate = true },
                containerColor = MaterialTheme.colorScheme.primary,
                contentColor = OnBrand,
                icon = { Icon(Icons.Rounded.Add, contentDescription = null) },
                text = { Text("کالکشن جدید", fontWeight = FontWeight.Bold) },
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
                            title = "هنوز کالکشنی نساختی",
                            subtitle = "با دکمهٔ «کالکشن جدید» اولین فهرستت را بساز و فیلم و سریال‌های محبوبت را کنار هم بگذار.",
                            modifier = Modifier.fillMaxSize(),
                        )
                    } else {
                        LazyVerticalGrid(
                            columns = GridCells.Fixed(2),
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(16.dp, 16.dp, 16.dp, 96.dp),
                            horizontalArrangement = Arrangement.spacedBy(14.dp),
                            verticalArrangement = Arrangement.spacedBy(18.dp),
                        ) {
                            items(s.data, key = { it.id }) { collection ->
                                CollectionCard(
                                    collection = collection,
                                    onClick = { onOpenCollection(collection.slug) },
                                    modifier = Modifier.fillMaxWidth(),
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
            confirmLabel = "بساز",
            initialName = "",
            initialDescription = "",
            initialVisibility = com.revayato.app.data.model.CollectionVisibility.PUBLIC,
            busy = state.creating,
            error = state.createError,
            onDismiss = { showCreate = false; viewModel.consumeCreateError() },
            onConfirm = { name, desc, visibility ->
                viewModel.create(name, desc, visibility) { slug ->
                    showCreate = false
                    onOpenCollection(slug)
                }
            },
        )
    }
}
