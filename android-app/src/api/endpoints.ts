/**
 * Typed endpoint functions — one function per backend route.
 * All URLs/props mirror `backend/config/urls.py` + serializer contracts.
 */
import {get, getRapid} from './client';
import type {
  ApiActor,
  ApiCountry,
  ApiGenre,
  ApiHomeRails,
  ApiMovieDetail,
  ApiMovieListItem,
  ApiPaginated,
  ApiSearchResponse,
  ApiSeriesDetail,
  ApiSeriesListItem,
  ApiTrending,
  CatalogFilters,
} from './types';

function asParams(filters: CatalogFilters): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null || value === '') {continue;}
    out[key] = value as string | number;
  }
  return out;
}

// ------------------------------------------------------------------- catalog

export function listMovies(filters: CatalogFilters = {}): Promise<ApiPaginated<ApiMovieListItem>> {
  const query = asParams({
    limit: 20,
    sort: 'newest',
    ...filters,
  });
  return get<ApiPaginated<ApiMovieListItem>>('/movies/', {query});
}

export function getMovie(slug: string): Promise<ApiMovieDetail> {
  return get<ApiMovieDetail>(`/movies/${encodeURIComponent(slug)}/`, {
    timeout: 12_000,
  });
}

export function getMovieSimilar(
  slug: string,
  limit = 12,
): Promise<ApiPaginated<ApiMovieListItem>> {
  return get<ApiPaginated<ApiMovieListItem>>(
    `/movies/${encodeURIComponent(slug)}/similar/`,
    {query: {limit}},
  );
}

export function listSeries(filters: CatalogFilters = {}): Promise<ApiPaginated<ApiSeriesListItem>> {
  const query = asParams({limit: 20, sort: 'newest', ...filters});
  return get<ApiPaginated<ApiSeriesListItem>>('/series/', {query});
}

export function getSeries(slug: string): Promise<ApiSeriesDetail> {
  return get<ApiSeriesDetail>(`/series/${encodeURIComponent(slug)}/`, {
    timeout: 12_000,
  });
}

export function getSeriesSimilar(
  slug: string,
  limit = 12,
): Promise<ApiPaginated<ApiSeriesListItem>> {
  return get<ApiPaginated<ApiSeriesListItem>>(
    `/series/${encodeURIComponent(slug)}/similar/`,
    {query: {limit}},
  );
}

// ---------------------------------------------------------------- discovery

export function getHomeRails(limit = 7): Promise<ApiHomeRails> {
  return getRapid<ApiHomeRails>('/home/rails/', {limit});
}

export function getTrending(
  type: 'all' | 'movie' | 'series' = 'all',
  limit = 20,
): Promise<ApiTrending> {
  return get<ApiTrending>('/trending/', {query: {type, limit}});
}

export function listGenres(): Promise<ApiGenre[]> {
  return get<ApiGenre[]>('/genres/');
}

export function listCountries(): Promise<ApiCountry[]> {
  return get<ApiCountry[]>('/countries/');
}

// ----------------------------------------------------------------- search

export function searchContent(
  q: string,
  type: 'all' | 'movie' | 'series' | 'actor' = 'all',
  limit = 12,
): Promise<ApiSearchResponse> {
  return get<ApiSearchResponse>('/search/', {query: {q, type, limit}});
}

// ------------------------------------------------------------------- people

export function listActors(): Promise<ApiPaginated<ApiActor>> {
  return get<ApiPaginated<ApiActor>>('/actors/', {query: {limit: 50}});
}

export function getActor(slug: string): Promise<ApiActor & {movies: ApiMovieListItem[]; series: ApiSeriesListItem[]}> {
  return get(`/actors/${encodeURIComponent(slug)}/`, {timeout: 12_000});
}
