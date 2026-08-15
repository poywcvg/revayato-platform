import { analyticsEventTypes } from '~/types'
import type {
  AnalyticsSyncResult,
  AnalyticsEvent,
  AnalyticsEventInput,
  ContentType,
  Movie,
  RecommendationPreferences,
} from '~/types'

const EVENTS_STORAGE_KEY = 'revayato:behavior-events:v1'
const PREFERENCES_STORAGE_KEY = 'revayato:recommendation-preferences:v1'
const SESSION_STORAGE_KEY = 'revayato:anonymous-session:v1'
const SYNC_CURSOR_STORAGE_KEY = 'revayato:behavior-sync-cursor:v1'
const MAX_LOCAL_EVENTS = 300
const MAX_EVENT_AGE_MS = 90 * 24 * 60 * 60 * 1000
let hydrationScheduled = false
let syncTimer: ReturnType<typeof setTimeout> | null = null

type TrackableContent = Pick<Movie, 'id' | 'slug' | 'type'>
type WatchProgressAction = 'start' | 'pause' | 'progress' | 'complete'

function defaultPreferences(): RecommendationPreferences {
  return {
    favorite_genres: [],
    disliked_genres: [],
    preferred_countries: [],
    preferred_languages: [],
    playback_preference: 'any',
    content_sensitivity: 'any',
    preferred_age_ratings: [],
  }
}

function sanitizeStringList(value: unknown, maxItems = 24) {
  if (!Array.isArray(value)) return []
  return [...new Set(value.filter(item => typeof item === 'string').map(item => sanitizeText(item, 80)).filter(Boolean))].slice(0, maxItems)
}

function sanitizePreferences(value: unknown): RecommendationPreferences {
  const input = value && typeof value === 'object' ? value as Partial<RecommendationPreferences> : {}
  const playbackPreference = ['any', 'original', 'subtitle', 'dubbed'].includes(String(input.playback_preference))
    ? input.playback_preference as RecommendationPreferences['playback_preference']
    : 'any'
  const contentSensitivity = ['any', 'standard', 'reduced'].includes(String(input.content_sensitivity))
    ? input.content_sensitivity as RecommendationPreferences['content_sensitivity']
    : 'any'

  return {
    favorite_genres: sanitizeStringList(input.favorite_genres),
    disliked_genres: sanitizeStringList(input.disliked_genres),
    preferred_countries: sanitizeStringList(input.preferred_countries, 16),
    preferred_languages: sanitizeStringList(input.preferred_languages, 12),
    playback_preference: playbackPreference,
    content_sensitivity: contentSensitivity,
    preferred_age_ratings: sanitizeStringList(input.preferred_age_ratings, 3).filter((rating): rating is RecommendationPreferences['preferred_age_ratings'][number] => ['12+', '15+', '18+'].includes(rating)),
  }
}

function sanitizeText(value: string, maxLength: number) {
  return value.replace(/\s+/g, ' ').trim().slice(0, maxLength)
}

function sanitizeSourcePage(value: string) {
  const path = value.split('?')[0] || '/'
  return path.startsWith('/') ? path.slice(0, 180) : '/'
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function fallbackEventId(input: Pick<AnalyticsEventInput, 'event_type' | 'timestamp' | 'title_slug'>) {
  let hash = 2166136261
  for (const character of input.title_slug || '') hash = Math.imul(hash ^ character.charCodeAt(0), 16777619)
  return `${input.timestamp || new Date().toISOString()}:${input.event_type}:${(hash >>> 0).toString(36)}`.slice(0, 100)
}

function normalizeStoredEvent(value: unknown): AnalyticsEvent | null {
  if (!value || typeof value !== 'object') return null
  const input = value as Partial<AnalyticsEvent> & { movie_id?: unknown; movie_slug?: unknown }
  if (!analyticsEventTypes.includes(input.event_type as AnalyticsEvent['event_type'])
    || typeof input.source_page !== 'string'
    || typeof input.timestamp !== 'string'
    || !Number.isFinite(Date.parse(input.timestamp))) return null

  const event: AnalyticsEvent = {
    event_id: typeof input.event_id === 'string' && input.event_id.length >= 8
      ? sanitizeText(input.event_id, 100)
      : fallbackEventId({
          event_type: input.event_type as AnalyticsEvent['event_type'],
          timestamp: input.timestamp,
          title_slug: typeof input.title_slug === 'string' ? input.title_slug : undefined,
        }),
    event_type: input.event_type as AnalyticsEvent['event_type'],
    source_page: sanitizeSourcePage(input.source_page),
    timestamp: new Date(input.timestamp).toISOString(),
  }
  const titleId = input.title_id ?? input.movie_id
  const titleSlug = input.title_slug ?? input.movie_slug
  if (typeof titleId === 'number' && Number.isFinite(titleId)) event.title_id = Math.max(1, Math.trunc(titleId))
  if (typeof titleSlug === 'string') event.title_slug = sanitizeText(titleSlug, 120)
  if (input.content_type === 'movie' || input.content_type === 'series') event.content_type = input.content_type
  if (typeof input.query === 'string') event.query = sanitizeText(input.query, 255)
  if (typeof input.genre === 'string') event.genre = sanitizeText(input.genre, 100)
  if (typeof input.progress_percent === 'number') event.progress_percent = Math.round(clamp(input.progress_percent, 0, 100))
  if (typeof input.rating === 'number') event.rating = clamp(input.rating, 0, 10)
  if (typeof input.result_count === 'number') event.result_count = Math.max(0, Math.trunc(input.result_count))
  if (typeof input.filter_name === 'string') event.filter_name = sanitizeText(input.filter_name, 60)
  if (typeof input.filter_value === 'string') event.filter_value = sanitizeText(input.filter_value, 120)
  if (typeof input.sort === 'string') event.sort = sanitizeText(input.sort, 60)
  if (typeof input.user_id === 'number' && Number.isFinite(input.user_id)) event.user_id = Math.max(1, Math.trunc(input.user_id))
  if (typeof input.anonymous_session_id === 'string') event.anonymous_session_id = sanitizeText(input.anonymous_session_id, 80)
  if (typeof input.is_empty_query === 'boolean') event.is_empty_query = input.is_empty_query
  return event
}

function isSafeEventsEndpoint(value: unknown) {
  return typeof value === 'string' && /^\/(?!\/)/.test(value) && !value.includes('://')
}

export function useAnalyticsEvent() {
  const config = useRuntimeConfig()
  const { api } = useApi()
  const authStore = useAuthStore()
  const { consent, events, personalizationEnabled, eventCount } = usePersonalizationState()
  const preferences = useState<RecommendationPreferences>('recommendation-preferences', defaultPreferences)
  const hydrated = useState('analytics-local-hydrated', () => false)
  const syncing = useState('analytics-syncing', () => false)

  function persistEvents() {
    if (!import.meta.client || !personalizationEnabled.value || !authStore.isAuthenticated) return
    try {
      localStorage.setItem(EVENTS_STORAGE_KEY, JSON.stringify(events.value))
    } catch {
      // Storage may be unavailable in private browsing; tracking remains optional.
    }
  }

  function persistPreferences() {
    if (!import.meta.client || !personalizationEnabled.value) return
    try {
      localStorage.setItem(PREFERENCES_STORAGE_KEY, JSON.stringify(preferences.value))
    } catch {
      // Preferences remain reactive for the current page even without storage.
    }
  }

  function hydrateLocalState() {
    if (!import.meta.client || hydrated.value) return
    hydrated.value = true

    if (!personalizationEnabled.value || !authStore.isAuthenticated) {
      events.value = []
      try { localStorage.removeItem(EVENTS_STORAGE_KEY) } catch { /* Optional storage. */ }
      return
    }

    try {
      const storedEvents = JSON.parse(localStorage.getItem(EVENTS_STORAGE_KEY) || '[]') as unknown
      const cutoff = Date.now() - MAX_EVENT_AGE_MS
      events.value = Array.isArray(storedEvents)
        ? storedEvents.map(normalizeStoredEvent).filter((event): event is AnalyticsEvent => Boolean(event)).filter(event => Date.parse(event.timestamp) >= cutoff).slice(-MAX_LOCAL_EVENTS)
        : []

      const storedPreferences = JSON.parse(localStorage.getItem(PREFERENCES_STORAGE_KEY) || 'null') as unknown
      if (storedPreferences) {
        preferences.value = sanitizePreferences(storedPreferences)
      }
    } catch {
      events.value = []
      preferences.value = defaultPreferences()
    }
  }

  function clearEvents() {
    events.value = []
    if (!import.meta.client) return
    try {
      localStorage.removeItem(EVENTS_STORAGE_KEY)
      localStorage.removeItem(SYNC_CURSOR_STORAGE_KEY)
      sessionStorage.removeItem(SESSION_STORAGE_KEY)
    } catch {
      // State is already cleared even if browser storage is unavailable.
    }
  }

  function clearLocalPersonalizationData() {
    clearEvents()
    preferences.value = defaultPreferences()
    if (!import.meta.client) return
    try { localStorage.removeItem(PREFERENCES_STORAGE_KEY) } catch { /* Optional storage. */ }
  }

  function setPersonalizationEnabled(enabled: boolean) {
    consent.value = enabled ? 'enabled' : 'disabled'
    if (!enabled) {
      clearEvents()
      return
    }
    hydrated.value = false
    hydrateLocalState()
    persistPreferences()
  }

  function updatePreferences(next: Partial<RecommendationPreferences>) {
    preferences.value = sanitizePreferences({ ...preferences.value, ...next })
    persistPreferences()
  }

  function track(input: AnalyticsEventInput) {
    if (!import.meta.client || !personalizationEnabled.value || !authStore.isAuthenticated) return null
    hydrateLocalState()

    const event: AnalyticsEvent = {
      event_id: input.event_id || crypto.randomUUID(),
      event_type: input.event_type,
      source_page: sanitizeSourcePage(input.source_page || window.location.pathname),
      timestamp: input.timestamp || new Date().toISOString(),
    }
    if (input.user_id) event.user_id = input.user_id
    if (input.title_id) event.title_id = Math.max(1, Math.trunc(input.title_id))
    if (input.title_slug) event.title_slug = sanitizeText(input.title_slug, 120)
    if (input.content_type) event.content_type = input.content_type
    if (typeof input.query === 'string') event.query = sanitizeText(input.query, 255)
    if (input.genre) event.genre = sanitizeText(input.genre, 100)
    if (typeof input.progress_percent === 'number') event.progress_percent = Math.round(clamp(input.progress_percent, 0, 100))
    if (typeof input.rating === 'number') event.rating = clamp(input.rating, 0, 10)
    if (typeof input.result_count === 'number') event.result_count = Math.max(0, Math.trunc(input.result_count))
    if (input.filter_name) event.filter_name = sanitizeText(input.filter_name, 60)
    if (input.filter_value) event.filter_value = sanitizeText(input.filter_value, 120)
    if (input.sort) event.sort = sanitizeText(input.sort, 60)
    if (typeof input.is_empty_query === 'boolean') event.is_empty_query = input.is_empty_query

    const previous = events.value.at(-1)
    const isDuplicate = previous
      && previous.event_type === event.event_type
      && previous.title_slug === event.title_slug
      && previous.query === event.query
      && previous.progress_percent === event.progress_percent
      && Date.parse(event.timestamp) - Date.parse(previous.timestamp) < 750
    if (isDuplicate) return previous

    events.value = [...events.value, event].slice(-MAX_LOCAL_EVENTS)
    persistEvents()
    scheduleSync()
    if (import.meta.dev) console.debug('[privacy-safe-event]', event)
    return event
  }

  function trackTitleView(item: TrackableContent) {
    return track({
      event_type: item.type === 'movie' ? 'view_movie' : 'view_series',
      title_id: item.id,
      title_slug: item.slug,
      content_type: item.type,
    })
  }

  /** @deprecated Use trackTitleView for the unified movie/series contract. */
  const trackMovieView = trackTitleView

  function trackSearch(query: string, resultCount: number) {
    const normalizedQuery = sanitizeText(query, 255)
    return track({
      event_type: normalizedQuery ? 'search' : 'empty_search',
      query: normalizedQuery,
      result_count: resultCount,
      is_empty_query: normalizedQuery.length === 0,
    })
  }

  function trackWatchProgress(item: TrackableContent, progressPercent: number, action: WatchProgressAction) {
    const eventType = {
      start: 'start_watch',
      pause: 'pause_watch',
      progress: 'watch_progress',
      complete: 'complete_watch',
    } as const
    return track({
      event_type: eventType[action],
      title_id: item.id,
      title_slug: item.slug,
      content_type: item.type,
      progress_percent: progressPercent,
    })
  }

  function trackContinueWatching(item: TrackableContent, progressPercent: number) {
    return track({
      event_type: 'continue_watch',
      title_id: item.id,
      title_slug: item.slug,
      content_type: item.type,
      progress_percent: progressPercent,
    })
  }

  function trackTrailerPlay(item: TrackableContent) {
    return track({ event_type: 'play_trailer', title_id: item.id, title_slug: item.slug, content_type: item.type })
  }

  function trackWatchlistAction(item: TrackableContent, added: boolean) {
    return track({
      event_type: added ? 'add_watchlist' : 'remove_watchlist',
      title_id: item.id,
      title_slug: item.slug,
      content_type: item.type,
    })
  }

  function trackRatingAction(item: TrackableContent, rating: number) {
    return track({ event_type: 'rate', title_id: item.id, title_slug: item.slug, content_type: item.type, rating })
  }

  function trackLikeAction(item: TrackableContent, liked: boolean) {
    return track({
      event_type: liked ? 'like' : 'remove_like',
      title_id: item.id,
      title_slug: item.slug,
      content_type: item.type,
    })
  }

  function trackDislikeAction(item: TrackableContent) {
    return track({ event_type: 'dislike', title_id: item.id, title_slug: item.slug, content_type: item.type })
  }

  function trackRecommendationClick(item: TrackableContent) {
    return track({
      event_type: 'recommendation_click',
      title_id: item.id,
      title_slug: item.slug,
      content_type: item.type,
    })
  }

  function trackGenreClick(genre: string) {
    return track({ event_type: 'click_genre', genre })
  }

  function trackPersonClick(kind: 'cast' | 'director', name: string, item?: TrackableContent) {
    return track({
      event_type: kind === 'cast' ? 'click_cast' : 'click_director',
      title_id: item?.id,
      title_slug: item?.slug,
      content_type: item?.type,
      filter_value: name,
    })
  }

  function trackFilterApply(name: string, value: string, contentType?: ContentType) {
    return track({ event_type: 'filter_apply', filter_name: name, filter_value: value, content_type: contentType })
  }

  function trackSortApply(sort: string, contentType?: ContentType) {
    return track({ event_type: 'sort_apply', sort, content_type: contentType })
  }

  async function syncPendingEvents(): Promise<AnalyticsSyncResult> {
    if (!authStore.isAuthenticated
      || !personalizationEnabled.value
      || config.public.analyticsTransport !== 'api'
      || !isSafeEventsEndpoint(config.public.eventsEndpoint)
      || syncing.value) {
      return { sent: 0, remaining: events.value.length }
    }
    syncing.value = true
    let sent = 0
    let pending = [...events.value]
    try {
      if (import.meta.client) {
        const cursor = localStorage.getItem(SYNC_CURSOR_STORAGE_KEY)
        const cursorIndex = cursor ? pending.findIndex(event => event.event_id === cursor) : -1
        if (cursorIndex >= 0) pending = pending.slice(cursorIndex + 1)
      }
      for (const event of pending) {
        await api(config.public.eventsEndpoint, {
          method: 'POST',
          body: event,
          headers: { 'X-Personalization-Consent': 'granted' },
        })
        sent += 1
        if (import.meta.client) localStorage.setItem(SYNC_CURSOR_STORAGE_KEY, event.event_id)
      }
      return { sent, remaining: Math.max(0, pending.length - sent) }
    } finally {
      syncing.value = false
    }
  }

  function scheduleSync() {
    if (!import.meta.client || !authStore.isAuthenticated || config.public.analyticsTransport !== 'api' || !personalizationEnabled.value) return
    if (syncTimer) clearTimeout(syncTimer)
    syncTimer = setTimeout(() => {
      syncTimer = null
      void syncPendingEvents().catch(() => {
        // The retained local history is retried after the next consented event.
      })
    }, 4000)
  }

  if (import.meta.client && !hydrationScheduled) {
    hydrationScheduled = true
    onNuxtReady(() => {
      hydrateLocalState()
      scheduleSync()
    })
  }

  return {
    consent: readonly(consent),
    personalizationEnabled,
    events: readonly(events),
    eventCount,
    preferences: readonly(preferences),
    syncing: readonly(syncing),
    setPersonalizationEnabled,
    updatePreferences,
    clearEvents,
    clearLocalPersonalizationData,
    track,
    trackTitleView,
    trackMovieView,
    trackSearch,
    trackWatchProgress,
    trackContinueWatching,
    trackTrailerPlay,
    trackWatchlistAction,
    trackRatingAction,
    trackLikeAction,
    trackDislikeAction,
    trackRecommendationClick,
    trackGenreClick,
    trackPersonClick,
    trackFilterApply,
    trackSortApply,
    syncPendingEvents,
  }
}
