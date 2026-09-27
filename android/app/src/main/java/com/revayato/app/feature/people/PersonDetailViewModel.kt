package com.revayato.app.feature.people

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.network.ApiResult
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.PersonDetailDto
import com.revayato.app.data.repository.CatalogRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/** Actor/director profile with filmography. [kind] is "actor" or "director". */
@HiltViewModel
class PersonDetailViewModel @Inject constructor(
    private val catalogRepository: CatalogRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<UiState<PersonDetailDto>>(UiState.Loading)
    val state: StateFlow<UiState<PersonDetailDto>> = _state.asStateFlow()

    private var started = false

    fun start(kind: String, slug: String) {
        if (started) return
        started = true
        load(kind, slug)
    }

    fun load(kind: String, slug: String) {
        _state.value = UiState.Loading
        viewModelScope.launch {
            val res = if (kind == "director") {
                catalogRepository.directorDetail(slug)
            } else {
                catalogRepository.actorDetail(slug)
            }
            _state.value = when (res) {
                is ApiResult.Success -> UiState.Success(res.data)
                is ApiResult.Error -> UiState.Error(res.message)
            }
        }
    }
}
