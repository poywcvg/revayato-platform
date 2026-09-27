package com.revayato.app.data.remote

import com.revayato.app.data.model.AnalyticsBehaviorEnvelope
import com.revayato.app.data.model.AnalyticsContentEnvelope
import com.revayato.app.data.model.AnalyticsEngagementEnvelope
import com.revayato.app.data.model.AnalyticsOverviewEnvelope
import com.revayato.app.data.model.AnalyticsUsersEnvelope
import com.revayato.app.data.model.AppReleaseDto
import com.revayato.app.data.model.CatalogCardDto
import com.revayato.app.data.model.ChatMessageDto
import com.revayato.app.data.model.CollectionCreateRequest
import com.revayato.app.data.model.CollectionDto
import com.revayato.app.data.model.CollectionItemMutationDto
import com.revayato.app.data.model.CollectionItemRequest
import com.revayato.app.data.model.CollectionPickRowDto
import com.revayato.app.data.model.ContentIssueReportRequest
import com.revayato.app.data.model.ContentIssueReportResult
import com.revayato.app.data.model.CountryDto
import com.revayato.app.data.model.CreateRoomRequest
import com.revayato.app.data.model.EngagementEventRequest
import com.revayato.app.data.model.GenreDto
import com.revayato.app.data.model.LoginRequest
import com.revayato.app.data.model.MessageResponse
import com.revayato.app.data.model.MovieDetailDto
import com.revayato.app.data.model.PagedResponse
import com.revayato.app.data.model.PasswordResetRequest
import com.revayato.app.data.model.PersonDetailDto
import com.revayato.app.data.model.PersonListItemDto
import com.revayato.app.data.model.PlaybackSubtitleEnsureRequest
import com.revayato.app.data.model.PlaybackSubtitleResult
import com.revayato.app.data.model.PublicProfileDto
import com.revayato.app.data.model.RateRequest
import com.revayato.app.data.model.RatingDto
import com.revayato.app.data.model.RatingSummaryDto
import com.revayato.app.data.model.RefreshRequest
import com.revayato.app.data.model.RefreshResponse
import com.revayato.app.data.model.RegisterRequest
import com.revayato.app.data.model.RoomDto
import com.revayato.app.data.model.SearchResponseDto
import com.revayato.app.data.model.SeriesDetailDto
import com.revayato.app.data.model.SupportReplyRequest
import com.revayato.app.data.model.SupportTicketDetailDto
import com.revayato.app.data.model.SupportTicketDto
import com.revayato.app.data.model.SupportTicketListItemDto
import com.revayato.app.data.model.SupportTicketRequest
import com.revayato.app.data.model.ToggleRequest
import com.revayato.app.data.model.ToggleResponse
import com.revayato.app.data.model.TokenResponse
import com.revayato.app.data.model.UserCollectionDto
import com.revayato.app.data.model.UserDto
import com.revayato.app.data.model.WatchlistItemDto
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.HTTP
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query
import retrofit2.http.QueryMap

interface ApiService {

    // ---- Auth ----
    @POST("api/auth/token/")
    suspend fun login(@Body body: LoginRequest): TokenResponse

    @POST("api/auth/register/")
    suspend fun register(@Body body: RegisterRequest): TokenResponse

    @POST("api/auth/token/refresh/")
    suspend fun refresh(@Body body: RefreshRequest): RefreshResponse

    @POST("api/auth/logout/")
    suspend fun logout(@Body body: RefreshRequest): Response<Unit>

    @POST("api/auth/password-reset/")
    suspend fun requestPasswordReset(@Body body: PasswordResetRequest): MessageResponse

    @GET("api/accounts/me/")
    suspend fun me(): UserDto

    // ---- Catalog ----
    @GET("api/movies/")
    suspend fun movies(@QueryMap filters: Map<String, String>): PagedResponse<CatalogCardDto>

    @GET("api/movies/{slug}/")
    suspend fun movieDetail(@Path("slug") slug: String): MovieDetailDto

    @GET("api/movies/{slug}/similar/")
    suspend fun movieSimilar(@Path("slug") slug: String): List<CatalogCardDto>

    @GET("api/series/")
    suspend fun series(@QueryMap filters: Map<String, String>): PagedResponse<CatalogCardDto>

    @GET("api/series/{slug}/")
    suspend fun seriesDetail(@Path("slug") slug: String): SeriesDetailDto

    @GET("api/series/{slug}/similar/")
    suspend fun seriesSimilar(@Path("slug") slug: String): List<CatalogCardDto>

    @GET("api/genres/")
    suspend fun genres(): List<GenreDto>

    @GET("api/countries/")
    suspend fun countries(): List<CountryDto>

    @GET("api/actors/")
    suspend fun actors(@QueryMap query: Map<String, String>): PagedResponse<PersonListItemDto>

    @GET("api/actors/{slug}/")
    suspend fun actorDetail(@Path("slug") slug: String): PersonDetailDto

    @GET("api/directors/")
    suspend fun directors(@QueryMap query: Map<String, String>): PagedResponse<PersonListItemDto>

    @GET("api/directors/{slug}/")
    suspend fun directorDetail(@Path("slug") slug: String): PersonDetailDto

    @GET("api/collections/")
    suspend fun collections(): List<CollectionDto>

    @GET("api/collections/{slug}/")
    suspend fun collectionDetail(@Path("slug") slug: String): CollectionDto

    @GET("api/search/")
    suspend fun search(@Query("q") query: String): SearchResponseDto

    /** Search-as-you-type: same payload as [search], answered from an in-memory index. */
    @GET("api/search/suggest/")
    suspend fun searchSuggest(
        @Query("q") query: String,
        @Query("limit") limit: Int = 24,
    ): SearchResponseDto

    // ---- Playback subtitles (online auto-import) ----
    @POST("api/catalog/playback-subtitle-ensure/")
    suspend fun ensurePlaybackSubtitles(
        @Body body: PlaybackSubtitleEnsureRequest,
    ): PlaybackSubtitleResult

    @GET("api/catalog/playback-subtitle-status/")
    suspend fun playbackSubtitleStatus(
        @QueryMap query: Map<String, String>,
    ): PlaybackSubtitleResult

    // ---- Structured content issue report (auto-remediated) ----
    // Player «گزارش خطا»; the backend engine auto-fixes based on problem_type.
    @POST("api/catalog/report-issue/")
    suspend fun reportContentIssue(
        @Body body: ContentIssueReportRequest,
    ): ContentIssueReportResult

    // Mixed movies+series, newest first. Returns a paginated envelope, not a bare list.
    @GET("api/catalog/recent/")
    suspend fun recent(@QueryMap query: Map<String, String>): PagedResponse<CatalogCardDto>

    // Mixed anime (movies+series), newest first; ?type=movie / ?type=series to narrow.
    @GET("api/catalog/anime/")
    suspend fun anime(@QueryMap query: Map<String, String>): PagedResponse<CatalogCardDto>

    // IMDb Top 250 in chart order; ?type=movie|series, ?available=1 for playable positions only.
    @GET("api/catalog/top250/")
    suspend fun top250(@QueryMap query: Map<String, String>): PagedResponse<CatalogCardDto>

    @GET("api/recommendations/")
    suspend fun recommendations(): List<CatalogCardDto>

    // ---- Engagement ----
    @GET("api/engagement/watchlist/")
    suspend fun watchlist(): List<WatchlistItemDto>

    @POST("api/engagement/watchlist/toggle/")
    suspend fun toggleWatchlist(@Body body: ToggleRequest): ToggleResponse

    @GET("api/engagement/likes/")
    suspend fun likes(): List<WatchlistItemDto>

    @POST("api/engagement/likes/toggle/")
    suspend fun toggleLike(@Body body: ToggleRequest): ToggleResponse

    @POST("api/engagement/ratings/")
    suspend fun rate(@Body body: RateRequest): RatingDto

    @GET("api/engagement/ratings/summary/")
    suspend fun ratingSummary(
        @Query("content_type") contentType: String,
        @Query("object_id") objectId: Int,
    ): RatingSummaryDto

    @POST("api/engagement/events/")
    suspend fun sendEvent(@Body body: EngagementEventRequest): Response<Unit>

    // ---- Collections ("کالکشن") ----
    @GET("api/engagement/collections/")
    suspend fun myCollections(): List<UserCollectionDto>

    @POST("api/engagement/collections/")
    suspend fun createCollection(@Body body: CollectionCreateRequest): UserCollectionDto

    // Which of my collections already contain a given title (powers the picker).
    @GET("api/engagement/collections/containing/")
    suspend fun collectionsContaining(
        @Query("content_type") contentType: String,
        @Query("object_id") objectId: Int,
    ): List<CollectionPickRowDto>

    @GET("api/engagement/collections/{slug}/")
    suspend fun myCollectionDetail(@Path("slug") slug: String): UserCollectionDto

    @PATCH("api/engagement/collections/{slug}/")
    suspend fun updateCollection(
        @Path("slug") slug: String,
        @Body body: CollectionCreateRequest,
    ): UserCollectionDto

    @DELETE("api/engagement/collections/{slug}/")
    suspend fun deleteCollection(@Path("slug") slug: String): Response<Unit>

    @POST("api/engagement/collections/{slug}/items/")
    suspend fun addCollectionItem(
        @Path("slug") slug: String,
        @Body body: CollectionItemRequest,
    ): CollectionItemMutationDto

    // DELETE with a body (content_type + object_id) — Retrofit needs @HTTP for this.
    @HTTP(method = "DELETE", path = "api/engagement/collections/{slug}/items/", hasBody = true)
    suspend fun removeCollectionItem(
        @Path("slug") slug: String,
        @Body body: CollectionItemRequest,
    ): CollectionItemMutationDto

    // ---- Public reads (no auth required) ----
    @GET("api/share/collection/{token}/")
    suspend fun sharedCollection(@Path("token") token: String): UserCollectionDto

    @GET("api/users/{username}/")
    suspend fun publicProfile(@Path("username") username: String): PublicProfileDto

    @GET("api/users/{username}/collections/{slug}/")
    suspend fun publicCollection(
        @Path("username") username: String,
        @Path("slug") slug: String,
    ): UserCollectionDto

    // ---- Support / problem reports ----
    // User taps «گزارش خطا» on a detail page; lands in the admin support inbox.
    @POST("api/support/tickets/")
    suspend fun createSupportTicket(@Body body: SupportTicketRequest): SupportTicketDto

    // «درخواست‌های من» — the user's own conversations with the روایتو team.
    @GET("api/support/tickets/")
    suspend fun myTickets(): List<SupportTicketListItemDto>

    @GET("api/support/tickets/{code}/")
    suspend fun ticketDetail(@Path("code") code: String): SupportTicketDetailDto

    // Posting a body to an existing ticket adds a reply and returns the full thread.
    @POST("api/support/tickets/{code}/")
    suspend fun replyTicket(
        @Path("code") code: String,
        @Body body: SupportReplyRequest,
    ): SupportTicketDetailDto

    // ---- Watch Party ----
    @POST("api/watch-party/rooms/")
    suspend fun createRoom(@Body body: CreateRoomRequest): RoomDto

    @GET("api/watch-party/rooms/{code}/")
    suspend fun getRoom(@Path("code") code: String): RoomDto

    @POST("api/watch-party/rooms/{code}/join/")
    suspend fun joinRoom(@Path("code") code: String): RoomDto

    @POST("api/watch-party/rooms/{code}/leave/")
    suspend fun leaveRoom(@Path("code") code: String): Response<Unit>

    @GET("api/watch-party/rooms/{code}/messages/")
    suspend fun roomMessages(
        @Path("code") code: String,
        @Query("limit") limit: Int = 50,
    ): List<ChatMessageDto>

    @POST("api/watch-party/rooms/{code}/end/")
    suspend fun endRoom(@Path("code") code: String): Response<Unit>

    // ---- Staff analytics (staff-only; 403 for non-staff) ----
    @GET("api/analytics/overview/")
    suspend fun analyticsOverview(@Query("period") period: String = "30d"): AnalyticsOverviewEnvelope

    @GET("api/analytics/users/")
    suspend fun analyticsUsers(@Query("period") period: String = "30d"): AnalyticsUsersEnvelope

    @GET("api/analytics/content/top/")
    suspend fun analyticsContentTop(@Query("period") period: String = "30d"): AnalyticsContentEnvelope

    @GET("api/analytics/engagement/")
    suspend fun analyticsEngagement(@Query("period") period: String = "30d"): AnalyticsEngagementEnvelope

    @GET("api/analytics/behavior/")
    suspend fun analyticsBehavior(@Query("period") period: String = "30d"): AnalyticsBehaviorEnvelope

    // ---- In-app update ----
    // The APK is sideloaded, so Play never tells us about a new build; we ask.
    // Sending our own version_code lets the server decide whether the update is
    // required, so that policy can change without shipping a release.
    @GET("api/app/version/")
    suspend fun appVersion(@Query("version_code") versionCode: Int): AppReleaseDto
}
