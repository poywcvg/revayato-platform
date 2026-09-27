package com.revayato.app.feature.root

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.revayato.app.core.auth.SessionEvents
import com.revayato.app.data.repository.AuthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import javax.inject.Inject

data class StartState(
    val loading: Boolean = true,
    val isLoggedIn: Boolean = false,
)

@HiltViewModel
class RootViewModel @Inject constructor(
    authRepository: AuthRepository,
    sessionEventsSource: SessionEvents,
) : ViewModel() {

    val sessionEvents: SharedFlow<Unit> = sessionEventsSource.loggedOut

    val startState: StateFlow<StartState> = authRepository.isLoggedIn
        .map { StartState(loading = false, isLoggedIn = it) }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.Eagerly,
            initialValue = StartState(loading = true, isLoggedIn = false),
        )
}
