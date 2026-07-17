import type { AgeRating, CastMember, ContentFormat, ContentType, CrewMember, Genre, Movie } from '~/types'
import { getCatalogGenre } from '~/data/genres'

export interface ApiGenre {
  id: number
  title: string
  slug: string
}

interface ApiPerson {
  id: number
  name: string
  photo?: string | null
}

interface ApiEpisode {
  id: number
  title: string
  episode_number: number
  description?: string
  duration_minutes?: number | null
  poster?: string | null
  video_url?: string
  subtitle_tracks?: ApiSubtitleTrack[]
  is_published?: boolean
}

interface ApiSubtitleTrack {
  id?: string
  label?: string
  language?: string
  src?: string
  default?: boolean
}

interface ApiSeason {
  id: number
  title?: string
  season_number: number
  episode_count?: number
  episodes?: ApiEpisode[]
}

interface ApiCredit {
  id: number
  actor: ApiPerson
  role?: string
}

export interface ApiCatalogItem {
  id: number
  title: string
  slug: string
  original_title?: string
  short_description?: string
  description?: string
  release_year?: number | null
  start_year?: number | null
  duration_minutes?: number | null
  genres?: ApiGenre[]
  countries?: Array<{ name: string }>
  directors?: ApiPerson[]
  movie_actors?: ApiCredit[]
  series_actors?: ApiCredit[]
  poster?: string | null
  backdrop?: string | null
  trailer_url?: string
  video_url?: string
  download_url?: string
  subtitle_tracks?: ApiSubtitleTrack[]
  imdb_rating?: number | string | null
  site_rating?: number | string | null
  age_rating?: string
  language?: string
  content_format?: string
  is_dubbed?: boolean
  has_subtitle?: boolean
  is_published?: boolean
  is_featured?: boolean
  is_uncensored?: boolean
  content_warnings?: string[]
  view_count?: number
  like_count?: number
  created_at?: string
  seasons?: ApiSeason[]
}

export interface ApiListResponse<T> {
  results?: T[]
}

function normalizeAgeRating(value?: string): AgeRating {
  const rating = value?.replace(/[^0-9]/g, '')
  if (rating === '18') return '18+'
  if (rating === '15' || rating === '16' || rating === '17') return '15+'
  return '12+'
}

function normalizeGenres(genres: ApiGenre[] = []): Genre[] {
  return genres.map(adaptApiGenre)
}

export function adaptApiGenre(genre: ApiGenre): Genre {
  const canonical = getCatalogGenre(genre.slug)
  return {
    ...genre,
    title: canonical?.title || genre.title,
    icon: canonical?.icon || 'tag',
  }
}

function normalizeContentFormat(value?: string): ContentFormat {
  return value === 'animation' || value === 'short' ? value : 'live_action'
}

function normalizeWarnings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((warning): warning is string => typeof warning === 'string' && warning.trim().length > 0)
    : []
}

function resolvePublicMediaUrl(value: string | null | undefined, mediaBase: string, fallback: string) {
  if (!value) return fallback
  if (/^(?:https?:)?\/\//.test(value) || value.startsWith('data:') || value.startsWith('blob:')) return value
  if (!/^https?:\/\//.test(mediaBase)) return value.startsWith('/') ? value : `/media/${value}`
  try {
    return new URL(value.replace(/^\/+/, ''), `${mediaBase.replace(/\/$/, '')}/`).toString()
  } catch {
    return value
  }
}

function normalizeCast(item: ApiCatalogItem, mediaBase: string): CastMember[] {
  return [...(item.movie_actors || []), ...(item.series_actors || [])].map(credit => ({
    id: credit.id,
    name: credit.actor.name,
    role: credit.role || 'بازیگر',
    photo_url: credit.actor.photo ? resolvePublicMediaUrl(credit.actor.photo, mediaBase, credit.actor.photo) : null,
  }))
}

function normalizeCrew(directors: ApiPerson[] = []): CrewMember[] {
  return directors.map(person => ({ id: person.id, name: person.name, job: 'کارگردان' }))
}

export function unwrapApiList<T>(response: ApiListResponse<T> | T[]): T[] {
  return Array.isArray(response) ? response : response.results || []
}

export function adaptApiCatalogItem(item: ApiCatalogItem, type: ContentType, mediaBase = ''): Movie {
  const rating = Number(item.imdb_rating ?? item.site_rating ?? 0)
  const directors = item.directors || []
  const createdAt = item.created_at ? new Date(item.created_at).getTime() : 0
  const isRecent = createdAt > Date.now() - (1000 * 60 * 60 * 24 * 90)
  const episodes = (item.seasons || []).flatMap(season => (season.episodes || []).map(episode => ({
    id: episode.id,
    title: episode.title,
    episode_number: episode.episode_number,
    duration_minutes: episode.duration_minutes || 0,
    description: episode.description || '',
    season_number: season.season_number,
    thumbnail_url: resolvePublicMediaUrl(episode.poster, mediaBase, '/placeholder-poster.svg'),
    hls_url: resolvePublicMediaUrl(episode.video_url, mediaBase, ''),
  })))
  const firstPlayableEpisode = (item.seasons || []).flatMap(season => season.episodes || []).find(episode => episode.video_url)
  const hlsUrl = resolvePublicMediaUrl(item.video_url || firstPlayableEpisode?.video_url, mediaBase, '')
  const subtitleTracks = (item.subtitle_tracks || firstPlayableEpisode?.subtitle_tracks || [])
    .filter(track => Boolean(track.src))
    .map((track, index) => ({
      id: track.id || `${track.language || 'subtitle'}-${index}`,
      label: track.label || track.language || 'Subtitle',
      language: track.language || 'und',
      src: resolvePublicMediaUrl(track.src, mediaBase, ''),
      default: Boolean(track.default),
    }))

  return {
    id: item.id,
    title: item.title,
    slug: item.slug,
    original_title: item.original_title || item.title,
    description: item.description || item.short_description || 'توضیحی برای این عنوان ثبت نشده است.',
    year: item.release_year || item.start_year || new Date().getFullYear(),
    duration_minutes: item.duration_minutes || 0,
    genres: normalizeGenres(item.genres),
    country: item.countries?.map(country => country.name).join('، ') || 'ثبت نشده',
    language: item.language || 'ثبت نشده',
    director: directors[0]?.name || 'ثبت نشده',
    poster_url: resolvePublicMediaUrl(item.poster, mediaBase, '/placeholder-poster.svg'),
    backdrop_url: resolvePublicMediaUrl(item.backdrop, mediaBase, '/media/backdrop-orbit.svg'),
    trailer_url: resolvePublicMediaUrl(item.trailer_url, mediaBase, ''),
    hls_url: hlsUrl,
    rating: Number.isFinite(rating) ? rating : 0,
    age_rating: normalizeAgeRating(item.age_rating),
    is_uncensored: Boolean(item.is_uncensored),
    is_dubbed: Boolean(item.is_dubbed),
    has_subtitle: Boolean(item.has_subtitle),
    format: normalizeContentFormat(item.content_format),
    content_warnings: normalizeWarnings(item.content_warnings),
    status: 'published',
    type,
    is_trending: Boolean(item.is_featured || item.view_count),
    is_recommended: Boolean(item.is_featured),
    is_new: isRecent,
    progress_percent: 0,
    popularity: Number(item.view_count || 0) + Number(item.like_count || 0),
    cast: normalizeCast(item, mediaBase),
    crew: normalizeCrew(directors),
    recommendation_reason: item.is_featured ? 'انتخاب ویژه تحریریه' : 'بر اساس محبوبیت کاربران',
    audio_languages: item.is_dubbed ? ['دوبله فارسی', item.language || 'زبان اصلی'] : [item.language || 'زبان اصلی'],
    subtitle_languages: item.has_subtitle ? ['فارسی'] : [],
    playback: hlsUrl ? {
      hls_url: hlsUrl,
      poster_url: resolvePublicMediaUrl(item.poster, mediaBase, '/placeholder-poster.svg'),
      subtitle_tracks: subtitleTracks,
    } : undefined,
    seasons_count: item.seasons?.length,
    episodes,
  }
}
