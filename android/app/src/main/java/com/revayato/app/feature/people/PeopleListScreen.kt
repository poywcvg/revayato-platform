package com.revayato.app.feature.people

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.BrandMint
import com.revayato.app.feature.collection.BackTopBar
import com.revayato.app.ui.components.EmptyState
import com.revayato.app.ui.components.ErrorState
import com.revayato.app.ui.components.LoadingState
import com.revayato.app.ui.components.PersonAvatar

/**
 * Paginated grid of actors or directors. [kind] is "actors" / "directors".
 * A tapped person opens their profile via [onOpenPerson] (kind passed as
 * "actor" / "director" to match the detail route).
 */
@Composable
fun PeopleListScreen(
    kind: String,
    onBack: () -> Unit,
    onOpenPerson: (slug: String) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: PeopleListViewModel = hiltViewModel(),
) {
    LaunchedEffect(kind) { viewModel.start(kind) }
    val state by viewModel.state.collectAsStateWithLifecycle()

    val gridState = rememberLazyGridState()
    val shouldLoadMore by remember {
        derivedStateOf {
            val last = gridState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0
            val total = gridState.layoutInfo.totalItemsCount
            total > 0 && last >= total - 6
        }
    }
    LaunchedEffect(shouldLoadMore) {
        if (shouldLoadMore) viewModel.loadMore()
    }

    Column(modifier.fillMaxSize()) {
        BackTopBar(title = if (kind == "directors") "کارگردانان" else "بازیگران", onBack = onBack)
        when {
            state.loading -> LoadingState(Modifier.fillMaxSize())
            state.error != null -> ErrorState(state.error!!, Modifier.fillMaxSize(), onRetry = viewModel::reload)
            state.items.isEmpty() -> EmptyState("چیزی برای نمایش نیست", modifier = Modifier.fillMaxSize())
            else -> LazyVerticalGrid(
                columns = GridCells.Fixed(3),
                state = gridState,
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(16.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalArrangement = Arrangement.spacedBy(20.dp),
            ) {
                items(state.items, key = { it.id }) { person ->
                    PersonAvatar(
                        name = person.displayName,
                        imageUrl = person.imageUrl,
                        subtitle = person.birthPlace,
                        onClick = { onOpenPerson(person.slug) },
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                if (state.loadingMore) {
                    item(span = { GridItemSpan(3) }) {
                        Box(Modifier.fillMaxWidth().padding(16.dp), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator(color = BrandMint, strokeWidth = 2.dp)
                        }
                    }
                }
            }
        }
    }
}
