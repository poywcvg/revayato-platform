package com.revayato.app.feature.catalog

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ArrowDropDown
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.FilterAltOff
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
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
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.BrandMint
import com.revayato.app.feature.collection.BackTopBar
import com.revayato.app.ui.components.EmptyState
import com.revayato.app.ui.components.ErrorState
import com.revayato.app.ui.components.LoadingState
import com.revayato.app.ui.components.PosterCard

// Values MUST match the backend catalog `sort` contract (_catalog_ordering): the
// server maps unknown values to "newest", so a mislabeled option would silently no-op.
private val SORT_OPTIONS = listOf(
    "newest" to "جدیدترین",
    "rating" to "بیشترین امتیاز",
    "popular" to "محبوب‌ترین",
    "trending" to "پرطرفدار",
)

// Static filter vocabularies — values MUST match the backend contract in
// apps/catalog/api.py (content_format ∈ {live_action, animation, short};
// availability ∈ {dubbed, subtitle, download}). Leading blank = «همه» (clear).
private val FORMAT_OPTIONS = listOf(
    "" to "همه",
    "live_action" to "لایو اکشن",
    "animation" to "انیمیشن",
    "short" to "کوتاه",
)
private val AVAILABILITY_OPTIONS = listOf(
    "" to "همه",
    "dubbed" to "دوبله",
    "subtitle" to "زیرنویس",
    "download" to "قابل دانلود",
)

/**
 * A single pill-shaped filter control. Tapping it opens a Material3 dropdown of
 * [options] (value → label); the current [selectedValue] is check-marked. When a
 * narrowing value is active the pill turns mint so active filters read at a glance.
 */
@Composable
private fun FilterDropdown(
    fieldLabel: String,
    selectedValue: String,
    options: List<Pair<String, String>>,
    onSelect: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    var expanded by remember { mutableStateOf(false) }
    val active = selectedValue.isNotBlank()
    val currentLabel = options.firstOrNull { it.first == selectedValue }?.second
    // Sort always carries a value; narrowing filters show the field name until set.
    val display = if (active) currentLabel ?: fieldLabel else fieldLabel

    Box(modifier) {
        Box(
            modifier = Modifier
                .clip(RoundedCornerShape(999.dp))
                .background(if (active) BrandMint else Color(0x14FFFFFF))
                .border(
                    1.dp,
                    if (active) BrandMint else Color(0x22FFFFFF),
                    RoundedCornerShape(999.dp),
                )
                .clickable { expanded = true }
                .padding(start = 14.dp, end = 8.dp, top = 8.dp, bottom = 8.dp),
        ) {
            androidx.compose.foundation.layout.Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                Text(
                    text = display,
                    style = MaterialTheme.typography.labelMedium,
                    color = if (active) Color(0xFF0D1A14) else MaterialTheme.colorScheme.onSurface,
                    fontWeight = if (active) FontWeight.Bold else FontWeight.Medium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.widthIn(max = 140.dp),
                )
                Icon(
                    Icons.Rounded.ArrowDropDown,
                    contentDescription = null,
                    tint = if (active) Color(0xFF0D1A14) else MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.size(18.dp),
                )
            }
        }
        DropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
            modifier = Modifier.heightIn(max = 360.dp),
        ) {
            options.forEach { (value, label) ->
                DropdownMenuItem(
                    text = {
                        Text(
                            text = label,
                            fontWeight = if (value == selectedValue) FontWeight.Bold else FontWeight.Normal,
                        )
                    },
                    onClick = {
                        onSelect(value)
                        expanded = false
                    },
                    trailingIcon = {
                        if (value == selectedValue) {
                            Icon(Icons.Rounded.Check, contentDescription = null, tint = BrandMint)
                        }
                    },
                )
            }
        }
    }
}

@Composable
private fun FilterBar(state: CatalogListState, viewModel: CatalogListViewModel) {
    val genreOptions = remember(state.genreOptions) {
        listOf("" to "همه ژانرها") + state.genreOptions.map { it.slug to it.title }
    }
    val countryOptions = remember(state.countryOptions) {
        listOf("" to "همه کشورها") + state.countryOptions.map { it.filterValue to it.name }
    }
    LazyRow(
        modifier = Modifier.fillMaxWidth(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        item(key = "sort") {
            FilterDropdown(
                fieldLabel = "مرتب‌سازی",
                selectedValue = state.sort,
                options = SORT_OPTIONS,
                onSelect = viewModel::setSort,
            )
        }
        if (state.genreOptions.isNotEmpty()) {
            item(key = "genre") {
                FilterDropdown(
                    fieldLabel = "ژانر",
                    selectedValue = state.genre,
                    options = genreOptions,
                    onSelect = viewModel::setGenre,
                )
            }
        }
        if (state.countryOptions.isNotEmpty()) {
            item(key = "country") {
                FilterDropdown(
                    fieldLabel = "کشور",
                    selectedValue = state.country,
                    options = countryOptions,
                    onSelect = viewModel::setCountry,
                )
            }
        }
        item(key = "availability") {
            FilterDropdown(
                fieldLabel = "دسترسی",
                selectedValue = state.availability,
                options = AVAILABILITY_OPTIONS,
                onSelect = viewModel::setAvailability,
            )
        }
        item(key = "format") {
            FilterDropdown(
                fieldLabel = "نوع",
                selectedValue = state.format,
                options = FORMAT_OPTIONS,
                onSelect = viewModel::setFormat,
            )
        }
        if (state.hasActiveFilters) {
            item(key = "clear") {
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(999.dp))
                        .background(Color(0x1FF2555A))
                        .clickable { viewModel.clearFilters() }
                        .padding(horizontal = 12.dp, vertical = 8.dp),
                ) {
                    androidx.compose.foundation.layout.Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        Icon(
                            Icons.Rounded.FilterAltOff,
                            contentDescription = null,
                            tint = Color(0xFFF2555A),
                            modifier = Modifier.size(16.dp),
                        )
                        Text(
                            "پاک کردن",
                            style = MaterialTheme.typography.labelMedium,
                            color = Color(0xFFF2555A),
                            fontWeight = FontWeight.Medium,
                        )
                    }
                }
            }
        }
    }
}

/** «۲۵۰ فیلم برتر» / «۲۵۰ سریال برتر» — the two IMDb charts, one tap apart. */
@Composable
private fun ChartTypeToggle(selected: String, onSelect: (String) -> Unit) {
    androidx.compose.foundation.layout.Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        listOf("movie" to "۲۵۰ فیلم برتر", "series" to "۲۵۰ سریال برتر").forEach { (value, label) ->
            val active = value == selected
            Box(
                modifier = Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(12.dp))
                    .background(if (active) Color(0xFFF5C518) else Color(0x14FFFFFF))
                    .clickable { onSelect(value) }
                    .padding(vertical = 11.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    text = label,
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = if (active) FontWeight.Black else FontWeight.Medium,
                    color = if (active) Color(0xFF0B0B0C) else MaterialTheme.colorScheme.onSurface,
                )
            }
        }
    }
}

@Composable
fun CatalogListScreen(
    kind: String,
    title: String,
    onBack: () -> Unit,
    onOpenTitle: (contentType: String, slug: String) -> Unit,
    genre: String = "",
    country: String = "",
    format: String = "",
    availability: String = "",
    initialSort: String = "",
    embedded: Boolean = false,
    modifier: Modifier = Modifier,
    viewModel: CatalogListViewModel = hiltViewModel(),
) {
    LaunchedEffect(kind, genre, country, format, availability) {
        viewModel.start(kind, genre, country, format, availability, initialSort)
    }
    val state by viewModel.state.collectAsStateWithLifecycle()

    val gridState = rememberLazyGridState()
    val shouldLoadMore by remember {
        derivedStateOf {
            val last = gridState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0
            val total = gridState.layoutInfo.totalItemsCount
            total > 0 && last >= total - 4
        }
    }
    LaunchedEffect(shouldLoadMore) {
        if (shouldLoadMore) viewModel.loadMore()
    }

    Column(modifier.fillMaxSize()) {
        if (!embedded) {
            BackTopBar(title = title.ifBlank { if (kind == "series") "سریال‌ها" else "فیلم‌ها" }, onBack = onBack)
        }
        // Mixed feeds (recent / anime) merge movies+series by recency on the server and
        // ignore the sort/filter parameters, so the filter bar would be misleading there.
        val supportsFilters = kind != "recent" && kind != "anime" && kind != "top250"
        if (supportsFilters) {
            FilterBar(state = state, viewModel = viewModel)
        }
        if (kind == "top250") {
            ChartTypeToggle(selected = state.chartType, onSelect = viewModel::setChartType)
        }
        when {
            state.loading -> LoadingState(Modifier.fillMaxSize())
            state.error != null -> ErrorState(state.error!!, Modifier.fillMaxSize(), onRetry = viewModel::reload)
            state.items.isEmpty() -> EmptyState(
                if (state.hasActiveFilters) "با این فیلترها چیزی پیدا نشد" else "چیزی برای نمایش نیست",
                modifier = Modifier.fillMaxSize(),
            )
            else -> LazyVerticalGrid(
                columns = GridCells.Fixed(3),
                state = gridState,
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(16.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                items(state.items, key = { "${it.contentType}-${it.id}" }) { item ->
                    PosterCard(
                        item = item,
                        onClick = { onOpenTitle(item.contentType, item.slug) },
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
