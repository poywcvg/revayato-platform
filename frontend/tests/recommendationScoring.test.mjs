import assert from 'node:assert/strict'
import test from 'node:test'

import { buildBehaviorProfile, collapseBehaviorEvents, rankRecommendations } from '../app/utils/recommendationScoring.ts'

const now = Date.parse('2026-07-15T12:00:00.000Z')
const preferences = {
  favorite_genres: [],
  disliked_genres: [],
  preferred_countries: [],
  preferred_languages: [],
  playback_preference: 'any',
  content_sensitivity: 'any',
  preferred_age_ratings: [],
}

function movie(id, overrides = {}) {
  return {
    id,
    title: `عنوان ${id}`,
    slug: `title-${id}`,
    original_title: `Title ${id}`,
    description: 'داستان آزمایشی',
    year: 2026,
    duration_minutes: 110,
    genres: [{ id: 1, title: 'درام', slug: 'drama', icon: 'drama' }],
    country: 'ایران',
    language: 'فارسی',
    director: 'کارگردان آزمایشی',
    poster_url: '/poster.svg',
    backdrop_url: '/backdrop.svg',
    trailer_url: '',
    hls_url: '',
    rating: 8,
    age_rating: '12+',
    is_uncensored: false,
    is_dubbed: false,
    has_subtitle: true,
    format: 'live_action',
    content_warnings: [],
    status: 'published',
    type: 'movie',
    is_trending: false,
    is_recommended: true,
    is_new: false,
    progress_percent: 0,
    popularity: 70,
    cast: [],
    crew: [],
    ...overrides,
  }
}

test('reduced sensitivity strongly down-ranks adult uncensored content', () => {
  const safe = movie(1, { rating: 7.4, popularity: 55 })
  const adult = movie(2, {
    rating: 9.5,
    popularity: 100,
    age_rating: '18+',
    is_uncensored: true,
    content_warnings: ['خشونت', 'مواد مخدر'],
  })

  const result = rankRecommendations(
    [adult, safe],
    { ...preferences, content_sensitivity: 'reduced' },
    [],
    [],
    2,
    now,
  )

  assert.equal(result[0].item.slug, safe.slug)
  assert.match(result[0].item.recommendation_reason, /کم‌حساسیت‌تر/)
})

test('explicit genre and dubbed preferences affect ranking and reason copy', () => {
  const drama = movie(1)
  const action = movie(2, {
    genres: [{ id: 2, title: 'اکشن', slug: 'action', icon: 'action' }],
    is_dubbed: true,
    is_recommended: false,
  })

  const result = rankRecommendations(
    [drama, action],
    { ...preferences, favorite_genres: ['action'], playback_preference: 'dubbed' },
    [],
    [],
    2,
    now,
  )

  assert.equal(result[0].item.slug, action.slug)
  assert.match(result[0].item.recommendation_reason, /اکشن/)
})

test('a recent dislike down-ranks the exact item without external signals', () => {
  const disliked = movie(1, { rating: 9.2, popularity: 100 })
  const alternative = movie(2, { rating: 7.5, popularity: 50 })
  const events = [{
    event_type: 'dislike',
    title_id: disliked.id,
    title_slug: disliked.slug,
    content_type: 'movie',
    source_page: `/movies/${disliked.slug}`,
    timestamp: '2026-07-15T10:00:00.000Z',
  }]

  const result = rankRecommendations([disliked, alternative], preferences, events, [], 2, now)

  assert.equal(result[0].item.slug, alternative.slug)
})

test('aggregate demand signals contain no personal identifier dependency', () => {
  const sciFi = movie(1, { genres: [{ id: 3, title: 'علمی‌تخیلی', slug: 'sci-fi', icon: 'rocket' }] })
  const drama = movie(2)
  const signals = [{
    source: 'search_console_aggregate',
    query: 'فیلم علمی تخیلی',
    genre_slugs: ['sci-fi'],
    score: 10,
    period_start: '2026-07-01',
    period_end: '2026-07-07',
    site_scope_only: true,
  }]

  const result = rankRecommendations([drama, sciFi], preferences, [], signals, 2, now)

  assert.equal(result[0].item.slug, sciFi.slug)
})

test('repeated progress events count only the furthest meaningful watch point', () => {
  const events = [20, 70, 40].map((progress, index) => ({
    event_type: 'watch_progress',
    title_id: 1,
    title_slug: 'title-1',
    content_type: 'movie',
    progress_percent: progress,
    source_page: '/watch/title-1',
    timestamp: `2026-07-15T10:0${index}:00.000Z`,
    anonymous_session_id: 'session-one-123456',
  }))

  const collapsed = collapseBehaviorEvents(events)

  assert.equal(collapsed.length, 1)
  assert.equal(collapsed[0].progress_percent, 70)
})

test('removing a like is not treated as an explicit dislike', () => {
  const title = movie(1)
  const baseEvent = {
    title_id: title.id,
    title_slug: title.slug,
    content_type: title.type,
    source_page: `/movies/${title.slug}`,
  }
  const unlikeProfile = buildBehaviorProfile([
    { ...baseEvent, event_type: 'like', timestamp: '2026-07-15T09:00:00.000Z' },
    { ...baseEvent, event_type: 'remove_like', timestamp: '2026-07-15T10:00:00.000Z' },
  ], [title], now)
  const dislikeProfile = buildBehaviorProfile([
    { ...baseEvent, event_type: 'dislike', timestamp: '2026-07-15T10:00:00.000Z' },
  ], [title], now)

  assert.equal(unlikeProfile.disliked.has(title.slug), false)
  assert.equal(dislikeProfile.disliked.has(title.slug), true)
  assert.ok((dislikeProfile.items.get(title.slug) || 0) < (unlikeProfile.items.get(title.slug) || 0) - 50)
})

test('deep watch behavior promotes similar unseen titles over unrelated popularity', () => {
  const source = movie(1, {
    genres: [{ id: 2, title: 'اکشن', slug: 'action', icon: 'bolt' }],
    director: 'کارگردان اکشن',
  })
  const similar = movie(2, {
    rating: 7.2,
    popularity: 40,
    is_recommended: false,
    genres: [{ id: 2, title: 'اکشن', slug: 'action', icon: 'bolt' }],
    director: 'کارگردان اکشن',
  })
  const popular = movie(3, { rating: 9.4, popularity: 100 })
  const events = [{
    event_type: 'watch_progress',
    title_id: source.id,
    title_slug: source.slug,
    content_type: source.type,
    progress_percent: 90,
    source_page: `/watch/${source.slug}`,
    timestamp: '2026-07-15T10:00:00.000Z',
  }]

  const result = rankRecommendations([source, popular, similar], preferences, events, [], 3, now)

  assert.equal(result[0].item.slug, similar.slug)
  assert.match(result[0].item.recommendation_reason, /اکشن|کارگردان|حال‌وهوای/)
})

test('recent behavior has materially more influence than stale behavior', () => {
  const action = movie(1, { genres: [{ id: 2, title: 'اکشن', slug: 'action', icon: 'bolt' }] })
  const event = timestamp => ({
    event_type: 'complete_watch',
    title_id: action.id,
    title_slug: action.slug,
    content_type: action.type,
    progress_percent: 100,
    source_page: `/watch/${action.slug}`,
    timestamp,
  })

  const recent = buildBehaviorProfile([event('2026-07-15T10:00:00.000Z')], [action], now)
  const stale = buildBehaviorProfile([event('2026-05-16T10:00:00.000Z')], [action], now)

  assert.ok((recent.genres.get('action') || 0) > (stale.genres.get('action') || 0) * 10)
})

test('diversification avoids filling the whole row with near-identical titles', () => {
  const actionOne = movie(1, { genres: [{ id: 2, title: 'اکشن', slug: 'action', icon: 'bolt' }] })
  const actionTwo = movie(2, { genres: [{ id: 2, title: 'اکشن', slug: 'action', icon: 'bolt' }] })
  const drama = movie(3, { genres: [{ id: 1, title: 'درام', slug: 'drama', icon: 'masks' }] })

  const result = rankRecommendations([actionOne, actionTwo, drama], preferences, [], [], 2, now)

  assert.notEqual(result[0].item.genres[0].slug, result[1].item.genres[0].slug)
})
