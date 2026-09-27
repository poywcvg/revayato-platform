package com.revayato.app.feature.people

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.network.ApiResult
import com.revayato.app.data.model.PersonListItemDto
import com.revayato.app.data.repository.CatalogRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

private const val PAGE_SIZE = 30

data class PeopleListState(
    val items: List<PersonListItemDto> = emptyList(),
    val loading: Boolean = true,
    val loadingMore: Boolean = false,
    val endReached: Boolean = false,
    val error: String? = null,
)

/** Paginated actor/director browse list. [kind] is "actors" or "directors". */
@HiltViewModel
class PeopleListViewModel @Inject constructor(
    private val catalogRepository: CatalogRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(PeopleListState())
    val state: StateFlow<PeopleListState> = _state.asStateFlow()

    private var kind: String = "actors"
    private var started = false
    private var offset = 0
    private var inFlight = false

    fun start(kind: String) {
        if (started && this.kind == kind) return
        started = true
        this.kind = kind
        reload()
    }

    fun reload() {
        offset = 0
        _state.update { it.copy(items = emptyList(), loading = true, endReached = false, error = null) }
        fetch(reset = true)
    }

    fun loadMore() {
        if (inFlight || _state.value.endReached || _state.value.loading) return
        _state.update { it.copy(loadingMore = true) }
        fetch(reset = false)
    }

    private fun fetch(reset: Boolean) {
        inFlight = true
        viewModelScope.launch {
            val res = if (kind == "directors") {
                catalogRepository.directors(limit = PAGE_SIZE, offset = offset)
            } else {
                catalogRepository.actors(limit = PAGE_SIZE, offset = offset)
            }
            when (res) {
                is ApiResult.Success -> {
                    val page = res.data.results
                    offset += page.size
                    _state.update {
                        it.copy(
                            items = if (reset) page else it.items + page,
                            loading = false,
                            loadingMore = false,
                            endReached = res.data.next == null || page.isEmpty(),
                        )
                    }
                }
                is ApiResult.Error -> _state.update {
                    it.copy(
                        loading = false,
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
