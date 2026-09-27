package com.revayato.app.feature.support

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.network.ApiResult
import com.revayato.app.core.network.onError
import com.revayato.app.core.network.onSuccess
import com.revayato.app.core.ui.UiState
import com.revayato.app.data.model.SupportTicketDetailDto
import com.revayato.app.data.repository.SupportRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class RequestDetailState(
    val ticket: UiState<SupportTicketDetailDto> = UiState.Loading,
    val sending: Boolean = false,
    val sendError: String? = null,
)

@HiltViewModel
class RequestDetailViewModel @Inject constructor(
    private val repository: SupportRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(RequestDetailState())
    val state: StateFlow<RequestDetailState> = _state.asStateFlow()

    fun load(code: String) {
        _state.update { it.copy(ticket = UiState.Loading) }
        viewModelScope.launch {
            when (val r = repository.ticketDetail(code)) {
                is ApiResult.Success -> _state.update { it.copy(ticket = UiState.Success(r.data)) }
                is ApiResult.Error -> _state.update { it.copy(ticket = UiState.Error(r.message)) }
            }
        }
    }

    /** Post a reply; on success the returned thread replaces the current one. */
    fun reply(code: String, body: String, onSent: () -> Unit) {
        val trimmed = body.trim()
        if (trimmed.isEmpty() || _state.value.sending) return
        _state.update { it.copy(sending = true, sendError = null) }
        viewModelScope.launch {
            repository.reply(code, trimmed)
                .onSuccess { updated ->
                    _state.update { it.copy(ticket = UiState.Success(updated), sending = false) }
                    onSent()
                }
                .onError { msg, _ ->
                    _state.update { it.copy(sending = false, sendError = msg) }
                }
        }
    }

    fun consumeSendError() = _state.update { it.copy(sendError = null) }
}
