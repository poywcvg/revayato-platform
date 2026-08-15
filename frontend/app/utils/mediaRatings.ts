import type { MediaRating, RatingSource } from '~/types/ratings'
import { RATING_SOURCES } from '~/data/ratingSources'

const VALID_SOURCES = new Set<RatingSource>(Object.keys(RATING_SOURCES) as RatingSource[])

function asNumber(value: unknown): number | null {
  if (value == null || value === '') return null
  const number = Number(value)
  if (!Number.isFinite(number)) return null
  return number
}

function inRange(value: number, scale: number): boolean {
  if (scale === 5) return value > 0 && value <= 5
  if (scale === 10) return value > 0 && value <= 10
  if (scale === 100) return value > 0 && value <= 100
  return false
}

function displayFor(value: number, scale: 5 | 10 | 100, suffix = ''): string {
  if (scale === 100 && suffix === '%') return `${Math.round(value)}${suffix}`
  if (Number.isInteger(value)) return `${value}${suffix}`
  return `${value.toFixed(1)}${suffix}`
}

/** Validate and normalize a single rating payload from the API. */
export function validateMediaRating(raw: unknown): MediaRating | null {
  if (!raw || typeof raw !== 'object') return null
  const row = raw as Record<string, unknown>
  const source = row.source as RatingSource
  if (!VALID_SOURCES.has(source)) return null

  const config = RATING_SOURCES[source]
  const value = asNumber(row.value)
  const scaleRaw = asNumber(row.scale) ?? config.scale
  const scale = (scaleRaw === 5 || scaleRaw === 10 || scaleRaw === 100 ? scaleRaw : config.scale) as 5 | 10 | 100
  if (value == null || !inRange(value, scale)) return null

  const voteCount = asNumber(row.voteCount ?? row.vote_count)
  if (voteCount != null && voteCount < 0) return null

  const criticType = row.criticType ?? row.critic_type
  const allowedCritics = new Set(['critics', 'audience', 'users'])
  const normalizedCritic = typeof criticType === 'string' && allowedCritics.has(criticType)
    ? criticType as MediaRating['criticType']
    : undefined

  const url = typeof row.url === 'string' && /^https?:\/\//i.test(row.url) ? row.url : undefined
  const updatedAt = typeof (row.updatedAt ?? row.updated_at) === 'string'
    ? String(row.updatedAt ?? row.updated_at)
    : undefined

  return {
    source,
    value: scale === 100 ? Math.round(value) : Math.round(value * 10) / 10,
    scale,
    displayValue: typeof row.displayValue === 'string' && row.displayValue
      ? row.displayValue
      : displayFor(value, scale, config.suffix || ''),
    voteCount: voteCount != null ? Math.floor(voteCount) : undefined,
    url,
    updatedAt,
    criticType: normalizedCritic,
    isVerified: Boolean(row.isVerified ?? row.is_verified),
  }
}

export function normalizeMediaRatings(raw: unknown): MediaRating[] {
  if (!Array.isArray(raw)) return []
  const seen = new Set<string>()
  const ratings: MediaRating[] = []
  for (const entry of raw) {
    const rating = validateMediaRating(entry)
    if (!rating) continue
    const key = `${rating.source}:${rating.criticType || ''}`
    if (seen.has(key)) continue
    seen.add(key)
    ratings.push(rating)
  }
  return ratings
}

/**
 * Build ratings from legacy scalar fields when the API has not yet attached
 * a normalized ``ratings`` array.
 */
export function ratingsFromLegacyFields(input: {
  imdb_rating?: number | null
  tmdb_rating?: number | null
  site_rating?: number | null
  imdb_id?: string | null
  tmdb_id?: number | null
  type?: 'movie' | 'series'
}): MediaRating[] {
  const ratings: MediaRating[] = []
  const tmdb = asNumber(input.tmdb_rating)
  const imdb = asNumber(input.imdb_rating)
  const site = asNumber(input.site_rating)

  if (tmdb != null && inRange(tmdb, 10)) {
    const tmdbId = input.tmdb_id
    ratings.push({
      source: 'tmdb',
      value: Math.round(tmdb * 10) / 10,
      scale: 10,
      displayValue: displayFor(tmdb, 10),
      url: tmdbId
        ? `https://www.themoviedb.org/${input.type === 'series' ? 'tv' : 'movie'}/${tmdbId}`
        : undefined,
      isVerified: true,
    })
  }

  if (imdb != null && inRange(imdb, 10)) {
    const imdbId = (input.imdb_id || '').trim()
    ratings.push({
      source: 'imdb',
      value: Math.round(imdb * 10) / 10,
      scale: 10,
      displayValue: displayFor(imdb, 10),
      url: imdbId.startsWith('tt') ? `https://www.imdb.com/title/${imdbId}/` : undefined,
      isVerified: Boolean(imdbId),
    })
  }

  if (site != null && inRange(site, 10)) {
    ratings.push({
      source: 'site',
      value: Math.round(site * 10) / 10,
      scale: 10,
      displayValue: displayFor(site, 10),
      isVerified: true,
    })
  }

  return ratings
}

export function primaryCardRating(ratings: MediaRating[]): MediaRating | null {
  const order: RatingSource[] = ['imdb', 'tmdb', 'rottentomatoes', 'metacritic', 'site']
  for (const source of order) {
    const match = ratings.find(item => item.source === source && item.source !== 'site')
    if (match) return match
  }
  return ratings.find(item => item.source !== 'site') || null
}

export function externalRatings(ratings: MediaRating[]): MediaRating[] {
  return ratings.filter(item => item.source !== 'site')
}

export function siteRating(ratings: MediaRating[]): MediaRating | null {
  return ratings.find(item => item.source === 'site') || null
}

export function formatVoteCount(count?: number): string {
  if (count == null || count <= 0) return ''
  return `${count.toLocaleString('fa-IR')} رأی`
}

export function formatScaleLabel(rating: MediaRating): string {
  const config = RATING_SOURCES[rating.source]
  if (config.suffix === '%') return ''
  return `/ ${rating.scale}`
}

export function criticTypeLabel(rating: MediaRating): string {
  if (rating.criticType === 'critics') return 'منتقدان'
  if (rating.criticType === 'audience') return 'تماشاگران'
  if (rating.criticType === 'users') return 'کاربران'
  return ''
}
