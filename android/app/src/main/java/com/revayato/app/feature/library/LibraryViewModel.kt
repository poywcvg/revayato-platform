package com.revayato.app.feature.library

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.network.orNull
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.CatalogCardDto
import com.revayato.app.data.repository.EngagementRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class LibraryData(
    val watchlist: List<CatalogCardDto>,
    val favorites: List<CatalogCardDto>,
)

@HiltViewModel
class LibraryViewModel @Inject constructor(
    private val engagementRepository: EngagementRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<UiState<LibraryData>>(UiState.Loading)
    val state: StateFlow<UiState<LibraryData>> = _state.asStateFlow()

    fun load() {
        _state.value = UiState.Loading
        viewModelScope.launch {
            val watchlistDef = async { engagementRepository.watchlist() }
            val likesDef = async { engagementRepository.likes() }
            val watchlist = watchlistDef.await().orNull().orEmpty().mapNotNull { it.card }
            val favorites = likesDef.await().orNull().orEmpty().mapNotNull { it.card }
            _state.value = UiState.Success(LibraryData(watchlist, favorites))
        }
    }
}
