"""TMDB HTTP client — credentials stay server-side only."""

from __future__ import annotations

import gzip
import io
import json
import logging
import time
import urllib.error
import urllib.request
from datetime import date
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class TMDBError(Exception):
    """Raised when TMDB returns an error or is unreachable."""

    def __init__(self, message, *, status_code=None, retryable=False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class TMDBClient:
    def __init__(
        self,
        *,
        token='',
        api_key='',
        api_base='',
        image_base='',
        language='fa-IR',
        fallback_language='en-US',
        region='',
        timeout=20,
        max_retries=3,
        http_proxy='',
        https_proxy='',
    ):
        self.token = (token or '').strip()
        self.api_key = (api_key or '').strip()
        self.api_base = (api_base or '').rstrip('/')
        self.image_base = (image_base or 'https://image.tmdb.org/t/p').rstrip('/')
        self.language = language or 'fa-IR'
        self.fallback_language = fallback_language or 'en-US'
        self.region = region or ''
        self.timeout = max(5, int(timeout or 20))
        self.max_retries = max(1, int(max_retries or 3))
        self.http_proxy = (http_proxy or '').strip()
        self.https_proxy = (https_proxy or http_proxy or '').strip()
        if not self.api_base:
            raise ImproperlyConfigured('TMDB_BASE_URL is required.')
        if not self.token and not self.api_key:
            raise ImproperlyConfigured(
                'Set TMDB_READ_ACCESS_TOKEN or TMDB_API_KEY on the backend.',
            )

    @property
    def uses_proxy(self):
        return bool(self.https_proxy or self.http_proxy)

    def image_url(self, path, size='w500'):
        if not path:
            return ''
        if str(path).startswith(('http://', 'https://')):
            return str(path)
        return f'{self.image_base}/{size}{path}'

    def _opener(self):
        if not self.uses_proxy:
            return urllib.request.build_opener()
        handlers = []
        if self.https_proxy:
            handlers.append(urllib.request.ProxyHandler({
                'http': self.http_proxy or self.https_proxy,
                'https': self.https_proxy,
            }))
        elif self.http_proxy:
            handlers.append(urllib.request.ProxyHandler({'http': self.http_proxy}))
        return urllib.request.build_opener(*handlers)

    def _request(self, path, params=None, *, language=None):
        query = dict(params or {})
        query.setdefault('language', language or self.language)
        if self.region:
            query.setdefault('region', self.region)
        if self.api_key and not self.token:
            query['api_key'] = self.api_key

        url = f'{self.api_base}/{path.lstrip("/")}?{urlencode(query)}'
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'RevayatoCatalog/1.0',
        }
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            request = urllib.request.Request(url, headers=headers)
            try:
                opener = self._opener()
                with opener.open(request, timeout=self.timeout) as response:  # noqa: S310
                    payload = json.loads(response.read().decode('utf-8'))
                if not isinstance(payload, dict):
                    raise TMDBError(
                        f'TMDB returned an invalid response for {path}',
                        retryable=False,
                    )
                logger.info(
                    'tmdb_request path=%s status=ok attempt=%s proxy=%s',
                    path,
                    attempt,
                    self.uses_proxy,
                )
                return payload
            except urllib.error.HTTPError as exc:
                retryable = exc.code in {408, 429, 500, 502, 503, 504}
                last_error = TMDBError(
                    f'TMDB HTTP {exc.code} for {path}',
                    status_code=exc.code,
                    retryable=retryable,
                )
                logger.warning(
                    'tmdb_request path=%s status=%s attempt=%s retryable=%s',
                    path,
                    exc.code,
                    attempt,
                    retryable,
                )
                if not retryable or attempt >= self.max_retries:
                    raise last_error from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                last_error = TMDBError(
                    f'TMDB network error for {path}: {exc.__class__.__name__}',
                    retryable=True,
                )
                logger.warning(
                    'tmdb_request path=%s error=%s attempt=%s proxy=%s',
                    path,
                    exc.__class__.__name__,
                    attempt,
                    self.uses_proxy,
                )
                if attempt >= self.max_retries:
                    raise last_error from exc
            time.sleep(min(2 ** (attempt - 1), 8))
        raise last_error or TMDBError(f'TMDB request failed for {path}')

    def search_movies(self, query, *, page=1, include_adult=False, language=None, year=None):
        query = (query or '').strip()
        if not query:
            return {'page': 1, 'results': [], 'total_pages': 0, 'total_results': 0}
        params = {
            'query': query,
            'page': max(1, int(page or 1)),
            'include_adult': 'true' if include_adult else 'false',
        }
        if year:
            params['year'] = int(year)
            params['primary_release_year'] = int(year)
        return self._request('search/movie', params, language=language)

    def search_tv(self, query, *, page=1, include_adult=False, language=None, first_air_year=None):
        query = (query or '').strip()
        if not query:
            return {'page': 1, 'results': [], 'total_pages': 0, 'total_results': 0}
        params = {
            'query': query,
            'page': max(1, int(page or 1)),
            'include_adult': 'true' if include_adult else 'false',
        }
        if first_air_year:
            params['first_air_date_year'] = int(first_air_year)
        return self._request('search/tv', params, language=language)

    def discover_movies(
        self,
        *,
        released_from,
        released_until,
        max_pages=1,
        sort_by='popularity.desc',
        with_original_language=None,
        region=None,
    ):
        for page in range(1, min(500, max(1, int(max_pages))) + 1):
            params = {
                'include_adult': 'false',
                'include_video': 'false',
                'page': page,
                'primary_release_date.gte': released_from.isoformat(),
                'primary_release_date.lte': released_until.isoformat(),
                'sort_by': sort_by or 'popularity.desc',
            }
            if with_original_language:
                params['with_original_language'] = with_original_language
            if region:
                params['region'] = region
            payload = self._request('discover/movie', params)
            for movie in payload.get('results', []):
                if movie.get('id'):
                    yield movie
            if page >= int(payload.get('total_pages') or 1):
                break

    def discover_tv(
        self,
        *,
        aired_from,
        aired_until,
        max_pages=1,
        sort_by='popularity.desc',
        with_original_language=None,
    ):
        """Yield TV shows with first_air_date in the given inclusive window."""
        for page in range(1, min(500, max(1, int(max_pages))) + 1):
            params = {
                'include_adult': 'false',
                'include_null_first_air_dates': 'false',
                'page': page,
                'first_air_date.gte': aired_from.isoformat(),
                'first_air_date.lte': aired_until.isoformat(),
                'sort_by': sort_by or 'popularity.desc',
            }
            if with_original_language:
                params['with_original_language'] = with_original_language
            payload = self._request('discover/tv', params)
            for show in payload.get('results', []):
                if show.get('id') and not show.get('adult', False):
                    yield show
            if page >= int(payload.get('total_pages') or 1):
                break

    def now_playing_movies(self, *, max_pages=1):
        for page in range(1, min(100, max(1, int(max_pages))) + 1):
            payload = self._request('movie/now_playing', {'page': page})
            for movie in payload.get('results', []):
                if movie.get('id') and not movie.get('adult', False):
                    yield movie
            if page >= int(payload.get('total_pages') or 1):
                break

    def trending_movies(self, *, window='day', max_pages=1):
        window = window if window in {'day', 'week'} else 'day'
        for page in range(1, min(20, max(1, int(max_pages))) + 1):
            payload = self._request(f'trending/movie/{window}', {'page': page})
            for movie in payload.get('results', []):
                if movie.get('id') and not movie.get('adult', False):
                    yield movie
            if page >= int(payload.get('total_pages') or 1):
                break

    def trending_tv(self, *, window='day', max_pages=1):
        window = window if window in {'day', 'week'} else 'day'
        for page in range(1, min(20, max(1, int(max_pages))) + 1):
            payload = self._request(f'trending/tv/{window}', {'page': page})
            for show in payload.get('results', []):
                if show.get('id') and not show.get('adult', False):
                    yield show
            if page >= int(payload.get('total_pages') or 1):
                break

    def popular_movies(self, *, limit=200):
        """Yield up to ``limit`` non-adult entries from TMDB movie/popular."""
        collected = 0
        page = 1
        cap = max(1, int(limit or 1))
        while collected < cap:
            payload = self._request('movie/popular', {'page': page})
            results = payload.get('results') or []
            if not results:
                break
            for movie in results:
                if movie.get('adult'):
                    continue
                if movie.get('id'):
                    yield movie
                    collected += 1
                    if collected >= cap:
                        return
            page += 1
            if page > int(payload.get('total_pages') or 1):
                break

    def popular_tv(self, *, limit=200):
        """Yield up to ``limit`` non-adult entries from TMDB tv/popular."""
        collected = 0
        page = 1
        cap = max(1, int(limit or 1))
        while collected < cap:
            payload = self._request('tv/popular', {'page': page})
            results = payload.get('results') or []
            if not results:
                break
            for show in results:
                if show.get('adult'):
                    continue
                if show.get('id'):
                    yield show
                    collected += 1
                    if collected >= cap:
                        return
            page += 1
            if page > int(payload.get('total_pages') or 1):
                break

    def top_rated_movies(self, *, limit=250, min_vote_count=1000):
        """Yield up to ``limit`` non-adult entries from TMDB movie/top_rated."""
        collected = 0
        page = 1
        cap = max(1, int(limit or 1))
        min_votes = max(0, int(min_vote_count or 0))
        while collected < cap:
            payload = self._request('movie/top_rated', {'page': page})
            results = payload.get('results') or []
            if not results:
                break
            for movie in results:
                if movie.get('adult'):
                    continue
                if min_votes and int(movie.get('vote_count') or 0) < min_votes:
                    continue
                if movie.get('id'):
                    yield movie
                    collected += 1
                    if collected >= cap:
                        return
            page += 1
            if page > int(payload.get('total_pages') or 1):
                break

    def top_rated_tv(self, *, limit=250, min_vote_count=200):
        """Yield up to ``limit`` non-adult entries from TMDB tv/top_rated."""
        collected = 0
        page = 1
        cap = max(1, int(limit or 1))
        min_votes = max(0, int(min_vote_count or 0))
        while collected < cap:
            payload = self._request('tv/top_rated', {'page': page})
            results = payload.get('results') or []
            if not results:
                break
            for show in results:
                if show.get('adult'):
                    continue
                if min_votes and int(show.get('vote_count') or 0) < min_votes:
                    continue
                if show.get('id'):
                    yield show
                    collected += 1
                    if collected >= cap:
                        return
            page += 1
            if page > int(payload.get('total_pages') or 1):
                break

    def find_by_imdb_id(self, imdb_id: str, *, language=None) -> dict:
        """Resolve an IMDb tt id to TMDB movie/tv results via /find."""
        imdb_id = (imdb_id or '').strip()
        if not imdb_id:
            return {'movie_results': [], 'tv_results': []}
        return self._request(
            f'find/{imdb_id}',
            {'external_source': 'imdb_id'},
            language=language or self.fallback_language or 'en-US',
        )

    def resolve_imdb_to_tmdb(self, imdb_id: str, *, content_type: str) -> dict | None:
        """Return the best TMDB summary for an IMDb id (movie or tv)."""
        payload = self.find_by_imdb_id(imdb_id)
        if content_type == 'series':
            results = payload.get('tv_results') or []
        else:
            results = payload.get('movie_results') or []
        for row in results:
            if isinstance(row, dict) and row.get('id'):
                return row
        return None

    def changed_movies(self, *, changed_from, changed_until, max_pages=50):
        """Yield IDs changed in TMDB's supported 14-day window."""
        for page in range(1, min(500, max(1, int(max_pages))) + 1):
            payload = self._request('movie/changes', {
                'start_date': changed_from.isoformat(),
                'end_date': changed_until.isoformat(),
                'page': page,
            })
            for movie in payload.get('results', []):
                if movie.get('id') and not movie.get('adult', False):
                    yield movie
            if page >= int(payload.get('total_pages') or 1):
                break

    def iter_movie_export(self, export_date):
        """Stream TMDB's official daily movie-ID export without loading it in RAM."""
        if not isinstance(export_date, date):
            raise ValueError('export_date must be a date')
        filename = f'movie_ids_{export_date:%m_%d_%Y}.json.gz'
        url = f'https://files.tmdb.org/p/exports/{filename}'
        headers = {
            'Accept': 'application/gzip, application/octet-stream',
            'User-Agent': 'RevayatoCatalog/1.0',
        }
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            request = urllib.request.Request(url, headers=headers)
            try:
                with self._opener().open(request, timeout=self.timeout) as response:  # noqa: S310
                    with gzip.GzipFile(fileobj=response) as compressed:
                        with io.TextIOWrapper(compressed, encoding='utf-8') as stream:
                            for line in stream:
                                if not line.strip():
                                    continue
                                payload = json.loads(line)
                                if isinstance(payload, dict) and payload.get('id'):
                                    yield payload
                logger.info(
                    'tmdb_export file=%s status=ok attempt=%s proxy=%s',
                    filename,
                    attempt,
                    self.uses_proxy,
                )
                return
            except urllib.error.HTTPError as exc:
                retryable = exc.code in {408, 429, 500, 502, 503, 504}
                last_error = TMDBError(
                    f'TMDB export HTTP {exc.code}',
                    status_code=exc.code,
                    retryable=retryable,
                )
                if not retryable or attempt >= self.max_retries:
                    raise last_error from exc
            except (
                urllib.error.URLError,
                TimeoutError,
                OSError,
                UnicodeDecodeError,
                json.JSONDecodeError,
            ) as exc:
                last_error = TMDBError(
                    f'TMDB export error: {exc.__class__.__name__}',
                    retryable=True,
                )
                if attempt >= self.max_retries:
                    raise last_error from exc
            time.sleep(min(2 ** (attempt - 1), 8))
        raise last_error or TMDBError('TMDB export failed')

    @staticmethod
    def _details_params(append: str) -> dict:
        # null = original theatrical artwork; en/fa keep localized stills available.
        return {
            'append_to_response': append,
            'include_image_language': 'null,en,fa',
        }

    def movie_details(self, movie_id, *, language=None, append='credits,videos,images,release_dates,external_ids,translations'):
        params = self._details_params(append)
        details = self._request(
            f'movie/{int(movie_id)}',
            params,
            language=language,
        )
        fallback = None
        # Always load English when the localized title is non-Latin, or for missing
        # text/trailers / CJK originals that need latinization.
        if language is None and self.fallback_language and self.fallback_language != self.language:
            from .localization import contains_cjk, contains_disallowed_catalog_script
            needs_fallback = (
                not (details.get('overview') or '').strip()
                or not (details.get('title') or '').strip()
                or not ((details.get('videos') or {}).get('results') or [])
                or contains_cjk(details.get('original_title') or '')
                or contains_disallowed_catalog_script(details.get('title') or '')
                or contains_disallowed_catalog_script(details.get('original_title') or '')
            )
            if needs_fallback:
                fallback = self._request(
                    f'movie/{int(movie_id)}',
                    params,
                    language=self.fallback_language,
                )
                for key in ('title', 'overview', 'tagline'):
                    if not (details.get(key) or '').strip() and (fallback.get(key) or '').strip():
                        details[key] = fallback[key]
                if not details.get('genres') and fallback.get('genres'):
                    details['genres'] = fallback['genres']
                if not ((details.get('videos') or {}).get('results') or []) and fallback.get('videos'):
                    details['videos'] = fallback['videos']
                # Prefer English image pack when localized append is thin.
                if not ((details.get('images') or {}).get('posters') or []) and fallback.get('images'):
                    details['images'] = fallback['images']
        from .localization import ensure_persian_metadata
        return ensure_persian_metadata(
            details,
            content_type='movie',
            english_details=fallback,
        )

    def tv_details(self, series_id, *, language=None, append='credits,videos,images,content_ratings,external_ids,translations'):
        params = self._details_params(append)
        details = self._request(
            f'tv/{int(series_id)}',
            params,
            language=language,
        )
        fallback = None
        # TMDB localizations are often incomplete; preserve localized overviews and
        # fill missing parts from English. Always fetch English when titles are non-Latin.
        if language is None and self.fallback_language and self.fallback_language != self.language:
            from .localization import contains_cjk, contains_disallowed_catalog_script
            needs_fallback = (
                not (details.get('overview') or '').strip()
                or not (details.get('name') or '').strip()
                or not ((details.get('videos') or {}).get('results') or [])
                or contains_cjk(details.get('original_name') or '')
                or contains_disallowed_catalog_script(details.get('name') or '')
                or contains_disallowed_catalog_script(details.get('original_name') or '')
            )
            if needs_fallback:
                fallback = self._request(
                    f'tv/{int(series_id)}',
                    params,
                    language=self.fallback_language,
                )
                for key in ('name', 'overview', 'tagline'):
                    if not (details.get(key) or '').strip() and (fallback.get(key) or '').strip():
                        details[key] = fallback[key]
                if not details.get('genres') and fallback.get('genres'):
                    details['genres'] = fallback['genres']
                if not ((details.get('videos') or {}).get('results') or []) and fallback.get('videos'):
                    details['videos'] = fallback['videos']
                if not ((details.get('images') or {}).get('posters') or []) and fallback.get('images'):
                    details['images'] = fallback['images']
        from .localization import ensure_persian_metadata
        return ensure_persian_metadata(
            details,
            content_type='tv',
            english_details=fallback,
        )

    def genre_list(self, *, language=None):
        return self._request('genre/movie/list', language=language)

    def person_details(self, person_id, *, language=None):
        return self._request(f'person/{int(person_id)}', language=language)

    def configuration(self):
        return self._request('configuration', {}, language=self.language)

    def certification(self, details):
        results = ((details.get('release_dates') or {}).get('results') or [])
        by_region = {item.get('iso_3166_1'): item.get('release_dates') or [] for item in results}
        for region in (self.region, 'US', 'GB'):
            if not region:
                continue
            for item in by_region.get(region, []):
                value = (item.get('certification') or '').strip()
                if value:
                    return value
        return ''

    def content_rating(self, details):
        results = ((details.get('content_ratings') or {}).get('results') or [])
        by_region = {item.get('iso_3166_1'): (item.get('rating') or '').strip() for item in results}
        for region in (self.region, 'US', 'GB'):
            if region and by_region.get(region):
                return by_region[region]
        return ''

    @staticmethod
    def official_trailer(details):
        videos = ((details.get('videos') or {}).get('results') or [])
        candidates = [item for item in videos if item.get('site') == 'YouTube' and item.get('type') in {'Trailer', 'Teaser'}]
        candidates.sort(key=lambda item: (
            item.get('type') == 'Trailer', bool(item.get('official')), item.get('published_at') or '',
        ), reverse=True)
        return candidates[0] if candidates else None

    def preview_movie(self, movie_id):
        details = self.movie_details(movie_id)
        videos = ((details.get('videos') or {}).get('results') or [])
        trailer = self.official_trailer(details)
        return {
            'content_type': 'movie',
            'tmdb_id': details.get('id'),
            'title': details.get('title') or details.get('original_title'),
            'original_title': details.get('original_title'),
            'overview': details.get('overview') or '',
            'tagline': details.get('tagline') or '',
            'release_date': details.get('release_date') or '',
            'runtime': details.get('runtime'),
            'original_language': details.get('original_language') or '',
            'spoken_languages': details.get('spoken_languages') or [],
            'genres': details.get('genres') or [],
            'production_countries': details.get('production_countries') or [],
            'production_companies': details.get('production_companies') or [],
            'certification': self.certification(details),
            'imdb_id': ((details.get('external_ids') or {}).get('imdb_id') or ''),
            'vote_average': details.get('vote_average'),
            'vote_count': details.get('vote_count'),
            'popularity': details.get('popularity'),
            'poster_path': details.get('poster_path'),
            'backdrop_path': details.get('backdrop_path'),
            'poster_url': self.image_url(details.get('poster_path'), 'w500'),
            'backdrop_url': self.image_url(details.get('backdrop_path'), 'w1280'),
            'trailer_youtube_key': (trailer or {}).get('key') or '',
            'cast': [
                {
                    'name': item.get('name'),
                    'character': item.get('character'),
                    'order': item.get('order'),
                    'profile_url': self.image_url(item.get('profile_path'), 'w185'),
                    'profile_path': item.get('profile_path'),
                    'tmdb_id': item.get('id'),
                }
                for item in ((details.get('credits') or {}).get('cast') or [])[:12]
            ],
            'crew': [
                {
                    'name': item.get('name'),
                    'job': item.get('job'),
                    'department': item.get('department'),
                    'tmdb_id': item.get('id'),
                    'profile_path': item.get('profile_path'),
                    'profile_url': self.image_url(item.get('profile_path'), 'w185'),
                }
                for item in ((details.get('credits') or {}).get('crew') or [])
                if item.get('job') in {'Director', 'Writer', 'Screenplay'}
            ][:12],
            'already_imported': False,
        }

    def preview_tv(self, series_id):
        details = self.tv_details(series_id)
        trailer = self.official_trailer(details)
        episode_runtime = details.get('episode_run_time') or []
        return {
            'content_type': 'series',
            'tmdb_id': details.get('id'),
            'title': details.get('name') or details.get('original_name'),
            'original_title': details.get('original_name'),
            'overview': details.get('overview') or '',
            'tagline': details.get('tagline') or '',
            'release_date': details.get('first_air_date') or '',
            'runtime': episode_runtime[0] if episode_runtime else None,
            'original_language': details.get('original_language') or '',
            'genres': details.get('genres') or [],
            'certification': self.content_rating(details),
            'imdb_id': ((details.get('external_ids') or {}).get('imdb_id') or ''),
            'vote_average': details.get('vote_average'),
            'vote_count': details.get('vote_count'),
            'popularity': details.get('popularity'),
            'poster_path': details.get('poster_path'),
            'backdrop_path': details.get('backdrop_path'),
            'poster_url': self.image_url(details.get('poster_path'), 'w500'),
            'backdrop_url': self.image_url(details.get('backdrop_path'), 'w1280'),
            'trailer_youtube_key': (trailer or {}).get('key') or '',
            'season_count': details.get('number_of_seasons') or 0,
            'episode_count': details.get('number_of_episodes') or 0,
            'status': details.get('status') or '',
            'cast': [
                {
                    'name': item.get('name'),
                    'character': item.get('character'),
                    'order': item.get('order'),
                    'profile_url': self.image_url(item.get('profile_path'), 'w185'),
                    'profile_path': item.get('profile_path'),
                    'tmdb_id': item.get('id'),
                }
                for item in ((details.get('credits') or {}).get('cast') or [])[:12]
            ],
            'crew': [
                {
                    'name': item.get('name'),
                    'job': item.get('job'),
                    'department': item.get('department'),
                    'tmdb_id': item.get('id'),
                    'profile_path': item.get('profile_path'),
                    'profile_url': self.image_url(item.get('profile_path'), 'w185'),
                }
                for item in ((details.get('credits') or {}).get('crew') or [])
                if item.get('job') in {'Director', 'Writer', 'Screenplay', 'Executive Producer'}
            ][:12],
            'already_imported': False,
        }


def configured_tmdb_client():
    from .importer_config import get_importer_settings

    importer = get_importer_settings()
    proxy_url = getattr(settings, 'TMDB_PROXY_URL', '')
    return TMDBClient(
        token=getattr(settings, 'TMDB_READ_ACCESS_TOKEN', ''),
        api_key=getattr(settings, 'TMDB_API_KEY', ''),
        api_base=getattr(settings, 'TMDB_BASE_URL', ''),
        image_base=getattr(settings, 'TMDB_IMAGE_BASE_URL', 'https://image.tmdb.org/t/p'),
        language=importer.language,
        fallback_language=importer.fallback_language,
        region=importer.region,
        timeout=getattr(settings, 'TMDB_TIMEOUT_SECONDS', 20),
        max_retries=getattr(settings, 'TMDB_MAX_RETRIES', 3),
        http_proxy=proxy_url or getattr(settings, 'TMDB_HTTP_PROXY', ''),
        https_proxy=proxy_url or getattr(settings, 'TMDB_HTTPS_PROXY', ''),
    )
