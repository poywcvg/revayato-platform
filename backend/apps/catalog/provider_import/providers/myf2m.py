"""Film2Media (myf2m.info) public download-link crawler.

Public HTML already embeds direct CDN URLs — no VIP login required.
Does not bypass CAPTCHA/Cloudflare challenges when present.
"""

from __future__ import annotations

import html
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from urllib.parse import quote_plus, urljoin, urlsplit

from django.conf import settings
from django.core.cache import cache

from ..base import ProviderAuthResult
from ..exceptions import ProviderImportError, ProviderNotConfigured, ProviderRateLimited
from ..sanitizers import sanitize_payload
from .myf2m_parser import (
    TRAILER_FILE_RE,
    build_slug_candidates,
    normalize_detail_path,
    parse_download_links,
    parse_search_results,
    slugify_title,
)

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None


def _file_size_label(size_bytes: int) -> str:
    """Human-readable binary size while retaining exact bytes in metadata."""
    size = max(0, int(size_bytes or 0))
    gib = 1024 ** 3
    mib = 1024 ** 2
    if size >= gib:
        return f'{size / gib:.2f} GB'
    return f'{size / mib:.2f} MB'


def enrich_download_link_metadata(
    rows: list[dict],
    *,
    timeout_seconds: int = 15,
    max_workers: int = 6,
    min_size_bytes: int = 8 * 1024 * 1024,
    verify_ssl: bool = True,
) -> dict:
    """Resolve exact CDN file sizes and reject trailers/samples.

    Film2Media's HTML download box does not expose a size field, but its CDN
    returns the exact object length after redirects. HEAD is used first, with a
    one-byte Range request as a compatibility fallback. No media body is
    downloaded.
    """
    if httpx is None:
        raise ProviderNotConfigured('httpx is required to verify myf2m files.')

    candidates: list[tuple[int, dict]] = []
    rejected: list[dict] = []
    for index, item in enumerate(rows or []):
        if not isinstance(item, dict):
            continue
        row = dict(item)
        url = str(row.get('url') or '').strip()
        filename = unescape(urlsplit(url).path.rsplit('/', 1)[-1])
        if not url.startswith(('http://', 'https://')) or TRAILER_FILE_RE.search(filename):
            rejected.append({'url': url, 'reason': 'trailer_or_invalid'})
            continue
        candidates.append((index, row))

    timeout = httpx.Timeout(max(5.0, float(timeout_seconds)), connect=min(10.0, float(timeout_seconds)))
    client = httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        verify=verify_ssl,
        headers={
            'User-Agent': 'RevayatoCatalogVerifier/1.0 (+https://revayato.com)',
            'Accept-Encoding': 'identity',
        },
    )

    def content_length(url: str) -> int:
        for attempt in range(2):
            try:
                response = client.head(url)
                if response.status_code < 400:
                    value = response.headers.get('content-length') or ''
                    if value.isdigit() and int(value) > 1:
                        return int(value)
                with client.stream('GET', url, headers={'Range': 'bytes=0-0'}) as ranged:
                    if ranged.status_code < 400:
                        content_range = ranged.headers.get('content-range') or ''
                        total = content_range.rsplit('/', 1)[-1].strip()
                        if total.isdigit() and int(total) > 1:
                            return int(total)
                        value = ranged.headers.get('content-length') or ''
                        if value.isdigit() and int(value) > 1 and ranged.status_code == 200:
                            return int(value)
            except Exception:
                if attempt == 0:
                    time.sleep(0.35)
        return 0

    sizes: dict[int, int] = {}
    workers = max(1, min(int(max_workers or 1), len(candidates) or 1, 8))
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(content_length, str(row.get('url') or '')): index
                for index, row in candidates
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    sizes[index] = int(future.result() or 0)
                except Exception:
                    sizes[index] = 0
    finally:
        client.close()

    enriched: list[dict] = []
    missing: list[dict] = []
    for index, row in candidates:
        size = sizes.get(index, 0)
        if size < max(1, int(min_size_bytes or 1)):
            missing.append({
                'url': str(row.get('url') or ''),
                'reason': 'size_unavailable' if not size else 'file_too_small',
                'size_bytes': size,
            })
            continue
        row['size_bytes'] = size
        row['size_label'] = _file_size_label(size)
        row['verified_full'] = True
        enriched.append(row)

    return {
        'links': enriched,
        'missing': missing,
        'rejected': rejected,
        'verified_count': len(enriched),
        'candidate_count': len(candidates),
    }


# A link to IMDb's title page, not any bare tt-number. The current page layout
# links none (only an IMDb icon beside the score), so this is the stronger signal
# when present and the heading below is the one every page carries.
IMDB_TITLE_LINK_RE = re.compile(r'imdb\.com/title/(tt\d{7,10})', re.I)
# ``<h1 class="entry-title ...">Masters of the Universe 2026</h1>`` — the page's
# own statement of which title and year it is.
PAGE_HEADING_RE = re.compile(r'<h1[^>]*class="[^"]*entry-title[^"]*"[^>]*>(.*?)</h1>', re.I | re.S)


class CachedMyf2MPage:
    """Minimal httpx.Response-compatible stand-in for cached detail HTML.

    Only the attributes the myf2m connector reads off a live response are
    exposed (text / status_code / url), so cached and live fetches are
    interchangeable for parsing callers. Mirrors CachedDornatvPage.
    """

    def __init__(self, html: str, *, final_path: str, headers: dict | None = None):
        self._html = html
        self.text = html
        self.content = html.encode('utf-8', 'replace')
        self.status_code = 200
        self.url = final_path  # used only for url-splitting by callers
        self.headers = headers or {
            'content-type': 'text/html; charset=UTF-8',
            'x-wp-cached': '1',
        }


# Only exact detail pages are cached: movie ``/{id}/{slug}/`` and series
# ``/series/{slug}/``. Listing walks (/movies/, /series/, /page/N/) and search
# (/?s=) must always reach the live page or new titles would be missed.
_MYF2M_MOVIE_DETAIL_RE = re.compile(r'^/\d+/[^/]+/?$')
_MYF2M_SERIES_DETAIL_RE = re.compile(r'^/series/([^/]+)/?$')


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


class MyF2MConnector:
    slug = 'myf2m'

    def __init__(self, provider_source=None):
        self.provider = provider_source
        self.base_url = getattr(settings, 'MYF2M_BASE_URL', 'https://www.myf2ms.top').rstrip('/')
        self.timeout = int(getattr(settings, 'MYF2M_TIMEOUT_SECONDS', 30))
        # 1 req/s aggregate is still polite for a WordPress catalog (a human
        # browses faster); bursts that do trip the WAF are retried with backoff
        # in _request, so a 429 degrades into a short sleep, not a failure.
        self.rate_limit = max(1, int(getattr(settings, 'MYF2M_RATE_LIMIT_PER_MINUTE', 60)))
        self.verify_ssl = bool(getattr(settings, 'MYF2M_VERIFY_SSL', True))
        self.user_agent = getattr(
            settings,
            'MYF2M_USER_AGENT',
            'RevayatoCatalogCrawler/1.0 (+https://revayato.ir)',
        )
        self.max_results = int(getattr(settings, 'MYF2M_MAX_RESULTS_PER_LOOKUP', 20))
        self._last_request_at = 0.0
        self._client = None

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None

    def _ensure_httpx(self):
        if httpx is None:
            raise ProviderNotConfigured('httpx is required for the myf2m connector.')

    def _client_or_create(self):
        self._ensure_httpx()
        if self._client is None:
            # Large series download boxes can exceed default read windows; keep connect
            # snappy but allow a longer body read for episode-heavy pages.
            read_timeout = max(float(self.timeout), 90.0)
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(read_timeout, connect=min(30.0, read_timeout)),
                follow_redirects=True,
                verify=self.verify_ssl,
                headers={
                    'User-Agent': self.user_agent,
                    'Accept': 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'fa-IR,fa;q=0.9,en;q=0.8',
                    # Prefer identity encoding — chunked gzip sometimes truncates mid-body.
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

    # --- detail-page HTML cache -----------------------------------------
    # Download boxes are re-read within minutes by the multi-provider crawl
    # (myf2m fetch, then a second fetch inside crawl_myf2m_downloads_* with a
    # fresh connector), by refresh ticks and by the drafts hunter. The raw
    # detail HTML is cached for a short TTL so those re-reads cost no network
    # and no rate budget, while the hourly refresh passes always see a live
    # page. Listing/search pages are never cached. Mirrors the dornatv cache.
    def _cache_key(self, path: str) -> str:
        import hashlib

        digest = hashlib.sha1(str(path).encode('utf-8', 'replace')).hexdigest()
        return f'catalog:myf2m:page:{digest}'

    def _cacheable_detail_path(self, path: str) -> bool:
        """Only exact detail pages (not listings/search/home) are cached."""
        raw = str(path or '')
        if not raw.startswith('/') or '?' in raw:
            return False
        if _MYF2M_MOVIE_DETAIL_RE.match(raw):
            return True
        match = _MYF2M_SERIES_DETAIL_RE.match(raw)
        if match and match.group(1) not in {'page'}:
            return True
        return False

    def _detail_from_cache(self, path: str) -> str | None:
        try:
            ttl = int(getattr(settings, 'MYF2M_PAGE_CACHE_TTL_SECONDS', 300))
        except (TypeError, ValueError):
            ttl = 300
        if ttl <= 0 or not self._cacheable_detail_path(path):
            return None
        from apps.catalog.title_rebuild import is_fresh_fetch

        if is_fresh_fetch():
            # A rebuild re-asks the provider; the fresh page refills the cache.
            return None
        try:
            blob = cache.get(self._cache_key(path))
        except Exception:
            return None
        if isinstance(blob, bytes):
            try:
                return blob.decode('utf-8', 'replace')
            except Exception:
                return None
        if isinstance(blob, str) and blob:
            return blob
        return None

    def _detail_to_cache(self, path: str, html: str, *, final_url: str = '') -> None:
        try:
            ttl = int(getattr(settings, 'MYF2M_PAGE_CACHE_TTL_SECONDS', 300))
        except (TypeError, ValueError):
            ttl = 300
        if ttl <= 0 or not self._cacheable_detail_path(path):
            return
        # A soft-404/profile redirect is a miss, not a page — never cache it.
        if '/profile/' in str(final_url or ''):
            return
        # Only cache usable pages: a truncated (IncompleteRead partial) body
        # without any download marker must never poison later lanes.
        lowered = (html or '').lower()
        if 'download-list' not in lowered and '.mkv' not in lowered and '.mp4' not in lowered:
            return
        try:
            max_bytes = int(getattr(settings, 'MYF2M_PAGE_CACHE_MAX_BYTES', 512 * 1024))
        except (TypeError, ValueError):
            max_bytes = 512 * 1024
        if not html or len(html) > max_bytes:
            return
        try:
            cache.set(self._cache_key(path), html, timeout=ttl)
        except Exception:
            pass

    def _request_urllib(self, method: str, path: str):
        """Fallback GET/HEAD that keeps IncompleteRead.partial (large myf2m pages)."""
        import http.client
        import ssl
        import urllib.error
        import urllib.request

        class _Resp:
            def __init__(self, *, status_code: int, url: str, text: str):
                self.status_code = status_code
                self.url = url
                self.text = text

        if method.upper() not in {'GET', 'HEAD'}:
            raise ProviderImportError(f'urllib fallback only supports GET/HEAD, got {method}')

        url = self._absolute_url(path)
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'fa-IR,fa;q=0.9,en;q=0.8',
            'Accept-Encoding': 'identity',
        }
        context = None
        if not self.verify_ssl:
            context = ssl._create_unverified_context()  # noqa: S323
        req = urllib.request.Request(url, headers=headers, method=method.upper())
        timeout = max(float(self.timeout), 90.0)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=context) as raw:  # noqa: S310
                final = str(raw.geturl())
                status = int(getattr(raw, 'status', 200) or 200)
                body = b'' if method.upper() == 'HEAD' else raw.read()
        except http.client.IncompleteRead as exc:
            # Cloudflare / CDN often closes mid-body; download lists are usually already present.
            body = exc.partial or b''
            final = url
            status = 200
        except urllib.error.HTTPError as exc:
            return _Resp(status_code=int(exc.code), url=str(exc.url or url), text='')
        text = body.decode('utf-8', errors='ignore') if body else ''
        return _Resp(status_code=status, url=final, text=text)

    def _request(self, method: str, path: str, **kwargs):
        # Serve cached detail HTML for plain GETs so refresh ticks and the
        # multi-provider second fetch do not re-download the same page or burn
        # rate budget. Cached hits skip the throttle entirely.
        if method.upper() == 'GET' and not kwargs and self._cacheable_detail_path(path):
            cached = self._detail_from_cache(path)
            if cached is not None:
                return CachedMyf2MPage(cached, final_path=path)
        self._throttle()
        # Prefer urllib for HTML GETs — httpx frequently hits Incomplete chunked reads on
        # large Film2Media series pages inside Docker, while urllib keeps usable partials.
        if method.upper() == 'GET' and not kwargs:
            self._last_request_at = time.monotonic()
            try:
                response = self._request_urllib(method, path)
                if response.status_code in {429, 403}:
                    time.sleep(2.5)
                    self._throttle()
                    self._last_request_at = time.monotonic()
                    response = self._request_urllib(method, path)
                    if response.status_code == 429:
                        raise ProviderRateLimited('myf2m rate-limited the crawler.')
                if response.status_code < 400:
                    self._detail_to_cache(path, response.text or '', final_url=str(response.url))
                return response
            except ProviderRateLimited:
                raise
            except Exception:
                # Fall through to httpx.
                pass

        client = self._client_or_create()
        last_exc: Exception | None = None
        response = None
        for attempt in range(1, 4):
            self._last_request_at = time.monotonic()
            try:
                response = client.request(method, path, **kwargs)
                last_exc = None
                break
            except httpx.TransportError as exc:
                # Peer closed connection / incomplete chunked body on large download pages.
                last_exc = exc
                self.close()
                if method.upper() == 'GET' and not kwargs:
                    try:
                        return self._request_urllib(method, path)
                    except Exception:
                        pass
                client = self._client_or_create()
                time.sleep(1.5 * attempt)
        if last_exc is not None or response is None:
            if method.upper() == 'GET' and not kwargs:
                try:
                    return self._request_urllib(method, path)
                except Exception as fallback_exc:
                    raise last_exc from fallback_exc
            raise last_exc or ProviderImportError('myf2m request failed without a response.')
        if response.status_code in {429, 403}:
            # Brief cooldown then one retry — myf2m WAF occasionally trips on bursty search.
            time.sleep(2.5)
            self._throttle()
            self._last_request_at = time.monotonic()
            try:
                response = client.request(method, path, **kwargs)
            except httpx.TransportError:
                if method.upper() == 'GET' and not kwargs:
                    return self._request_urllib(method, path)
                self.close()
                client = self._client_or_create()
                self._last_request_at = time.monotonic()
                response = client.request(method, path, **kwargs)
            if response.status_code == 429:
                raise ProviderRateLimited('myf2m rate-limited the crawler.')
            # Leave 403 to the caller so alternate search terms can still be tried.
        if (
            method.upper() == 'GET' and not kwargs
            and response.status_code < 400
        ):
            try:
                self._detail_to_cache(
                    path, response.text or '', final_url=str(response.url),
                )
            except Exception:
                pass
        return response

    def validate_credentials(self) -> ProviderAuthResult:
        try:
            response = self._request('GET', '/')
            ok = response.status_code < 400 and 'film2media' in (response.text or '').lower()
            return ProviderAuthResult(
                ok=ok,
                message='myf2m public catalog reachable.' if ok else 'myf2m home page unexpected.',
                auth_type='public',
                sanitized_details={'http_status': response.status_code, 'base_url': self.base_url},
            )
        except Exception as exc:
            return ProviderAuthResult(ok=False, message=str(exc)[:200], auth_type='public')

    def authenticate(self) -> ProviderAuthResult:
        # Public download HTML — no session required.
        return self.validate_credentials()

    def _search_terms(self, query: dict | str) -> list[str]:
        if isinstance(query, str):
            term = query.strip()
            return [term] if term else []
        payload = query or {}
        terms: list[str] = []
        # Prefer original/Latin titles — Persian queries often miss Film2Media cards
        # and punctuation like ":" breaks provider search ranking.
        for key in ('original_title', 'title', 'query', 'q'):
            value = str(payload.get(key) or '').strip()
            if value and value not in terms and len(value) <= 120 and value.count(' ') <= 14:
                terms.append(value)
        for value in payload.get('titles') or []:
            text = str(value or '').strip()
            if text and text not in terms and len(text) <= 120 and text.count(' ') <= 14:
                terms.append(text)

        def latin_score(text: str) -> int:
            return sum(1 for ch in text if ('A' <= ch <= 'Z') or ('a' <= ch <= 'z'))

        terms.sort(key=lambda t: (-latin_score(t), len(t)))
        # Film2Media search is Latin-oriented; drop pure non-Latin queries.
        terms = [t for t in terms if latin_score(t) >= 3] or terms

        expanded: list[str] = []
        for term in terms:
            if term not in expanded:
                expanded.append(term)
            cleaned = re.sub(r'[:?!_/\\|]+', ' ', term)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            if cleaned and cleaned not in expanded and latin_score(cleaned) >= 3:
                expanded.append(cleaned)
            # Drop leading articles for broader matches.
            no_article = re.sub(r'^(the|a|an)\s+', '', cleaned, flags=re.I).strip()
            if no_article and no_article not in expanded and latin_score(no_article) >= 3:
                expanded.append(no_article)
        return expanded[:3]

    def _search_term(self, query: dict | str) -> str:
        terms = self._search_terms(query)
        return terms[0] if terms else ''

    def _token_present(self, token: str, page_blob: str) -> bool:
        if token in page_blob:
            return True
        # Tolerate provider typos / truncated slug tokens (puss → pus).
        if len(token) < 4:
            return False
        for part in page_blob.split('-'):
            if len(part) < 3:
                continue
            if token.startswith(part) or part.startswith(token[: max(3, len(token) - 1)]):
                return True
            if abs(len(part) - len(token)) <= 1 and part[:3] == token[:3]:
                return True
        return False

    def _search_via_query(self, query: dict | str, *, content_type: str) -> list[ProviderTitleCandidate]:
        terms = self._search_terms(query)
        if not terms:
            return []
        out: list[ProviderTitleCandidate] = []
        seen: set[str] = set()
        payload = query if isinstance(query, dict) else {'title': terms[0], 'original_title': terms[0]}
        for term in terms[:2]:
            params = f'/?s={quote_plus(term)}'
            if content_type in {'movie', 'series'}:
                params += f'&type={content_type}'
            response = self._request('GET', params)
            if response.status_code >= 400:
                continue
            rows = parse_search_results(response.text or '', content_type=content_type)
            for row in rows[: self.max_results]:
                path = row['provider_item_id']
                if path in seen:
                    continue
                candidate = ProviderTitleCandidate(
                    provider_item_id=path,
                    content_type=row.get('content_type') or content_type,
                    title=row.get('title') or '',
                    original_title=row.get('original_title') or row.get('title') or '',
                    year=row.get('year'),
                    sanitized_metadata={'source': 'search', 'term': term},
                )
                if not self._title_match_ok(
                    query=payload,
                    page_title=candidate.title,
                    page_path=candidate.provider_item_id,
                ):
                    continue
                seen.add(path)
                out.append(candidate)
            if out:
                return out
        return out

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
        """Reject accidental slug collisions (e.g. Evangelion subtitle 'Air' → Air 2023)."""
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
            tokens = [tok for tok in slug.split('-') if len(tok) > 2 and tok not in {
                'the', 'and', 'for', 'with', 'from', 'film', 'movie', 'season',
            }]
            # Very short / single-token titles are too ambiguous for slug probes.
            if len(slug) < 6 or len(tokens) <= 1:
                path_hit = (
                    slug == path_slug
                    or path_slug.startswith(slug + '-')
                    or path_slug.startswith(slug)
                    or slug.startswith(path_slug)
                )
                # Exact hyphen token on the page (lucifer in h1), not a substring of
                # another title (house ⊂ little-house-on-the-prairie).
                page_parts = [part for part in page_blob.split('-') if part]
                title_hit = slug in page_parts or any(tok in page_parts for tok in tokens)
                if path_hit:
                    if year is None or str(year) in page_blob or str(year) in path_slug:
                        return True
                    years = [int(y) for y in re.findall(r'\b((?:19|20)\d{2})\b', page_blob)]
                    if years and abs(min(years, key=lambda y: abs(y - year)) - year) <= 1:
                        return True
                    # Exact slug match from search cards (e.g. /series/fargo/) is enough —
                    # provider pages often omit the year in the path while TMDB has one.
                    if slug == path_slug and len(slug) >= 4:
                        return True
                elif title_hit and len(slug) >= 5:
                    # Prefer pages where this token is the primary Latin identity
                    # (Lucifer), not a later word in a longer title (House ⊂ Little House).
                    latin_parts = [part for part in page_parts if part.isascii() and part.isalpha()]
                    if latin_parts and latin_parts[0] == slug:
                        if year is None or str(year) in page_blob or str(year) in path_slug:
                            return True
                        years = [int(y) for y in re.findall(r'\b((?:19|20)\d{2})\b', page_blob)]
                        if not years or abs(min(years, key=lambda y: abs(y - year)) - year) <= 1:
                            return True
                continue
            hits = sum(1 for tok in tokens if self._token_present(tok, page_blob))
            need = 2 if len(tokens) >= 3 else 1
            if hits >= need:
                if year is not None:
                    # If page advertises a clear different year, reject.
                    # Allow ±1 year for release-date / listing drift (e.g. 2025 vs 2026).
                    years = [int(y) for y in re.findall(r'\b((?:19|20)\d{2})\b', page_blob)]
                    if years and year not in years and abs(min(years, key=lambda y: abs(y - year)) - year) > 1:
                        if str(year) not in path_slug:
                            continue
                return True
            # Exact page title match from search cards is high-confidence even with slug typos.
            if slugify_title(page_title) == slug and (year is None or str(year) in page_blob or str(year) in path_slug):
                return True
        return False

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
        # Drop ultra-short ambiguous slugs unless year-qualified.
        year_s = str(payload.get('year') or '')
        filtered = []
        for slug in candidates:
            if len(slug) < 6 and (not year_s or year_s not in slug):
                continue
            filtered.append(slug)
        candidates = filtered or candidates

        results: list[ProviderTitleCandidate] = []
        profile_misses = 0
        # Keep probes tiny — missing titles often 301 to /profile/ and burn rate budget.
        for slug in candidates[:3]:
            if content_type == 'series':
                paths = [f'/series/{slug}/']
            else:
                paths = [f'/{slug}/']
            for path in paths:
                try:
                    response = self._request('GET', path, follow_redirects=True)
                except ProviderRateLimited:
                    return results
                except Exception:
                    continue
                final_path = urlsplit(str(response.url)).path
                final_path = '/' + final_path.strip('/') + '/'
                if response.status_code >= 400:
                    continue
                # Reject soft 404/profile pages early.
                if '/profile/' in final_path:
                    profile_misses += 1
                    # Year-suffixed misses are common; keep probing remaining candidates
                    # (plain slug often exists while `{slug}-{year}` 301s to /profile/).
                    if profile_misses >= 4:
                        return results
                    continue
                body = response.text or ''
                if 'نتجیه ایی یافت نشد' in body:
                    continue
                if 'download-list' not in body and '.mkv' not in body.lower() and '.mp4' not in body.lower():
                    continue
                title = slug.replace('-', ' ')
                title_match = re.search(r'<h1[^>]*class="[^"]*entry-title[^"]*"[^>]*>(.*?)</h1>', body, re.I | re.S)
                if title_match:
                    title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() or title
                if not self._title_match_ok(query=payload, page_title=title, page_path=final_path):
                    continue
                # Do not require the final slug to resemble the probe — Film2Media
                # often uses typo/short redirects (lucifer → lufe-series, westworld → ww2020).
                # _title_match_ok already guards against unrelated collisions.
                results.append(ProviderTitleCandidate(
                    provider_item_id=final_path,
                    content_type=content_type,
                    title=title,
                    original_title=title,
                    year=payload.get('year') if isinstance(payload.get('year'), int) else None,
                    sanitized_metadata={'source': 'slug_probe', 'slug': slug},
                ))
                return results
        return results

    def search_movie(self, query: dict | str) -> list[ProviderTitleCandidate]:
        # Prefer search results first — slug probes are collision-prone and expensive on misses.
        hits = self._search_via_query(query, content_type='movie')
        if hits:
            return hits
        # Only probe when we have a Latin original title (Persian-only queries rarely match).
        titles = self._query_titles(query)
        if not any(sum(1 for ch in t if ('A' <= ch <= 'Z') or ('a' <= ch <= 'z')) >= 3 for t in titles):
            return []
        return self._search_via_slug_probes(query, content_type='movie')

    def search_series(self, query: dict | str) -> list[ProviderTitleCandidate]:
        hits = self._search_via_query(query, content_type='series')
        if hits:
            return hits
        titles = self._query_titles(query)
        if not any(sum(1 for ch in t if ('A' <= ch <= 'Z') or ('a' <= ch <= 'z')) >= 3 for t in titles):
            return []
        return self._search_via_slug_probes(query, content_type='series')

    def crawl_download_links(self, page_url_or_slug: str, *, content_type: str = 'movie') -> dict:
        path = normalize_detail_path(page_url_or_slug, content_type=content_type)
        response = self._request('GET', path)
        if response.status_code >= 400:
            raise ProviderImportError(
                f'myf2m page not found ({response.status_code}).',
                code='myf2m_page_required',
            )
        final_path = '/' + urlsplit(str(response.url)).path.strip('/') + '/'
        if '/profile/' in final_path:
            raise ProviderImportError(
                'myf2m page redirected to profile (missing title).',
                code='myf2m_page_required',
            )
        parsed = parse_download_links(response.text or '', page_path=final_path)
        # Which title the page says it is. The crawl only ever found the page by
        # title + year, so this is what lets the caller check it against the
        # IMDb id it already holds (see catalog_lookup._crawl_with_healed_path).
        parsed['imdb_ids'] = sorted({m.lower() for m in IMDB_TITLE_LINK_RE.findall(response.text or '')})
        heading = PAGE_HEADING_RE.search(response.text or '')
        parsed['page_heading'] = (
            html.unescape(re.sub(r'<[^>]+>|\s+', ' ', heading.group(1))).strip() if heading else ''
        )
        parsed['page_path'] = final_path
        parsed['page_url'] = urljoin(self.base_url + '/', final_path.lstrip('/'))
        return parsed
