package com.revayato.app.data.model

import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.jsonPrimitive

/**
 * Decodes a score that may arrive as a JSON number (8.0) or, from older/other
 * serializers, a quoted decimal string ("8.0"). Kotlinx's lenient mode does not
 * reliably coerce quoted numbers, so we normalize here — a rated review then
 * always parses instead of failing the whole response.
 */
object LenientDoubleSerializer : KSerializer<Double> {
    override val descriptor: SerialDescriptor =
        PrimitiveSerialDescriptor("LenientDouble", PrimitiveKind.DOUBLE)

    override fun deserialize(decoder: Decoder): Double {
        val raw = (decoder as? JsonDecoder)?.decodeJsonElement()?.jsonPrimitive?.content
            ?: return decoder.decodeDouble()
        return raw.toDoubleOrNull() ?: 0.0
    }

    override fun serialize(encoder: Encoder, value: Double) = encoder.encodeDouble(value)
}

@Serializable
data class ToggleRequest(
    @SerialName("content_type") val contentType: String,
    @SerialName("object_id") val objectId: Int,
)

@Serializable
data class ToggleResponse(
    val active: Boolean = false,
    // The backend's watchlist endpoint answers {"added": bool} and the likes
    // endpoint answers {"liked": bool}; older/other shapes may send
    // {"in_watchlist": bool} or {"active": bool}. Accept them all so the button
    // reflects the real server state instead of silently falling back to false.
    val added: Boolean? = null,
    @SerialName("in_watchlist") val inWatchlist: Boolean? = null,
    val liked: Boolean? = null,
) {
    val isOn: Boolean get() = added ?: inWatchlist ?: liked ?: active
}

@Serializable
data class RateRequest(
    @SerialName("content_type") val contentType: String,
    @SerialName("object_id") val objectId: Int,
    val score: Double,
    val review: String? = null,
    @SerialName("is_spoiler") val isSpoiler: Boolean? = null,
)

@Serializable
data class RatingDto(
    val id: Int = 0,
    val username: String? = null,
    @Serializable(with = LenientDoubleSerializer::class) val score: Double = 0.0,
    val review: String? = null,
    @SerialName("is_spoiler") val isSpoiler: Boolean = false,
    @SerialName("created_at") val createdAt: String? = null,
    // Admin↔user interaction: a public «پاسخ روایتو» reply the team can post under
    // a review, and the «نقد برگزیده» flag that pins a standout review to the top.
    @SerialName("admin_reply") val adminReply: String? = null,
    @SerialName("admin_reply_by_name") val adminReplyByName: String? = null,
    @SerialName("admin_reply_at") val adminReplyAt: String? = null,
    @SerialName("is_featured") val isFeatured: Boolean = false,
    @SerialName("featured_at") val featuredAt: String? = null,
)

/**
 * Aggregate ratings + user reviews for a title, from
 * `GET api/engagement/ratings/summary/` — powers the comments & ratings panel on
 * movie and series detail. `myRating` is the signed-in user's own rating (null
 * when anonymous or unrated); `reviews` are other users' rated comments.
 */
@Serializable
data class RatingSummaryDto(
    val average: Double? = null,
    val count: Int = 0,
    @SerialName("my_rating") val myRating: RatingDto? = null,
    val reviews: List<RatingDto> = emptyList(),
)

@Serializable
data class WatchlistItemDto(
    val id: Int = 0,
    @SerialName("content_type") val contentType: String = "movie",
    @SerialName("object_id") val objectId: Int = 0,
    // The backend serializes the poster/title/slug card under `content` (for both
    // the watchlist and likes lists). `movie`/`series` are legacy fallbacks.
    val content: CatalogCardDto? = null,
    val movie: CatalogCardDto? = null,
    val series: CatalogCardDto? = null,
    @SerialName("created_at") val createdAt: String? = null,
) {
    val card: CatalogCardDto? get() = content ?: movie ?: series
}

/**
 * A user-submitted problem report for a title. Mirrors the backend
 * `SupportTicketCreateSerializer` (POST api/support/tickets/), which requires
 * auth and a body of at least 10 characters. `category` is always "bug" for the
 * in-app report button so it lands in the admin support inbox tagged «گزارش مشکل».
 */
@Serializable
data class SupportTicketRequest(
    val category: String,
    val subject: String,
    val body: String,
    @SerialName("related_title") val relatedTitle: String = "",
    @SerialName("related_year") val relatedYear: Int? = null,
    @SerialName("related_url") val relatedUrl: String = "",
)

/** Server ack for a created ticket; only the tracking code is surfaced to the user. */
@Serializable
data class SupportTicketDto(
    @SerialName("tracking_code") val trackingCode: String = "",
    val status: String = "",
)

/** Client engagement event (drives recommendations + resume telemetry). */
@Serializable
data class EngagementEventRequest(
    @SerialName("event_type") val eventType: String,
    @SerialName("source_page") val sourcePage: String,
    @SerialName("title_id") val titleId: Int? = null,
    @SerialName("title_slug") val titleSlug: String? = null,
    @SerialName("content_type") val contentType: String? = null,
    @SerialName("progress_percent") val progressPercent: Double? = null,
    // Download signal fields (event_type == "download"). Feed the staff
    // downloads analytics panel; omitted for every other event type.
    val quality: String? = null,
    val platform: String? = null,
)
