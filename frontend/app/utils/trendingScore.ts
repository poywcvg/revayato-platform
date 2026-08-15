import type { Movie } from '~/types'

function log1p(value: number) {
  return Math.log(1 + Math.max(0, value))
}

function viewsOf(item: Movie) {
  return Number((item as Movie & { view_count?: number }).view_count || 0)
}

function likesOf(item: Movie) {
  return Number((item as Movie & { like_count?: number }).like_count || 0)
}

function ageHours(item: Movie, now: number, field: 'updated' | 'created' = 'updated') {
  const stamp = field === 'created'
    ? Date.parse(String(item.created_at || item.updated_at || ''))
    : Date.parse(String(item.updated_at || item.created_at || ''))
  const parsed = Number.isFinite(stamp) ? stamp : now
  return Math.max(field === 'created' ? 1 : 6, (now - parsed) / 3_600_000)
}

function ratingOf(item: Movie) {
  return Number(
    item.ratings?.find(entry => entry.source === 'imdb')?.value
    ?? item.ratings?.find(entry => entry.source === 'tmdb')?.value
    ?? item.imdb_rating
    ?? item.tmdb_rating
    ?? item.rating
    ?? 0,
  )
}

function playableBonus(item: Movie) {
  let score = 0
  if (item.is_dubbed) score += 3.5
  if (item.has_subtitle) score += 3
  if ((item.download_links || []).some(link => Boolean(link.url)) || item.has_downloads) score += 4
  if ((item.playback?.subtitle_tracks || item.subtitle_tracks || []).length) score += 2
  return score
}

function hasArtwork(item: Movie) {
  return Boolean(item.poster_url || item.backdrop_url || item.has_artwork)
}

function imdbRankBonus(item: Movie) {
  const rank = Number((item as Movie & { imdb_rank?: number }).imdb_rank || 0)
  if (!Number.isFinite(rank) || rank <= 0) return 0
  if (rank <= 50) return 6
  if (rank <= 100) return 4
  if (rank <= 250) return 2.5
  return 0
}

function engagementVelocity(item: Movie, now: number) {
  const createdHours = ageHours(item, now, 'created')
  const createdDays = Math.max(0.35, createdHours / 24)
  const viewsPerDay = viewsOf(item) / createdDays
  const likesPerDay = likesOf(item) / createdDays
  const freshnessGate = createdHours <= 24 * 10 ? 1.35 : 1
  return (log1p(viewsPerDay) * 3.2 + log1p(likesPerDay) * 4.4) * freshnessGate
}

function dailyJitter(item: Movie, now: number, salt: string, amplitude = 1.8) {
  const day = new Date(now).toISOString().slice(0, 10)
  const seed = `${salt}:${day}:${item.id}`
  let hash = 2166136261
  for (let i = 0; i < seed.length; i += 1) hash = Math.imul(hash ^ seed.charCodeAt(i), 16777619)
  const unit = (hash >>> 0) / 0xFFFFFFFF
  return (unit - 0.5) * 2 * amplitude
}

/**
 * Client-side «ترند امروز» — mirrors backend/apps/catalog/trending.py.
 */
export function trendingScore(item: Movie, now = Date.now(), recentHits = 0) {
  const createdHours = ageHours(item, now, 'created')
  const updatedHours = ageHours(item, now, 'updated')
  let score = engagementVelocity(item, now) * 1.15
    + log1p(viewsOf(item)) * 1.15
    + log1p(likesOf(item)) * 1.55
    + Number(item.popularity || 0) / 28
    + log1p(recentHits) * 5.5

  if (createdHours <= 24) score += 10
  else if (createdHours <= 24 * 3) score += 7
  else if (createdHours <= 24 * 7) score += 4.5
  else if (createdHours <= 24 * 14) score += 2.2
  else score += 6 / Math.sqrt(createdHours / 24)

  if (updatedHours <= 36 && createdHours > 48) score += 1.2

  score += playableBonus(item) * 1.05
  if (hasArtwork(item)) score += 1.6

  // Editorial is a nudge — featured alone must not own the trending rail.
  if (item.is_trending) score += 2.4
  if (item.is_recommended) score += 1.6

  const rating = ratingOf(item)
  if (rating) score += Math.max(0, (rating - 6) * 0.55)

  if (createdHours > 24 * 21 && recentHits < 2) score *= 0.82
  if (createdHours > 24 * 45 && recentHits < 1) score *= 0.88

  score += dailyJitter(item, now, 'trending', 2.2)
  return score
}

/** «منتخب‌ها» — editorial + quality + watchability with light daily rotation. */
export function featuredScore(item: Movie, now = Date.now(), recentHits = 0) {
  const createdAge = ageHours(item, now, 'created')
  let score = Number(item.popularity || 0) / 16
    + log1p(viewsOf(item)) * 0.85
    + log1p(likesOf(item)) * 1.35
    + Math.max(0, (ratingOf(item) - 5.5) * 2.8)
    + imdbRankBonus(item)
    + log1p(recentHits) * 2.2
    + playableBonus(item) * 1.05
    + 7 / Math.sqrt(Math.max(1, createdAge / 24))

  if (hasArtwork(item)) score += 2.4
  if (item.is_recommended) score += 11
  if (item.is_trending) score += 9
  if (createdAge <= 24 * 21) score += 2.8

  score += dailyJitter(item, now, 'featured', 1.4)
  return score
}

/** «محبوب» — sustained audience engagement. */
export function popularScore(item: Movie, now = Date.now(), recentHits = 0) {
  const age = ageHours(item, now)
  let score = log1p(viewsOf(item)) * 3.4
    + log1p(likesOf(item)) * 4.2
    + Number(item.popularity || 0) / 12
    + Math.max(0, (ratingOf(item) - 6) * 1.1)
    + log1p(recentHits) * 1.6
    + playableBonus(item) * 0.55

  if (item.is_trending) score += 2
  if (item.is_recommended) score += 1.5
  if (age > 24 * 45) score *= 0.9
  return score
}

export function newestTimestamp(item: Movie) {
  return Date.parse(String(item.created_at || item.updated_at || '')) || 0
}

export function rankTrending(items: readonly Movie[], limit = 12, now = Date.now()) {
  return [...items]
    .sort((a, b) => trendingScore(b, now) - trendingScore(a, now) || b.popularity - a.popularity || a.id - b.id)
    .slice(0, Math.max(0, limit))
}

export function rankFeatured(items: readonly Movie[], limit = 12, now = Date.now()) {
  return [...items]
    .sort((a, b) => featuredScore(b, now) - featuredScore(a, now) || b.popularity - a.popularity || a.id - b.id)
    .slice(0, Math.max(0, limit))
}

export function rankPopular(items: readonly Movie[], limit = 12, now = Date.now()) {
  return [...items]
    .sort((a, b) => popularScore(b, now) - popularScore(a, now) || b.popularity - a.popularity || a.id - b.id)
    .slice(0, Math.max(0, limit))
}

export function rankNewest(items: readonly Movie[], limit = 12) {
  return [...items]
    .sort((a, b) => newestTimestamp(b) - newestTimestamp(a) || b.year - a.year)
    .slice(0, Math.max(0, limit))
}
