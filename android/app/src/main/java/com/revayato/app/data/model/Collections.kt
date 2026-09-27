package com.revayato.app.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * User-created collections ("کالکشن") + public profiles. Mirrors the backend
 * `apps.engagement.collections_api` serializers exactly. A collection is an
 * ordered list that can mix movies and series (the movie/series content_type +
 * object_id pattern), with three visibility levels and a share token for links.
 * All data is real and DB-backed.
 */

/** Collection visibility, matching `UserCollection.Visibility` on the backend. */
object CollectionVisibility {
    const val PUBLIC = "public"
    const val UNLISTED = "unlisted"
    const val PRIVATE = "private"

    /** Persian label for a visibility value (falls back to the raw value). */
    fun label(value: String): String = when (value) {
        PUBLIC -> "عمومی"
        UNLISTED -> "با لینک"
        PRIVATE -> "خصوصی"
        else -> value
    }
}

@Serializable
data class CollectionOwnerDto(
    val username: String = "",
    val avatar: String? = null,
)

/**
 * One title inside a collection. The backend serializes the poster card fields
 * flat (id/content_type/title/slug/poster/site_rating + release_year|start_year),
 * then adds the per-item note/position/added_at. `toCard()` adapts it back to a
 * `CatalogCardDto` so it renders with the shared poster-tile UI.
 */
@Serializable
data class CollectionItemDto(
    val id: Int = 0,
    @SerialName("content_type") val contentType: String = "movie",
    val title: String = "",
    val slug: String = "",
    val poster: String? = null,
    @SerialName("site_rating") val siteRating: Double? = null,
    @SerialName("release_year") val releaseYear: Int? = null,
    @SerialName("start_year") val startYear: Int? = null,
    val note: String = "",
    val position: Int = 0,
    @SerialName("added_at") val addedAt: String? = null,
) {
    val year: Int? get() = releaseYear ?: startYear
    val isSeries: Boolean get() = contentType == "series"

    fun toCard(): CatalogCardDto = CatalogCardDto(
        id = id,
        title = title,
        slug = slug,
        releaseYear = releaseYear,
        startYear = startYear,
        siteRating = siteRating,
        poster = poster,
    )
}

@Serializable
data class UserCollectionDto(
    val id: Int = 0,
    val slug: String = "",
    val title: String = "",
    val description: String = "",
    val visibility: String = CollectionVisibility.PUBLIC,
    val accent: String = "#7c5cff",
    @SerialName("item_count") val itemCount: Int = 0,
    val covers: List<String> = emptyList(),
    val owner: CollectionOwnerDto = CollectionOwnerDto(),
    @SerialName("share_token") val shareToken: String = "",
    @SerialName("share_url") val shareUrl: String = "",
    @SerialName("is_mine") val isMine: Boolean = false,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
    // Present only on detail reads.
    val items: List<CollectionItemDto> = emptyList(),
) {
    val visibilityLabel: String get() = CollectionVisibility.label(visibility)
}

/**
 * Lightweight row for the «افزودن به کالکشن» picker
 * (`GET api/engagement/collections/containing/`): each of my collections plus a
 * `contains` flag for the title being added.
 */
@Serializable
data class CollectionPickRowDto(
    val id: Int = 0,
    val slug: String = "",
    val title: String = "",
    val visibility: String = CollectionVisibility.PUBLIC,
    val accent: String = "#7c5cff",
    @SerialName("item_count") val itemCount: Int = 0,
    val contains: Boolean = false,
)

@Serializable
data class CollectionCreateRequest(
    val title: String,
    val description: String = "",
    val visibility: String = CollectionVisibility.PUBLIC,
    val accent: String = "",
)

@Serializable
data class CollectionItemRequest(
    @SerialName("content_type") val contentType: String,
    @SerialName("object_id") val objectId: Int,
    val note: String = "",
)

/** Ack for add/remove item ops. */
@Serializable
data class CollectionItemMutationDto(
    val added: Boolean? = null,
    val removed: Boolean? = null,
    @SerialName("item_count") val itemCount: Int = 0,
)

/** One public review on a profile (`public_profile.reviews`). */
@Serializable
data class ProfileReviewDto(
    @SerialName("content_type") val contentType: String = "movie",
    @SerialName("object_id") val objectId: Int = 0,
    val content: CatalogCardDto? = null,
    @Serializable(with = LenientDoubleSerializer::class) val score: Double = 0.0,
    val review: String = "",
    @SerialName("is_spoiler") val isSpoiler: Boolean = false,
    @SerialName("created_at") val createdAt: String? = null,
)

@Serializable
data class ProfileStatsDto(
    val collections: Int = 0,
    @SerialName("public_titles") val publicTitles: Int = 0,
    val ratings: Int = 0,
    val likes: Int? = null,
)

/**
 * A public profile (`GET api/users/<username>/`). When `isPrivate` is true only
 * the identity card is present; stats/collections/reviews are empty.
 */
@Serializable
data class PublicProfileDto(
    val username: String = "",
    @SerialName("display_name") val displayName: String = "",
    val avatar: String? = null,
    val bio: String = "",
    @SerialName("is_verified") val isVerified: Boolean = false,
    @SerialName("member_since") val memberSince: String? = null,
    @SerialName("is_private") val isPrivate: Boolean = false,
    @SerialName("is_self") val isSelf: Boolean = false,
    val stats: ProfileStatsDto = ProfileStatsDto(),
    val collections: List<UserCollectionDto> = emptyList(),
    val reviews: List<ProfileReviewDto> = emptyList(),
)
