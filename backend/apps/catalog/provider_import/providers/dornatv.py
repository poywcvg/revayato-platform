"""Dornatv (dornatv.com) public catalog + download-link crawler.

WordPress BartarTheme — movies and series are both posts (categories 27/28).
Public HTML embeds direct CDN URLs (dlyar.top). Online play uses the same CDN.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from urllib.parse import quote_plus, urljoin, urlsplit

from django.conf import settings

from ..base import ProviderAuthResult, ProviderMovie, ProviderSeries
from ..exceptions import ProviderImportError, ProviderNotConfigured, ProviderRateLimited
from ..sanitizers import sanitize_payload
from .dornatv_parser import (
    MOVIE_CATEGORY_IDS,
    SERIES_CATEGORY_IDS,
    build_slug_candidates,
    normalize_detail_path,
    parse_download_links,
    parse_search_results,
    parse_wp_rest_item,
    slugify_title,
)

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None


@dataclass
class ProviderTitleCandidate:
    provider_item_id: str
    content_type: str
    title: str = ''
    original_title: str = ''
    year: int | None = None
    tmdb_id: int | None = None
    imdb_id: str = ''
    sanitized_metadata: dict = field(default_factory=dict)

    def to_public_dict(self):
        return {
            'provider_item_id': self.provider_item_id,
            'content_type': self.content_type,
            'title': self.title,
            'original_title': self.original_title,
            'year': self.year,
            'tmdb_id': self.tmdb_id,
            'imdb_id': self.imdb_id,
            'sanitized_metadata': sanitize_payload(self.sanitized_metadata),
        }


class DornatvConnector:
    slug = 'dornatv'

    def __init__(self, provider_source=None):
        self.provider = provider_source
        self.base_url = getattr(settings, 'DORNATV_BASE_URL', 'https://dornatv.com').rstrip('/')
        self.timeout = int(getattr(settings, 'DORNATV_TIMEOUT_SECONDS', 30))
        self.rate_limit = max(1, int(getattr(settings, 'DORNATV_RATE_LIMIT_PER_MINUTE', 30)))
        self.verify_ssl = bool(getattr(settings, 'DORNATV_VERIFY_SSL', True))
        self.user_agent = getattr(
            settings,
            'DORNATV_USER_AGENT',
            'RevayatoCatalogCrawler/1.0 (+https://revayato.ir)',
        )
        self.max_results = int(getattr(settings, 'DORNATV_MAX_RESULTS_PER_LOOKUP', 20))
        self.rest_per_page = max(1, min(100, int(getattr(settings, 'DORNATV_REST_PER_PAGE', 100))))
        self._last_request_at = 0.0
        self._client = None

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None

    def _ensure_httpx(self):
        if httpx is None:
            raise ProviderNotConfigured('httpx is required for the dornatv connector.')

    def _client_or_create(self):
        self._ensure_httpx()
        if self._client is None:
            read_timeout = max(float(self.timeout), 90.0)
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(read_timeout, connect=min(30.0, read_timeout)),
                follow_redirects=True,
                verify=self.verify_ssl,
                headers={
                    'User-Agent': self.user_agent,
                    'Accept': 'text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'fa-IR,fa;q=0.9,en;q=0.8',
                    'Accept-Encoding': 'identity',
                },
            )
        return self._client

    def _throttle(self):
        minimum = 60.0 / float(self.rate_limit)
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < minimum:
            time.sleep(minimum - elapsed)

    def _absolute_url(self, path: str) -> str:
        if path.startswith('http://') or path.startswith('https://'):
            return path
        return urljoin(self.base_url + '/', path.lstrip('/'))

    def _request(self, method: str, path: str, **kwargs):
        self._throttle()
        client = self._client_or_create()
        self._last_request_at = time.monotonic()
        try:
            response = client.request(method, path, **kwargs)
        except Exception as exc:  # pragma: no cover
            raise ProviderImportError(
                f'dornatv request failed: {exc}',
                code='dornatv_request_failed',
            ) from exc
        if response.status_code == 429:
            raise ProviderRateLimited('Dornatv rate-limited the crawler.')
        return response

    def validate_credentials(self) -> ProviderAuthResult:
        try:
            response = self._request('GET', '/')
            text = (response.text or '').lower()
            ok = response.status_code < 400 and (
                'bartartheme' in text or 'dornatv' in text or 'درنا' in (response.text or '')
            )
            return ProviderAuthResult(
                ok=ok,
                message='Dornatv public catalog reachable.' if ok else 'Dornatv home page unexpected.',
                auth_type='public',
                sanitized_details={'http_status': response.status_code, 'base_url': self.base_url},
            )
        except Exception as exc:
            return ProviderAuthResult(ok=False, message=str(exc)[:200], auth_type='public')

    def authenticate(self) -> ProviderAuthResult:
        return self.validate_credentials()

    def _rest_list(self, endpoint: str, *, page: int = 1, search: str = '', embed: bool = False) -> tuple[list[dict], dict]:
        params = {
            'per_page': self.rest_per_page,
            'page': max(1, int(page or 1)),
            'orderby': 'modified',
            'order': 'desc',
            'status': 'publish',
        }
        if search:
            params['search'] = search
        if embed:
            params['_embed'] = '1'
        query = '&'.join(f'{k}={quote_plus(str(v))}' for k, v in params.items())
        path = f'/wp-json/wp/v2/{endpoint}?{query}'
        response = self._request('GET', path)
        if response.status_code >= 400:
            raise ProviderImportError(
                f'dornatv REST {endpoint} HTTP {response.status_code}',
                code='dornatv_http_error',
            )
        try:
            rows = response.json()
        except Exception as exc:
            raise ProviderImportError(
                'dornatv REST response was not JSON.',
                code='dornatv_bad_json',
            ) from exc
        if not isinstance(rows, list):
            rows = []
        meta = {
            'total': int(response.headers.get('X-WP-Total') or 0),
            'total_pages': int(response.headers.get('X-WP-TotalPages') or 0),
            'page': params['page'],
        }
        return rows, meta

    def resolve_release_term_id(self, year: int) -> int | None:
        """Map a calendar year to Dornatv WP `release` taxonomy term id."""
        year_i = int(year)
        cache = getattr(self, '_release_term_cache', None)
        if cache is None:
            cache = {}
            self._release_term_cache = cache
        if year_i in cache:
            return cache[year_i]
        path = f'/wp-json/wp/v2/release?slug={quote_plus(str(year_i))}&_fields=id,slug,count'
        response = self._request('GET', path)
        if response.status_code >= 400:
            cache[year_i] = None
            return None
        try:
            rows = response.json()
        except Exception:
            cache[year_i] = None
            return None
        term_id = None
        if isinstance(rows, list) and rows:
            try:
                term_id = int(rows[0].get('id'))
            except (TypeError, ValueError):
                term_id = None
        cache[year_i] = term_id
        return term_id

    def _rest_list_by_category(
        self,
        *,
        category_ids,
        page: int = 1,
        search: str = '',
        embed: bool = False,
        release_id: int | None = None,
        orderby: str = 'modified',
    ):
        # Dornatv uses posts for both movies and series; filter via WP categories.
        params = {
            'per_page': self.rest_per_page,
            'page': max(1, int(page or 1)),
            'orderby': orderby or 'modified',
            'order': 'desc',
            'status': 'publish',
            'categories': ','.join(str(int(x)) for x in sorted(category_ids)),
        }
        if release_id:
            params['release'] = int(release_id)
        if search:
            params['search'] = search
        if embed:
            params['_embed'] = '1'
        query = '&'.join(f'{k}={quote_plus(str(v))}' for k, v in params.items())
        path = f'/wp-json/wp/v2/posts?{query}'
        response = self._request('GET', path)
        if response.status_code >= 400:
            raise ProviderImportError(
                f'dornatv REST posts HTTP {response.status_code}',
                code='dornatv_http_error',
            )
        try:
            rows = response.json()
        except Exception as exc:
            raise ProviderImportError(
                'dornatv REST response was not JSON.',
                code='dornatv_bad_json',
            ) from exc
        if not isinstance(rows, list):
            rows = []
        meta = {
            'total': int(response.headers.get('X-WP-Total') or 0),
            'total_pages': int(response.headers.get('X-WP-TotalPages') or 0),
            'page': params['page'],
        }
        return rows, meta

    def list_movies(self, *, page: int = 1, since=None) -> list[ProviderMovie]:
        rows, _meta = self._rest_list_by_category(category_ids=MOVIE_CATEGORY_IDS, page=page)
        out: list[ProviderMovie] = []
        for item in rows:
            parsed = parse_wp_rest_item(item, content_type='movie')
            out.append(ProviderMovie(
                provider_item_id=parsed['provider_item_id'],
                title=parsed.get('title') or '',
                original_title=parsed.get('original_title') or '',
                year=parsed.get('year'),
                imdb_id=parsed.get('imdb_id') or '',
                raw_payload={'wp_id': parsed.get('wp_id'), 'slug': parsed.get('slug'), 'link': parsed.get('link')},
            ))
        return out

    def list_series(self, *, page: int = 1, since=None) -> list[ProviderSeries]:
        rows, _meta = self._rest_list_by_category(category_ids=SERIES_CATEGORY_IDS, page=page)
        out: list[ProviderSeries] = []
        for item in rows:
            parsed = parse_wp_rest_item(item, content_type='series')
            out.append(ProviderSeries(
                provider_item_id=parsed['provider_item_id'],
                title=parsed.get('title') or '',
                original_title=parsed.get('original_title') or '',
                year=parsed.get('year'),
                imdb_id=parsed.get('imdb_id') or '',
                raw_payload={'wp_id': parsed.get('wp_id'), 'slug': parsed.get('slug'), 'link': parsed.get('link')},
            ))
        return out

    def _search_terms(self, query: dict | str) -> list[str]:
        if isinstance(query, str):
            term = query.strip()
            return [term] if term else []
        payload = query or {}
        terms: list[str] = []
        for key in ('original_title', 'title', 'query', 'q'):
            value = str(payload.get(key) or '').strip()
            if value and value not in terms and len(value) <= 120:
                terms.append(value)
        for value in payload.get('titles') or []:
            text = str(value or '').strip()
            if text and text not in terms and len(text) <= 120:
                terms.append(text)

        def latin_score(text: str) -> int:
            return sum(1 for ch in text if ('A' <= ch <= 'Z') or ('a' <= ch <= 'z'))

        terms.sort(key=lambda t: (-latin_score(t), len(t)))
        expanded: list[str] = []
        for term in terms:
            if term not in expanded:
                expanded.append(term)
            cleaned = re.sub(r'[:?!_/\\|]+', ' ', term)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            if cleaned and cleaned not in expanded:
                expanded.append(cleaned)
        return expanded[:4]

    def _query_titles(self, query: dict | str) -> list[str]:
        if isinstance(query, str):
            return [query] if query.strip() else []
        payload = query or {}
        out: list[str] = []
        for key in ('original_title', 'title'):
            value = str(payload.get(key) or '').strip()
            if value and value not in out:
                out.append(value)
        for value in payload.get('titles') or []:
            text = str(value or '').strip()
            if text and text not in out:
                out.append(text)
        return out

    def _query_year(self, query: dict | str):
        if isinstance(query, dict):
            year = query.get('year')
            if isinstance(year, int):
                return year
            try:
                return int(year) if year else None
            except (TypeError, ValueError):
                return None
        return None

    def _title_match_ok(self, *, query: dict | str, page_title: str, page_path: str) -> bool:
        titles = self._query_titles(query)
        if not titles:
            return True
        year = self._query_year(query)
        page_blob = slugify_title(f'{page_title} {page_path}')
        path_slug = slugify_title(page_path.strip('/').split('/')[-1] if page_path else '')
        for title in titles:
            slug = slugify_title(re.sub(r'\(\d{4}\)', '', title))
            if not slug:
                continue
            tokens = [
                tok for tok in slug.split('-')
                if len(tok) > 2 and tok not in {'the', 'and', 'for', 'with', 'from', 'film', 'movie', 'season'}
            ]
            if slug == path_slug or path_slug.startswith(slug + '-') or slug.startswith(path_slug):
                if year is None or str(year) in page_blob or str(year) in path_slug:
                    return True
                years = [int(y) for y in re.findall(r'\b((?:19|20)\d{2})\b', page_blob)]
                if not years or abs(min(years, key=lambda y: abs(y - year)) - year) <= 1:
                    return True
            hits = sum(1 for tok in tokens if tok in page_blob.split('-') or tok in page_blob)
            need = 2 if len(tokens) >= 3 else 1
            if hits >= need:
                if year is not None:
                    years = [int(y) for y in re.findall(r'\b((?:19|20)\d{2})\b', page_blob)]
                    if years and year not in years and abs(min(years, key=lambda y: abs(y - year)) - year) > 1:
                        if str(year) not in path_slug:
                            continue
                return True
        return False

    def _candidate_from_parsed(self, parsed: dict, *, source: str) -> ProviderTitleCandidate:
        return ProviderTitleCandidate(
            provider_item_id=parsed['provider_item_id'],
            content_type=parsed.get('content_type') or 'movie',
            title=parsed.get('title') or '',
            original_title=parsed.get('original_title') or parsed.get('title') or '',
            year=parsed.get('year'),
            imdb_id=parsed.get('imdb_id') or '',
            sanitized_metadata={'source': source, 'wp_id': parsed.get('wp_id'), 'slug': parsed.get('slug')},
        )

    def _search_via_rest(self, query: dict | str, *, content_type: str) -> list[ProviderTitleCandidate]:
        terms = self._search_terms(query)
        if not terms:
            return []
        cats = SERIES_CATEGORY_IDS if content_type == 'series' else MOVIE_CATEGORY_IDS
        out: list[ProviderTitleCandidate] = []
        seen: set[str] = set()
        payload = query if isinstance(query, dict) else {'title': terms[0], 'original_title': terms[0]}
        for term in terms[:2]:
            rows, _meta = self._rest_list_by_category(category_ids=cats, page=1, search=term)
            for item in rows[: self.max_results]:
                parsed = parse_wp_rest_item(item, content_type=content_type)
                path = parsed['provider_item_id']
                if path in seen:
                    continue
                page_title = ' '.join(filter(None, [
                    parsed.get('title_en') or '',
                    parsed.get('title') or '',
                    parsed.get('original_title') or '',
                ]))
                if not self._title_match_ok(
                    query=payload,
                    page_title=page_title,
                    page_path=path,
                ):
                    continue
                seen.add(path)
                out.append(self._candidate_from_parsed(parsed, source='rest_search'))
            if out:
                return out
        return out

    def _search_via_html(self, query: dict | str, *, content_type: str) -> list[ProviderTitleCandidate]:
        terms = self._search_terms(query)
        if not terms:
            return []
        out: list[ProviderTitleCandidate] = []
        seen: set[str] = set()
        payload = query if isinstance(query, dict) else {'title': terms[0]}
        post_type = 'post'
        for term in terms[:2]:
            path = f'/?s={quote_plus(term)}&search_type=advanced&post_type={post_type}'
            response = self._request('GET', path)
            if response.status_code >= 400:
                continue
            rows = parse_search_results(response.text or '', content_type=content_type)
            for row in rows[: self.max_results]:
                item_path = row['provider_item_id']
                if item_path in seen:
                    continue
                if not self._title_match_ok(query=payload, page_title=row.get('title') or '', page_path=item_path):
                    continue
                seen.add(item_path)
                out.append(ProviderTitleCandidate(
                    provider_item_id=item_path,
                    content_type=row.get('content_type') or content_type,
                    title=row.get('title') or '',
                    original_title=row.get('original_title') or row.get('title') or '',
                    year=row.get('year'),
                    sanitized_metadata={'source': 'html_search', 'term': term},
                ))
            if out:
                return out
        return out

    def _search_via_slug_probes(self, query: dict | str, *, content_type: str) -> list[ProviderTitleCandidate]:
        if isinstance(query, str):
            payload = {'title': query, 'original_title': query}
        else:
            payload = query or {}
        candidates = build_slug_candidates(
            title=str(payload.get('title') or ''),
            original_title=str(payload.get('original_title') or ''),
            year=payload.get('year'),
        )
        for slug in candidates[:4]:
            paths = [f'/{slug}/', f'/دانلود-فیلم-{slug}/', f'/دانلود-سریال-{slug}/']
            for path in paths:
                try:
                    response = self._request('GET', path)
                except ProviderRateLimited:
                    return []
                except Exception:
                    continue
                if response.status_code >= 400:
                    continue
                final_path = '/' + urlsplit(str(response.url)).path.strip('/') + '/'
                body = response.text or ''
                if 'downloadBox' not in body and 'downloadWrapper' not in body and '.mkv' not in body.lower() and '.mp4' not in body.lower():
                    continue
                parsed = parse_download_links(body, page_path=final_path)
                title = parsed.get('title') or slug.replace('-', ' ')
                if not self._title_match_ok(query=payload, page_title=title, page_path=final_path):
                    continue
                year = parsed.get('year')
                if year is None and isinstance(payload.get('year'), int):
                    year = payload.get('year')
                return [ProviderTitleCandidate(
                    provider_item_id=final_path,
                    content_type=content_type,
                    title=title,
                    original_title=parsed.get('original_title') or title,
                    year=year,
                    imdb_id=parsed.get('imdb_id') or '',
                    sanitized_metadata={'source': 'slug_probe', 'slug': slug},
                )]
        return []

    def search_movie(self, query: dict | str) -> list[ProviderTitleCandidate]:
        hits = self._search_via_rest(query, content_type='movie')
        if hits:
            return hits
        hits = self._search_via_html(query, content_type='movie')
        if hits:
            return hits
        return self._search_via_slug_probes(query, content_type='movie')

    def search_series(self, query: dict | str) -> list[ProviderTitleCandidate]:
        hits = self._search_via_rest(query, content_type='series')
        if hits:
            return hits
        hits = self._search_via_html(query, content_type='series')
        if hits:
            return hits
        return self._search_via_slug_probes(query, content_type='series')

    def crawl_download_links(self, page_url_or_slug: str, *, content_type: str = 'movie') -> dict:
        path = normalize_detail_path(page_url_or_slug, content_type=content_type)
        response = self._request('GET', path)
        if response.status_code >= 400:
            raise ProviderImportError(
                f'dornatv page not found ({response.status_code}).',
                code='dornatv_page_required',
            )
        final_path = '/' + urlsplit(str(response.url)).path.strip('/') + '/'
        parsed = parse_download_links(response.text or '', page_path=final_path)
        parsed['page_path'] = final_path
        parsed['page_url'] = urljoin(self.base_url + '/', final_path.lstrip('/'))
        return parsed

    def get_movie_detail(self, provider_item_id: str) -> ProviderMovie:
        crawled = self.crawl_download_links(provider_item_id, content_type='movie')
        return ProviderMovie(
            provider_item_id=crawled.get('page_path') or provider_item_id,
            title=crawled.get('title') or '',
            original_title=crawled.get('original_title') or '',
            year=crawled.get('year'),
            imdb_id=crawled.get('imdb_id') or '',
            raw_payload={'link_count': crawled.get('total_entries', 0)},
        )

    def get_series_detail(self, provider_item_id: str) -> ProviderSeries:
        crawled = self.crawl_download_links(provider_item_id, content_type='series')
        return ProviderSeries(
            provider_item_id=crawled.get('page_path') or provider_item_id,
            title=crawled.get('title') or '',
            original_title=crawled.get('original_title') or '',
            year=crawled.get('year'),
            imdb_id=crawled.get('imdb_id') or '',
            raw_payload={'link_count': crawled.get('total_entries', 0)},
        )
