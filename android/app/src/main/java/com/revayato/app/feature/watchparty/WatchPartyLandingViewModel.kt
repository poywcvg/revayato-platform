package com.revayato.app.feature.watchparty

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.network.ApiResult
import com.revayato.app.data.repository.AuthRepository
import com.revayato.app.data.repository.WatchPartyRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class WatchPartyLandingState(
    val code: String = "",
    val joining: Boolean = false,
    val isLoggedIn: Boolean = false,
    val error: String? = null,
    val navigateToCode: String? = null,
    val requireLogin: Boolean = false,
)

/** Invite-code regex the backend routing enforces: 20–32 url-safe chars. */
private val INVITE_REGEX = Regex("^[A-Za-z0-9_-]{20,32}$")

@HiltViewModel
class WatchPartyLandingViewModel @Inject constructor(
    private val watchPartyRepository: WatchPartyRepository,
    private val authRepository: AuthRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(WatchPartyLandingState())
    val state: StateFlow<WatchPartyLandingState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            _state.update { it.copy(isLoggedIn = authRepository.isLoggedIn.first()) }
        }
    }

    fun onCodeChange(value: String) {
        // Accept a pasted full invite URL too — keep only the last path segment.
        val cleaned = value.trim().trimEnd('/').substringAfterLast('/')
        _state.update { it.copy(code = cleaned, error = null) }
    }

    fun join() {
        val code = _state.value.code.trim()
        if (!INVITE_REGEX.matches(code)) {
            _state.update { it.copy(error = "کد دعوت نامعتبر است") }
            return
        }
        viewModelScope.launch {
            if (!authRepository.isLoggedIn.first()) {
                _state.update { it.copy(requireLogin = true) }
                return@launch
            }
            _state.update { it.copy(joining = true, error = null) }
            when (val res = watchPartyRepository.joinRoom(code)) {
                is ApiResult.Success ->
                    _state.update { it.copy(joining = false, navigateToCode = res.data.inviteCode.ifBlank { code }) }
                is ApiResult.Error ->
                    _state.update { it.copy(joining = false, error = res.message) }
            }
        }
    }

    fun consumeNavigation() = _state.update { it.copy(navigateToCode = null) }
    fun consumeRequireLogin() = _state.update { it.copy(requireLogin = false) }
}
