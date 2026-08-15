export type MoviePublicationStatus = 'draft' | 'published' | 'archived'
export type MovieCatalogType = 'movie' | 'documentary' | 'short'
export type TMDBContentType = 'movie' | 'series'
export type CatalogSyncMode = 'daily' | 'trending' | 'incremental' | 'full'
export type CatalogSyncStatus = 'queued' | 'running' | 'cancelling' | 'cancelled' | 'succeeded' | 'failed'

export interface AdminGenre {
  id: number
  title: string
  slug: string
}

export interface AdminCountry {
  id: number
  name: string
  code?: string
}

export interface AdminMovie {
  id: number
  title: string
  original_title: string
  slug: string
  short_description: string
  description: string
  release_date: string | null
  release_year: number | null
  duration_minutes: number | null
  duration_text: string
  catalog_type: MovieCatalogType
  publication_status: MoviePublicationStatus
  genre_ids: number[]
  country_ids: number[]
  language: string
  original_language: string
  spoken_languages: Array<{ iso_639_1?: string; english_name?: string; name?: string }>
  age_rating: string
  imdb_id: string | null
  tmdb_id: number | null
  poster: string | null
  backdrop: string | null
  poster_path: string
  backdrop_path: string
  poster_external_url: string
  backdrop_external_url: string
  poster_url: string | null
  backdrop_url: string | null
  trailer_url: string
  trailer_external_url: string
  video_url: string
  download_key: string
  download_links: Array<{ label: string; url?: string; key?: string; quality?: string; size_label?: string; kind?: string; subtitle_type?: string }>
  quality: string
  subtitle_tracks: unknown[]
  content_format: 'live_action' | 'animation' | 'short'
  is_dubbed: boolean
  has_subtitle: boolean
  is_uncensored: boolean
  content_warnings: string[]
  imdb_rating: string | number | null
  rating_average: string | number | null
  vote_count: number
  popularity: number
  production_companies: Array<{ id?: number; name?: string }>
  crew_metadata: AdminCrewMember[]
  writers: AdminCrewMember[]
  movie_actors?: Array<{
    id: number
    role: string
    order?: number
    actor: {
      id: number
      name: string
      slug?: string
      photo?: string | null
      photo_external_url?: string | null
    }
  }>
  directors?: Array<{ id: number; name: string; slug?: string; photo?: string | null }>
  is_featured: boolean
  is_recommended: boolean
  meta_title: string
  meta_description: string
  seo_keywords: string[]
  media_status: 'missing' | 'processing' | 'ready' | 'error' | 'failed'
  rights_verified: boolean
  metadata_source: 'manual' | 'tmdb' | string
  manual_override_fields: string[]
  last_tmdb_sync_at: string | null
  created_at: string
  updated_at: string
  duplicate_warnings: string[]
}

export interface AdminCrewMember {
  tmdb_id?: number
  name?: string
  job?: string
  department?: string
  profile_path?: string | null
  profile_url?: string | null
}

export interface AdminMovieListResponse {
  count: number
  next: string | null
  previous: string | null
  results: AdminMovie[]
}

export interface AdminSeries {
  id: number
  title: string
  original_title: string
  slug: string
  short_description: string
  description: string
  start_year: number | null
  end_year: number | null
  genre_ids: number[]
  country_ids: number[]
  language: string
  original_language: string
  age_rating: string
  imdb_id: string | null
  tmdb_id: number | null
  poster: string | null
  backdrop: string | null
  poster_external_url: string
  backdrop_external_url: string
  poster_url: string | null
  backdrop_url: string | null
  trailer_url: string
  trailer_external_url: string
  download_links: Array<{ label: string; url?: string; key?: string; quality?: string; size_label?: string; kind?: string; subtitle_type?: string }>
  has_downloads: boolean
  download_qualities: string[]
  content_format: 'live_action' | 'animation' | 'short'
  is_dubbed: boolean
  has_subtitle: boolean
  is_uncensored: boolean
  content_warnings: string[]
  imdb_rating: string | number | null
  rating_average: string | number | null
  vote_count: number
  popularity: number
  series_actors?: Array<{
    id: number
    role: string
    order?: number
    actor: {
      id: number
      name: string
      slug?: string
      photo?: string | null
      photo_external_url?: string | null
    }
  }>
  directors?: Array<{ id: number; name: string; slug?: string; photo?: string | null }>
  status: 'ongoing' | 'ended' | 'upcoming' | 'cancelled' | 'on_hold'
  is_published: boolean
  is_featured: boolean
  metadata_source: 'manual' | 'tmdb' | string
  last_tmdb_sync_at: string | null
  created_at: string
  updated_at: string
  duplicate_warnings: string[]
}

export interface AdminSeriesListResponse {
  count: number
  next: string | null
  previous: string | null
  results: AdminSeries[]
}

export interface AdminSeriesFilters {
  q: string
  status: '' | 'published' | 'draft'
  source: '' | 'manual' | 'tmdb'
  genre: string
  year: string
  ordering: string
  limit: number
  offset: number
}

export interface AdminMovieFilters {
  q: string
  status: '' | MoviePublicationStatus
  source: '' | 'manual' | 'tmdb'
  type: '' | MovieCatalogType
  genre: string
  year: string
  ordering: string
  limit: number
  offset: number
}

export interface TMDBSearchMovie {
  tmdb_id: number
  title: string
  original_title: string
  overview: string
  release_date: string
  original_language: string
  vote_average: number | null
  popularity: number | null
  poster_path: string | null
  poster_url: string
  backdrop_url: string
  already_imported: boolean
  local_movie: { id: number; slug: string; title: string } | null
}

export interface TMDBSearchResponse {
  query: string
  page: number
  total_pages: number
  total_results: number
  proxy: boolean
  results: TMDBSearchMovie[]
}

export interface DuplicateMovie {
  id: number
  title: string
  slug: string
  tmdb_id: number | null
  imdb_id: string | null
  release_year: number | null
  publication_status: MoviePublicationStatus
}

export interface TMDBPreview {
  content_type: TMDBContentType
  tmdb_id: number
  title: string
  original_title: string
  overview: string
  tagline: string
  release_date: string
  runtime: number | null
  original_language: string
  genres: Array<{ id: number; name: string }>
  certification: string
  imdb_id: string
  imdb_rating: number | string | null
  imdb_votes?: string | null
  vote_average: number | null
  vote_count: number | null
  popularity: number | null
  poster_url: string
  backdrop_url: string
  trailer_youtube_key: string
  cast: Array<{ name: string; character: string; profile_url: string }>
  crew: AdminCrewMember[]
  already_imported: boolean
  local_movie: { id: number; slug: string; title: string; is_published: boolean } | null
  local_item?: { id: number; slug: string; title: string; is_published: boolean } | null
  duplicates: DuplicateMovie[]
  season_count?: number
  episode_count?: number
  status?: string
}

export interface ImportedSeries {
  id: number
  title: string
  slug: string
  tmdb_id: number
  is_published: boolean
  poster_url: string | null
  season_count: number
}

export interface TMDBImportResponse {
  content_type?: TMDBContentType
  dry_run: boolean
  created: boolean
  published: boolean
  skipped_manual_fields: string[]
  publication_blockers?: string[]
  movie?: AdminMovie
  series?: ImportedSeries
  preview?: { title: string; slug: string; overview: string; release_date?: string; runtime?: number }
}

export interface CatalogSyncRun {
  id: number
  provider: 'tmdb'
  mode: CatalogSyncMode
  status: CatalogSyncStatus
  phase: string
  parameters: Record<string, string | number | boolean>
  started_at: string
  updated_at: string
  heartbeat_at: string | null
  cancel_requested_at: string | null
  finished_at: string | null
  discovered_count: number
  total_count: number
  processed_count: number
  created_count: number
  updated_count: number
  published_count: number
  skipped_count: number
  error_count: number
  current_tmdb_id: number | null
  progress_percent: number
  is_active: boolean
  can_cancel: boolean
  errors: Array<{ tmdb_id?: number; error: string }>
  requested_by: { id: number; username: string } | null
}

export interface CatalogSyncRunListResponse {
  results: CatalogSyncRun[]
}

export interface CatalogImporterSettings {
  language: string
  fallback_language: string
  region: string
  daily_lookback_days: number
  daily_lookahead_days: number
  daily_max_pages: number
  trending_window: 'day' | 'week'
  trending_max_pages: number
  import_people_images: boolean
  cast_import_limit: number
  fetch_imdb_ratings: boolean
  feature_trending: boolean
  auto_publish: boolean
  automation_enabled: boolean
  automation_mode: 'daily' | 'trending'
  automation_interval_hours: number
  tmdb_configured: boolean
  imdb_rating_provider_configured: boolean
  updated_at: string | null
}

export type ProviderAuthType =
  | 'none'
  | 'api_key'
  | 'bearer_token'
  | 'username_password'
  | 'cookie_session'
  | 'feed'

export type ProviderImportJobStatus =
  | 'queued'
  | 'validating'
  | 'searching'
  | 'awaiting_review'
  | 'running'
  | 'transferring'
  | 'cancel_requested'
  | 'completed'
  | 'partially_completed'
  | 'blocked'
  | 'failed'
  | 'cancelled'

export interface ProviderSecretFlags {
  api_token_configured: boolean
  cookie_configured: boolean
  username_configured: boolean
  password_configured: boolean
  credentials_configured?: boolean
}

export interface ProviderSource {
  id: number
  name: string
  slug: string
  provider_type: string
  base_url: string
  auth_type: ProviderAuthType
  is_active: boolean
  rate_limit_per_minute: number
  timeout_seconds: number
  verify_ssl: boolean
  config: Record<string, unknown>
  login_url: string
  movies_url: string
  series_url: string
  secrets: ProviderSecretFlags
  credential_status: string
  last_validated_at: string | null
  last_validation_message: string
  created_at: string
  updated_at: string
}

export interface ProviderValidateResult {
  ok: boolean
  message: string
  requires_interactive_verification?: boolean
  auth_type?: string
  sanitized_details?: Record<string, unknown>
  secrets?: ProviderSecretFlags
  credential_status?: string
  code?: string
}

export interface ProviderImportJob {
  id: string
  provider: number
  provider_slug: string
  provider_name: string
  trigger?: string
  target_movie?: number | null
  target_series?: number | null
  content_type: 'movies' | 'series' | 'both' | 'movie'
  status: ProviderImportJobStatus
  mode: 'discover_only' | 'import_missing_files' | 'import_selected' | 'import_missing' | 'sync_all'
  params: Record<string, unknown>
  total_items: number
  processed_items: number
  matched_items: number
  imported_files: number
  skipped_items: number
  failed_items: number
  current_item_label: string
  cancel_requested: boolean
  error_message: string
  sanitized_error_code?: string
  is_active: boolean
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

export interface ProviderImportItem {
  id: number
  provider_item_id: string
  content_type: 'movie' | 'series' | 'episode'
  title: string
  original_title: string
  year: number | null
  season_number: number | null
  episode_number: number | null
  tmdb_id: number | null
  imdb_id: string
  match_score?: number
  match_reasons?: string[]
  selected?: boolean
  manually_approved?: boolean
  matched_movie_id: number | null
  matched_series_id: number | null
  matched_episode_id: number | null
  archive_asset_id: string | null
  selected_candidate: Record<string, unknown>
  status: string
  status_message: string
  created_at: string
  updated_at: string
}

export interface ProviderImportLog {
  id: number
  level: 'debug' | 'info' | 'warning' | 'error'
  event_code?: string
  message: string
  context: Record<string, unknown>
  created_at: string
}

export interface AdminUser {
  id: number
  email: string
  username: string
  first_name: string
  last_name: string
  phone: string | null
  is_active: boolean
  is_staff: boolean
  is_superuser: boolean
  is_verified: boolean
  date_joined: string
  last_login: string | null
  created_at?: string
  updated_at?: string
  failed_login_attempts: number
  locked_until: string | null
}

export interface AdminUserFilters {
  q?: string
  role?: '' | 'staff' | 'user'
  active?: '' | 'true' | 'false'
  limit?: number
  offset?: number
}

export interface AdminUserListResponse {
  count: number
  next: string | null
  previous: string | null
  results: AdminUser[]
}

export interface AdminReviewContent {
  title: string
  slug: string
  poster: string | null
}

export interface AdminReviewItem {
  id: number
  username: string
  content_type: 'movie' | 'series'
  object_id: number
  score: string
  review: string
  is_spoiler: boolean
  is_hidden: boolean
  created_at: string
  updated_at: string
  content: AdminReviewContent | null
}

export interface AdminReviewListResponse {
  count: number
  next: string | null
  previous: string | null
  results: AdminReviewItem[]
}

export interface AdminSupportInboxResponse {
  count: number
  next: string | null
  previous: string | null
  results: import('./engagement').SupportTicketListItem[]
  unread_count: number
  open_count: number
}

export interface AdminDashboardComparison {
  current: number
  previous: number
  change_percent: number | null
}

export interface AdminDashboardCatalogGroup {
  total: number
  published: number
  draft: number
  recorded_views: number
  archived?: number
  featured?: number
  media_ready?: number
  media_missing?: number
  media_error?: number
}

export interface AdminDashboardTrendPoint {
  date: string
  tracked_views: number
  playback_events: number
  completed_views: number
  active_users: number
  recorded_audience: number
  new_users: number
}

export interface AdminDashboardTopContent {
  content_type: 'movie' | 'series'
  object_id: number
  title: string
  slug: string
  is_published: boolean
  activity: number
  tracked_views: number
  playback_events: number
  completed_views: number
  view_count?: number
}

export interface AdminDashboardTopSearch {
  query: string
  count: number
  zero_result_count: number
}

export interface AdminDashboardFunnelRate {
  current: number | null
  previous: number | null
}

export interface AdminDashboardHealthAlert {
  code: string
  severity: 'info' | 'warning' | 'critical'
  count: number
  message: string
  href: string
}

export interface AdminDashboardResponse {
  generated_at: string
  period: {
    days: 7 | 30 | 90
    start: string
    end: string
    previous_start: string
    previous_end: string
    timezone: string
    current_day_is_partial: boolean
  }
  summary: {
    total_users: number
    new_users: AdminDashboardComparison
    active_users: AdminDashboardComparison
    recorded_audience: AdminDashboardComparison
    tracked_views: AdminDashboardComparison
    playback_events: AdminDashboardComparison
    completed_views: AdminDashboardComparison
    download_clicks?: AdminDashboardComparison
    searches?: AdminDashboardComparison
  }
  funnel: {
    view_to_play: AdminDashboardFunnelRate
    play_to_complete: AdminDashboardFunnelRate
    view_to_complete: AdminDashboardFunnelRate
    stages: Array<{ key: string, label: string, count: number }>
  }
  users: {
    total: number
    active: number
    verified: number
    staff: number
  }
  catalog: {
    movies: AdminDashboardCatalogGroup
    series: AdminDashboardCatalogGroup
    episodes: AdminDashboardCatalogGroup
  }
  health: {
    movies_missing_poster: number
    movies_media_not_ready: number
    movies_draft: number
    series_draft: number
    movies_rights_pending: number
    alert_count: number
    alerts: AdminDashboardHealthAlert[]
  }
  engagement: {
    ratings_total: number
    ratings_in_period: number
    average_rating: number | null
    likes_total: number
    likes_in_period: number
    watchlist_total: number
    watchlist_in_period: number
    favorites_total?: number
    download_clicks_in_period?: number
    trailer_watches_in_period?: number
  }
  trend: AdminDashboardTrendPoint[]
  hourly: Array<{ hour: number, count: number }>
  actions: Array<{ action: string, label: string, count: number }>
  devices: Array<{ device: string, count: number }>
  top_content: AdminDashboardTopContent[]
  top_searches: AdminDashboardTopSearch[]
  top_genres: Array<{ query: string, count: number }>
  watchparty: {
    available: boolean
    total: number
    active: number
    created_in_period: number
    ended_in_period: number
  }
  tracking: {
    events_total: number
    events_in_period: number
    identified_events_in_period: number
    anonymous_events_in_period: number
    identified_users_in_period: number
    anonymous_sessions_in_period: number
    latest_event_at: string | null
    source: 'server_database'
    scope: 'recorded_events_only'
    consent_required: boolean
  }
}
