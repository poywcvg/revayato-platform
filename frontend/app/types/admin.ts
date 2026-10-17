import type { RepairRun } from '~/utils/stagedRebuild'

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
  featured_order: number
  slider_platform: 'all' | 'web' | 'app'
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
  featured_order: number
  slider_platform: 'all' | 'web' | 'app'
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

export type SliderPlatform = 'all' | 'web' | 'app'
export type SliderContentType = 'movie' | 'series'

export interface AdminSliderItem {
  id: number
  content_type: SliderContentType
  title: string
  original_title?: string
  slug: string
  poster_url: string | null
  backdrop_url: string | null
  release_year?: number | null
  start_year?: number | null
  is_published: boolean
  publication_status?: string
  is_featured: boolean
  featured_order: number
  slider_order: number
  slider_platform: SliderPlatform
  updated_at: string
}

export interface AdminSliderListResponse {
  platform: string
  count: number
  results: AdminSliderItem[]
}

export interface AdminSliderReorderItem {
  content_type: SliderContentType
  id: number
  is_featured?: boolean
  featured_order?: number
  slider_platform?: SliderPlatform
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
  /** The catalog row a per-title crawl targets, when it is not a broad sweep. */
  object_id?: number | null
  job_type?: string
  content_type: 'movies' | 'series' | 'both' | 'movie' | 'serie'
  status: ProviderImportJobStatus
  mode: 'discover_only' | 'import_missing_files' | 'import_selected' | 'import_missing' | 'sync_all'
  params: Record<string, unknown>
  total_items: number
  processed_items: number
  matched_items: number
  imported_files: number
  /** Older alias for `imported_files`; some responses still carry only this. */
  imported_items?: number
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

export interface AdminUserActivityStats {
  downloads: number
  plays: number
  completes: number
  searches: number
  total_events: number
  likes: number
  ratings: number
  watchlist: number
  last_seen: string | null
  days_since_joined: number | null
}

export interface AdminUserRecentActivity {
  action: string
  content_type: string
  object_id: number | null
  title: string
  slug: string
  created_at: string | null
}

export interface AdminUserDetail extends AdminUser {
  stats: AdminUserActivityStats
  recent_activity: AdminUserRecentActivity[]
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
  summary: {
    total: number
    active: number
    inactive: number
    staff: number
    verified: number
  }
}

export interface AdminReviewContent {
  id: number
  content_type: 'movie' | 'series'
  title: string
  slug: string
  poster: string | null
  site_rating: number | null
  release_year?: number | null
  start_year?: number | null
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
  admin_reply: string
  admin_reply_at: string | null
  admin_reply_by_name: string
  is_featured: boolean
  featured_at: string | null
  created_at: string
  updated_at: string
  content: AdminReviewContent | null
}

export interface AdminReviewListResponse {
  count: number
  next: string | null
  previous: string | null
  results: AdminReviewItem[]
  counts: AdminReviewCounts
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
  app_install_funnel?: {
    prompts: number
    clicks: number
    dismissals: number
    click_through_rate: number | null
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

// --------------------------------------------------------------------------- //
//  Community: review moderation + support inbox (admin↔user interaction)
//  (AdminReviewContent / AdminReviewItem / AdminReviewListResponse and
//  AdminSupportInboxResponse are declared above and extended in-place.)
// --------------------------------------------------------------------------- //
export interface AdminReviewCounts {
  total: number
  unanswered: number
  answered: number
  featured: number
  hidden: number
}

export type AdminSupportTicket = import('./engagement').SupportTicket & {
  staff_note: string
  user_email: string
}

export interface AdminInteractionOverview {
  reviews: AdminReviewCounts
  support: { unread: number, open: number, total: number }
}

/* --- staff-driven import ------------------------------------------------- */

/** One TMDB hit, from `/admin/tmdb/search/?kind=all`. */
export interface TmdbSearchRow {
  tmdb_id: number
  /** Which TMDB index this came from. The import endpoints differ per kind. */
  kind: 'movie' | 'series'
  title: string
  original_title: string | null
  overview: string
  /** `release_date` for films, `first_air_date` for shows — normalized server-side. */
  release_date: string
  original_language: string
  vote_average: number | null
  popularity: number | null
  poster_url: string | null
  backdrop_url: string | null
  already_imported: boolean
  local_item: { id: number, slug: string, title: string } | null
}

export interface TmdbSearchResponse {
  query: string
  kind: 'movie' | 'series' | 'all'
  page: number
  total_pages: number
  total_results: number
  proxy: boolean
  results: TmdbSearchRow[]
}

/** TMDB detail used to confirm a title before it is written to the catalog. */
export interface TmdbPreview {
  tmdb_id: number
  title?: string
  name?: string
  original_title?: string
  overview?: string
  release_date?: string
  first_air_date?: string
  runtime?: number | null
  number_of_seasons?: number | null
  number_of_episodes?: number | null
  genres?: { id?: number, name?: string }[] | string[]
  vote_average?: number | null
  imdb_id?: string | null
  imdb_rating?: number | null
  poster_url?: string | null
  backdrop_url?: string | null
  already_imported?: boolean
  local_movie?: { id: number, slug: string, title: string, is_published?: boolean } | null
  local_item?: { id: number, slug: string, title: string, is_published?: boolean } | null
  duplicates?: unknown[]
}

/**
 * Alias of {@link ProviderImportJobStatus}, kept because the import console and
 * the operations page both spell it this way. A *second* `ProviderImportJob`
 * interface used to live here; TypeScript merged it with the one above instead
 * of rejecting it, which turned every field whose optionality differed into an
 * error somewhere else entirely.
 */
export type ProviderJobStatus = ProviderImportJobStatus

// ---------------------------------------------------------------------------
// Operations desk — /api/admin/catalog/… and /api/admin/ops/…
//
// Mirrors `backend/apps/catalog/admin_ops.py`. The desk is one payload on
// purpose: links, the last media verdict, the open gaps and the viewer reports
// have to agree on screen, and they only do when they arrive together.
// ---------------------------------------------------------------------------

export type LinkHealth = 'live' | 'dead' | 'unknown' | 'unchecked'
export type AdminContentKind = 'movie' | 'series'

export interface DeskLink {
  index: number
  url: string
  label: string
  quality: string
  size_label: string
  kind: string
  source: string
  season_number: number | null
  episode_number: number | null
  health: LinkHealth
  reason: string
  browser_safe: boolean | null
  container: string
  video_codec: string
  codec_family: string
  integrity: { category: string, contaminated: boolean }
}

export interface DeskSubtitle {
  index: number
  src: string
  label: string
  lang: string
  kind: string
  offset_seconds?: number | null
}

export interface DeskCheck {
  status: string
  playable: boolean
  downloadable: boolean
  reason: string
  checked_urls: number
  dead_urls: number
  attempts: number
  checked_at: string | null
  tech: Record<string, unknown> | null
}

export interface DeskGap {
  id: number
  status: string
  reason: string
  episode_id: number
  report_count: number
  last_result: string
  updated_at: string | null
}

export interface DeskReport {
  id: number
  problem_type: string
  problem_label: string
  status: string
  status_label: string
  episode_id: number
  season_number: number | null
  episode_number: number | null
  report_count: number
  attempts: number
  remediation_action: string
  last_result: string
  detail: string
  created_at: string
  updated_at: string
  target?: HealthTarget
}

export interface DeskAudit {
  id: number
  action: string
  action_label: string
  movie_id: number | null
  movie_title?: string
  actor: string
  changed_fields: string[]
  details: Record<string, unknown>
  created_at: string
}

export interface DeskEpisode {
  id: number
  season_number: number
  episode_number: number
  title: string
  is_published: boolean
  has_stream: boolean
  playback_mode: string
  link_count: number
  dead_links: number
  subtitle_count: number
  check: DeskCheck | null
}

export interface DeskJob {
  id: string
  status: ProviderJobStatus
  mode: string
  trigger: string
  error_message: string
  created_at: string
  finished_at: string | null
}

export interface DeskDiagnosis {
  unplayable: boolean
  safe: number
  unsafe: number
  reason: string
  containers: string[]
  codecs: string[]
}

export interface MediaDesk {
  kind: AdminContentKind
  id: number
  title: string
  slug: string
  year: number | null
  is_published: boolean
  publication_status: string | null
  tmdb_id: number | null
  imdb_id: string | null
  playback_mode: string
  playback_checked_at: string | null
  links: DeskLink[]
  subtitles: DeskSubtitle[]
  check: DeskCheck | null
  diagnosis: DeskDiagnosis
  metadata_gaps: string[]
  publish_blockers: string[]
  source_gap: DeskGap | null
  subtitle_gap: DeskGap | null
  reports: DeskReport[]
  jobs: DeskJob[]
  episodes?: DeskEpisode[]
  audits: DeskAudit[]
  completion?: DeskCompletion | null
  /** The latest «بازسازی کامل» backup that can still be put back. */
  rebuild_backup?: { id: number, created_at: string, links: number } | null
}

export type CompletionStepKey =
  | 'backup' | 'metadata' | 'titles' | 'sources' | 'episodes' | 'sizes' | 'verify' | 'publish' | 'subtitles'
  | 'stage' | 'test' | 'apply' | 'problems' | 'playback'

export interface DeskCompletionStep {
  key: CompletionStepKey
  status: 'pending' | 'running' | 'ok' | 'skipped' | 'empty' | 'warn' | 'blocked' | 'error'
  detail: string
  links_before?: number
  links_after?: number
  /** Rebuild only: links the providers answered with, and stale ones removed. */
  fresh?: number
  removed?: number
  unpublished?: number
  blockers?: string[]
  /** Staged rebuild only: what the shadow crawl found and how its probes went. */
  staged_links?: number
  live?: number
  dead?: number
  unknown?: number
  verdict?: string
  added?: number
  /** «رفع مشکل‌ها»: health-page problem codes after the run. */
  fixed?: string[]
  queued?: string[]
  left?: string[]
}

/** «جستجوی دوباره و تکمیل» / «بازسازی کامل»: one background run of every importer step. */
export interface DeskCompletion {
  state: 'queued' | 'running' | 'done' | 'failed'
  mode?: 'complete' | 'rebuild' | 'staged'
  publish: boolean
  started_at: string
  finished_at: string | null
  steps: DeskCompletionStep[]
  failed_steps?: string[]
  links?: number
  is_published?: boolean
  already_running?: boolean
  error?: string
  /** Staged rebuild only: whether the tested set replaced the title's links, and if not why. */
  verdict?: 'applied' | 'rejected'
  verdict_reason?: string
}

export type DeskAction =
  | 'verify' | 'remove_link' | 'add_link' | 'prune_dead' | 'strip_contaminated'
  | 'complete' | 'recrawl' | 'rebuild' | 'rebuild_staged' | 'rebuild_undo' | 'refresh_subtitles' | 'remove_subtitle' | 'publish' | 'unpublish'
  | 'archive' | 'sync_tmdb' | 'resolve_gaps'

export interface DeskActionResponse {
  action: DeskAction
  result: Record<string, unknown>
  desk: MediaDesk
}

export interface BulkResultRow {
  id: number
  title: string
  ok: boolean
  error: string | null
  /** Publish-gate reasons when ``error`` is ``publish_blocked``. */
  blockers?: string[] | null
  result: Record<string, unknown> | null
}

export interface BulkResponse {
  action: string
  kind: AdminContentKind
  requested: number
  succeeded: number
  failed: number
  results: BulkResultRow[]
}

export type HealthQueue =
  | 'source_gaps' | 'subtitle_gaps' | 'failed_checks'
  | 'reports' | 'unverified' | 'incomplete' | 'approx_ratings' | 'sourceless_drafts'

export type HealthCounts = Record<HealthQueue, number>

export interface HealthTarget {
  id: number
  kind: AdminContentKind
  title: string
  slug: string
  is_published?: boolean
}

/** One queue row. Fields beyond `target` differ per queue; all are optional. */
export interface HealthRow {
  id?: number
  target: HealthTarget
  episode_id?: number
  status?: string
  reason?: string
  report_count?: number
  last_result?: string
  checked_urls?: number
  dead_urls?: number
  attempts?: number
  checked_at?: string | null
  updated_at?: string
  link_count?: number
  gaps?: string[]
  problem_label?: string
  status_label?: string
  detail?: string
  /** The last repair run on this title (any mode), so the queue shows what was already tried. */
  repair?: RepairRun
}

export interface HealthResponse {
  queue: HealthQueue
  counts: HealthCounts
  results: HealthRow[]
  limit: number
  offset: number
}

export interface OpsQueueLane { queue: string, label: string, depth: number | null }

export interface OpsWorkers {
  reachable: boolean
  workers: { name: string, active_tasks: number, queues: string[] }[]
}

export interface OpsJobRow {
  id: string
  provider: string
  status: ProviderJobStatus
  mode: string
  trigger: string
  label: string
  processed: number
  total: number
  matched: number
  failed: number
  error_message: string
  created_at: string
  finished_at: string | null
}

export interface OpsProvider {
  id: number
  name: string
  slug: string
  type: string
  base_url: string
  is_active: boolean
  rate_limit_per_minute: number
  jobs_24h: number
}

export interface OpsSyncRun {
  id: number
  status: string
  mode: string
  phase: string
  processed: number
  total: number
  created: number
  updated: number
  errors: number
  started_at: string
  finished_at: string | null
}

export interface OpsOverview {
  queues: OpsQueueLane[]
  workers: OpsWorkers
  jobs: {
    active: number
    last_24h: number
    by_status: Record<string, number>
    recent: OpsJobRow[]
  }
  providers: OpsProvider[]
  sync_runs: OpsSyncRun[]
  importer_settings: Record<string, unknown>
  catalog: Record<AdminContentKind, { total: number, published: number, draft: number, archived?: number }>
  health: HealthCounts
  generated_at: string
}

export interface AuditFeedResponse {
  count: number
  limit: number
  offset: number
  results: DeskAudit[]
}
