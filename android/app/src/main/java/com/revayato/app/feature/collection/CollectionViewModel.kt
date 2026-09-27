package com.revayato.app.feature.collection

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.network.ApiResult
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.CollectionDto
import com.revayato.app.data.repository.CatalogRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class CollectionViewModel @Inject constructor(
    private val catalogRepository: CatalogRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<UiState<CollectionDto>>(UiState.Loading)
    val state: StateFlow<UiState<CollectionDto>> = _state.asStateFlow()

    private var slug: String = ""

    fun load(slug: String) {
        this.slug = slug
        _state.value = UiState.Loading
        viewModelScope.launch {
            _state.value = when (val res = catalogRepository.collectionDetail(slug)) {
                is ApiResult.Success -> UiState.Success(res.data)
                is ApiResult.Error -> UiState.Error(res.message)
            }
        }
    }

    fun retry() = load(slug)
}
