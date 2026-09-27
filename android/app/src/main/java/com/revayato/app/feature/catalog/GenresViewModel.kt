package com.revayato.app.feature.catalog

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.network.ApiResult
import com.revayato.app.data.model.GenreDto
import com.revayato.app.data.repository.CatalogRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class GenresState(
    val genres: List<GenreDto> = emptyList(),
    val loading: Boolean = true,
    val error: String? = null,
)

/** Shared source of the genre list for the categories tab and the browse drawer. */
@HiltViewModel
class GenresViewModel @Inject constructor(
    private val catalogRepository: CatalogRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(GenresState())
    val state: StateFlow<GenresState> = _state.asStateFlow()

    init { load() }

    fun load() {
        if (_state.value.genres.isNotEmpty()) return
        _state.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val res = catalogRepository.genres()) {
                is ApiResult.Success -> _state.update { it.copy(genres = res.data, loading = false) }
                is ApiResult.Error -> _state.update { it.copy(loading = false, error = res.message) }
            }
        }
    }
}
