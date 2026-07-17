import type { PlaybackSource } from './playback'
import type { CinematicIconName } from './ui'

export type AgeRating = '12+' | '15+' | '18+'
export type ContentType = 'movie' | 'series'
export type ContentStatus = 'published'
export type ContentFormat = 'live_action' | 'animation' | 'short'

export interface Genre {
  id: number
  title: string
  slug: string
  icon: CinematicIconName
}

export interface CastMember {
  id: number
  name: string
  role: string
  photo_url: string | null
}

export interface CrewMember {
  id: number
  name: string
  job: string
}

export interface Episode {
  id: number
  title: string
  episode_number: number
  duration_minutes: number
  description: string
  season_number?: number
  progress_percent?: number
  is_watched?: boolean
  thumbnail_url?: string
  hls_url?: string
}

/**
 * API-ready catalog model. The same shape is used for movies and series so
 * cards, discovery filters and recommendations stay transport-agnostic.
 */
export interface Movie {
  id: number
  title: string
  slug: string
  original_title: string
  description: string
  year: number
  duration_minutes: number
  genres: Genre[]
  country: string
  language: string
  director: string
  poster_url: string
  backdrop_url: string
  trailer_url: string
  hls_url: string
  rating: number
  age_rating: AgeRating
  is_uncensored: boolean
  is_dubbed: boolean
  has_subtitle: boolean
  format: ContentFormat
  content_warnings: string[]
  status: ContentStatus
  type: ContentType
  is_trending: boolean
  is_recommended: boolean
  is_new: boolean
  progress_percent: number
  popularity: number
  cast: CastMember[]
  crew: CrewMember[]
  recommendation_reason?: string
  audio_languages?: string[]
  subtitle_languages?: string[]
  playback?: PlaybackSource
  seasons_count?: number
  episodes?: Episode[]
}

export type CatalogItem = Movie
export type MovieListItem = Movie
export type Series = Movie
export type SeriesListItem = Movie

export interface SearchResults {
  query: string
  movies: Movie[]
  series: Movie[]
  actors: CastMember[]
}

export interface TrendingResults {
  movies: Movie[]
  series: Movie[]
}
