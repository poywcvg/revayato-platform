package com.revayato.app.feature.watchparty

import com.revayato.app.data.model.ChatMessageDto
import com.revayato.app.data.model.PlaybackStateDto
import com.revayato.app.data.model.RoomDto
import com.revayato.app.data.model.RoomMemberDto
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

/** Parsed inbound watch-party socket events. */
sealed interface WsEvent {
    data class RoomState(
        val room: RoomDto,
        val members: List<RoomMemberDto>,
        val messages: List<ChatMessageDto>,
        val playback: PlaybackStateDto?,
        val currentMember: RoomMemberDto?,
    ) : WsEvent

    data class Playback(val eventType: String, val playback: PlaybackStateDto) : WsEvent
    data class Chat(val message: ChatMessageDto) : WsEvent
    data class Reaction(val emoji: String, val displayName: String) : WsEvent
    data class MemberJoined(val member: RoomMemberDto) : WsEvent
    data class MemberLeft(val member: RoomMemberDto) : WsEvent
    data object SyncRequested : WsEvent
    data class LatencyPong(val clientTimeMs: Long, val serverTimeMs: Long) : WsEvent
    data class Error(val code: String, val message: String) : WsEvent
    data class Closed(val code: Int, val reason: String) : WsEvent
    data class Failure(val reason: String) : WsEvent
    data object Open : WsEvent
}

/**
 * OkHttp WebSocket wrapper for a single watch-party room. Auth travels in the
 * `watchparty.jwt.<token>` subprotocol so it never leaks into URLs or logs.
 */
class WatchPartySocket(
    private val baseWsUrl: String,
    private val inviteCode: String,
    private val accessToken: String,
    private val client: OkHttpClient,
    private val json: Json,
) {
    private var webSocket: WebSocket? = null

    private val _events = MutableSharedFlow<WsEvent>(
        replay = 0,
        extraBufferCapacity = 64,
        onBufferOverflow = BufferOverflow.DROP_OLDEST,
    )
    val events: SharedFlow<WsEvent> = _events

    fun connect() {
        val request = Request.Builder()
            .url("$baseWsUrl/ws/watch-party/$inviteCode/")
            .addHeader("Sec-WebSocket-Protocol", "$SUBPROTOCOL_PREFIX$accessToken")
            .build()
        webSocket = client.newWebSocket(request, listener)
    }

    fun close() {
        webSocket?.close(1000, "left")
        webSocket = null
    }

    // ---- Outbound actions ----
    fun sendPlayback(
        eventType: String,
        positionSeconds: Double,
        durationSeconds: Double,
        playbackRate: Double,
        isPlaying: Boolean,
        streamUrl: String? = null,
    ) {
        send(buildJsonObject {
            put("type", eventType)
            put("position_seconds", positionSeconds)
            put("duration_seconds", durationSeconds)
            put("playback_rate", playbackRate)
            put("is_playing", isPlaying)
            if (!streamUrl.isNullOrBlank()) put("stream_url", streamUrl)
        })
    }

    fun sendChat(message: String) {
        send(buildJsonObject {
            put("type", "chat.message")
            put("message", message)
        })
    }

    /** Fire an ephemeral floating reaction to everyone in the room. */
    fun sendReaction(emoji: String) {
        send(buildJsonObject {
            put("type", "reaction.send")
            put("emoji", emoji)
        })
    }

    fun requestSync() = send(buildJsonObject { put("type", "playback.sync.request") })

    fun heartbeat() = send(buildJsonObject { put("type", "heartbeat") })

    fun latencyPing(clientTimeMs: Long) = send(buildJsonObject {
        put("type", "latency.ping")
        put("client_time_ms", clientTimeMs)
    })

    private fun send(obj: JsonObject) {
        webSocket?.send(json.encodeToString(JsonObject.serializer(), obj))
    }

    private val listener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            _events.tryEmit(WsEvent.Open)
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            runCatching { parse(text) }.getOrNull()?.let { _events.tryEmit(it) }
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            webSocket.close(1000, null)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            _events.tryEmit(WsEvent.Closed(code, reason))
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            _events.tryEmit(WsEvent.Failure(t.message ?: "اتصال قطع شد"))
        }
    }

    private fun parse(text: String): WsEvent? {
        val obj = json.parseToJsonElement(text).jsonObject
        return when (val type = obj["type"]?.jsonPrimitive?.content) {
            "room.state" -> WsEvent.RoomState(
                room = decode(obj["room"]),
                members = decodeList(obj["members"]),
                messages = decodeList(obj["messages"]),
                playback = obj["playback_state"]?.let { decodeOrNull(it) },
                currentMember = obj["current_member"]?.let { decodeOrNull(it) },
            )
            "playback.state" -> obj["playback_state"]?.let {
                decodeOrNull<PlaybackStateDto>(it)?.let { pb -> WsEvent.Playback("playback.state", pb) }
            }
            "playback.play", "playback.pause", "playback.seek", "playback.sync", "playback.sync.response" ->
                obj["playback_state"]?.let {
                    decodeOrNull<PlaybackStateDto>(it)?.let { pb -> WsEvent.Playback(type, pb) }
                }
            "playback.sync.requested" -> WsEvent.SyncRequested
            "chat.message" -> obj["message"]?.let {
                decodeOrNull<ChatMessageDto>(it)?.let { m -> WsEvent.Chat(m) }
            }
            "reaction" -> {
                val emoji = obj["emoji"]?.jsonPrimitive?.content
                if (emoji.isNullOrBlank()) null
                else WsEvent.Reaction(
                    emoji = emoji,
                    displayName = obj["user"]?.jsonObject?.get("display_name")?.jsonPrimitive?.content.orEmpty(),
                )
            }
            "member.joined" -> obj["member"]?.let {
                decodeOrNull<RoomMemberDto>(it)?.let { m -> WsEvent.MemberJoined(m) }
            }
            "member.left" -> obj["member"]?.let {
                decodeOrNull<RoomMemberDto>(it)?.let { m -> WsEvent.MemberLeft(m) }
            }
            "latency.pong" -> WsEvent.LatencyPong(
                clientTimeMs = obj["client_time_ms"]?.jsonPrimitive?.content?.toLongOrNull() ?: 0,
                serverTimeMs = obj["server_time_ms"]?.jsonPrimitive?.content?.toLongOrNull() ?: 0,
            )
            "error" -> WsEvent.Error(
                code = obj["code"]?.jsonPrimitive?.content ?: "error",
                message = obj["message"]?.jsonPrimitive?.content ?: "خطا",
            )
            else -> null
        }
    }

    private inline fun <reified T> decode(element: kotlinx.serialization.json.JsonElement?): T =
        json.decodeFromJsonElement<T>(element!!)

    private inline fun <reified T> decodeOrNull(element: kotlinx.serialization.json.JsonElement): T? =
        runCatching { json.decodeFromJsonElement<T>(element) }.getOrNull()

    private inline fun <reified T> decodeList(element: kotlinx.serialization.json.JsonElement?): List<T> =
        element?.let { runCatching { json.decodeFromJsonElement<List<T>>(it) }.getOrNull() } ?: emptyList()

    companion object {
        const val SUBPROTOCOL_PREFIX = "watchparty.jwt."
    }
}
