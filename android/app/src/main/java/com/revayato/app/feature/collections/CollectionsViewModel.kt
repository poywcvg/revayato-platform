package com.revayato.app.feature.collections

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.network.ApiResult
import com.revayato.app.core.network.onError
import com.revayato.app.core.network.onSuccess
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.CollectionVisibility
import com.revayato.app.data.model.UserCollectionDto
import com.revayato.app.data.repository.CollectionsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class MyCollectionsState(
    val list: UiState<List<UserCollectionDto>> = UiState.Loading,
    val creating: Boolean = false,
    val createError: String? = null,
)

@HiltViewModel
class CollectionsViewModel @Inject constructor(
    private val repository: CollectionsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(MyCollectionsState())
    val state: StateFlow<MyCollectionsState> = _state.asStateFlow()

    fun load() {
        _state.update { it.copy(list = UiState.Loading) }
        viewModelScope.launch {
            when (val r = repository.myCollections()) {
                is ApiResult.Success -> _state.update { it.copy(list = UiState.Success(r.data)) }
                is ApiResult.Error -> _state.update { it.copy(list = UiState.Error(r.message)) }
            }
        }
    }

    /** Create a collection; invokes [onCreated] with the new slug so the caller can open it. */
    fun create(
        title: String,
        description: String,
        visibility: String = CollectionVisibility.PUBLIC,
        onCreated: (String) -> Unit,
    ) {
        if (title.isBlank()) {
            _state.update { it.copy(createError = "عنوان کالکشن را وارد کن.") }
            return
        }
        _state.update { it.copy(creating = true, createError = null) }
        viewModelScope.launch {
            repository.create(title = title, description = description, visibility = visibility)
                .onSuccess { created ->
                    _state.update { it.copy(creating = false) }
                    load()
                    onCreated(created.slug)
                }
                .onError { msg, _ ->
                    _state.update { it.copy(creating = false, createError = msg) }
                }
        }
    }

    fun consumeCreateError() = _state.update { it.copy(createError = null) }
}
