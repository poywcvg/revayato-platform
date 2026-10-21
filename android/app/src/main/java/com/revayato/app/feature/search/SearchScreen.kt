package com.revayato.app.feature.search

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
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
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.revayato.app.core.theme.BgElevated
import com.revayato.app.core.theme.Brand
import com.revayato.app.core.theme.NeutralSurface
import com.revayato.app.core.theme.OnBrand
import com.revayato.app.core.theme.OutlineSoft
import com.revayato.app.core.theme.RevayatoMotion
import com.revayato.app.core.theme.TextMuted
import com.revayato.app.core.theme.TextPrimary
import com.revayato.app.core.theme.TextSecondary
import com.revayato.app.core.theme.motionScale
import com.revayato.app.core.theme.rememberedPressScale
import com.revayato.app.data.model.CatalogCardDto
import com.revayato.app.data.model.PersonDto
import com.revayato.app.ui.components.EmptyState
import com.revayato.app.ui.components.ErrorState
import com.revayato.app.ui.components.LoadingState
import com.revayato.app.ui.components.NetworkImage
import com.revayato.app.ui.components.PosterGrid

/** Result-type filter for the search grid. */
private enum class SearchTypeFilter(val label: String) {
    ALL("همه"), MOVIE("فیلم"), SERIES("سریال")
}

/** The four distinct screens the search surface can be in. */
private enum class SearchMode { IDLE, LOADING, RESULTS, EMPTY, ERROR }

@Composable
fun SearchScreen(
    onOpenTitle: (contentType: String, slug: String) -> Unit,
    onOpenPerson: (slug: String) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: SearchViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var typeFilter by rememberSaveable { mutableStateOf(SearchTypeFilter.ALL) }

    // Search is a lean-forward task; open the keyboard as soon as the page lands.
    val focusRequester = remember { FocusRequester() }
    LaunchedEffect(Unit) { focusRequester.requestFocus() }

    val movieCount = state.results.count { it.contentType == "movie" }
    val seriesCount = state.results.count { it.contentType == "series" }
    val filteredResults = when (typeFilter) {
        SearchTypeFilter.ALL -> state.results
        SearchTypeFilter.MOVIE -> state.results.filter { it.contentType == "movie" }
        SearchTypeFilter.SERIES -> state.results.filter { it.contentType == "series" }
    }
    val mode = when {
        state.error != null -> SearchMode.ERROR
        state.loading && !state.hasResults -> SearchMode.LOADING
        state.hasSearched && state.hasResults -> SearchMode.RESULTS
        state.hasSearched && !state.loading -> SearchMode.EMPTY
        else -> SearchMode.IDLE
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
        AnimatedVisibility(visible = state.loading && state.hasResults) {
            LinearProgressIndicator(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(2.dp),
                color = Brand,
                trackColor = Color.Transparent,
            )
        }
        AnimatedContent(
            targetState = mode,
            transitionSpec = {
                (fadeIn(tween(220, delayMillis = 30)) +
                    slideInVertically(tween(280, easing = RevayatoMotion.Decelerate)) { it / 16 })
                    .togetherWith(
                        fadeOut(tween(130)) +
                            slideOutVertically(tween(160)) { -it / 24 },
                    )
            },
            label = "searchMode",
        ) { currentMode ->
            when (currentMode) {
                SearchMode.ERROR -> ErrorState(
                    message = state.error ?: "جستجو انجام نشد",
                    modifier = Modifier.fillMaxSize(),
                    onRetry = { if (state.query.isBlank()) viewModel.clear() else viewModel.submit(state.query) },
                )

                SearchMode.LOADING -> LoadingState(Modifier.fillMaxSize())

                SearchMode.EMPTY -> EmptyState(
                    title = "نتیجه‌ای برای «${state.query.trim()}» پیدا نشد",
                    subtitle = "املای عبارت را بررسی کن یا نام فارسی/انگلیسی را امتحان کن.",
                    actionLabel = "پاک کردن جستجو",
                    onAction = viewModel::clear,
                    modifier = Modifier.fillMaxSize(),
                )

                SearchMode.RESULTS -> {
                    val featured = if (
                        typeFilter == SearchTypeFilter.ALL &&
                        !state.loading &&
                        state.results.isNotEmpty()
                    ) {
                        state.results.first()
                    } else {
                        null
                    }
                    val gridItems = if (featured != null) filteredResults.drop(1) else filteredResults
                    PosterGrid(
                        items = gridItems,
                        onItemClick = { onOpenTitle(it.contentType, it.slug) },
                        header = {
                            Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                                if (state.people.isNotEmpty()) {
                                    PeopleResults(people = state.people, onOpenPerson = onOpenPerson)
                                }
                                if (state.results.isNotEmpty()) {
                                    ResultSummary(
                                        count = state.results.size,
                                        query = state.query,
                                    )
                                    ResultFilters(
                                        selected = typeFilter,
                                        allCount = state.results.size,
                                        movieCount = movieCount,
                                        seriesCount = seriesCount,
                                        onSelect = { typeFilter = it },
                                    )
                                }
                                if (filteredResults.isEmpty() && state.results.isNotEmpty()) {
                                    Text(
                                        text = if (typeFilter == SearchTypeFilter.MOVIE) {
                                            "در این جستجو فیلمی پیدا نشد؛ «همه» را ببین."
                                        } else {
                                            "در این جستجو سریالی پیدا نشد؛ «همه» را ببین."
                                        },
                                        style = MaterialTheme.typography.bodySmall,
                                        color = TextMuted,
                                        modifier = Modifier.padding(bottom = 8.dp),
                                    )
                                }
                            }
                        },
                        featured = featured?.let { best ->
                            { BestMatchCard(item = best, onClick = { onOpenTitle(best.contentType, best.slug) }) }
                        },
                    )
                }

                SearchMode.IDLE -> PosterGrid(
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
                                SearchSectionLabel("پیشنهاد برای تماشا")
                            } else if (state.history.isEmpty()) {
                                IdlePrompt()
                            }
                        }
                    },
                )
            }
        }
    }
}

@Composable
private fun SearchSectionLabel(title: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier
                .size(width = 4.dp, height = 18.dp)
                .clip(RoundedCornerShape(2.dp))
                .background(Brand),
        )
        Spacer(Modifier.width(8.dp))
        Text(
            text = title,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
            color = TextPrimary,
        )
    }
}

@Composable
private fun IdlePrompt() {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(20.dp))
            .background(BgElevated)
            .padding(22.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(
            text = "دنبال چه چیزی هستی؟",
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
            color = TextPrimary,
        )
        Text(
            text = "نام فیلم، سریال یا بازیگر را بنویس. نزدیک‌ترین نتیجه همیشه اولین کارت است.",
            style = MaterialTheme.typography.bodyMedium,
            color = TextSecondary,
        )
    }
}

/**
 * The nearest title to the query, promoted above the grid. The ranking engine
 * already put it first; this makes that fact visible instead of hiding it in a
 * three-column grid where the eye has to hunt.
 */
@Composable
private fun BestMatchCard(item: CatalogCardDto, onClick: () -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    val pressScale = rememberedPressScale(interaction, pressedScale = 0.975f)
    val meta = buildList {
        add(if (item.isSeries) "سریال" else "فیلم")
        item.year?.let { add(it.toString()) }
        item.bestRating?.let { add("${String.format(java.util.Locale.US, "%.1f", it)} IMDb") }
    }.joinToString("  ·  ")

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(198.dp)
            .motionScale(pressScale)
            .clip(RoundedCornerShape(20.dp))
            .background(BgElevated)
            .clickable(
                interactionSource = interaction,
                indication = null,
                onClick = onClick,
            ),
    ) {
        NetworkImage(
            url = item.backdropUrl,
            contentDescription = item.title,
            fallbackText = item.title,
            modifier = Modifier.fillMaxSize(),
        )
        Box(
            Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        0f to Color.Black.copy(alpha = 0.08f),
                        0.42f to Color.Black.copy(alpha = 0.18f),
                        1f to Color.Black.copy(alpha = 0.92f),
                    ),
                ),
        )
        Row(
            modifier = Modifier
                .align(Alignment.TopStart)
                .padding(12.dp)
                .clip(RoundedCornerShape(999.dp))
                .background(Brand)
                .padding(horizontal = 12.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                Icons.Rounded.Star,
                contentDescription = null,
                tint = OnBrand,
                modifier = Modifier.size(14.dp),
            )
            Spacer(Modifier.width(5.dp))
            Text(
                text = "نزدیک‌ترین تطابق",
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold,
                color = OnBrand,
            )
        }
        Box(
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(12.dp)
                .size(38.dp)
                .clip(CircleShape)
                .background(Color.Black.copy(alpha = 0.38f)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                Icons.Rounded.PlayArrow,
                contentDescription = null,
                tint = Color.White,
                modifier = Modifier.size(22.dp),
            )
        }
        Column(
            modifier = Modifier
                .align(Alignment.BottomStart)
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 14.dp),
            verticalArrangement = Arrangement.spacedBy(3.dp),
        ) {
            Text(
                text = item.title,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                color = Color.White,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            val english = item.englishTitle
            if (english.isNotBlank() && english != item.title) {
                Text(
                    text = english,
                    style = MaterialTheme.typography.bodySmall,
                    color = Color.White.copy(alpha = 0.72f),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Text(
                text = meta,
                style = MaterialTheme.typography.labelMedium,
                color = Color.White.copy(alpha = 0.86f),
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
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        SearchTypeFilter.entries.forEach { filter ->
            if (filter != SearchTypeFilter.ALL && counts[filter] == 0) return@forEach
            FilterPill(
                label = "${filter.label} ${counts[filter]}",
                active = selected == filter,
                onClick = { onSelect(filter) },
            )
        }
    }
}

@Composable
private fun ResultSummary(count: Int, query: String) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(6.dp)
                    .clip(CircleShape)
                    .background(Brand),
            )
            Spacer(Modifier.width(7.dp))
            Text(
                text = "مرتب‌شده بر اساس نزدیک‌ترین تطابق",
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.SemiBold,
                color = TextSecondary,
            )
            Spacer(Modifier.weight(1f))
            Text(
                text = "$count نتیجه",
                style = MaterialTheme.typography.labelMedium,
                color = TextMuted,
            )
        }
        Text(
            text = "برای «${query.trim()}»",
            style = MaterialTheme.typography.bodySmall,
            color = TextMuted,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun FilterPill(label: String, active: Boolean, onClick: () -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    val scale = rememberedPressScale(interaction, pressedScale = 0.94f)
    val bg by animateColorAsState(
        targetValue = if (active) Brand else NeutralSurface,
        animationSpec = tween(RevayatoMotion.Fast),
        label = "filterBg",
    )
    Box(
        modifier = Modifier
            .motionScale(scale)
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
        SearchSectionLabel("افراد مرتبط")
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
    val scale = rememberedPressScale(interaction, pressedScale = 0.94f)
    Column(
        modifier = Modifier
            .width(78.dp)
            .motionScale(scale)
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

@OptIn(ExperimentalLayoutApi::class)
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
                color = TextPrimary,
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
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            history.forEach { term ->
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
    val interaction = remember { MutableInteractionSource() }
    val scale = rememberedPressScale(interaction, pressedScale = 0.96f)
    Row(
        modifier = Modifier
            .motionScale(scale)
            .clip(RoundedCornerShape(999.dp))
            .background(BgElevated)
            .clickable(interactionSource = interaction, indication = null, onClick = onClick)
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
            .padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 6.dp)
            .focusRequester(focusRequester),
        placeholder = {
            Text("جستجوی فیلم، سریال و بازیگر…", color = TextMuted)
        },
        singleLine = true,
        shape = RoundedCornerShape(18.dp),
        textStyle = MaterialTheme.typography.bodyLarge.copy(color = TextPrimary),
        leadingIcon = {
            Icon(Icons.Rounded.Search, contentDescription = null)
        },
        trailingIcon = {
            Box {
                if (loading) {
                    CircularProgressIndicator(
                        modifier = Modifier
                            .padding(12.dp)
                            .size(20.dp),
                        strokeWidth = 2.dp,
                        color = Brand,
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
        colors = OutlinedTextFieldDefaults.colors(
            focusedContainerColor = BgElevated,
            unfocusedContainerColor = BgElevated,
            focusedBorderColor = Brand.copy(alpha = 0.72f),
            unfocusedBorderColor = OutlineSoft.copy(alpha = 0.55f),
            cursorColor = Brand,
            focusedLeadingIconColor = Brand,
            unfocusedLeadingIconColor = TextMuted,
        ),
    )
}
