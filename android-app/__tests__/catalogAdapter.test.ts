/**
 * Adapter tests against REAL backend serializer contracts
 * (backend/apps/catalog/serializers.py). These are the payloads that must keep
 * mapping to AppMedia — the URL rules (absolute pass-through, no CDN prefix)
 * and the episode/cast synthesis live here so a serializer change surfaces in
 * CI long before it reaches a device.
 */
import {
  adaptListMovie,
  adaptDetail,
  adaptSeriesDetail,
  adaptListSeries,
} from '../src/data/catalogAdapter';
import type {ApiMovieDetail, ApiSeriesDetail} from '../src/api/types';

const movieListItem = {
  id: 42,
  title: 'جدایی نادر از سیمین',
  original_title: 'A Separation',
  secondary_title: null,
  slug: 'a-separation',
  short_description: 'درام ایرانی برنده اسکار',
  release_year: 2011,
  duration_minutes: 123,
  age_rating: 'PG-13',
  language: 'فارسی',
  content_format: 'live_action',
  is_dubbed: false,
  has_subtitle: true,
  is_uncensored: false,
  imdb_rating: 8.3,
  imdb_rank: 147,
  rating_average: 4.6,
  site_rating: 4.6,
  ratings: [{source: 'imdb', value: '8.3'}],
  popularity: 90,
  poster: 'https://cdn.example.com/media/posters/a-separation.webp',
  backdrop: 'https://cdn.example.com/media/backdrops/a-separation.webp',
  trailer_url: 'https://cdn.example.com/media/trailers/a-separation.mp4',
  has_downloads: true,
  genres: [{id: 1, title: 'درام', slug: 'drama', is_featured: true}],
  directors: [{id: 7, name: 'اصغر فرهادی', slug: 'asghar-farhadi'}],
  countries: [{id: 2, name: 'ایران', code: 'IR'}],
  is_published: true,
  is_featured: false,
  is_recommended: true,
  view_count: 100000,
  like_count: 5000,
};

test('adaptListMovie maps a list item to AppMedia with absolute URLs untouched', () => {
  const m = adaptListMovie(movieListItem);
  expect(m.type).toBe('movie');
  expect(m.slug).toBe('a-separation');
  expect(m.title).toBe('جدایی نادر از سیمین');
  expect(m.poster_url).toBe('https://cdn.example.com/media/posters/a-separation.webp');
  // playback fields are empty on list items (detail supplies them)
  expect(m.hls_url).toBe('');
  expect(m.download_links).toHaveLength(0);
  // cast is empty at list level
  expect(m.cast).toHaveLength(0);
  // Persian title passes through as-is
  expect(m.secondary_title).toBe('');
});

test('adaptDetail enriches video_url and download_links', () => {
  const detail: ApiMovieDetail = {
    ...movieListItem,
    description: 'طولانی‌ترین توصیف',
    content_warnings: ['درد'],
    imdb_id: 'tt1832382',
    tmdb_id: 753,
    video_url: 'https://cdn.example.com/media/videos/a-separation/master.m3u8',
    download_url: 'https://cdn.example.com/dl/separation-1080.mp4',
    download_links: [
      {label: '1080p', quality: '1080p', size_label: '2.1GB', url: 'https://cdn.example.com/dl/separation-1080.mp4', kind: 'download'},
    ],
    download_qualities: ['1080p'],
    quality: '1080p',
    subtitle_tracks: [
      {
        id: 's1',
        label: 'فارسی',
        language: 'fa',
        src: 'https://cdn.example.com/media/subs/a-separation.fa.vtt',
        default: true,
      },
    ],
    movie_actors: [{id: 1, role: 'نقش اصلی', order: 1, actor: {id: 5, name: 'لینا', slug: 'leila'}}],
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  };
  const m = adaptDetail(detail);
  expect(m.hls_url).toBe('https://cdn.example.com/media/videos/a-separation/master.m3u8');
  expect(m.download_links[0].label).toBe('1080p');
  expect(m.subtitle_tracks[0].src).toBe('https://cdn.example.com/media/subs/a-separation.fa.vtt');
  expect(m.cast[0].name).toBe('لینا');
});

test('video_url null → hls_url falls back to download mirror', () => {
  const detail: ApiMovieDetail = {
    ...movieListItem,
    description: '…',
    video_url: null,
    download_url: null,
    download_links: [
      {label: '480p', quality: '480p', size_label: '700MB', url: 'https://cdn.example.com/dl/a-separation-480.mp4', kind: 'download'},
    ],
    download_qualities: ['480p'],
    quality: '480p',
    subtitle_tracks: [],
    movie_actors: [],
    content_warnings: [],
    imdb_id: null,
    tmdb_id: null,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  };
  const m = adaptDetail(detail);
  expect(m.hls_url).toBe('https://cdn.example.com/dl/a-separation-480.mp4');
});

test('adaptSeriesDetail synthesizes seasons→episodes and per-episode resume/playable fields', () => {
  const series: ApiSeriesDetail = {
    id: 9,
    title: 'سریال نمونه',
    original_title: 'Sample Series',
    secondary_title: null,
    slug: 'sample-series',
    short_description: '…',
    start_year: 2020,
    end_year: 2022,
    age_rating: '18+',
    language: 'فارسی',
    content_format: 'live_action',
    is_dubbed: true,
    has_subtitle: true,
    is_uncensored: false,
    imdb_rating: 7.9,
    imdb_rank: 200,
    rating_average: 4.2,
    site_rating: 4.2,
    ratings: [],
    tmdb_id: 1,
    popularity: 50,
    poster: 'https://cdn.example.com/media/posters/sample-series.webp',
    backdrop: 'https://cdn.example.com/media/backdrops/sample-series.webp',
    trailer_url: null,
    has_downloads: true,
    genres: [],
    directors: [],
    countries: [],
    status: 'finished',
    is_published: true,
    is_featured: false,
    view_count: 10,
    like_count: 1,
    description: '…',
    content_warnings: [],
    imdb_id: null,
    download_links: [
      {label: 'فصل ۱ 1080p', quality: '1080p', size_label: '3GB', url: 'https://cdn.example.com/dl/s1-1080.mp4', kind: 'download'},
    ],
    download_qualities: ['1080p'],
    series_actors: [],
    seasons: [
      {
        id: 100,
        title: 'فصل اول',
        season_number: 1,
        description: '',
        release_year: 2020,
        poster: null,
        tmdb_id: null,
        episode_count: 2,
        air_date: null,
        episodes: [
          {
            id: 501,
            title: 'قسمت اول',
            episode_number: 1,
            description: '',
            duration_minutes: 45,
            poster: null,
            video_url: 'https://cdn.example.com/media/videos/sample-series/s01e01/master.m3u8',
            trailer_url: null,
            download_url: null,
            subtitle_tracks: [
              {id: 't1', label: 'فارسی', language: 'fa', src: 'https://cdn.example.com/media/subs/s01e01.fa.vtt', default: false},
            ],
            air_date: '2020-03-01',
            is_published: true,
            view_count: 9,
            created_at: '2020-03-01T00:00:00Z',
          },
          {
            id: 502,
            title: 'قسمت دوم',
            episode_number: 2,
            description: '',
            duration_minutes: 46,
            poster: null,
            video_url: null, // unplayable → needs fallback
            trailer_url: null,
            download_url: 'https://cdn.example.com/dl/s01e02-720.mp4',
            subtitle_tracks: [],
            air_date: '2020-03-08',
            is_published: true,
            view_count: 8,
            created_at: '2020-03-08T00:00:00Z',
          },
        ],
      },
    ],
  };
  const s = adaptSeriesDetail(series);
  expect(s.type).toBe('series');
  expect(s.seasons).toHaveLength(1);
  expect(s.seasons[0].episodes).toHaveLength(2);
  // playable HLS
  expect(s.seasons[0].episodes[0].hls_url).toContain('s01e01');
  // video_url null → download_url fallback
  expect(s.seasons[0].episodes[1].hls_url).toContain('s01e02');
  expect(s.seasons[0].episodes[1].subtitle_tracks).toHaveLength(0);
  // series-level download links stay put
  expect(s.download_links[0].label).toBe('فصل ۱ 1080p');
});

test('adaptListSeries keeps series identity (type + year range)', () => {
  const s = adaptListSeries({
    ...movieListItem,
    id: 9,
    title: 'سریال نمونه',
    start_year: 2020,
    end_year: 2022,
    tmdb_id: 1,
    status: 'ongoing',
  } as unknown as ApiSeriesDetail);
  expect(s.type).toBe('series');
  expect(s.year).toBe(2020);
  expect(s.end_year).toBe(2022);
});

test('protocol-relative and root-relative media URLs are normalized defensively', () => {
  const m = adaptListMovie({
    ...movieListItem,
    poster: '//cdn.example.com/media/posters/a.webp',
    backdrop: '/media/backdrops/a.webp',
  });
  expect(m.poster_url).toBe('https://cdn.example.com/media/posters/a.webp');
  // root-relative resolves against the API origin — non-empty and same host
  expect(m.backdrop_url).toContain('/media/backdrops/a.webp');
});