package com.revayato.app.feature.search

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.History
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.runtime.LaunchedEffect
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.BrandMint
import com.revayato.app.core.theme.NeutralSurface
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.data.model.CatalogCardDto
import com.revayato.app.data.model.PersonDto
import com.revayato.app.ui.components.EmptyState
import com.revayato.app.ui.components.ErrorState
import com.revayato.app.ui.components.NetworkImage
import com.revayato.app.ui.components.PosterGrid
import com.revayato.app.ui.components.SectionHeader

/** Result-type filter for the search grid. */
private enum class SearchTypeFilter(val label: String) {
    ALL("همه"), MOVIE("فیلم"), SERIES("سریال")
}

@Composable
fun SearchScreen(
    onOpenTitle: (contentType: String, slug: String) -> Unit,
    onOpenPerson: (slug: String) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: SearchViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var typeFilter by rememberSaveable { mutableStateOf(SearchTypeFilter.ALL) }

    // Open the keyboard the moment search is shown — search is a lean-forward task,
    // so making the user tap the field first is friction we can remove.
    val focusRequester = remember { FocusRequester() }
    LaunchedEffect(Unit) { focusRequester.requestFocus() }

    val movieCount = state.results.count { it.contentType == "movie" }
    val seriesCount = state.results.count { it.contentType == "series" }
    val filteredResults = when (typeFilter) {
        SearchTypeFilter.ALL -> state.results
        SearchTypeFilter.MOVIE -> state.results.filter { it.contentType == "movie" }
        SearchTypeFilter.SERIES -> state.results.filter { it.contentType == "series" }
    }

    Column(modifier = modifier.fillMaxSize()) {
        SearchBar(
            query = state.query,
            loading = state.loading,
            focusRequester = focusRequester,
            onQueryChange = viewModel::onQueryChange,
            onSubmit = { viewModel.submit(state.query) },
            onClear = viewModel::clear,
        )
        when {
            state.error != null -> ErrorState(state.error!!, Modifier.fillMaxSize())

            // Search ran but nothing matched (neither titles nor people).
            state.hasSearched && !state.hasResults && !state.loading ->
                EmptyState(
                    title = "نتیجه‌ای پیدا نشد",
                    subtitle = "با کلمات دیگری جستجو کن",
                    modifier = Modifier.fillMaxSize(),
                )

            // Live results: people ride on top, then a type filter + result grid.
            state.hasSearched && state.hasResults ->
                PosterGrid(
                    items = filteredResults,
                    onItemClick = { onOpenTitle(it.contentType, it.slug) },
                    header = {
                        Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                            if (state.people.isNotEmpty()) {
                                PeopleResults(people = state.people, onOpenPerson = onOpenPerson)
                            }
                            if (state.results.isNotEmpty()) {
                                ResultFilters(
                                    selected = typeFilter,
                                    allCount = state.results.size,
                                    movieCount = movieCount,
                                    seriesCount = seriesCount,
                                    onSelect = { typeFilter = it },
                                )
                            }
                        }
                    },
                )

            // Idle: recent searches first (one-tap re-run), then suggestions.
            else -> PosterGrid(
                items = state.suggestions,
                onItemClick = { onOpenTitle(it.contentType, it.slug) },
                header = {
                    Column(verticalArrangement = Arrangement.spacedBy(20.dp)) {
                        if (state.history.isNotEmpty()) {
                            SearchHistory(
                                history = state.history,
                                onPick = viewModel::submit,
                                onRemove = viewModel::removeHistory,
                                onClearAll = viewModel::clearHistory,
                            )
                        }
                        if (state.suggestions.isNotEmpty()) {
                            SectionHeader(title = "پیشنهاد جستجو")
                        }
                    }
                },
            )
        }
    }
}

/** «همه / فیلم / سریال» selectable pills with live result counts. */
@Composable
private fun ResultFilters(
    selected: SearchTypeFilter,
    allCount: Int,
    movieCount: Int,
    seriesCount: Int,
    onSelect: (SearchTypeFilter) -> Unit,
) {
    val counts = mapOf(
        SearchTypeFilter.ALL to allCount,
        SearchTypeFilter.MOVIE to movieCount,
        SearchTypeFilter.SERIES to seriesCount,
    )
    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        items(SearchTypeFilter.entries.toList(), key = { it.name }) { filter ->
            // Hide the movie/series pill when that type produced nothing.
            if (filter != SearchTypeFilter.ALL && counts[filter] == 0) return@items
            FilterPill(
                label = "${filter.label} ${counts[filter]}",
                active = selected == filter,
                onClick = { onSelect(filter) },
            )
        }
    }
}

@Composable
private fun FilterPill(label: String, active: Boolean, onClick: () -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val scale by animateFloatAsState(
        targetValue = if (pressed) 0.93f else 1f,
        animationSpec = spring(dampingRatio = 0.55f, stiffness = 600f),
        label = "filterScale",
    )
    val bg by animateColorAsState(
        targetValue = if (active) BrandMint else NeutralSurface,
        label = "filterBg",
    )
    Box(
        modifier = Modifier
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .clip(RoundedCornerShape(999.dp))
            .background(bg)
            .clickable(interactionSource = interaction, indication = null, onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 8.dp),
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelMedium,
            color = if (active) OnBrand else TextSecondary,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

/** Horizontal strip of matching actors/directors, tap to open their page. */
@Composable
private fun PeopleResults(
    people: List<PersonDto>,
    onOpenPerson: (slug: String) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SectionHeader(title = "افراد")
        LazyRow(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            items(people, key = { it.id }) { person ->
                PersonAvatar(person = person, onClick = { onOpenPerson(person.slug) })
            }
        }
    }
}

@Composable
private fun PersonAvatar(person: PersonDto, onClick: () -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val scale by animateFloatAsState(
        targetValue = if (pressed) 0.93f else 1f,
        animationSpec = spring(dampingRatio = 0.55f, stiffness = 600f),
        label = "avatarScale",
    )
    Column(
        modifier = Modifier
            .width(78.dp)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .clip(RoundedCornerShape(12.dp))
            .clickable(interactionSource = interaction, indication = null, onClick = onClick)
            .padding(vertical = 4.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        NetworkImage(
            url = person.profileUrl ?: person.photo,
            contentDescription = person.name,
            fallbackText = person.name.take(1),
            modifier = Modifier
                .size(72.dp)
                .clip(CircleShape),
        )
        Text(
            text = person.name,
            style = MaterialTheme.typography.labelSmall,
            color = TextSecondary,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
            textAlign = TextAlign.Center,
        )
    }
}

@Composable
private fun SearchHistory(
    history: List<String>,
    onPick: (String) -> Unit,
    onRemove: (String) -> Unit,
    onClearAll: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "جستجوهای اخیر",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onSurface,
            )
            Text(
                text = "پاک کردن همه",
                style = MaterialTheme.typography.labelMedium,
                color = TextMuted,
                modifier = Modifier
                    .clip(RoundedCornerShape(6.dp))
                    .clickable(onClick = onClearAll)
                    .padding(horizontal = 8.dp, vertical = 4.dp),
            )
        }
        // Flowing chip rows kept simple with a LazyRow — recents are capped at 12.
        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items(history, key = { it }) { term ->
                HistoryChip(
                    term = term,
                    onClick = { onPick(term) },
                    onRemove = { onRemove(term) },
                )
            }
        }
    }
}

@Composable
private fun HistoryChip(term: String, onClick: () -> Unit, onRemove: () -> Unit) {
    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(999.dp))
            .background(BgElevated)
            .clickable(onClick = onClick)
            .padding(start = 12.dp, end = 6.dp, top = 7.dp, bottom = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Icon(
            Icons.Rounded.History,
            contentDescription = null,
            tint = TextMuted,
            modifier = Modifier.size(15.dp),
        )
        Text(
            text = term,
            style = MaterialTheme.typography.bodyMedium,
            color = TextSecondary,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Box(
            modifier = Modifier
                .clip(CircleShape)
                .clickable(onClick = onRemove)
                .padding(3.dp),
        ) {
            Icon(
                Icons.Rounded.Close,
                contentDescription = "حذف",
                tint = TextMuted,
                modifier = Modifier.size(14.dp),
            )
        }
    }
}

@Composable
private fun SearchBar(
    query: String,
    loading: Boolean,
    focusRequester: FocusRequester,
    onQueryChange: (String) -> Unit,
    onSubmit: () -> Unit,
    onClear: () -> Unit,
) {
    OutlinedTextField(
        value = query,
        onValueChange = onQueryChange,
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 12.dp)
            .focusRequester(focusRequester),
        placeholder = {
            Text("جستجوی فیلم، سریال و بازیگر…", color = TextMuted)
        },
        singleLine = true,
        shape = RoundedCornerShape(16.dp),
        textStyle = MaterialTheme.typography.bodyLarge.copy(color = TextPrimary),
        leadingIcon = {
            Icon(Icons.Rounded.Search, contentDescription = null)
        },
        trailingIcon = {
            Box {
                if (loading) {
                    CircularProgressIndicator(
                        modifier = Modifier.padding(12.dp),
                        strokeWidth = 2.dp,
                        color = BrandMint,
                    )
                } else if (query.isNotEmpty()) {
                    IconButton(onClick = onClear) {
                        Icon(Icons.Rounded.Close, contentDescription = "پاک کردن")
                    }
                }
            }
        },
        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
        keyboardActions = KeyboardActions(onSearch = { onSubmit() }),
        // A quiet filled pill that lifts to a mint outline on focus — cleaner and
        // more app-like than a hard bordered box.
        colors = OutlinedTextFieldDefaults.colors(
            focusedContainerColor = BgElevated,
            unfocusedContainerColor = BgElevated,
            focusedBorderColor = BrandMint,
            cursorColor = BrandMint,
            focusedLeadingIconColor = BrandMint,
            unfocusedLeadingIconColor = TextMuted,
            unfocusedBorderColor = Color.Transparent,
        ),
    )
}
