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
