package com.revayato.app.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Staff analytics DTOs mirroring the backend `api/analytics/` envelopes.
 * Every value here is real DB-backed data (no fabricated estimates): watch time
 * comes from recorded progress × catalog runtime, activity from real events.
 */

@Serializable
data class AnalyticsOverviewEnvelope(
    val data: AnalyticsOverviewDto = AnalyticsOverviewDto(),
    @SerialName("generated_at") val generatedAt: String? = null,
)

@Serializable
data class AnalyticsOverviewDto(
    val kpis: List<AnalyticsKpiDto> = emptyList(),
    val realtime: AnalyticsRealtimeDto = AnalyticsRealtimeDto(),
    val catalog: AnalyticsCatalogDto = AnalyticsCatalogDto(),
    val database: AnalyticsDatabaseDto = AnalyticsDatabaseDto(),
)

@Serializable
data class AnalyticsKpiDto(
    val id: String = "",
    val label: String = "",
    val value: Double = 0.0,
    @SerialName("delta_percent") val deltaPercent: Double? = null,
    val format: String = "number",
    val hint: String? = null,
)

@Serializable
data class AnalyticsRealtimeDto(
    @SerialName("online_users") val onlineUsers: Int = 0,
    @SerialName("online_guests") val onlineGuests: Int = 0,
    @SerialName("online_total") val onlineTotal: Int = 0,
    @SerialName("live_watch_sessions") val liveWatchSessions: Int = 0,
    @SerialName("playing_sessions") val playingSessions: Int = 0,
    @SerialName("active_watch_rooms") val activeWatchRooms: Int = 0,
    @SerialName("window_minutes") val windowMinutes: Int = 0,
)

@Serializable
data class AnalyticsCatalogDto(
    val movies: Int = 0,
    val series: Int = 0,
    val episodes: Int = 0,
    val total: Int = 0,
    val dubbed: Int = 0,
    @SerialName("with_subtitle") val withSubtitle: Int = 0,
)

@Serializable
data class AnalyticsDatabaseDto(
    @SerialName("activity_events") val activityEvents: Int = 0,
    val likes: Int = 0,
    val ratings: Int = 0,
    val watchlist: Int = 0,
)

@Serializable
data class AnalyticsUsersEnvelope(
    val data: AnalyticsUsersDto = AnalyticsUsersDto(),
    @SerialName("generated_at") val generatedAt: String? = null,
)

@Serializable
data class AnalyticsUsersDto(
    val registrations: AnalyticsRegistrationsDto = AnalyticsRegistrationsDto(),
    @SerialName("active_by_weekday") val activeByWeekday: List<AnalyticsNamedValueDto> = emptyList(),
    @SerialName("action_breakdown") val actionBreakdown: List<AnalyticsNamedValueDto> = emptyList(),
    @SerialName("top_active_users") val topActiveUsers: List<AnalyticsActiveUserDto> = emptyList(),
    val totals: AnalyticsUserTotalsDto = AnalyticsUserTotalsDto(),
)

@Serializable
data class AnalyticsRegistrationsDto(
    val granularity: String = "daily",
    val points: List<AnalyticsSeriesPointDto> = emptyList(),
)

@Serializable
data class AnalyticsSeriesPointDto(
    val date: String = "",
    val label: String = "",
    val value: Int = 0,
)

@Serializable
data class AnalyticsNamedValueDto(
    val id: String? = null,
    val label: String = "",
    val value: Int = 0,
)

@Serializable
data class AnalyticsActiveUserDto(
    @SerialName("user_id") val userId: Int = 0,
    val username: String = "",
    @SerialName("watch_time_minutes") val watchTimeMinutes: Double = 0.0,
    @SerialName("watch_time_hours") val watchTimeHours: Double = 0.0,
    val events: Int = 0,
    val plays: Int = 0,
    val completes: Int = 0,
    @SerialName("rooms_hosted") val roomsHosted: Int = 0,
    val likes: Int = 0,
    val ratings: Int = 0,
    val interactions: Int = 0,
    @SerialName("last_seen") val lastSeen: String? = null,
)

// ---- Content & engagement (api/analytics/content/top/ and engagement/) ----

@Serializable
data class AnalyticsContentEnvelope(
    val data: AnalyticsContentDto = AnalyticsContentDto(),
    @SerialName("generated_at") val generatedAt: String? = null,
)

@Serializable
data class AnalyticsContentDto(
    @SerialName("top_watched") val topWatched: List<AnalyticsTopContentDto> = emptyList(),
    @SerialName("recently_added") val recentlyAdded: List<AnalyticsRecentContentDto> = emptyList(),
    val catalog: AnalyticsPublishedCatalogDto = AnalyticsPublishedCatalogDto(),
)

@Serializable
data class AnalyticsTopContentDto(
    val id: Int = 0,
    val title: String = "",
    val slug: String? = null,
    @SerialName("content_type") val contentType: String = "movie",
    val activity: Int = 0,
    @SerialName("view_count") val viewCount: Int = 0,
    @SerialName("poster_url") val posterUrl: String? = null,
)

@Serializable
data class AnalyticsRecentContentDto(
    val id: Int = 0,
    val title: String = "",
    val slug: String? = null,
    @SerialName("content_type") val contentType: String = "movie",
    @SerialName("view_count") val viewCount: Int = 0,
)

@Serializable
data class AnalyticsPublishedCatalogDto(
    @SerialName("movies_published") val moviesPublished: Int = 0,
    @SerialName("series_published") val seriesPublished: Int = 0,
    @SerialName("episodes_published") val episodesPublished: Int = 0,
)

@Serializable
data class AnalyticsEngagementEnvelope(
    val data: AnalyticsEngagementDto = AnalyticsEngagementDto(),
    @SerialName("generated_at") val generatedAt: String? = null,
)

@Serializable
data class AnalyticsEngagementDto(
    @SerialName("average_session_minutes") val averageSessionMinutes: Double = 0.0,
    @SerialName("completion_rate") val completionRate: Double? = null,
    val plays: Int = 0,
    val completes: Int = 0,
    val views: Int = 0,
    @SerialName("watch_rooms") val watchRooms: Int = 0,
    @SerialName("likes_total") val likesTotal: Int = 0,
    @SerialName("likes_in_period") val likesInPeriod: Int = 0,
    @SerialName("ratings_total") val ratingsTotal: Int = 0,
    @SerialName("ratings_in_period") val ratingsInPeriod: Int = 0,
    @SerialName("average_rating") val averageRating: Double? = null,
    @SerialName("watchlist_total") val watchlistTotal: Int = 0,
    @SerialName("watchlist_in_period") val watchlistInPeriod: Int = 0,
    @SerialName("search_terms") val searchTerms: List<AnalyticsSearchTermDto> = emptyList(),
)

@Serializable
data class AnalyticsSearchTermDto(
    val term: String = "",
    val count: Int = 0,
    @SerialName("zero_result_count") val zeroResultCount: Int = 0,
)

// ---- Behaviour analytics (api/analytics/behavior/) ----

@Serializable
data class AnalyticsBehaviorEnvelope(
    val data: AnalyticsBehaviorDto = AnalyticsBehaviorDto(),
    @SerialName("generated_at") val generatedAt: String? = null,
)

@Serializable
data class AnalyticsBehaviorDto(
    val summary: AnalyticsBehaviorSummaryDto = AnalyticsBehaviorSummaryDto(),
    val funnel: AnalyticsFunnelDto = AnalyticsFunnelDto(),
    val discovery: AnalyticsDiscoveryDto = AnalyticsDiscoveryDto(),
    val sessions: AnalyticsSessionDepthDto = AnalyticsSessionDepthDto(),
    @SerialName("action_mix") val actionMix: List<AnalyticsNamedValueDto> = emptyList(),
    @SerialName("content_interest") val contentInterest: List<AnalyticsNamedValueDto> = emptyList(),
    val retention: AnalyticsRetentionDto = AnalyticsRetentionDto(),
)

@Serializable
data class AnalyticsBehaviorSummaryDto(
    @SerialName("tracked_events") val trackedEvents: Int = 0,
    @SerialName("active_users") val activeUsers: Int = 0,
    @SerialName("anonymous_sessions") val anonymousSessions: Int = 0,
    @SerialName("events_per_active") val eventsPerActive: Double? = null,
)

@Serializable
data class AnalyticsFunnelStageDto(
    val id: String = "",
    val label: String = "",
    val value: Int = 0,
    @SerialName("pct_of_top") val pctOfTop: Double? = null,
    @SerialName("step_conversion") val stepConversion: Double? = null,
)

@Serializable
data class AnalyticsFunnelDto(
    val stages: List<AnalyticsFunnelStageDto> = emptyList(),
    @SerialName("play_through_rate") val playThroughRate: Double? = null,
    @SerialName("completion_rate") val completionRate: Double? = null,
)

@Serializable
data class AnalyticsDiscoveryDto(
    val searches: Int = 0,
    @SerialName("unique_terms") val uniqueTerms: Int = 0,
    @SerialName("result_clicks") val resultClicks: Int = 0,
    @SerialName("click_through_rate") val clickThroughRate: Double? = null,
    @SerialName("zero_result_searches") val zeroResultSearches: Int = 0,
    @SerialName("zero_result_rate") val zeroResultRate: Double? = null,
)

@Serializable
data class AnalyticsSessionDepthDto(
    val sessions: Int = 0,
    @SerialName("avg_events_per_session") val avgEventsPerSession: Double = 0.0,
    @SerialName("median_events_per_session") val medianEventsPerSession: Int = 0,
    @SerialName("avg_duration_minutes") val avgDurationMinutes: Double = 0.0,
    @SerialName("bounce_rate") val bounceRate: Double? = null,
    @SerialName("depth_distribution") val depthDistribution: List<AnalyticsNamedValueDto> = emptyList(),
)

@Serializable
data class AnalyticsRetentionDto(
    val dau: Int = 0,
    val wau: Int = 0,
    val mau: Int = 0,
    val stickiness: Double? = null,
    @SerialName("wow_retention_rate") val wowRetentionRate: Double? = null,
    @SerialName("wow_prior_cohort") val wowPriorCohort: Int = 0,
    @SerialName("wow_retained") val wowRetained: Int = 0,
)

@Serializable
data class AnalyticsUserTotalsDto(
    val users: Int = 0,
    @SerialName("active_in_period") val activeInPeriod: Int = 0,
    @SerialName("new_in_period") val newInPeriod: Int = 0,
    @SerialName("new_today") val newToday: Int = 0,
    @SerialName("returning_in_period") val returningInPeriod: Int = 0,
    val dau: Int = 0,
    val wau: Int = 0,
    val mau: Int = 0,
    val active: Int = 0,
    val inactive: Int = 0,
    val verified: Int = 0,
    val unverified: Int = 0,
    val staff: Int = 0,
    @SerialName("verified_rate") val verifiedRate: Double = 0.0,
    val stickiness: Double = 0.0,
)
