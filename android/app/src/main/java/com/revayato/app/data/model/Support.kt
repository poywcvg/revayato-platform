package com.revayato.app.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One message inside a support conversation. `isStaffReply` decides the bubble
 * side and label (تیم روایتو vs. the user) on the request detail screen.
 * Mirrors the backend `SupportMessageSerializer`.
 */
@Serializable
data class SupportMessageDto(
    val id: Int = 0,
    val body: String = "",
    @SerialName("is_staff_reply") val isStaffReply: Boolean = false,
    @SerialName("author_username") val authorUsername: String = "",
    @SerialName("created_at") val createdAt: String = "",
)

/**
 * A row in the user's «درخواست‌های من» list (GET api/support/tickets/).
 * Mirrors the backend `SupportTicketListSerializer`. `unreadByUser` marks a
 * ticket with an unread staff reply so the list can flag it.
 */
@Serializable
data class SupportTicketListItemDto(
    val id: Int = 0,
    @SerialName("tracking_code") val trackingCode: String = "",
    val category: String = "support",
    @SerialName("category_label") val categoryLabel: String = "",
    val subject: String = "",
    @SerialName("related_title") val relatedTitle: String = "",
    val status: String = "open",
    @SerialName("status_label") val statusLabel: String = "",
    @SerialName("unread_by_staff") val unreadByStaff: Boolean = false,
    @SerialName("unread_by_user") val unreadByUser: Boolean = false,
    val username: String = "",
    @SerialName("message_count") val messageCount: Int = 0,
    @SerialName("last_message_at") val lastMessageAt: String = "",
    @SerialName("created_at") val createdAt: String = "",
)

/**
 * A full support conversation (GET/POST api/support/tickets/{code}/).
 * Mirrors the backend `SupportTicketSerializer`. The opening `body` plus every
 * entry in `messages` form the thread shown on the detail screen.
 */
@Serializable
data class SupportTicketDetailDto(
    val id: Int = 0,
    @SerialName("tracking_code") val trackingCode: String = "",
    val category: String = "support",
    @SerialName("category_label") val categoryLabel: String = "",
    val subject: String = "",
    val body: String = "",
    @SerialName("related_title") val relatedTitle: String = "",
    @SerialName("related_year") val relatedYear: Int? = null,
    @SerialName("related_url") val relatedUrl: String = "",
    val status: String = "open",
    @SerialName("status_label") val statusLabel: String = "",
    @SerialName("unread_by_staff") val unreadByStaff: Boolean = false,
    @SerialName("unread_by_user") val unreadByUser: Boolean = false,
    val username: String = "",
    val messages: List<SupportMessageDto> = emptyList(),
    @SerialName("last_message_at") val lastMessageAt: String = "",
    @SerialName("created_at") val createdAt: String = "",
    @SerialName("updated_at") val updatedAt: String = "",
) {
    /**
     * True only once the conversation is closed for new replies. A `resolved`
     * ticket still accepts a follow-up (the backend reopens it to `open`) —
     * same rule as the web inbox, which only hides the composer on `closed`.
     */
    val isClosed: Boolean get() = status == "closed"
}

/** Follow-up reply into an existing ticket (POST api/support/tickets/{code}/). */
@Serializable
data class SupportReplyRequest(val body: String)
