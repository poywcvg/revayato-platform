package com.revayato.app.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class CreateRoomRequest(
    @SerialName("content_type") val contentType: String, // "movie" | "episode"
    @SerialName("content_id") val contentId: Int,
    @SerialName("expires_in_minutes") val expiresInMinutes: Int? = null,
)

@Serializable
data class RoomUserDto(
    val id: Int = 0,
    @SerialName("display_name") val displayName: String = "",
    val avatar: String? = null,
)

@Serializable
data class RoomSeriesRefDto(
    val id: Int = 0,
    val slug: String = "",
    val title: String = "",
    @SerialName("season_number") val seasonNumber: Int = 1,
    @SerialName("episode_number") val episodeNumber: Int = 0,
)

@Serializable
data class RoomContentDto(
    val type: String = "movie",
    val id: Int = 0,
    val slug: String = "",
    val title: String = "",
    @SerialName("secondary_title") val secondaryTitle: String? = null,
    val description: String? = null,
    @SerialName("duration_seconds") val durationSeconds: Int = 0,
    @SerialName("video_url") val videoUrl: String? = null,
    @SerialName("stream_links") val streamLinks: List<DownloadLinkDto> = emptyList(),
    @SerialName("poster_url") val posterUrl: String? = null,
    @SerialName("backdrop_url") val backdropUrl: String? = null,
    @SerialName("subtitle_tracks") val subtitleTracks: List<SubtitleTrackDto> = emptyList(),
    // Episode rooms nest the parent series so auto-heal can map to the catalog
    // target (objectId=series id, episodeId=episode id) like the web client.
    val series: RoomSeriesRefDto? = null,
)

/** Watch-party member as broadcast over the socket (nested user). */
@Serializable
data class RoomMemberDto(
    val user: RoomUserDto? = null,
    val role: String = "guest",
    @SerialName("is_online") val isOnline: Boolean = false,
    @SerialName("joined_at") val joinedAt: String? = null,
    @SerialName("last_seen_at") val lastSeenAt: String? = null,
)

@Serializable
data class PlaybackStateDto(
    @SerialName("is_playing") val isPlaying: Boolean = false,
    @SerialName("position_seconds") val positionSeconds: Double = 0.0,
    @SerialName("duration_seconds") val durationSeconds: Double = 0.0,
    @SerialName("playback_rate") val playbackRate: Double = 1.0,
    @SerialName("updated_by") val updatedBy: RoomUserDto? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
    @SerialName("server_time_ms") val serverTimeMs: Long = 0,
    @SerialName("stream_url") val streamUrl: String? = null,
)

@Serializable
data class RoomDto(
    @SerialName("invite_code") val inviteCode: String = "",
    val status: String = "active",
    val host: RoomUserDto? = null,
    val content: RoomContentDto? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("expires_at") val expiresAt: String? = null,
    @SerialName("member_count") val memberCount: Int = 0,
    @SerialName("is_host") val isHost: Boolean = false,
    @SerialName("is_member") val isMember: Boolean = false,
    @SerialName("my_role") val myRole: String? = null,
    @SerialName("playback_state") val playbackState: PlaybackStateDto? = null,
)

@Serializable
data class ChatMessageDto(
    val id: Int = 0,
    val user: RoomUserDto? = null,
    val message: String = "",
    @SerialName("created_at") val createdAt: String? = null,
)
