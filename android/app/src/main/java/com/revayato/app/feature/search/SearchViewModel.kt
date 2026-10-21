package com.revayato.app.feature.search

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.network.ApiResult
import com.revayato.app.core.network.orNull
import com.revayato.app.core.search.SearchHistoryStore
import com.revayato.app.core.search.SearchRanker
import com.revayato.app.data.model.CatalogCardDto
import com.revayato.app.data.model.PersonDto
import com.revayato.app.data.model.SearchResponseDto
import com.revayato.app.data.repository.CatalogRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.launch
import javax.inject.Inject

data class SearchState(
    val query: String = "",
    val loading: Boolean = false,
    val results: List<CatalogCardDto> = emptyList(),
    val people: List<PersonDto> = emptyList(),
    val suggestions: List<CatalogCardDto> = emptyList(),
    val history: List<String> = emptyList(),
    val hasSearched: Boolean = false,
    val error: String? = null,
) {
    val hasResults: Boolean get() = results.isNotEmpty() || people.isNotEmpty()
}

@OptIn(FlowPreview::class)
@HiltViewModel
class SearchViewModel @Inject constructor(
    private val catalogRepository: CatalogRepository,
    private val searchHistoryStore: SearchHistoryStore,
) : ViewModel() {

    private val _state = MutableStateFlow(SearchState())
    val state: StateFlow<SearchState> = _state.asStateFlow()

    private val queryFlow = MutableStateFlow("")
    private var searchJob: Job? = null
    // Term of the last explicit submit, so the debounced keystroke path does
    // not cancel that full search with a suggest call for the same text.
    private var submittedTerm: String? = null

    // Small in-memory cache so backspacing/retyping a term returns instantly
    // instead of re-hitting the network — the biggest perceived-speed win.
    private val cache = object : LinkedHashMap<String, SearchResponseDto>(16, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, SearchResponseDto>?) = size > 40
    }

    init {
        loadSuggestions()
        observeHistory()
        viewModelScope.launch {
            queryFlow
                // Results follow every letter: the suggest endpoint answers in
                // milliseconds, so a short debounce only coalesces key repeats.
                .debounce(90)
                .distinctUntilChanged()
                .collect { q -> if (q.trim() != submittedTerm) runSearch(q) }
        }
    }

    fun onQueryChange(value: String) {
        if (value.trim() != submittedTerm) submittedTerm = null
        _state.value = _state.value.copy(query = value)
        queryFlow.value = value
    }

    /** Explicit submit (keyboard search action / tapping a history chip). */
    fun submit(term: String) {
        onQueryChange(term)
        submittedTerm = term.trim()
        runSearch(term, immediate = true)
    }

    fun clear() {
        _state.value = _state.value.copy(
            query = "", results = emptyList(), people = emptyList(),
            hasSearched = false, error = null, loading = false,
        )
        queryFlow.value = ""
        submittedTerm = null
        searchJob?.cancel()
    }

    fun removeHistory(term: String) {
        viewModelScope.launch { searchHistoryStore.remove(term) }
    }

    fun clearHistory() {
        viewModelScope.launch { searchHistoryStore.clear() }
    }

    private fun observeHistory() {
        viewModelScope.launch {
            searchHistoryStore.history.collect { items ->
                _state.value = _state.value.copy(history = items)
            }
        }
    }

    private fun loadSuggestions() {
        viewModelScope.launch {
            val recent = catalogRepository.recent().orNull().orEmpty()
            _state.value = _state.value.copy(suggestions = recent.take(12))
        }
    }

    private fun runSearch(q: String, immediate: Boolean = false) {
        val term = q.trim()
        // A newer keystroke always wins: an older, slower answer must never
        // overwrite the results for what is in the box now.
        searchJob?.cancel()
        if (term.isEmpty()) {
            _state.value = _state.value.copy(
                results = emptyList(), people = emptyList(),
                hasSearched = false, loading = false, error = null,
            )
            return
        }

        // Typing uses the fast suggest index; an explicit submit runs the full
        // search (synopsis/people/genre matching) and is what enters history.
        val key = if (immediate) "full:$term" else "suggest:$term"
        cache[key]?.let { cached ->
            applyResult(term, cached, record = immediate)
            return
        }

        _state.value = _state.value.copy(loading = true, error = null)
        searchJob = viewModelScope.launch {
            val res = if (immediate) catalogRepository.search(term) else catalogRepository.searchSuggest(term)
            when (res) {
                is ApiResult.Success -> {
                    cache[key] = res.data
                    applyResult(term, res.data, record = immediate)
                }
                is ApiResult.Error ->
                    _state.value = _state.value.copy(loading = false, hasSearched = true, error = res.message)
            }
        }
    }

    private fun applyResult(term: String, data: SearchResponseDto, record: Boolean) {
        // The backend chooses the candidate set; the client guarantees the
        // nearest result is actually nearest. This runs on every payload,
        // including cached ones, so order never depends on response timing.
        val rankedTitles = SearchRanker.rankTitles(term, data.combined)
        val rankedPeople = SearchRanker.rankPeople(term, data.actors)
        _state.value = _state.value.copy(
            loading = false,
            hasSearched = true,
            results = rankedTitles,
            people = rankedPeople,
            error = null,
        )
        // Only remember terms that actually found something, so the history stays
        // useful instead of filling with typos.
        if (record && (rankedTitles.isNotEmpty() || rankedPeople.isNotEmpty())) {
            viewModelScope.launch { searchHistoryStore.record(term) }
        }
    }
}
