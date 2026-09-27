package com.revayato.app.feature.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.network.onSuccess
import com.revayato.app.core.network.orNull
import com.revayato.app.data.model.PublicProfileDto
import com.revayato.app.data.model.UserDto
import com.revayato.app.data.repository.AuthRepository
import com.revayato.app.data.repository.CollectionsRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ProfileState(
    val user: UserDto? = null,
    val profile: PublicProfileDto? = null,
    val loading: Boolean = false,
    val loggedOut: Boolean = false,
)

@HiltViewModel
class ProfileViewModel @Inject constructor(
    private val authRepository: AuthRepository,
    private val collectionsRepository: CollectionsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(ProfileState())
    val state: StateFlow<ProfileState> = _state.asStateFlow()

    fun load() {
        _state.update { it.copy(loading = true) }
        viewModelScope.launch {
            val user = authRepository.me().orNull()
            _state.update { it.copy(user = user) }
            // Rich profile (stats + own collections + reviews) reuses the public
            // endpoint, which flags is_self and includes private collections for the owner.
            val username = user?.username?.takeIf { it.isNotBlank() }
            if (username != null) {
                collectionsRepository.publicProfile(username)
                    .onSuccess { profile -> _state.update { it.copy(profile = profile) } }
            }
            _state.update { it.copy(loading = false) }
        }
    }

    fun logout() {
        viewModelScope.launch {
            authRepository.logout()
            _state.update { it.copy(user = null, profile = null, loggedOut = true) }
        }
    }

    fun consumeLoggedOut() = _state.update { it.copy(loggedOut = false) }
}
