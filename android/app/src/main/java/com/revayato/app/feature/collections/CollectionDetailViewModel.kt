package com.revayato.app.feature.collections

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.network.ApiResult
import com.revayato.app.core.network.onError
import com.revayato.app.core.network.onSuccess
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.UserCollectionDto
import com.revayato.app.data.repository.CollectionsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

/** How a collection detail screen was reached — decides which endpoint to read. */
sealed interface CollectionSource {
    data class Owned(val slug: String) : CollectionSource
    data class Shared(val token: String) : CollectionSource
    data class Public(val username: String, val slug: String) : CollectionSource
}

data class CollectionDetailState(
    val content: UiState<UserCollectionDto> = UiState.Loading,
    val editing: Boolean = false,
    val editError: String? = null,
    val deleted: Boolean = false,
    val message: String? = null,
)

@HiltViewModel
class CollectionDetailViewModel @Inject constructor(
    private val repository: CollectionsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(CollectionDetailState())
    val state: StateFlow<CollectionDetailState> = _state.asStateFlow()

    private var source: CollectionSource? = null

    fun load(src: CollectionSource) {
        source = src
        _state.update { it.copy(content = UiState.Loading) }
        viewModelScope.launch {
            val result = when (src) {
                is CollectionSource.Owned -> repository.myCollectionDetail(src.slug)
                is CollectionSource.Shared -> repository.sharedCollection(src.token)
                is CollectionSource.Public -> repository.publicCollection(src.username, src.slug)
            }
            when (result) {
                is ApiResult.Success -> _state.update { it.copy(content = UiState.Success(result.data)) }
                is ApiResult.Error -> _state.update { it.copy(content = UiState.Error(result.message)) }
            }
        }
    }

    private fun currentSlug(): String? = when (val c = _state.value.content) {
        is UiState.Success -> c.data.slug
        else -> (source as? CollectionSource.Owned)?.slug
    }

    fun removeItem(contentType: String, objectId: Int) {
        val slug = currentSlug() ?: return
        viewModelScope.launch {
            repository.removeItem(slug, contentType, objectId).onSuccess {
                // Drop the item locally for an instant response, then refresh counts.
                _state.update { st ->
                    val c = st.content
                    if (c is UiState.Success) {
                        val items = c.data.items.filterNot {
                            it.contentType == contentType && it.id == objectId
                        }
                        st.copy(content = UiState.Success(c.data.copy(items = items, itemCount = items.size)))
                    } else st
                }
            }
        }
    }

    fun updateMeta(title: String, description: String, visibility: String) {
        val slug = currentSlug() ?: return
        _state.update { it.copy(editError = null) }
        viewModelScope.launch {
            repository.update(slug, title, description, visibility)
                .onSuccess { updated ->
                    source = CollectionSource.Owned(updated.slug)
                    _state.update { it.copy(content = UiState.Success(updated), editing = false) }
                }
                .onError { msg, _ -> _state.update { it.copy(editError = msg) } }
        }
    }

    fun delete(onDeleted: () -> Unit) {
        val slug = currentSlug() ?: return
        viewModelScope.launch {
            repository.delete(slug).onSuccess {
                _state.update { it.copy(deleted = true) }
                onDeleted()
            }
        }
    }

    fun startEditing() = _state.update { it.copy(editing = true, editError = null) }
    fun stopEditing() = _state.update { it.copy(editing = false, editError = null) }
    fun showMessage(msg: String) = _state.update { it.copy(message = msg) }
    fun consumeMessage() = _state.update { it.copy(message = null) }
}
