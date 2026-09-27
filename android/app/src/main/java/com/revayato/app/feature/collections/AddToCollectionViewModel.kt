package com.revayato.app.feature.collections

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.network.onError
import com.revayato.app.core.network.onSuccess
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.CollectionPickRowDto
import com.revayato.app.data.repository.CollectionsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class AddToCollectionState(
    val rows: UiState<List<CollectionPickRowDto>> = UiState.Loading,
    val pending: Set<String> = emptySet(),
    val creating: Boolean = false,
    val createError: String? = null,
    val message: String? = null,
)

/**
 * Backs the «افزودن به کالکشن» sheet: loads which of the viewer's collections
 * already hold a title, toggles membership per row, and creates a new collection
 * with the title already in it.
 */
@HiltViewModel
class AddToCollectionViewModel @Inject constructor(
    private val repository: CollectionsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(AddToCollectionState())
    val state: StateFlow<AddToCollectionState> = _state.asStateFlow()

    private var contentType: String = "movie"
    private var objectId: Int = 0

    fun load(contentType: String, objectId: Int) {
        this.contentType = contentType
        this.objectId = objectId
        _state.update { it.copy(rows = UiState.Loading) }
        viewModelScope.launch {
            repository.containing(contentType, objectId)
                .onSuccess { data -> _state.update { it.copy(rows = UiState.Success(data)) } }
                .onError { msg, _ -> _state.update { it.copy(rows = UiState.Error(msg)) } }
        }
    }

    fun toggle(row: CollectionPickRowDto) {
        if (_state.value.pending.contains(row.slug)) return
        _state.update { it.copy(pending = it.pending + row.slug) }
        viewModelScope.launch {
            val result = if (row.contains) {
                repository.removeItem(row.slug, contentType, objectId)
            } else {
                repository.addItem(row.slug, contentType, objectId)
            }
            result
                .onSuccess { mutation ->
                    val nowContains = !row.contains
                    _state.update { st ->
                        val list = (st.rows as? UiState.Success)?.data.orEmpty().map {
                            if (it.slug == row.slug) it.copy(contains = nowContains, itemCount = mutation.itemCount) else it
                        }
                        st.copy(
                            rows = UiState.Success(list),
                            pending = st.pending - row.slug,
                            message = if (nowContains) "به «${row.title}» اضافه شد" else "از «${row.title}» حذف شد",
                        )
                    }
                }
                .onError { msg, _ ->
                    _state.update { it.copy(pending = it.pending - row.slug, message = msg) }
                }
        }
    }

    fun createAndAdd(title: String, description: String, visibility: String) {
        _state.update { it.copy(creating = true, createError = null) }
        viewModelScope.launch {
            repository.create(title, description, visibility)
                .onSuccess { created ->
                    repository.addItem(created.slug, contentType, objectId)
                        .onSuccess { mutation ->
                            val row = CollectionPickRowDto(
                                id = created.id,
                                slug = created.slug,
                                title = created.title,
                                visibility = created.visibility,
                                accent = created.accent,
                                itemCount = mutation.itemCount,
                                contains = true,
                            )
                            _state.update { st ->
                                val list = listOf(row) + (st.rows as? UiState.Success)?.data.orEmpty()
                                st.copy(
                                    rows = UiState.Success(list),
                                    creating = false,
                                    message = "کالکشن «${created.title}» ساخته شد",
                                )
                            }
                        }
                        .onError { msg, _ ->
                            _state.update { it.copy(creating = false, createError = msg) }
                        }
                }
                .onError { msg, _ -> _state.update { it.copy(creating = false, createError = msg) } }
        }
    }

    fun consumeMessage() = _state.update { it.copy(message = null) }
    fun consumeCreateError() = _state.update { it.copy(createError = null) }
}
