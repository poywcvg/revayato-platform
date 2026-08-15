import type { AggregateDemandSignal, AnalyticsEvent, Movie, RecommendationPreferences } from '~/types'

export interface RankedRecommendation {
  item: Movie
  score: number
  reasons: string[]
}

export type RecommendationPreferencesInput = Omit<RecommendationPreferences,
  'favorite_genres' | 'disliked_genres' | 'preferred_countries' | 'preferred_languages' | 'preferred_age_ratings'> & {
    readonly favorite_genres: readonly string[]
    readonly disliked_genres: readonly string[]
    readonly preferred_countries: readonly string[]
    readonly preferred_languages: readonly string[]
    readonly preferred_age_ratings: readonly RecommendationPreferences['preferred_age_ratings'][number][]
  }

type SignalMap = Map<string, number>

export interface BehaviorProfile {
  genres: SignalMap
  directors: SignalMap
  cast: SignalMap
  countries: SignalMap
  languages: SignalMap
  formats: SignalMap
  contentTypes: SignalMap
  playback: SignalMap
  items: SignalMap
  progress: Map<string, number>
  completed: Set<string>
  disliked: Set<string>
  recentPositiveSlugs: string[]
  confidence: number
  preferredDuration: number | null
  preferredYear: number | null
}

const DAY_MS = 86_400_000
const RECENCY_HALF_LIFE_DAYS = 10
const MAX_DIVERSITY_POOL = 48
const EXPLORATION_SLOTS = 1

const languageAliases: Record<string, string[]> = {
  fa: ['fa', 'فارسی', 'persian', 'farsi'],
  en: ['en', 'انگلیسی', 'english'],
  ko: ['ko', 'کره‌ای', 'کره ای', 'korean'],
  fr: ['fr', 'فرانسوی', 'french'],
  de: ['de', 'آلمانی', 'german'],
  tr: ['tr', 'ترکی', 'turkish'],
}

const moodGenres: Record<string, string[]> = {
  exciting: ['action', 'adventure', 'crime'],
  calm: ['drama', 'romance', 'family'],
  scary: ['horror', 'mystery'],
  romantic: ['romance'],
  thoughtful: ['sci-fi', 'mystery', 'drama'],
  family: ['family', 'animation'],
  light: ['comedy', 'family'],
}

function normalizeText(value: string) {
  return value
    .normalize('NFKC')
    .replace(/[يى]/g, 'ی')
    .replace(/ك/g, 'ک')
    .replace(/[\u064B-\u065F\u0670]/g, '')
    .replace(/[\u200C\u200D]/g, ' ')
    .toLocaleLowerCase('fa')
    .replace(/[^\p{L}\p{N}+]+/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function normalizedTokens(value: string) {
  return value
    .toLocaleLowerCase('fa')
    .split(/[،,؛;/]/)
    .map(token => normalizeText(token))
    .filter(Boolean)
}

function includesPreference(value: string, preferences: readonly string[]) {
  const itemTokens = normalizedTokens(value)
  return preferences.some(preference => normalizedTokens(preference).some(token => itemTokens.includes(token)))
}

function includesLanguage(value: string, preferences: readonly string[]) {
  const normalized = normalizeText(value)
  return preferences.some((preference) => {
    const aliases = languageAliases[preference] || [normalizeText(preference)]
    return aliases.some(alias => normalized.includes(normalizeText(alias)))
  })
}

function addSignal(map: SignalMap, key: string | undefined, amount: number) {
  const normalizedKey = key?.trim()
  if (!normalizedKey || !Number.isFinite(amount) || amount === 0) return
  map.set(normalizedKey, (map.get(normalizedKey) || 0) + amount)
}

function squashedSignal(value: number) {
  return Math.sign(value) * Math.log1p(Math.abs(value)) * 3
}

function recencyMultiplier(timestamp: string, now: number) {
  const parsed = Date.parse(timestamp)
  if (!Number.isFinite(parsed)) return 0
  const ageDays = Math.max(0, now - parsed) / DAY_MS
  return Math.pow(0.5, ageDays / RECENCY_HALF_LIFE_DAYS)
}

function stateFamily(event: AnalyticsEvent) {
  if (['like', 'remove_like', 'dislike'].includes(event.event_type)) return 'affinity'
  if (['add_watchlist', 'remove_watchlist'].includes(event.event_type)) return 'watchlist'
  if (event.event_type === 'rate') return 'rating'
  return ''
}

function eventKey(event: AnalyticsEvent) {
  const titleKey = event.title_slug || String(event.title_id || '')
  const session = event.anonymous_session_id || 'local'
  const day = event.timestamp.slice(0, 10)
  const family = stateFamily(event)
  if (family && titleKey) return `state:${family}:${titleKey}`
  if (event.event_type === 'watch_progress' && titleKey) return `progress:${session}:${titleKey}`
  if (event.event_type === 'complete_watch' && titleKey) return `complete:${titleKey}`
  if (titleKey) return `${event.event_type}:${titleKey}:${day}`
  if (event.event_type === 'click_genre') return `genre:${event.genre || ''}:${day}`
  if (event.event_type === 'filter_apply') return `filter:${event.filter_name || ''}:${event.filter_value || ''}:${day}`
  if (event.event_type === 'search' || event.event_type === 'empty_search') return `search:${normalizeText(event.query || '')}:${day}`
  return `${event.event_type}:${event.filter_value || event.sort || ''}:${day}`
}

/**
 * Collapses noisy browser events into meaningful decisions. Progress keeps the
 * furthest point per title/session, while mutable actions keep only their last
 * state so an unlike is never interpreted as a permanent dislike.
 */
export function collapseBehaviorEvents(events: readonly AnalyticsEvent[]) {
  const collapsed = new Map<string, AnalyticsEvent>()
  for (const event of events) {
    const key = eventKey(event)
    const previous = collapsed.get(key)
    if (!previous) {
      collapsed.set(key, event)
      continue
    }
    if (event.event_type === 'watch_progress') {
      const previousProgress = previous.progress_percent || 0
      const nextProgress = event.progress_percent || 0
      if (nextProgress > previousProgress || (nextProgress === previousProgress && event.timestamp > previous.timestamp)) {
        collapsed.set(key, event)
      }
      continue
    }
    if (event.timestamp >= previous.timestamp) collapsed.set(key, event)
  }
  return [...collapsed.values()].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp))
}

function eventPreferenceWeight(event: AnalyticsEvent) {
  const progress = Math.max(0, Math.min(100, event.progress_percent || 0))
  const weights: Partial<Record<AnalyticsEvent['event_type'], number>> = {
    view_movie: 0.45,
    view_series: 0.45,
    recommendation_click: 1.2,
    play_trailer: 1.1,
    start_watch: 1.5,
    continue_watch: 2.4,
    pause_watch: progress >= 20 ? 0.7 : 0.2,
    watch_progress: progress < 10 ? 0 : 0.8 + progress * 0.045,
    complete_watch: 6,
    add_watchlist: 4,
    remove_watchlist: -1,
    like: 7,
    remove_like: -0.75,
    dislike: -10,
    click_genre: 3,
    click_cast: 3.25,
    click_director: 3.5,
    filter_apply: 1.7,
    search: 0.8,
  }
  if (event.event_type === 'rate' && typeof event.rating === 'number') return (event.rating - 5) * 1.6
  return weights[event.event_type] || 0
}

function exactItemWeight(event: AnalyticsEvent) {
  const progress = Math.max(0, Math.min(100, event.progress_percent || 0))
  const weights: Partial<Record<AnalyticsEvent['event_type'], number>> = {
    view_movie: 0.2,
    view_series: 0.2,
    recommendation_click: 1.5,
    play_trailer: 1.5,
    start_watch: -1,
    continue_watch: -4,
    pause_watch: -Math.max(0, progress - 10) * 0.08,
    watch_progress: -Math.max(1, progress * 0.12),
    complete_watch: -50,
    add_watchlist: 9,
    remove_watchlist: -14,
    like: -4,
    remove_like: -10,
    dislike: -120,
  }
  if (event.event_type === 'rate' && typeof event.rating === 'number') {
    return event.rating >= 7 ? -5 : event.rating <= 4 ? -55 : -12
  }
  return weights[event.event_type] || 0
}

function addItemFeatures(profile: BehaviorProfile, item: Movie, weight: number) {
  item.genres.forEach(genre => addSignal(profile.genres, genre.slug, weight))
  addSignal(profile.directors, item.director, weight * 0.75)
  item.cast.slice(0, 5).forEach(person => addSignal(profile.cast, person.name, weight * 0.28))
  normalizedTokens(item.country).forEach(country => addSignal(profile.countries, country, weight * 0.4))
  normalizedTokens(item.language).forEach(language => addSignal(profile.languages, language, weight * 0.35))
  addSignal(profile.formats, item.format, weight * 0.5)
  addSignal(profile.contentTypes, item.type, weight * 0.55)
}

function queryMatchScore(item: Movie, normalizedQuery: string) {
  if (!normalizedQuery) return 0
  let score = 0
  const title = normalizeText(item.title)
  const originalTitle = normalizeText(item.original_title)
  if ((title && normalizedQuery.includes(title)) || (originalTitle && normalizedQuery.includes(originalTitle))) score += 4
  if (item.genres.some(genre => normalizedQuery.includes(normalizeText(genre.title)) || normalizedQuery.includes(normalizeText(genre.slug)))) score += 2
  if (item.director && normalizedQuery.includes(normalizeText(item.director))) score += 2.5
  if (item.cast.some(person => normalizedQuery.includes(normalizeText(person.name)))) score += 2
  if (normalizedTokens(item.country).some(country => normalizedQuery.includes(country))) score += 1
  if (normalizedTokens(item.language).some(language => normalizedQuery.includes(language))) score += 1
  return score
}

function applyFilterSignal(profile: BehaviorProfile, event: AnalyticsEvent, weight: number) {
  const name = event.filter_name || ''
  const value = event.filter_value || ''
  if (name === 'genre') addSignal(profile.genres, value, weight)
  if (name === 'content_type' && ['movie', 'series'].includes(value)) addSignal(profile.contentTypes, value, weight)
  if (name === 'format') addSignal(profile.formats, value, weight)
  if (name === 'availability' && ['dubbed', 'subtitle'].includes(value)) addSignal(profile.playback, value, weight)
  if (name === 'home_category') {
    if (value.startsWith('genre:')) addSignal(profile.genres, value.slice(6), weight)
    if (['movie', 'series'].includes(value)) addSignal(profile.contentTypes, value, weight)
    if (value === 'animation') addSignal(profile.formats, value, weight)
    if (['dubbed', 'subtitle'].includes(value)) addSignal(profile.playback, value, weight)
  }
  if (name === 'mood') moodGenres[value]?.forEach(genre => addSignal(profile.genres, genre, weight / 2))
}

export function buildBehaviorProfile(events: readonly AnalyticsEvent[], catalog: readonly Movie[], now = Date.now()): BehaviorProfile {
  const profile: BehaviorProfile = {
    genres: new Map(),
    directors: new Map(),
    cast: new Map(),
    countries: new Map(),
    languages: new Map(),
    formats: new Map(),
    contentTypes: new Map(),
    playback: new Map(),
    items: new Map(),
    progress: new Map(),
    completed: new Set(),
    disliked: new Set(),
    recentPositiveSlugs: [],
    confidence: 0,
    preferredDuration: null,
    preferredYear: null,
  }
  const catalogBySlug = new Map(catalog.map(item => [item.slug, item]))
  const catalogById = new Map(catalog.map(item => [item.id, item]))
  let evidence = 0
  let durationTotal = 0
  let durationWeight = 0
  let yearTotal = 0
  let yearWeight = 0

  for (const event of collapseBehaviorEvents(events)) {
    const recency = recencyMultiplier(event.timestamp, now)
    if (recency <= 0) continue
    const item = event.title_slug ? catalogBySlug.get(event.title_slug) : event.title_id ? catalogById.get(event.title_id) : undefined
    const preferenceWeight = eventPreferenceWeight(event) * recency
    const itemWeight = exactItemWeight(event) * recency
    evidence += Math.min(6, Math.abs(preferenceWeight))

    if (event.genre) addSignal(profile.genres, event.genre, preferenceWeight || 2 * recency)
    if (event.event_type === 'click_director') addSignal(profile.directors, event.filter_value, preferenceWeight)
    if (event.event_type === 'click_cast') addSignal(profile.cast, event.filter_value, preferenceWeight)
    if (event.event_type === 'filter_apply') applyFilterSignal(profile, event, preferenceWeight)

    if (event.event_type === 'search' && event.query) {
      const query = normalizeText(event.query)
      catalog
        .map(candidate => ({ candidate, match: queryMatchScore(candidate, query) }))
        .filter(result => result.match > 0)
        .sort((a, b) => b.match - a.match)
        .slice(0, 4)
        .forEach(({ candidate, match }) => {
          const searchWeight = preferenceWeight * Math.min(1.4, match / 2.5)
          addItemFeatures(profile, candidate, searchWeight)
          addSignal(profile.items, candidate.slug, searchWeight * 0.3)
        })
    }

    if (!item) continue
    addItemFeatures(profile, item, preferenceWeight)
    addSignal(profile.items, item.slug, itemWeight)

    const progress = Math.max(0, Math.min(100, event.progress_percent || 0))
    if (progress) profile.progress.set(item.slug, Math.max(profile.progress.get(item.slug) || 0, progress))
    if (event.event_type === 'complete_watch') profile.completed.add(item.slug)
    if (event.event_type === 'dislike' || (event.event_type === 'rate' && (event.rating || 0) <= 3)) profile.disliked.add(item.slug)
    if (event.event_type === 'like') profile.disliked.delete(item.slug)

    if (preferenceWeight >= 1.4) {
      profile.recentPositiveSlugs = [...profile.recentPositiveSlugs.filter(slug => slug !== item.slug), item.slug].slice(-12)
      durationTotal += item.duration_minutes * preferenceWeight
      durationWeight += preferenceWeight
      yearTotal += item.year * preferenceWeight
      yearWeight += preferenceWeight
    }
  }

  profile.confidence = Math.min(1, 1 - Math.exp(-evidence / 16))
  profile.preferredDuration = durationWeight >= 2 ? durationTotal / durationWeight : null
  profile.preferredYear = yearWeight >= 2 ? yearTotal / yearWeight : null
  return profile
}

function buildDemandScores(signals: readonly AggregateDemandSignal[], catalog: readonly Movie[] = []) {
  const scores = new Map<string, number>()
  for (const signal of signals) {
    const boundedScore = Math.min(10, Math.max(0, signal.score)) / 5
    signal.genre_slugs.forEach(slug => addSignal(scores, slug, boundedScore))
  }
  // Live catalog demand: popular + trending titles seed cold-start genre affinity.
  if (!signals.length && catalog.length) {
    [...catalog]
      .sort((a, b) => (Number(b.is_trending) - Number(a.is_trending)) || b.popularity - a.popularity)
      .slice(0, 24)
      .forEach((item, index) => {
        const weight = Math.max(0.2, 1.4 - index * 0.04)
        item.genres.forEach(genre => addSignal(scores, genre.slug, weight))
      })
  }
  return scores
}

function playableBoost(item: Movie) {
  let boost = 0
  if (item.is_dubbed) boost += 2.4
  if (item.has_subtitle) boost += 2.1
  if ((item.download_links || []).some(link => Boolean(link.url))) boost += 3.2
  if (item.hls_url || item.playback?.signed_playback_url || item.playback?.hls_url) boost += 1.5
  if ((item.playback?.subtitle_tracks || item.subtitle_tracks || []).length) boost += 1.8
  return boost
}

function sensitivityScore(item: Movie, preference: RecommendationPreferences['content_sensitivity']) {
  if (preference === 'reduced') {
    return (item.is_uncensored ? -28 : 0)
      + (item.age_rating === '18+' ? -14 : 0)
      - Math.min(12, item.content_warnings.length * 3)
  }
  if (preference === 'standard') return (item.is_uncensored ? -5 : 0) - Math.min(4, item.content_warnings.length)
  return 0
}

function playbackScore(item: Movie, preference: RecommendationPreferences['playback_preference']) {
  if (preference === 'dubbed') return item.is_dubbed ? 7 : -2
  if (preference === 'subtitle') return item.has_subtitle ? 5 : -2
  if (preference === 'original') return item.is_dubbed ? 0 : 2
  return 0
}

function mapScore(map: SignalMap, key: string, coefficient = 1) {
  return squashedSignal(map.get(key) || 0) * coefficient
}

function similarity(a: Movie, b: Movie) {
  const aGenres = new Set(a.genres.map(genre => genre.slug))
  const bGenres = new Set(b.genres.map(genre => genre.slug))
  const sharedGenres = [...aGenres].filter(genre => bGenres.has(genre)).length
  const unionGenres = new Set([...aGenres, ...bGenres]).size || 1
  return (sharedGenres / unionGenres) * 0.72
    + (a.director && a.director === b.director ? 0.15 : 0)
    + (a.type === b.type ? 0.08 : 0)
    + (a.format === b.format ? 0.05 : 0)
}

function recommendationReasons(item: Movie, preferences: RecommendationPreferencesInput, profile: BehaviorProfile, catalogBySlug: Map<string, Movie>) {
  const reasons: string[] = []
  const favoriteGenre = item.genres.find(genre => preferences.favorite_genres.includes(genre.slug))
  const behaviorGenre = [...item.genres]
    .sort((a, b) => (profile.genres.get(b.slug) || 0) - (profile.genres.get(a.slug) || 0))
    .find(genre => (profile.genres.get(genre.slug) || 0) >= 1.8)
  const recentSimilar = [...profile.recentPositiveSlugs]
    .reverse()
    .map(slug => catalogBySlug.get(slug))
    .find(candidate => candidate && candidate.slug !== item.slug && similarity(item, candidate) >= 0.35)

  if (favoriteGenre) reasons.push(`چون به ${favoriteGenre.title} علاقه داری`)
  if (recentSimilar) reasons.push(`نزدیک به «${recentSimilar.title}»`)
  if (item.director && (profile.directors.get(item.director) || 0) >= 1.8) reasons.push(`از ${item.director}`)
  if (behaviorGenre) reasons.push(`در حال‌وهوای ${behaviorGenre.title}`)
  const matchingCast = item.cast.find(person => (profile.cast.get(person.name) || 0) >= 1.8)
  if (matchingCast) reasons.push(`با حضور ${matchingCast.name}`)
  if (preferences.playback_preference === 'dubbed' && item.is_dubbed) reasons.push('با دوبله فارسی')
  if (preferences.playback_preference === 'subtitle' && item.has_subtitle) reasons.push('با زیرنویس فارسی')
  if (includesPreference(item.country, preferences.preferred_countries)) reasons.push('از کشورهای موردعلاقه‌ات')
  if (includesLanguage(item.language, preferences.preferred_languages)) reasons.push('هم‌زبان با سلیقه تو')
  if (preferences.content_sensitivity === 'reduced' && !item.is_uncensored && item.age_rating !== '18+' && item.content_warnings.length <= 1) reasons.push('سبک‌تر و کم‌حساسیت‌تر')
  if (!reasons.length && item.is_trending) reasons.push('از انتخاب‌های امروز')
  if (!reasons.length) reasons.push(item.recommendation_reason || 'پیشنهاد روایتو')
  if (item.is_dubbed && preferences.playback_preference === 'any' && reasons.length < 2) {
    reasons.push('دوبله فارسی')
  } else if (item.has_subtitle && preferences.playback_preference === 'any' && reasons.length < 2) {
    reasons.push('زیرنویس فارسی')
  }
  return [...new Set(reasons)].slice(0, 2)
}

function diversify(ranked: RankedRecommendation[], limit: number) {
  if (limit <= 1) return ranked.slice(0, Math.max(0, limit))
  const pool = ranked.slice(0, Math.min(MAX_DIVERSITY_POOL, Math.max(limit * 4, limit)))
  const selected: RankedRecommendation[] = []
  while (selected.length < limit && pool.length) {
    let bestIndex = 0
    let bestAdjustedScore = Number.NEGATIVE_INFINITY
    const explore = selected.length >= Math.max(1, limit - EXPLORATION_SLOTS)
    pool.forEach((candidate, index) => {
      const overlap = selected.length ? Math.max(...selected.map(entry => similarity(candidate.item, entry.item))) : 0
      // Last slot: slightly prefer less-similar / fresher titles (exploration).
      const novelty = explore
        ? (candidate.item.is_new ? 1.4 : 0) + (candidate.item.is_trending ? 0.8 : 0) - overlap * 1.1
        : 0
      const adjustedScore = candidate.score - overlap * 3.25 + novelty
      if (adjustedScore > bestAdjustedScore) {
        bestAdjustedScore = adjustedScore
        bestIndex = index
      }
    })
    selected.push(pool.splice(bestIndex, 1)[0]!)
  }
  return selected
}

export function rankRecommendations(
  catalog: readonly Movie[],
  preferences: RecommendationPreferencesInput,
  events: readonly AnalyticsEvent[],
  demandSignals: readonly AggregateDemandSignal[],
  limit = 8,
  now = Date.now(),
): RankedRecommendation[] {
  const profile = buildBehaviorProfile(events, catalog, now)
  const demand = buildDemandScores(demandSignals, catalog)
  const catalogBySlug = new Map(catalog.map(item => [item.slug, item]))
  const behaviorBlend = 0.42 + profile.confidence * 0.58
  const recentContextItems = profile.recentPositiveSlugs
    .map(slug => catalogBySlug.get(slug))
    .filter((item): item is Movie => Boolean(item))

  const ranked = catalog.map((item) => {
    let score = item.rating * 1.25 + item.popularity / 18
    score += item.is_recommended ? 6.5 : 0
    score += item.is_trending ? 3.2 : 0
    score += item.is_new ? 1.1 : 0
    score += playableBoost(item)
    score += profile.items.get(item.slug) || 0
    score += playbackScore(item, preferences.playback_preference)
    score += sensitivityScore(item, preferences.content_sensitivity)

    if (includesPreference(item.country, preferences.preferred_countries)) score += 6
    if (includesLanguage(item.language, preferences.preferred_languages)) score += 5
    if (preferences.preferred_age_ratings.includes(item.age_rating)) score += 4
    else if (preferences.preferred_age_ratings.length) score -= 2

    let behavioralScore = mapScore(profile.directors, item.director, 0.95)
      + mapScore(profile.formats, item.format, 0.65)
      + mapScore(profile.contentTypes, item.type, 0.75)
    item.cast.slice(0, 5).forEach(person => { behavioralScore += mapScore(profile.cast, person.name, 0.38) })
    normalizedTokens(item.country).forEach(country => { behavioralScore += mapScore(profile.countries, country, 0.45) })
    normalizedTokens(item.language).forEach(language => { behavioralScore += mapScore(profile.languages, language, 0.45) })
    if (item.is_dubbed) behavioralScore += mapScore(profile.playback, 'dubbed', 0.8)
    if (item.has_subtitle) behavioralScore += mapScore(profile.playback, 'subtitle', 0.7)

    for (const genre of item.genres) {
      if (preferences.favorite_genres.includes(genre.slug)) score += 12
      if (preferences.disliked_genres.includes(genre.slug)) score -= 24
      behavioralScore += mapScore(profile.genres, genre.slug, 1.12)
      score += demand.get(genre.slug) || 0
    }
    score += behavioralScore * behaviorBlend

    const recentContextSimilarity = recentContextItems.length
      ? Math.max(...recentContextItems.filter(context => context.slug !== item.slug).map(context => similarity(item, context)), 0)
      : 0
    score += recentContextSimilarity * (7.5 + profile.confidence * 7.5)

    if (profile.preferredDuration !== null) score += Math.max(-1.5, 2.2 - Math.abs(item.duration_minutes - profile.preferredDuration) / 28)
    if (profile.preferredYear !== null) score += Math.max(-1, 1.4 - Math.abs(item.year - profile.preferredYear) / 5)
    score -= Math.max(item.progress_percent, profile.progress.get(item.slug) || 0) * 0.045
    if (profile.completed.has(item.slug)) score -= 28
    if (profile.disliked.has(item.slug)) score -= 85

    // Cold-start: lean on today's trends + playable quality until confidence grows.
    if (profile.confidence < 0.2) {
      score += item.is_trending ? 4 : 0
      score += playableBoost(item) * 0.45
    }

    const reasons = recommendationReasons(item, preferences, profile, catalogBySlug)
    return {
      item: { ...item, recommendation_reason: reasons[0] },
      score: Math.round(score * 1000) / 1000,
      reasons,
    }
  }).sort((a, b) => b.score - a.score || b.item.popularity - a.item.popularity || a.item.id - b.item.id)

  return diversify(ranked, Math.max(0, limit))
}
