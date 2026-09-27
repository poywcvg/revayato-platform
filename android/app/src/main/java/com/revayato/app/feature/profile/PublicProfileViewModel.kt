package com.revayato.app.feature.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.network.onError
import com.revayato.app.core.network.onSuccess
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.PublicProfileDto
import com.revayato.app.data.repository.CollectionsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class PublicProfileViewModel @Inject constructor(
    private val repository: CollectionsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<UiState<PublicProfileDto>>(UiState.Loading)
    val state: StateFlow<UiState<PublicProfileDto>> = _state.asStateFlow()

    fun load(username: String) {
        _state.value = UiState.Loading
        viewModelScope.launch {
            repository.publicProfile(username)
                .onSuccess { profile -> _state.value = UiState.Success(profile) }
                .onError { msg, _ -> _state.value = UiState.Error(msg) }
        }
    }
}
