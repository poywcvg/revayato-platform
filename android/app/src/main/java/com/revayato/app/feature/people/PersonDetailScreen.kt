package com.revayato.app.feature.people

import com.revayato.app.ui.components.posterGridColumns
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.Brand
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.PersonDetailDto
import com.revayato.app.feature.collection.BackTopBar
import com.revayato.app.ui.components.ErrorState
import com.revayato.app.ui.components.LoadingState
import com.revayato.app.ui.components.NetworkImage
import com.revayato.app.ui.components.PosterCard

/**
 * Shared actor/director profile: headshot + bio header, then a filmography grid.
 * [kind] is "actor" or "director" (drives which endpoint is hit and the title).
 */
@Composable
fun PersonDetailScreen(
    kind: String,
    slug: String,
    onBack: () -> Unit,
    onOpenTitle: (contentType: String, slug: String) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: PersonDetailViewModel = hiltViewModel(),
) {
    LaunchedEffect(kind, slug) { viewModel.start(kind, slug) }
    val state by viewModel.state.collectAsStateWithLifecycle()

    Column(modifier.fillMaxSize()) {
        BackTopBar(
            title = if (kind == "director") "کارگردان" else "بازیگر",
            onBack = onBack,
        )
        when (val s = state) {
            is UiState.Loading -> LoadingState(Modifier.fillMaxSize())
            is UiState.Error -> ErrorState(s.message, Modifier.fillMaxSize(), onRetry = { viewModel.load(kind, slug) })
            is UiState.Success -> PersonContent(s.data, onOpenTitle)
        }
    }
}

@Composable
private fun PersonContent(
    person: PersonDetailDto,
    onOpenTitle: (String, String) -> Unit,
) {
    val films = person.filmography
    val columns = posterGridColumns()
    LazyVerticalGrid(
        columns = GridCells.Fixed(columns),
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item(span = { GridItemSpan(columns) }) {
            PersonHeader(person)
        }
        if (films.isNotEmpty()) {
            item(span = { GridItemSpan(columns) }) {
                Text(
                    text = "آثار (${films.size})",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier.padding(top = 8.dp, bottom = 4.dp),
                )
            }
            items(films, key = { "${it.contentType}-${it.id}" }) { item ->
                PosterCard(
                    item = item,
                    onClick = { onOpenTitle(item.contentType, item.slug) },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
    }
}

@Composable
private fun PersonHeader(person: PersonDetailDto) {
    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        NetworkImage(
            url = person.imageUrl,
            contentDescription = person.displayName,
            fallbackText = person.displayName,
            modifier = Modifier
                .width(140.dp)
                .aspectRatio(1f)
                .clip(CircleShape),
        )
        Text(
            text = person.displayName,
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onSurface,
            textAlign = TextAlign.Center,
        )
        val meta = listOfNotNull(
            person.birthDate?.takeIf { it.isNotBlank() },
            person.birthPlace?.takeIf { it.isNotBlank() },
        ).joinToString(" · ")
        if (meta.isNotBlank()) {
            Text(
                text = meta,
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )
        }
        person.biography?.takeIf { it.isNotBlank() }?.let { bio ->
            Text(
                text = bio,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
    }
}
