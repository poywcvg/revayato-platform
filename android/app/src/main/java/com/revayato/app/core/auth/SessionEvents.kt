package com.revayato.app.core.auth

import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import javax.inject.Inject
import javax.inject.Singleton

/** App-wide session signals (e.g. the refresh token died → force sign-out). */
@Singleton
class SessionEvents @Inject constructor() {
    private val _loggedOut = MutableSharedFlow<Unit>(
        replay = 0,
        extraBufferCapacity = 1,
        onBufferOverflow = BufferOverflow.DROP_OLDEST,
    )
    val loggedOut: SharedFlow<Unit> = _loggedOut

    fun notifyLoggedOut() {
        _loggedOut.tryEmit(Unit)
    }
}
