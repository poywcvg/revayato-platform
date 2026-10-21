package com.revayato.app.feature.catalog

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.network.ApiResult
import com.revayato.app.data.model.CatalogCardDto
import com.revayato.app.data.model.CountryDto
import com.revayato.app.data.model.GenreDto
import com.revayato.app.data.repository.CatalogQuery
import com.revayato.app.data.repository.CatalogRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

private const val PAGE_SIZE = 24

data class CatalogListState(
    val items: List<CatalogCardDto> = emptyList(),
    val loading: Boolean = true,
    val refreshing: Boolean = false,
    val loadingMore: Boolean = false,
    val endReached: Boolean = false,
    val error: String? = null,
    val sort: String = "newest",
    // Live filter selections (backend values; blank == "all").
    val genre: String = "",
    val country: String = "",
    val format: String = "",
    val availability: String = "",
    // Option lists that back the genre / country dropdowns.
    val genreOptions: List<GenreDto> = emptyList(),
    val countryOptions: List<CountryDto> = emptyList(),
    // IMDb Top 250 screen only: which chart is showing ("movie" / "series").
    val chartType: String = "movie",
) {
    /** True when any narrowing filter (beyond sort) is active. */
    val hasActiveFilters: Boolean
        get() = genre.isNotBlank() || country.isNotBlank() ||
            format.isNotBlank() || availability.isNotBlank()
}

@HiltViewModel
class CatalogListViewModel @Inject constructor(
    private val catalogRepository: CatalogRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(CatalogListState())
    val state: StateFlow<CatalogListState> = _state.asStateFlow()

    private var kind: String = "movies"
    private var started = false
    private var optionsLoaded = false
    private var offset = 0
    private var inFlight = false

    fun start(
        kind: String,
        genre: String = "",
        country: String = "",
        format: String = "",
        availability: String = "",
        initialSort: String = "",
    ) {
        val s = _state.value
        if (started && this.kind == kind && s.genre == genre && s.country == country &&
            s.format == format && s.availability == availability
        ) {
            return
        }
        started = true
        this.kind = kind
        _state.update {
            it.copy(
                genre = genre,
                country = country,
                format = format,
                availability = availability,
                sort = if (initialSort.isNotBlank()) initialSort else it.sort,
                // On the Top 250 screen the route's `format` slot names the chart.
                chartType = if (kind == "top250" && format == "series") "series" else "movie",
            )
        }
        // Filter dropdowns only make sense on the plain movie/series lists, not the
        // mixed recent/anime feeds, so only fetch the option lists there.
        if (kind != "recent" && kind != "anime" && kind != "top250") loadFilterOptions()
        reload()
    }

    fun setSort(sort: String) {
        if (_state.value.sort == sort) return
        _state.update { it.copy(sort = sort) }
        reload()
    }

    /** Switch the Top 250 screen between the film and the series chart. */
    fun setChartType(type: String) {
        if (_state.value.chartType == type) return
        _state.update { it.copy(chartType = type) }
        reload()
    }

    fun setGenre(slug: String) = applyFilter { it.copy(genre = slug) }
    fun setCountry(value: String) = applyFilter { it.copy(country = value) }
    fun setFormat(value: String) = applyFilter { it.copy(format = value) }
    fun setAvailability(value: String) = applyFilter { it.copy(availability = value) }

    /** Clear every narrowing filter at once (keeps the current sort). */
    fun clearFilters() {
        val s = _state.value
        if (!s.hasActiveFilters) return
        _state.update { it.copy(genre = "", country = "", format = "", availability = "") }
        reload()
    }

    private inline fun applyFilter(transform: (CatalogListState) -> CatalogListState) {
        val next = transform(_state.value)
        if (next == _state.value) return
        _state.value = next
        reload()
    }

    private fun loadFilterOptions() {
        if (optionsLoaded) return
        optionsLoaded = true
        viewModelScope.launch {
            when (val res = catalogRepository.genres()) {
                is ApiResult.Success -> _state.update { it.copy(genreOptions = res.data) }
                is ApiResult.Error -> Unit
            }
        }
        viewModelScope.launch {
            when (val res = catalogRepository.countries()) {
                is ApiResult.Success -> _state.update { it.copy(countryOptions = res.data) }
                is ApiResult.Error -> Unit
            }
        }
    }

    fun reload() {
        offset = 0
        _state.update {
            it.copy(items = emptyList(), loading = true, refreshing = false, endReached = false, error = null)
        }
        fetch(reset = true)
    }

    /** Pull-to-refresh: re-fetch the first page without blanking the grid. */
    fun refresh() {
        val current = _state.value
        if (inFlight || current.loading || current.refreshing) return
        offset = 0
        _state.update { it.copy(refreshing = true, endReached = false, error = null) }
        fetch(reset = true)
    }

    fun loadMore() {
        if (inFlight || _state.value.endReached || _state.value.loading || _state.value.refreshing) return
        _state.update { it.copy(loadingMore = true) }
        fetch(reset = false)
    }

    private fun fetch(reset: Boolean) {
        inFlight = true
        viewModelScope.launch {
            // Mixed feeds (`recent`, `anime`) come from dedicated endpoints that merge
            // movies+series by recency and ignore sort/genre; everything else is a plain
            // filtered movie/series list that honours the sort + filter dropdowns.
            val res = when (kind) {
                "recent" -> catalogRepository.recentPaged(PAGE_SIZE, offset)
                "anime" -> catalogRepository.animePaged(PAGE_SIZE, offset)
                // Chart order is the whole point here, so no sort or filters apply.
                "top250" -> catalogRepository.top250Paged(_state.value.chartType, PAGE_SIZE, offset)
                else -> {
                    val s = _state.value
                    val query = CatalogQuery(
                        genre = s.genre.ifBlank { null },
                        country = s.country.ifBlank { null },
                        contentFormat = s.format.ifBlank { null },
                        availability = s.availability.ifBlank { null },
                        sort = s.sort,
                        limit = PAGE_SIZE,
                        offset = offset,
                    )
                    if (kind == "series") catalogRepository.series(query) else catalogRepository.movies(query)
                }
            }
            when (res) {
                is ApiResult.Success -> {
                    val page = res.data.results
                    offset += page.size
                    _state.update {
                        it.copy(
                            items = if (reset) page else it.items + page,
                            loading = false,
                            refreshing = false,
                            loadingMore = false,
                            endReached = res.data.next == null || page.isEmpty(),
                        )
                    }
                }
                is ApiResult.Error -> _state.update {
                    it.copy(
                        loading = false,
                        refreshing = false,
                        loadingMore = false,
                        endReached = true,
                        error = if (it.items.isEmpty()) res.message else null,
                    )
                }
            }
            inFlight = false
        }
    }
}
