package com.revayato.app.feature.support

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.network.ApiResult
import com.revayato.app.core.network.onError
import com.revayato.app.core.network.onSuccess
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.SupportTicketListItemDto
import com.revayato.app.data.repository.SupportRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class MyRequestsState(
    val list: UiState<List<SupportTicketListItemDto>> = UiState.Loading,
    val creating: Boolean = false,
    val createError: String? = null,
)

@HiltViewModel
class MyRequestsViewModel @Inject constructor(
    private val repository: SupportRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(MyRequestsState())
    val state: StateFlow<MyRequestsState> = _state.asStateFlow()

    fun load() {
        _state.update { it.copy(list = UiState.Loading) }
        viewModelScope.launch {
            when (val r = repository.myTickets()) {
                is ApiResult.Success -> _state.update { it.copy(list = UiState.Success(r.data)) }
                is ApiResult.Error -> _state.update { it.copy(list = UiState.Error(r.message)) }
            }
        }
    }

    /** Refresh silently without flashing the loading state (used on return from a thread). */
    fun refresh() {
        viewModelScope.launch {
            repository.myTickets().onSuccess { data ->
                _state.update { it.copy(list = UiState.Success(data)) }
            }
        }
    }

    /**
     * Open a new request. Validates locally (subject ≥ 4, body ≥ 10) before hitting
     * the server, and calls [onCreated] with the tracking code so the caller can
     * jump straight into the fresh conversation.
     */
    fun create(
        category: String,
        subject: String,
        body: String,
        onCreated: (trackingCode: String) -> Unit,
    ) {
        val subjectTrim = subject.trim()
        val bodyTrim = body.trim()
        if (subjectTrim.length < 4) {
            _state.update { it.copy(createError = "موضوع را کامل‌تر بنویس (حداقل ۴ نویسه).") }
            return
        }
        if (bodyTrim.length < 10) {
            _state.update { it.copy(createError = "متن پیام باید حداقل ۱۰ نویسه باشد.") }
            return
        }
        _state.update { it.copy(creating = true, createError = null) }
        viewModelScope.launch {
            repository.create(category, subjectTrim, bodyTrim)
                .onSuccess { created ->
                    _state.update { it.copy(creating = false) }
                    refresh()
                    onCreated(created.trackingCode)
                }
                .onError { msg, _ ->
                    _state.update { it.copy(creating = false, createError = msg) }
                }
        }
    }

    fun consumeCreateError() = _state.update { it.copy(createError = null) }
}
