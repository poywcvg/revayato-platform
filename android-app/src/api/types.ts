/**
 * Raw API DTOs — mirror of the DRF serializer contracts exactly
 * (backend/apps/catalog/serializers.py). Field names are kept verbatim.
 *
 * NOTE: the backend already resolves poster/backdrop/trailer/video/subtitle
 * URLs to ABSOLUTE addresses via PublicMediaSerializer / publicize_subtitle_tracks.
 * Do not prefix a CDN base anywhere in the client.
 */

// ---------------------------------------------------------------- pagination

/** DRF LimitOffsetPagination envelope. `next`/`previous` arrive relative. */
export interface ApiPaginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ---------------------------------------------------------------------- people

export interface ApiGenre {
  id: number;
  title: string;
  slug: string;
  is_featured: boolean;
  movie_count?: number;
  series_count?: number;
  title_count?: number;
}

export interface ApiCountry {
  id: number;
  name: string; // localized (Persian) via CountrySerializer.get_name
  code: string;
  movie_count: number;
  series_count: number;
}

export interface ApiDirector {
  id: number;
  name: string;
  original_name?: string;
  slug: string;
  photo?: string | null; // absolute media URL
}

export interface ApiActor {
  id: number;
  name: string;
  original_name?: string;
  slug: string;
  photo?: string | null;
  photo_external_url?: string | null;
  birth_place?: string;
  popularity?: number;
  is_featured?: boolean;
}

export interface ApiMovieActor {
  id: number;
  role: string;
  order: number;
  actor: ApiActor;
}

export interface ApiSeriesActor {
  id: number;
  role: string;
  order: number;
  actor: ApiActor;
}

// -------------------------------------------------------------------- ratings

export interface ApiRatingSource {
  source: string;
  value: string;
  display?: string;
}

// ------------------------------------------------------------------ subtitles

/** Publicized subtitle track — `src` is an absolute WebVTT URL. */
export interface ApiSubtitleTrack {
  id: string;
  label: string;
  language: string;
  src: string;
  default: boolean;
  provider?: string;
  source_url?: string;
  season_number?: number;
  episode_number?: number;
  source_priority?: number;
  sync_confidence?: number;
}

// ------------------------------------------------------------------ downloads

export interface ApiDownloadLink {
  label: string;
  quality?: string;
  size_label?: string;
  url: string;
  kind?: string;
  subtitle_type?: string;
  season?: string;
  episode?: string;
  season_number?: number;
  episode_number?: number;
}

// --------------------------------------------------------------------- movies

export interface ApiMovieListItem {
  id: number;
  title: string;
  original_title: string;
  secondary_title: string | null;
  slug: string;
  short_description: string;
  release_year: number;
  duration_minutes: number;
  age_rating: string;
  language: string;
  content_format: string;
  is_dubbed: boolean;
  has_subtitle: boolean;
  is_uncensored: boolean;
  imdb_rating: number | null;
  imdb_rank: number | null;
  rating_average: number | null;
  site_rating: number | null;
  ratings: ApiRatingSource[];
  popularity: number;
  poster: string | null;
  backdrop: string | null;
  trailer_url: string | null;
  has_downloads: boolean;
  genres: ApiGenre[];
  directors: ApiDirector[];
  countries: ApiCountry[];
  is_published: boolean;
  is_featured: boolean;
  is_recommended: boolean;
  view_count: number;
  like_count: number;
}

export interface ApiMovieDetail extends ApiMovieListItem {
  description: string;
  content_warnings: string[];
  imdb_id: string | null;
  tmdb_id: number | null;
  video_url: string | null; // HLS master.m3u8 (absolute) — may be null
  download_url: string | null;
  download_links: ApiDownloadLink[];
  download_qualities: string[];
  quality: string;
  subtitle_tracks: ApiSubtitleTrack[];
  movie_actors: ApiMovieActor[];
  seo_title?: string;
  seo_description?: string;
  seo_keywords?: string[];
  created_at: string;
  updated_at: string;
}

// -------------------------------------------------------------------- series

export interface ApiEpisode {
  id: number;
  title: string;
  episode_number: number;
  description: string;
  duration_minutes: number;
  poster: string | null;
  video_url: string | null; // absolute HLS — may be null; download fallback exists
  trailer_url: string | null;
  download_url: string | null;
  subtitle_tracks: ApiSubtitleTrack[];
  air_date: string | null;
  is_published: boolean;
  view_count: number;
  created_at: string;
}

export interface ApiSeason {
  id: number;
  title: string;
  season_number: number;
  description: string;
  release_year: number | null;
  poster: string | null;
  tmdb_id: number | null;
  episode_count: number;
  air_date: string | null;
  episodes: ApiEpisode[];
}

export interface ApiSeriesListItem {
  id: number;
  title: string;
  original_title: string;
  secondary_title: string | null;
  slug: string;
  short_description: string;
  start_year: number;
  end_year: number | null;
  age_rating: string;
  language: string;
  content_format: string;
  is_dubbed: boolean;
  has_subtitle: boolean;
  is_uncensored: boolean;
  imdb_rating: number | null;
  imdb_rank: number | null;
  rating_average: number | null;
  site_rating: number | null;
  ratings: ApiRatingSource[];
  tmdb_id: number | null;
  popularity: number;
  poster: string | null;
  backdrop: string | null;
  trailer_url: string | null;
  has_downloads: boolean;
  genres: ApiGenre[];
  directors: ApiDirector[];
  countries: ApiCountry[];
  status: string;
  is_published: boolean;
  is_featured: boolean;
  view_count: number;
  like_count: number;
}

export interface ApiSeriesDetail extends ApiSeriesListItem {
  description: string;
  content_warnings: string[];
  imdb_id: string | null;
  download_links: ApiDownloadLink[];
  download_qualities: string[];
  series_actors: ApiSeriesActor[];
  seasons: ApiSeason[]; // backend returns only playable seasons/episodes
}

// -------------------------------------------------------------------- grouped

export interface ApiHomeRails {
  meta: {
    day: string;
    bucket: string;
    limit: number;
    eyebrow: {
      featured: string;
      dubbed: string;
      popular_series: string;
    };
  };
  featured: ApiMovieListItem[];
  dubbed: ApiMovieListItem[];
  popular_series: ApiSeriesListItem[];
}

export interface ApiTrending {
  movies: ApiMovieListItem[];
  series: ApiSeriesListItem[];
}

export interface ApiSearchResponse {
  query: string;
  search_text: string;
  year: number | null;
  match_type: 'direct' | 'similar' | 'none';
  movies: ApiMovieListItem[]; // max `limit` (default 12)
  series: ApiSeriesListItem[];
  actors: ApiActor[];
}

// ------------------------------------------------------------------ filter types

export type CatalogSort =
  | 'newest'
  | 'rating'
  | 'popular'
  | 'trending';

export type ContentType = 'movie' | 'series';

export interface CatalogFilters {
  q?: string;
  year?: number;
  genre?: string; // genre slug
  country?: string; // country code
  language?: string;
  age_rating?: string; // e.g. '18+'
  min_rating?: number;
  content_format?: 'live_action' | 'animation' | 'short';
  availability?: string;
  sort?: CatalogSort;
  limit?: number;
  offset?: number;
}
