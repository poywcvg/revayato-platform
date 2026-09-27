package com.revayato.app.data.repository

import com.revayato.app.core.auth.SessionEvents
import com.revayato.app.core.auth.TokenStore
import com.revayato.app.core.network.ApiResult
import com.revayato.app.core.network.safeApiCall
import com.revayato.app.data.model.LoginRequest
import com.revayato.app.data.model.PasswordResetRequest
import com.revayato.app.data.model.RefreshRequest
import com.revayato.app.data.model.RegisterRequest
import com.revayato.app.data.model.UserDto
import com.revayato.app.data.remote.ApiService
import kotlinx.coroutines.flow.Flow
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AuthRepository @Inject constructor(
    private val api: ApiService,
    private val tokenStore: TokenStore,
    private val sessionEvents: SessionEvents,
) {
    val isLoggedIn: Flow<Boolean> = tokenStore.isLoggedIn
    val loggedOutEvents = sessionEvents.loggedOut

    suspend fun login(identifier: String, password: String): ApiResult<UserDto?> =
        safeApiCall {
            val res = api.login(LoginRequest(identifier.trim(), password))
            tokenStore.save(res.access, res.refresh)
            res.user
        }

    suspend fun register(email: String, username: String, password: String): ApiResult<UserDto?> =
        safeApiCall {
            val res = api.register(RegisterRequest(email.trim(), username.trim(), password))
            tokenStore.save(res.access, res.refresh)
            res.user
        }

    suspend fun me(): ApiResult<UserDto> = safeApiCall { api.me() }

    suspend fun requestPasswordReset(email: String): ApiResult<Unit> = safeApiCall {
        api.requestPasswordReset(PasswordResetRequest(email.trim()))
        Unit
    }

    suspend fun logout() {
        val refresh = tokenStore.refreshToken()
        if (!refresh.isNullOrBlank()) {
            runCatching { api.logout(RefreshRequest(refresh)) }
        }
        tokenStore.clear()
    }
}
