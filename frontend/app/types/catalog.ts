import type { PlaybackSource } from './playback'
import type { CinematicIconName } from './ui'
import type { MediaRating } from './ratings'

export type AgeRating = '12+' | '15+' | '18+'
export type ContentType = 'movie' | 'series'
export type MediaType = ContentType
export type ContentStatus = 'published'
export type ContentFormat = 'live_action' | 'animation' | 'short'

export interface Genre {
  id: number
  title: string
  slug: string
  icon: CinematicIconName
  is_featured?: boolean
  /** Published movies in this genre (from API). */
  movie_count?: number
  /** Published series in this genre (from API). */
  series_count?: number
  /** movie_count + series_count when available. */
  title_count?: number
}

export interface CastMember {
  id: number
  name: string
  /** Localized (e.g. Persian) name when English is primary. */
  secondary_name?: string
  slug: string
  role: string
  photo_url?: string | null
}

export interface DownloadLink {
  label: string
  quality?: string
  size_label?: string
  url: string
  kind?: string
  subtitle_type?: string
  season?: string
  episode?: string
  season_number?: number
  episode_number?: number
}

export interface SiteActor {
  id: number
  name: string
  /** Localized (e.g. Persian) name when English is primary. */
  secondary_name?: string
  original_name?: string
  slug: string
  photo: string | null
  biography?: string
  birth_date?: string | null
  birth_place?: string
  popularity?: number
  is_featured?: boolean
}

export interface CrewMember {
  id: number
  name: string
  secondary_name?: string
  slug?: string
  job: string
  photo_url: string | null
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
  download_url?: string | null
  /** SoftSub WebVTT tracks extracted for this episode (toggleable in player). */
  subtitle_tracks?: import('./playback').PlaybackTextTrack[]
}

/**
 * API-ready catalog model. The same shape is used for movies and series so
 * cards, discovery filters and recommendations stay transport-agnostic.
 */
export interface Movie {
  id: number
  title: string
  /** Localized (e.g. Persian) title when English is primary. */
  secondary_title?: string
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
  /** @deprecated Prefer ``ratings`` — kept for filter/sort compatibility. */
  rating: number
  imdb_rating?: number | null
  /** 1–250 when on IMDb Top 250 (movies or TV chart); omitted/null otherwise. */
  imdb_rank?: number | null
  tmdb_rating?: number | null
  /** Normalized external + site ratings from the shared media model. */
  ratings: MediaRating[]
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
  /** True when poster comes from TMDB/admin import (not a local placeholder). */
  has_artwork?: boolean
  /** True when backdrop comes from TMDB/admin import (not a local placeholder). */
  has_backdrop?: boolean
  progress_percent: number
  popularity: number
  /** Platform engagement counters from the catalog API (used by discovery ranking). */
  view_count?: number
  like_count?: number
  cast: CastMember[]
  crew: CrewMember[]
  download_url?: string | null
  download_links?: DownloadLink[]
  quality?: string
  has_downloads?: boolean
  download_qualities?: string[]
  seo_title?: string
  seo_description?: string
  seo_keywords?: string[]
  recommendation_reason?: string
  audio_languages?: string[]
  subtitle_languages?: string[]
  playback?: PlaybackSource
  seasons_count?: number
  episodes?: Episode[]
  created_at?: string
  updated_at?: string
}

export type CatalogItem = Movie
export type MovieListItem = Movie
export type Series = Movie
export type SeriesListItem = Movie
/** Canonical media entity shared by cards, search, detail, and library. */
export type MediaItem = Movie

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
