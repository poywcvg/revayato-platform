package com.revayato.app.feature.collection

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowForward
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.core.ui.UiState
import com.revayato.app.ui.components.EmptyState
import com.revayato.app.ui.components.ErrorState
import com.revayato.app.ui.components.LoadingState
import com.revayato.app.ui.components.PosterGrid

@Composable
fun CollectionScreen(
    slug: String,
    onBack: () -> Unit,
    onOpenTitle: (contentType: String, slug: String) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: CollectionViewModel = hiltViewModel(),
) {
    LaunchedEffect(slug) { viewModel.load(slug) }
    val state by viewModel.state.collectAsStateWithLifecycle()

    Column(modifier.fillMaxSize()) {
        val title = (state as? UiState.Success)?.data?.title ?: "مجموعه"
        BackTopBar(title = title, onBack = onBack)
        when (val s = state) {
            is UiState.Loading -> LoadingState(Modifier.fillMaxSize())
            is UiState.Error -> ErrorState(s.message, Modifier.fillMaxSize(), onRetry = viewModel::retry)
            is UiState.Success -> {
                if (s.data.items.isEmpty()) {
                    EmptyState("این مجموعه خالی است", modifier = Modifier.fillMaxSize())
                } else {
                    PosterGrid(
                        items = s.data.items,
                        onItemClick = { onOpenTitle(it.contentType, it.slug) },
                        header = if (!s.data.description.isNullOrBlank()) {
                            {
                                Text(
                                    s.data.description!!,
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = TextSecondary,
                                )
                            }
                        } else null,
                    )
                }
            }
        }
    }
}

@Composable
internal fun BackTopBar(title: String, onBack: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .statusBarsPadding()
            .padding(horizontal = 4.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = onBack) {
            Icon(Icons.AutoMirrored.Rounded.ArrowForward, contentDescription = "بازگشت")
        }
        Text(
            title,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.padding(start = 4.dp),
        )
    }
}
