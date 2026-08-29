import type { AgeRating, ContentType } from './catalog'

export const analyticsEventTypes = [
  'search',
  'empty_search',
  'view_movie',
  'view_series',
  'play_trailer',
  'start_watch',
  'continue_watch',
  'pause_watch',
  'watch_progress',
  'complete_watch',
  'add_watchlist',
  'remove_watchlist',
  'like',
  'remove_like',
  'dislike',
  'rate',
  'recommendation_click',
  'click_genre',
  'click_cast',
  'click_director',
  'filter_apply',
  'sort_apply',
] as const

export type EventType = typeof analyticsEventTypes[number]
export type PersonalizationConsent = 'unset' | 'enabled' | 'disabled'
export type PlaybackPreference = 'any' | 'original' | 'subtitle' | 'dubbed'
export type ContentSensitivityPreference = 'any' | 'standard' | 'reduced'

export interface AnalyticsEventInput {
  event_id?: string
  event_type: EventType
  title_id?: number
  title_slug?: string
  content_type?: ContentType
  query?: string
  genre?: string
  progress_percent?: number
  rating?: number
  result_count?: number
  filter_name?: string
  filter_value?: string
  sort?: string
  source_page?: string
  timestamp?: string
  user_id?: number
  is_empty_query?: boolean
}

export interface AnalyticsEvent extends AnalyticsEventInput {
  event_id: string
  source_page: string
  timestamp: string
  anonymous_session_id?: string
}

/** @deprecated Use EventType. Kept temporarily for source compatibility. */
export type BehaviorEventType = EventType
/** @deprecated Use AnalyticsEventInput. */
export type BehaviorEventInput = AnalyticsEventInput
/** @deprecated Use AnalyticsEvent. */
export type BehaviorEvent = AnalyticsEvent

export interface RecommendationPreferences {
  favorite_genres: string[]
  disliked_genres: string[]
  preferred_countries: string[]
  preferred_languages: string[]
  playback_preference: PlaybackPreference
  content_sensitivity: ContentSensitivityPreference
  preferred_age_ratings: AgeRating[]
}

export interface AnalyticsSyncResult {
  sent: number
  remaining: number
}

export interface AggregateDemandSignal {
  source: 'search_console_aggregate' | 'site_search_aggregate' | 'editorial_trend'
  query: string
  genre_slugs: string[]
  score: number
  impressions?: number
  clicks?: number
  period_start: string
  period_end: string
  site_scope_only: true
}

/** Staff analytics dashboard API contracts (`/api/analytics/*`). */

export type AnalyticsPeriodKey = '7d' | '30d' | '90d'

export interface AnalyticsEnvelope<T> {
  data: T
  period: {
    days: number
    label: string
    key: string
    start?: string
    end?: string
    timezone?: string
  }
  generated_at: string
  source?: string
}

export interface AnalyticsKpi {
  id: string
  label: string
  value: number | null
  delta_percent: number | null
  format?: 'number' | 'hours' | 'currency' | 'percent'
  hint?: string
}

export interface AnalyticsRealtime {
  online_users: number
  online_guests?: number
  online_total?: number
  live_watch_sessions: number
  playing_sessions?: number
  active_watch_rooms?: number
  window_minutes: number
  window_seconds?: number
  sources?: {
    presence?: number
    presence_available?: boolean
    activity_events?: number
    recent_logins?: number
    watchparty?: number
  }
}

export interface AnalyticsOverviewData {
  kpis: AnalyticsKpi[]
  realtime: AnalyticsRealtime
  catalog: {
    movies: number
    series: number
    episodes?: number
    total: number
    dubbed?: number
    with_subtitle?: number
  }
  database?: {
    activity_events: number
    likes: number
    ratings: number
    watchlist: number
  }
}

export interface AnalyticsSeriesPoint {
  date: string
  label: string
  value: number
}

export interface AnalyticsNamedValue {
  id?: string
  label: string
  value: number
  weekday?: number
}

export interface AnalyticsActiveUserRow {
  user_id: number
  username: string
  watch_time_minutes: number
  watch_time_hours: number
  events: number
  last_seen: string | null
}

export interface AnalyticsUsersData {
  registrations: {
    granularity: 'daily' | 'weekly' | 'monthly'
    points: AnalyticsSeriesPoint[]
  }
  active_by_weekday: AnalyticsNamedValue[]
  action_breakdown?: AnalyticsNamedValue[]
  devices: Array<{ id: string, label: string, value: number }>
  top_active_users: AnalyticsActiveUserRow[]
  totals?: {
    users: number
    active_in_period: number
    new_in_period: number
  }
}

export interface AnalyticsTopContentRow {
  id: number
  title: string
  slug: string
  content_type: 'movie' | 'series' | string
  activity: number
  tracked_views: number
  playback_events: number
  completed_views: number
  view_count: number
}

export interface AnalyticsHeatmapCell {
  weekday: number
  weekday_label: string
  hour: number
  value: number
}

export interface AnalyticsContentData {
  top_watched: AnalyticsTopContentRow[]
  sessions_over_time: AnalyticsSeriesPoint[]
  heatmap: {
    weekdays: Array<{ id: number, label: string }>
    hours: number[]
    cells: AnalyticsHeatmapCell[]
  }
  recently_added: Array<{
    id: number
    title: string
    slug: string
    content_type: string
    view_count: number
    created_at: string | null
  }>
  catalog?: {
    movies_published: number
    series_published: number
    episodes_published: number
  }
}

export interface AnalyticsEngagementData {
  average_session_minutes: number
  completion_rate: number | null
  plays: number
  completes: number
  views: number
  watch_rooms?: number
  likes_total?: number
  likes_in_period?: number
  ratings_total?: number
  ratings_in_period?: number
  average_rating?: number | null
  watchlist_total?: number
  watchlist_in_period?: number
  completion_by_content: Array<{
    id: number
    title: string
    content_type: string
    playback_events: number
    completed_views: number
    completion_rate: number | null
  }>
  search_terms: Array<{
    term: string
    count: number
    zero_result_count: number
  }>
  realtime: AnalyticsRealtime
}
