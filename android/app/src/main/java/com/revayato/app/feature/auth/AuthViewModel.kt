package com.revayato.app.feature.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.network.ApiResult
import com.revayato.app.data.repository.AuthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class AuthFormState(
    val identifier: String = "",   // email or username (login)
    val email: String = "",
    val username: String = "",
    val password: String = "",
    val loading: Boolean = false,
    val error: String? = null,
    val done: Boolean = false,     // success → caller navigates away
    val info: String? = null,      // e.g. reset-email confirmation
)

@HiltViewModel
class AuthViewModel @Inject constructor(
    private val authRepository: AuthRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(AuthFormState())
    val state: StateFlow<AuthFormState> = _state.asStateFlow()

    fun onIdentifierChange(v: String) = _state.update { it.copy(identifier = v, error = null) }
    fun onEmailChange(v: String) = _state.update { it.copy(email = v, error = null) }
    fun onUsernameChange(v: String) = _state.update { it.copy(username = v, error = null) }
    fun onPasswordChange(v: String) = _state.update { it.copy(password = v, error = null) }

    fun login() {
        val s = _state.value
        val problem = when {
            s.identifier.isBlank() -> "ایمیل یا نام کاربری‌ات را وارد کن."
            s.password.isBlank() -> "رمز عبورت را وارد کن."
            else -> null
        }
        if (problem != null) {
            _state.update { it.copy(error = problem) }
            return
        }
        run { authRepository.login(s.identifier, s.password) }
    }

    fun register() {
        val s = _state.value
        val problem = when {
            s.email.isBlank() -> "ایمیلت را وارد کن."
            !s.email.contains("@") || !s.email.contains(".") -> "ایمیل معتبر وارد کن، مثل name@mail.com."
            s.username.isBlank() -> "یک نام کاربری انتخاب کن."
            s.username.length < 3 -> "نام کاربری باید حداقل ۳ کاراکتر باشد."
            s.password.length < 8 -> "رمز عبور باید حداقل ۸ کاراکتر باشد."
            else -> null
        }
        if (problem != null) {
            _state.update { it.copy(error = problem) }
            return
        }
        run { authRepository.register(s.email, s.username, s.password) }
    }

    fun requestReset() {
        val s = _state.value
        if (s.email.isBlank()) {
            _state.update { it.copy(error = "ایمیل حسابت را وارد کن تا لینک بازیابی بفرستیم.") }
            return
        }
        _state.update { it.copy(loading = true, error = null, info = null) }
        viewModelScope.launch {
            when (val res = authRepository.requestPasswordReset(s.email)) {
                is ApiResult.Success -> _state.update {
                    it.copy(loading = false, info = "اگر این ایمیل ثبت شده باشد، لینک بازیابی ارسال شد.")
                }
                is ApiResult.Error -> _state.update { it.copy(loading = false, error = res.message) }
            }
        }
    }

    fun consumeDone() = _state.update { it.copy(done = false) }

    private fun run(call: suspend () -> ApiResult<*>) {
        _state.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val res = call()) {
                is ApiResult.Success -> _state.update { it.copy(loading = false, done = true) }
                is ApiResult.Error -> _state.update { it.copy(loading = false, error = res.message) }
            }
        }
    }
}
