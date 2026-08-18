/**
 * App-level catalog model + adapter from raw API DTOs.
 *
 * The shape mirrors the web app's `Movie` type and `catalogAdapter.ts`, so any
 * future shared types / screens stay familiar. Unlike the web adapter we do NOT
 * pipe a CDN base into URLs — the backend already resolves them absolutely.
 */
import {firstPlayable, isPlaceholderPoster, normalizeMediaUrl} from '../utils/url';
import type {
  ApiEpisode,
  ApiMovieDetail,
  ApiMovieListItem,
  ApiSeriesDetail,
  ApiSeriesListItem,
  ApiSubtitleTrack,
} from '../api/types';

export type MediaType = 'movie' | 'series';

export interface AppGenre {
  id: number;
  title: string;
  slug: string;
  is_featured: boolean;
}

export interface AppActor {
  id: number;
  name: string;
  slug: string;
  role?: string;
  photo_url: string;
}

export interface AppSubtitleTrack {
  id: string;
  label: string;
  language: string;
  src: string;
  default: boolean;
}

export interface AppDownloadLink {
  label: string;
  quality?: string;
  size_label?: string;
  url: string;
  kind?: string;
}

export interface AppEpisode {
  id: number;
  title: string;
  episode_number: number;
  season_number: number;
  duration_minutes: number;
  description: string;
  poster_url: string;
  hls_url: string; // firstPlayable(video_url, download_url)
  subtitle_tracks: AppSubtitleTrack[];
}

export interface AppMedia {
  id: number;
  type: MediaType;
  title: string;
  secondary_title: string;
  original_title: string;
  slug: string;
  description: string;
  short_description: string;
  year: number;
  end_year: number | null;
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
  is_featured: boolean;
  poster_url: string;
  backdrop_url: string;
  trailer_url: string;
  hls_url: string; // movie: video_url (fallback download mirror)
  subtitle_tracks: AppSubtitleTrack[]; // movies: detail tracks; list/series: []
  download_links: AppDownloadLink[];
  genres: AppGenre[];
  directors: AppActor[];
  countries: {id: number; name: string; code: string}[];
  cast: AppActor[];
  seasons: AppSeason[]; // movies: []
  view_count: number;
  like_count: number;
}

export interface AppSeason {
  id: number;
  title: string;
  season_number: number;
  release_year: number | null;
  description: string;
  poster_url: string;
  episodes: AppEpisode[];
}

function adaptGenre(g: ApiMovieListItem['genres'][number]): AppGenre {
  return {id: g.id, title: g.title, slug: g.slug, is_featured: Boolean(g.is_featured)};
}

function adaptDirector(d: ApiMovieListItem['directors'][number]): AppActor {
  return {id: d.id, name: d.name, slug: d.slug, photo_url: normalizeMediaUrl(d.photo)};
}

function adaptSubtitle(t: ApiSubtitleTrack): AppSubtitleTrack {
  return {
    id: t.id,
    label: t.label,
    language: t.language,
    src: normalizeMediaUrl(t.src),
    default: Boolean(t.default),
  };
}

function adaptDownloadLink(
  l: ApiMovieDetail['download_links'][number],
): AppDownloadLink {
  return {
    label: l.label,
    quality: l.quality,
    size_label: l.size_label,
    url: normalizeMediaUrl(l.url),
    kind: l.kind,
  };
}

function adaptCast(ma: ApiMovieDetail['movie_actors'][number]): AppActor {
  return {
    id: ma.actor.id,
    name: ma.actor.name,
    slug: ma.actor.slug,
    role: ma.role,
    photo_url: normalizeMediaUrl(ma.actor.photo),
  };
}

function posterOrBlank(url: string | null | undefined): string {
  const normalized = normalizeMediaUrl(url);
  return isPlaceholderPoster(normalized) ? '' : normalized;
}

/** Card/list rows — the detail payload supplies playback fields. */
export function adaptListMovie(m: ApiMovieListItem): AppMedia {
  return {
    id: m.id,
    type: 'movie',
    title: m.title,
    secondary_title: m.secondary_title ?? '',
    original_title: m.original_title ?? '',
    slug: m.slug,
    description: m.short_description ?? '',
    short_description: m.short_description ?? '',
    year: m.release_year,
    end_year: null,
    duration_minutes: m.duration_minutes,
    age_rating: m.age_rating ?? '',
    language: m.language ?? '',
    content_format: m.content_format ?? '',
    is_dubbed: m.is_dubbed,
    has_subtitle: m.has_subtitle,
    is_uncensored: m.is_uncensored,
    imdb_rating: m.imdb_rating ?? null,
    imdb_rank: m.imdb_rank ?? null,
    rating_average: m.rating_average ?? null,
    is_featured: m.is_featured,
    poster_url: posterOrBlank(m.poster),
    backdrop_url: posterOrBlank(m.backdrop),
    trailer_url: normalizeMediaUrl(m.trailer_url),
    hls_url: '',
    subtitle_tracks: [],
    download_links: [],
    genres: (m.genres ?? []).map(adaptGenre),
    directors: (m.directors ?? []).map(adaptDirector),
    countries: (m.countries ?? []).map(c => ({id: c.id, name: c.name, code: c.code})),
    cast: [],
    seasons: [],
    view_count: m.view_count,
    like_count: m.like_count,
  };
}

export function adaptListSeries(s: ApiSeriesListItem): AppMedia {
  const base = adaptListMovie(s as unknown as ApiMovieListItem);
  return {
    ...base,
    type: 'series',
    title: s.title,
    secondary_title: s.secondary_title ?? '',
    original_title: s.original_title ?? '',
    slug: s.slug,
    description: s.short_description ?? '',
    short_description: s.short_description ?? '',
    year: s.start_year,
    end_year: s.end_year ?? null,
    poster_url: posterOrBlank(s.poster),
    backdrop_url: posterOrBlank(s.backdrop),
    trailer_url: normalizeMediaUrl(s.trailer_url),
    genres: (s.genres ?? []).map(adaptGenre),
    directors: (s.directors ?? []).map(adaptDirector),
    countries: (s.countries ?? []).map(c => ({id: c.id, name: c.name, code: c.code})),
  };
}

export function adaptDetail(m: ApiMovieDetail): AppMedia {
  return {
    ...adaptListMovie(m),
    description: m.description || m.short_description || '',
    cast: (m.movie_actors ?? []).map(adaptCast),
    hls_url: firstPlayable(m.video_url, m.download_url, m.download_links?.[0]?.url),
    subtitle_tracks: (m.subtitle_tracks ?? []).map(adaptSubtitle),
    download_links: (m.download_links ?? []).map(adaptDownloadLink),
  };
}

function adaptEpisode(ep: ApiEpisode, seasonNumber: number): AppEpisode {
  return {
    id: ep.id,
    title: ep.title,
    episode_number: ep.episode_number,
    season_number: seasonNumber,
    duration_minutes: ep.duration_minutes,
    description: ep.description ?? '',
    poster_url: posterOrBlank(ep.poster),
    hls_url: firstPlayable(ep.video_url, ep.download_url),
    subtitle_tracks: (ep.subtitle_tracks ?? []).map(adaptSubtitle),
  };
}

export function adaptSeriesDetail(s: ApiSeriesDetail): AppMedia {
  return {
    ...adaptListSeries(s),
    description: s.description || s.short_description || '',
    cast: (s.series_actors ?? []).map(sa => ({
      id: sa.actor.id,
      name: sa.actor.name,
      slug: sa.actor.slug,
      role: sa.role,
      photo_url: normalizeMediaUrl(sa.actor.photo),
    })),
    download_links: (s.download_links ?? []).map(adaptDownloadLink),
    seasons: (s.seasons ?? []).map(season => ({
      id: season.id,
      title: season.title,
      season_number: season.season_number,
      release_year: season.release_year,
      description: season.description ?? '',
      poster_url: posterOrBlank(season.poster),
      episodes: (season.episodes ?? []).map(ep => adaptEpisode(ep, season.season_number)),
    })),
  };
}
