package com.revayato.app.data.repository

import com.revayato.app.core.network.ApiResult
import com.revayato.app.core.network.safeApiCall
import com.revayato.app.data.model.ChatMessageDto
import com.revayato.app.data.model.CreateRoomRequest
import com.revayato.app.data.model.RoomDto
import com.revayato.app.data.remote.ApiService
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class WatchPartyRepository @Inject constructor(
    private val api: ApiService,
) {
    suspend fun createRoom(
        contentType: String,
        contentId: Int,
        expiresInMinutes: Int? = null,
    ): ApiResult<RoomDto> =
        safeApiCall { api.createRoom(CreateRoomRequest(contentType, contentId, expiresInMinutes)) }

    suspend fun getRoom(code: String): ApiResult<RoomDto> = safeApiCall { api.getRoom(code) }

    suspend fun joinRoom(code: String): ApiResult<RoomDto> = safeApiCall { api.joinRoom(code) }

    suspend fun leaveRoom(code: String): ApiResult<Unit> = safeApiCall { api.leaveRoom(code); Unit }

    suspend fun endRoom(code: String): ApiResult<Unit> = safeApiCall { api.endRoom(code); Unit }

    suspend fun messages(code: String, limit: Int = 50): ApiResult<List<ChatMessageDto>> =
        safeApiCall { api.roomMessages(code, limit) }
}
