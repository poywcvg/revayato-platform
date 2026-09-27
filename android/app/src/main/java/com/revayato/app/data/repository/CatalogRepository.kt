package com.revayato.app.data.repository

import com.revayato.app.core.network.ApiResult
import com.revayato.app.core.network.safeApiCall
import com.revayato.app.data.model.CatalogCardDto
import com.revayato.app.data.model.SearchResponseDto
import com.revayato.app.data.model.CollectionDto
import com.revayato.app.data.model.ContentIssueReportRequest
import com.revayato.app.data.model.ContentIssueReportResult
import com.revayato.app.data.model.CountryDto
import com.revayato.app.data.model.GenreDto
import com.revayato.app.data.model.MovieDetailDto
import com.revayato.app.data.model.PagedResponse
import com.revayato.app.data.model.PersonDetailDto
import com.revayato.app.data.model.PersonListItemDto
import com.revayato.app.data.model.PlaybackSubtitleEnsureRequest
import com.revayato.app.data.model.PlaybackSubtitleResult
import com.revayato.app.data.model.SeriesDetailDto
import com.revayato.app.data.remote.ApiService
import javax.inject.Inject
import javax.inject.Singleton

/** Query builder mirroring the backend catalog filter contract. */
data class CatalogQuery(
    val q: String? = null,
    val genre: String? = null,
    val country: String? = null,
    val language: String? = null,
    val year: Int? = null,
    val minRating: Double? = null,
    val contentFormat: String? = null,
    val availability: String? = null,
    val sort: String = "newest",
    val limit: Int = 24,
    val offset: Int = 0,
) {
    fun toMap(): Map<String, String> = buildMap {
        q?.takeIf { it.isNotBlank() }?.let { put("q", it) }
        genre?.takeIf { it.isNotBlank() }?.let { put("genre", it) }
        country?.takeIf { it.isNotBlank() }?.let { put("country", it) }
        language?.takeIf { it.isNotBlank() }?.let { put("language", it) }
        year?.let { put("year", it.toString()) }
        minRating?.let { put("min_rating", it.toString()) }
        contentFormat?.takeIf { it.isNotBlank() }?.let { put("content_format", it) }
        availability?.takeIf { it.isNotBlank() }?.let { put("availability", it) }
        put("sort", sort)
        put("limit", limit.toString())
        put("offset", offset.toString())
    }
}

@Singleton
class CatalogRepository @Inject constructor(
    private val api: ApiService,
) {
    suspend fun movies(query: CatalogQuery): ApiResult<PagedResponse<CatalogCardDto>> =
        safeApiCall { api.movies(query.toMap()) }

    suspend fun series(query: CatalogQuery): ApiResult<PagedResponse<CatalogCardDto>> =
        safeApiCall { api.series(query.toMap()) }

    suspend fun movieDetail(slug: String): ApiResult<MovieDetailDto> =
        safeApiCall { api.movieDetail(slug) }

    suspend fun seriesDetail(slug: String): ApiResult<SeriesDetailDto> =
        safeApiCall { api.seriesDetail(slug) }

    suspend fun movieSimilar(slug: String): ApiResult<List<CatalogCardDto>> =
        safeApiCall { api.movieSimilar(slug) }

    suspend fun seriesSimilar(slug: String): ApiResult<List<CatalogCardDto>> =
        safeApiCall { api.seriesSimilar(slug) }

    suspend fun genres(): ApiResult<List<GenreDto>> = safeApiCall { api.genres() }

    suspend fun countries(): ApiResult<List<CountryDto>> = safeApiCall { api.countries() }

    suspend fun actors(featured: Boolean = false, limit: Int = 24, offset: Int = 0): ApiResult<PagedResponse<PersonListItemDto>> =
        safeApiCall { api.actors(peopleQuery(featured, limit, offset)) }

    suspend fun actorDetail(slug: String): ApiResult<PersonDetailDto> =
        safeApiCall { api.actorDetail(slug) }

    suspend fun directors(featured: Boolean = false, limit: Int = 24, offset: Int = 0): ApiResult<PagedResponse<PersonListItemDto>> =
        safeApiCall { api.directors(peopleQuery(featured, limit, offset)) }

    suspend fun directorDetail(slug: String): ApiResult<PersonDetailDto> =
        safeApiCall { api.directorDetail(slug) }

    private fun peopleQuery(featured: Boolean, limit: Int, offset: Int): Map<String, String> = buildMap {
        if (featured) put("featured", "1")
        put("limit", limit.toString())
        put("offset", offset.toString())
    }

    suspend fun collections(): ApiResult<List<CollectionDto>> = safeApiCall { api.collections() }

    suspend fun collectionDetail(slug: String): ApiResult<CollectionDto> =
        safeApiCall { api.collectionDetail(slug) }

    /** Full search payload: movies + series + matching people (actors/directors). */
    suspend fun search(query: String): ApiResult<SearchResponseDto> =
        safeApiCall { api.search(query) }

    /** Per-keystroke results; falls back to [search] if the server predates the endpoint. */
    suspend fun searchSuggest(query: String): ApiResult<SearchResponseDto> =
        when (val res = safeApiCall { api.searchSuggest(query) }) {
            is ApiResult.Success -> res
            is ApiResult.Error -> search(query)
        }

    /** Ask the backend to report+attach a missing SoftSub for the online player. */
    suspend fun ensurePlaybackSubtitles(
        request: PlaybackSubtitleEnsureRequest,
    ): ApiResult<PlaybackSubtitleResult> =
        safeApiCall { api.ensurePlaybackSubtitles(request) }

    /**
     * File a structured content problem report from the player. The backend
     * auto-remediation engine dispatches the fix based on [problemType]
     * (subtitle / wrong_title / wrong_episode / playback / audio / other).
     */
    suspend fun reportContentIssue(
        contentType: String,
        problemType: String,
        objectId: Int,
        slug: String,
        episodeId: Int = 0,
        version: String = "",
        sourceUrl: String = "",
        detail: String = "",
    ): ApiResult<ContentIssueReportResult> = safeApiCall {
        api.reportContentIssue(
            ContentIssueReportRequest(
                contentType = contentType,
                problemType = problemType,
                objectId = objectId,
                slug = slug,
                episodeId = if (contentType == "series") episodeId else 0,
                playbackVersion = version,
                sourceUrl = sourceUrl,
                detail = detail.take(500),
            ),
        )
    }

    /** Cheap poll: has the reported subtitle gap been filled yet? */
    suspend fun playbackSubtitleStatus(
        contentType: String,
        slug: String,
        episodeId: Int,
        reportId: Int?,
    ): ApiResult<PlaybackSubtitleResult> = safeApiCall {
        api.playbackSubtitleStatus(
            buildMap {
                put("content_type", contentType)
                put("slug", slug)
                if (episodeId > 0) put("episode_id", episodeId.toString())
                reportId?.let { put("report_id", it.toString()) }
            },
        )
    }

    suspend fun recent(limit: Int = 24, type: String? = null): ApiResult<List<CatalogCardDto>> =
        safeApiCall {
            api.recent(
                buildMap {
                    put("limit", limit.toString())
                    type?.takeIf { it.isNotBlank() }?.let { put("type", it) }
                },
            ).results
        }

    suspend fun anime(limit: Int = 24, type: String? = null): ApiResult<List<CatalogCardDto>> =
        safeApiCall {
            api.anime(
                buildMap {
                    put("limit", limit.toString())
                    type?.takeIf { it.isNotBlank() }?.let { put("type", it) }
                },
            ).results
        }

    /** Paginated mixed feed for the "see all" catalog screen (recent / anime). */
    suspend fun recentPaged(limit: Int, offset: Int, type: String? = null): ApiResult<PagedResponse<CatalogCardDto>> =
        safeApiCall { api.recent(mixedQuery(limit, offset, type)) }

    suspend fun animePaged(limit: Int, offset: Int, type: String? = null): ApiResult<PagedResponse<CatalogCardDto>> =
        safeApiCall { api.anime(mixedQuery(limit, offset, type)) }

    /**
     * IMDb Top 250, best rank first. Only positions that are actually playable
     * come back (`available=1`) — the app never shows a card it cannot open.
     */
    suspend fun top250(type: String, limit: Int = 16): ApiResult<List<CatalogCardDto>> =
        safeApiCall { api.top250(top250Query(type, limit, 0)).results }

    suspend fun top250Paged(type: String, limit: Int, offset: Int): ApiResult<PagedResponse<CatalogCardDto>> =
        safeApiCall { api.top250(top250Query(type, limit, offset)) }

    private fun top250Query(type: String, limit: Int, offset: Int): Map<String, String> = mapOf(
        "type" to if (type == "series") "series" else "movie",
        "available" to "1",
        "limit" to limit.toString(),
        "offset" to offset.toString(),
    )

    private fun mixedQuery(limit: Int, offset: Int, type: String?): Map<String, String> = buildMap {
        put("limit", limit.toString())
        put("offset", offset.toString())
        type?.takeIf { it.isNotBlank() }?.let { put("type", it) }
    }

    suspend fun recommendations(): ApiResult<List<CatalogCardDto>> =
        safeApiCall { api.recommendations() }
}
