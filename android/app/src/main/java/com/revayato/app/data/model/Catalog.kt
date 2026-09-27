package com.revayato.app.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class PagedResponse<T>(
    val count: Int = 0,
    val next: String? = null,
    val previous: String? = null,
    val results: List<T> = emptyList(),
)

@Serializable
data class GenreDto(
    val id: Int = 0,
    val title: String = "",
    val slug: String = "",
    @SerialName("movie_count") val movieCount: Int = 0,
    @SerialName("series_count") val seriesCount: Int = 0,
    @SerialName("title_count") val titleCount: Int = 0,
    @SerialName("is_featured") val isFeatured: Boolean = false,
)

@Serializable
data class PersonDto(
    val id: Int = 0,
    val name: String = "",
    val slug: String = "",
    @SerialName("photo") val photo: String? = null,
    @SerialName("profile_url") val profileUrl: String? = null,
)

@Serializable
data class CastMemberDto(
    val id: Int = 0,
    val actor: PersonDto? = null,
    val role: String = "",
    val order: Int = 0,
)

@Serializable
data class CountryDto(
    val id: Int = 0,
    val name: String = "",
    val slug: String = "",
    val code: String = "",
    @SerialName("movie_count") val movieCount: Int = 0,
    @SerialName("series_count") val seriesCount: Int = 0,
) {
    /** Preferred filter value for the catalog `country` param (code, else name). */
    val filterValue: String get() = code.ifBlank { name }
    val titleCount: Int get() = movieCount + seriesCount
}

/**
 * Rich person row used by the actor and director browse lists. Both endpoints
 * share the same shape (`/api/actors/`, `/api/directors/`).
 */
@Serializable
data class PersonListItemDto(
    val id: Int = 0,
    val name: String = "",
    @SerialName("original_name") val originalName: String? = null,
    val slug: String = "",
    val photo: String? = null,
    @SerialName("photo_external_url") val photoExternalUrl: String? = null,
    @SerialName("birth_place") val birthPlace: String? = null,
    val popularity: Double? = null,
    @SerialName("is_featured") val isFeatured: Boolean = false,
) {
    val displayName: String get() = name.ifBlank { originalName.orEmpty() }
    val imageUrl: String? get() = photo ?: photoExternalUrl
}

/** Person profile with filmography (`/api/actors/{slug}/`, `/api/directors/{slug}/`). */
@Serializable
data class PersonDetailDto(
    val id: Int = 0,
    val name: String = "",
    @SerialName("original_name") val originalName: String? = null,
    val slug: String = "",
    val photo: String? = null,
    @SerialName("photo_external_url") val photoExternalUrl: String? = null,
    val biography: String? = null,
    @SerialName("birth_date") val birthDate: String? = null,
    @SerialName("birth_place") val birthPlace: String? = null,
    val popularity: Double? = null,
    val movies: List<CatalogCardDto> = emptyList(),
    val series: List<CatalogCardDto> = emptyList(),
) {
    val displayName: String get() = name.ifBlank { originalName.orEmpty() }
    val imageUrl: String? get() = photo ?: photoExternalUrl
    val filmography: List<CatalogCardDto> get() = movies + series
}

@Serializable
data class DownloadLinkDto(
    val label: String = "",
    val quality: String = "",
    @SerialName("size_label") val sizeLabel: String = "",
    val url: String = "",
    val kind: String? = null,
    @SerialName("subtitle_type") val subtitleType: String? = null,
    @SerialName("season_number") val seasonNumber: Int? = null,
    @SerialName("episode_number") val episodeNumber: Int? = null,
)

@Serializable
data class SubtitleTrackDto(
    val id: String = "",
    val label: String = "",
    val language: String = "",
    val src: String = "",
    val default: Boolean = false,
    @SerialName("source_url") val sourceUrl: String? = null,
    val provider: String? = null,
    @SerialName("source_priority") val sourcePriority: Int? = null,
    @SerialName("sync_confidence") val syncConfidence: String? = null,
    @SerialName("season_number") val seasonNumber: Int? = null,
    @SerialName("episode_number") val episodeNumber: Int? = null,
)

/**
 * Unified card model for both movies and series list payloads. Series expose
 * start_year/end_year instead of release_year; both are folded into [year].
 */
@Serializable
data class CatalogCardDto(
    val id: Int = 0,
    val title: String = "",
    @SerialName("original_title") val originalTitle: String? = null,
    @SerialName("secondary_title") val secondaryTitle: String? = null,
    val slug: String = "",
    @SerialName("short_description") val shortDescription: String? = null,
    @SerialName("release_year") val releaseYear: Int? = null,
    @SerialName("start_year") val startYear: Int? = null,
    @SerialName("end_year") val endYear: Int? = null,
    @SerialName("duration_minutes") val durationMinutes: Int? = null,
    @SerialName("age_rating") val ageRating: String? = null,
    val language: String? = null,
    @SerialName("content_format") val contentFormat: String? = null,
    @SerialName("is_dubbed") val isDubbed: Boolean = false,
    @SerialName("has_subtitle") val hasSubtitle: Boolean = false,
    @SerialName("imdb_rating") val imdbRating: Double? = null,
    /** 1–250 when the title is on the IMDb Top 250 chart; null otherwise. */
    @SerialName("imdb_rank") val imdbRank: Int? = null,
    @SerialName("rating_average") val ratingAverage: Double? = null,
    @SerialName("site_rating") val siteRating: Double? = null,
    val popularity: Double? = null,
    val poster: String? = null,
    val backdrop: String? = null,
    @SerialName("trailer_url") val trailerUrl: String? = null,
    @SerialName("has_downloads") val hasDownloads: Boolean = false,
    val genres: List<GenreDto> = emptyList(),
    val status: String? = null,
    @SerialName("is_featured") val isFeatured: Boolean = false,
    /** Mixed feeds (recent, anime, Top 250) say outright what each card is. */
    @SerialName("content_type") val declaredType: String? = null,
) {
    val year: Int? get() = releaseYear ?: startYear
    // The server's word beats the year-shape guess, which misreads a series whose
    // start_year is missing as a movie.
    val isSeries: Boolean get() = when (declaredType) {
        "series" -> true
        "movie" -> false
        else -> releaseYear == null && (startYear != null || status != null)
    }
    val contentType: String get() = if (isSeries) "series" else "movie"
    val posterUrl: String? get() = poster
    val backdropUrl: String? get() = backdrop ?: poster
    val bestRating: Double? get() = imdbRating ?: ratingAverage ?: siteRating
}

@Serializable
data class MovieDetailDto(
    val id: Int = 0,
    val title: String = "",
    @SerialName("original_title") val originalTitle: String? = null,
    @SerialName("secondary_title") val secondaryTitle: String? = null,
    val slug: String = "",
    val description: String? = null,
    @SerialName("release_year") val releaseYear: Int? = null,
    @SerialName("duration_minutes") val durationMinutes: Int? = null,
    @SerialName("age_rating") val ageRating: String? = null,
    val language: String? = null,
    @SerialName("content_format") val contentFormat: String? = null,
    @SerialName("is_dubbed") val isDubbed: Boolean = false,
    @SerialName("has_subtitle") val hasSubtitle: Boolean = false,
    @SerialName("is_uncensored") val isUncensored: Boolean = false,
    @SerialName("imdb_rating") val imdbRating: Double? = null,
    @SerialName("rating_average") val ratingAverage: Double? = null,
    @SerialName("site_rating") val siteRating: Double? = null,
    @SerialName("imdb_id") val imdbId: String? = null,
    val poster: String? = null,
    val backdrop: String? = null,
    @SerialName("trailer_url") val trailerUrl: String? = null,
    @SerialName("video_url") val videoUrl: String? = null,
    @SerialName("download_url") val downloadUrl: String? = null,
    @SerialName("download_links") val downloadLinks: List<DownloadLinkDto> = emptyList(),
    val quality: String? = null,
    @SerialName("subtitle_tracks") val subtitleTracks: List<SubtitleTrackDto> = emptyList(),
    @SerialName("has_downloads") val hasDownloads: Boolean = false,
    @SerialName("download_qualities") val downloadQualities: List<String> = emptyList(),
    val genres: List<GenreDto> = emptyList(),
    @SerialName("movie_actors") val cast: List<CastMemberDto> = emptyList(),
    val directors: List<PersonDto> = emptyList(),
    val countries: List<CountryDto> = emptyList(),
    @SerialName("view_count") val viewCount: Int = 0,
    @SerialName("like_count") val likeCount: Int = 0,
)

@Serializable
data class EpisodeDto(
    val id: Int = 0,
    val title: String = "",
    @SerialName("episode_number") val episodeNumber: Int = 0,
    val description: String? = null,
    @SerialName("duration_minutes") val durationMinutes: Int? = null,
    val poster: String? = null,
    @SerialName("video_url") val videoUrl: String? = null,
    @SerialName("download_url") val downloadUrl: String? = null,
    @SerialName("stream_links") val streamLinks: List<DownloadLinkDto> = emptyList(),
    @SerialName("subtitle_tracks") val subtitleTracks: List<SubtitleTrackDto> = emptyList(),
    @SerialName("air_date") val airDate: String? = null,
    @SerialName("view_count") val viewCount: Int = 0,
)

@Serializable
data class SeasonDto(
    val id: Int = 0,
    val title: String = "",
    @SerialName("season_number") val seasonNumber: Int = 0,
    val description: String? = null,
    val poster: String? = null,
    @SerialName("episode_count") val episodeCount: Int = 0,
    val episodes: List<EpisodeDto> = emptyList(),
)

@Serializable
data class SeriesDetailDto(
    val id: Int = 0,
    val title: String = "",
    @SerialName("original_title") val originalTitle: String? = null,
    @SerialName("secondary_title") val secondaryTitle: String? = null,
    val slug: String = "",
    val description: String? = null,
    @SerialName("start_year") val startYear: Int? = null,
    @SerialName("end_year") val endYear: Int? = null,
    @SerialName("age_rating") val ageRating: String? = null,
    val language: String? = null,
    @SerialName("content_format") val contentFormat: String? = null,
    @SerialName("is_dubbed") val isDubbed: Boolean = false,
    @SerialName("has_subtitle") val hasSubtitle: Boolean = false,
    @SerialName("imdb_rating") val imdbRating: Double? = null,
    @SerialName("rating_average") val ratingAverage: Double? = null,
    @SerialName("site_rating") val siteRating: Double? = null,
    @SerialName("imdb_id") val imdbId: String? = null,
    val poster: String? = null,
    val backdrop: String? = null,
    @SerialName("trailer_url") val trailerUrl: String? = null,
    @SerialName("download_links") val downloadLinks: List<DownloadLinkDto> = emptyList(),
    @SerialName("has_downloads") val hasDownloads: Boolean = false,
    @SerialName("download_qualities") val downloadQualities: List<String> = emptyList(),
    val genres: List<GenreDto> = emptyList(),
    @SerialName("series_actors") val cast: List<CastMemberDto> = emptyList(),
    val directors: List<PersonDto> = emptyList(),
    val countries: List<CountryDto> = emptyList(),
    val status: String? = null,
    @SerialName("view_count") val viewCount: Int = 0,
    @SerialName("like_count") val likeCount: Int = 0,
    val seasons: List<SeasonDto> = emptyList(),
)

@Serializable
data class SearchResponseDto(
    val query: String = "",
    @SerialName("match_type") val matchType: String? = null,
    val movies: List<CatalogCardDto> = emptyList(),
    val series: List<CatalogCardDto> = emptyList(),
    val actors: List<PersonDto> = emptyList(),
) {
    /** Movies and series interleaved for a single results grid. */
    val combined: List<CatalogCardDto> get() = movies + series
}

@Serializable
data class PlaybackSubtitleEnsureRequest(
    @SerialName("content_type") val contentType: String,
    val slug: String,
    @SerialName("episode_id") val episodeId: Int = 0,
    val version: String = "",
    @SerialName("source_url") val sourceUrl: String = "",
    val sync: Boolean = true,
)

/** Response of both playback-subtitle-ensure and playback-subtitle-status. */
@Serializable
data class PlaybackSubtitleResult(
    val status: String = "",
    val reported: Boolean = false,
    val queued: Boolean = false,
    @SerialName("has_subtitle_tracks") val hasSubtitleTracks: Boolean = false,
    @SerialName("subtitle_tracks") val subtitleTracks: List<SubtitleTrackDto> = emptyList(),
    @SerialName("episode_id") val episodeId: Int? = null,
    @SerialName("report_id") val reportId: Int? = null,
    val message: String? = null,
)

/**
 * A structured, machine-actionable content problem report (POST
 * api/catalog/report-issue/). Unlike the free-text support ticket, `problemType`
 * lets the backend auto-remediation engine dispatch the fix to the right crawler
 * (subtitle pipeline, playback re-crawl, link-integrity strip). `problemType` is
 * one of: subtitle, wrong_title, wrong_episode, playback, audio, other.
 */
@Serializable
data class ContentIssueReportRequest(
    @SerialName("content_type") val contentType: String,
    @SerialName("problem_type") val problemType: String,
    @SerialName("object_id") val objectId: Int = 0,
    val slug: String = "",
    @SerialName("episode_id") val episodeId: Int = 0,
    @SerialName("playback_version") val playbackVersion: String = "",
    @SerialName("source_url") val sourceUrl: String = "",
    val detail: String = "",
)

/** Server ack for a filed content issue report. */
@Serializable
data class ContentIssueReportResult(
    val ok: Boolean = true,
    @SerialName("report_id") val reportId: Int? = null,
    val status: String = "",
    @SerialName("problem_type") val problemType: String = "",
    @SerialName("report_count") val reportCount: Int = 1,
    val auto: Boolean = false,
    val created: Boolean = false,
)

@Serializable
data class CollectionDto(
    val id: Int = 0,
    val title: String = "",
    val slug: String = "",
    val description: String? = null,
    val poster: String? = null,
    val backdrop: String? = null,
    val items: List<CatalogCardDto> = emptyList(),
)
