package com.revayato.app.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyGridState
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.revayato.app.data.model.CatalogCardDto

/** Responsive 3-column poster grid used by search, library, collections and lists. */
@Composable
fun PosterGrid(
    items: List<CatalogCardDto>,
    onItemClick: (CatalogCardDto) -> Unit,
    modifier: Modifier = Modifier,
    columns: Int = posterGridColumns(),
    state: LazyGridState = rememberLazyGridState(),
    header: (@Composable () -> Unit)? = null,
    featured: (@Composable () -> Unit)? = null,
) {
    LazyVerticalGrid(
        columns = GridCells.Fixed(columns),
        state = state,
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        if (header != null) {
            item(span = { androidx.compose.foundation.lazy.grid.GridItemSpan(columns) }) {
                header()
            }
        }
        if (featured != null) {
            item(span = { androidx.compose.foundation.lazy.grid.GridItemSpan(columns) }) {
                featured()
            }
        }
        items(items, key = { "${it.contentType}-${it.id}" }) { item ->
            PosterCard(
                item = item,
                onClick = { onItemClick(item) },
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}
