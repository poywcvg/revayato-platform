"""Kargadan Movie (kargadanmovie.com) connector.

Discovery is public: WordPress ``wp-sitemap`` lists every movie and series page,
and each page URL *is* its IMDb id (``/movies/tt0070849/``), so a title is matched
exactly and never by a title search.

Download links are shown only to a signed-in account, and the site's sign-in form
carries a CAPTCHA. The crawler therefore never signs in by itself: an operator
signs in with a normal browser and places that browser session's ``Cookie``
header in ``KARGADAN_SESSION_COOKIE``. Without it, or once it lapses, the crawler
still walks the catalog but reports ``kargadan_login_required`` instead of links —
it never solves the CAPTCHA and never posts a password.
"""

from __future__ import annotations

import time
from urllib.parse import urljoin, urlsplit

from django.conf import settings

from ..base import ProviderAuthResult
from ..exceptions import ProviderImportError, ProviderNotConfigured, ProviderRateLimited
from .kargadan_parser import (
    detail_path,
    imdb_from_path,
    login_state,
    parse_download_links,
    parse_sitemap,
    parse_sitemap_index,
)

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None

SESSION_STATE_CACHE_KEY = 'catalog:kargadan:session_state'
SESSION_STATE_TTL = 24 * 60 * 60
INVENTORY_CACHE_KEY = 'catalog:kargadan:inventory'
INVENTORY_TTL = 3 * 24 * 60 * 60

# Shared by every connector instance in the process: the discovery lane and the
# per-title crawls it triggers each build their own connector, and a per-instance
# clock would let them together exceed ``KARGADAN_RATE_LIMIT_PER_MINUTE``.
_LAST_REQUEST_AT = [0.0]


def _cookie_pairs(raw: str) -> dict[str, str]:
    """``name=value; name2=value2`` (a browser's ``Cookie`` header) → dict."""
    pairs: dict[str, str] = {}
    for part in (raw or '').split(';'):
        name, sep, value = part.strip().partition('=')
        if sep and name.strip():
            pairs[name.strip()] = value.strip()
    return pairs


def _cookie_fingerprint() -> str:
    import hashlib

    raw = (getattr(settings, 'KARGADAN_SESSION_COOKIE', '') or '').strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:16] if raw else ''


def record_session_state(logged_in: bool | None, *, detail: str = '') -> None:
    """Remember what the last page said about the session, for the admin and lane.

    Stored with a fingerprint of the configured cookie, so replacing the cookie
    is noticed on the very next crawl instead of after the state expires.
    """
    from django.core.cache import cache
    from django.utils import timezone

    cache.set(SESSION_STATE_CACHE_KEY, {
        'logged_in': logged_in,
        'cookie_configured': bool(_cookie_fingerprint()),
        'cookie_fingerprint': _cookie_fingerprint(),
        'detail': detail[:200],
        'checked_at': timezone.now().isoformat(),
    }, timeout=SESSION_STATE_TTL)


def session_state() -> dict:
    from django.core.cache import cache

    return cache.get(SESSION_STATE_CACHE_KEY) or {}


def session_blocker() -> str:
    """Why a link crawl cannot succeed right now, without a request; ``''`` if it may.

    Kargadan sits in every catalog crawl (publish, playback refresh, report
    repair). Without this, each of those would spend a throttled page fetch just
    to learn again that nobody is signed in.
    """
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    fingerprint = _cookie_fingerprint()
    if not fingerprint:
        return 'kargadan_session_missing'
    state = session_state()
    if state.get('logged_in') is False and state.get('cookie_fingerprint') == fingerprint:
        checked = parse_datetime(str(state.get('checked_at') or ''))
        recheck = float(getattr(settings, 'KARGADAN_SESSION_RECHECK_MINUTES', 30) or 30)
        if checked and (timezone.now() - checked).total_seconds() < recheck * 60:
            return 'kargadan_login_required'
    return ''


def record_inventory(entries: list[dict]) -> None:
    """Keep the sitemap's IMDb ids so per-title crawls skip titles Kargadan lacks."""
    from django.core.cache import cache
    from django.utils import timezone

    cache.set(INVENTORY_CACHE_KEY, {
        'movie': sorted({e['imdb_id'] for e in entries if e.get('content_type') == 'movie'}),
        'series': sorted({e['imdb_id'] for e in entries if e.get('content_type') == 'series'}),
        'at': timezone.now().isoformat(),
    }, timeout=INVENTORY_TTL)


def inventory_says_missing(imdb_id: str, *, content_type: str) -> bool:
    """``True`` only when a stored sitemap walk exists and lacks this title."""
    from django.core.cache import cache

    inventory = cache.get(INVENTORY_CACHE_KEY)
    if not inventory:
        return False
    ids = inventory.get('series' if content_type == 'series' else 'movie') or []
    return bool(ids) and (imdb_id or '').lower() not in set(ids)


class KargadanConnector:
    slug = 'kargadan'

    def __init__(self, provider_source=None):
        self.provider = provider_source
        self.base_url = getattr(settings, 'KARGADAN_BASE_URL', 'https://kargadanmovie.com').rstrip('/')
        self.base_host = (urlsplit(self.base_url).hostname or 'kargadanmovie.com').lower().removeprefix('www.')
        self.timeout = int(getattr(settings, 'KARGADAN_TIMEOUT_SECONDS', 30))
        self.rate_limit = max(1, int(getattr(settings, 'KARGADAN_RATE_LIMIT_PER_MINUTE', 20)))
        self.verify_ssl = bool(getattr(settings, 'KARGADAN_VERIFY_SSL', True))
        self.user_agent = getattr(
            settings, 'KARGADAN_USER_AGENT', 'RevayatoCatalogCrawler/1.0 (+https://revayato.ir)',
        )
        self.cookies = _cookie_pairs(getattr(settings, 'KARGADAN_SESSION_COOKIE', '') or '')
        self._client = None

    @property
    def has_session(self) -> bool:
        return bool(self.cookies)

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None

    def _client_or_create(self):
        if httpx is None:
            raise ProviderNotConfigured('httpx is required for the kargadan connector.')
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(max(float(self.timeout), 60.0), connect=min(20.0, float(self.timeout))),
                follow_redirects=True,
                verify=self.verify_ssl,
                cookies=self.cookies,
                headers={
                    'User-Agent': self.user_agent,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'fa-IR,fa;q=0.9,en;q=0.8',
                },
            )
        return self._client

    def _throttle(self):
        minimum = 60.0 / float(self.rate_limit)
        elapsed = time.monotonic() - _LAST_REQUEST_AT[0]
        if elapsed < minimum:
            time.sleep(minimum - elapsed)
        _LAST_REQUEST_AT[0] = time.monotonic()

    def _request(self, method: str, path: str, **kwargs):
        client = self._client_or_create()
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            self._throttle()
            try:
                response = client.request(method, path, **kwargs)
            except httpx.TransportError as exc:
                last_exc = exc
                time.sleep(1.5 * attempt)
                continue
            if response.status_code == 429:
                if attempt == 3:
                    raise ProviderRateLimited('kargadan rate-limited the crawler.')
                time.sleep(5.0 * attempt)
                continue
            return response
        raise ProviderImportError(f'kargadan request failed: {last_exc}', code='kargadan_unreachable')

    def validate_credentials(self) -> ProviderAuthResult:
        """Reachability (public) plus whether the configured session is signed in."""
        try:
            response = self._request('GET', '/')
        except Exception as exc:
            return ProviderAuthResult(ok=False, message=str(exc)[:200], auth_type='cookie_session')
        ok = response.status_code < 400 and 'kargadan' in (response.text or '').lower()
        logged = login_state(response.text or '') if ok else None
        if ok:
            record_session_state(logged, detail='home page')
        return ProviderAuthResult(
            ok=ok,
            message=(
                'kargadan reachable; session signed in.' if logged
                else 'kargadan reachable; no signed-in session (links need KARGADAN_SESSION_COOKIE).'
            ) if ok else 'kargadan home page unexpected.',
            auth_type='cookie_session',
            sanitized_details={
                'http_status': response.status_code,
                'base_url': self.base_url,
                'logged_in': logged,
                'cookie_configured': self.has_session,
            },
        )

    def authenticate(self) -> ProviderAuthResult:
        # Never automated: the sign-in form carries a CAPTCHA. See module docstring.
        return self.validate_credentials()

    # --- discovery -----------------------------------------------------------
    def sitemap_entries(self) -> list[dict]:
        """Every movie and series page with its ``lastmod`` (≈10 requests)."""
        index = self._request('GET', '/wp-sitemap.xml')
        if index.status_code >= 400:
            raise ProviderImportError(f'kargadan sitemap index http {index.status_code}', code='kargadan_sitemap_failed')
        parts = parse_sitemap_index(index.text or '')
        if not parts:
            raise ProviderImportError(
                'kargadan sitemap index lists no movie/series sitemaps — the template changed.',
                code='kargadan_sitemap_unparsed',
            )
        entries: list[dict] = []
        for _kind, url in parts:
            response = self._request('GET', url)
            if response.status_code >= 400:
                raise ProviderImportError(f'kargadan sitemap http {response.status_code}: {url}', code='kargadan_sitemap_failed')
            entries.extend(parse_sitemap(response.text or ''))
        return entries

    # --- detail pages -------------------------------------------------------
    def _resolve_redirectors(self, rows: list[dict]) -> list[dict]:
        """Swap on-site redirector links for the file URL they land on."""
        out = []
        for row in rows:
            if not row.get('needs_resolve'):
                out.append(row)
                continue
            try:
                client = self._client_or_create()
                self._throttle()
                with client.stream('GET', row['url'], headers={'Range': 'bytes=0-0'}) as response:
                    final = str(response.url)
                    ctype = (response.headers.get('content-type') or '').lower()
            except Exception:
                continue
            host = (urlsplit(final).hostname or '').lower()
            if host.endswith(self.base_host) or 'text/html' in ctype:
                continue
            resolved = {k: v for k, v in row.items() if k != 'needs_resolve'}
            resolved['url'] = final
            out.append(resolved)
        return out

    def crawl_download_links(self, page_url_or_imdb: str, *, content_type: str = 'movie') -> dict:
        target = (page_url_or_imdb or '').strip()
        kind, imdb_id = imdb_from_path(target)
        if not imdb_id and target.lower().startswith('tt'):
            imdb_id = target.lower()
        if not imdb_id:
            raise ProviderImportError('A Kargadan page is addressed by IMDb id.', code='kargadan_imdb_required')
        path = detail_path(imdb_id, content_type=kind or content_type)
        response = self._request('GET', path)
        if response.status_code == 404:
            raise ProviderImportError('Title is not on Kargadan.', code='kargadan_page_missing')
        if response.status_code >= 400:
            raise ProviderImportError(f'kargadan page http {response.status_code}', code='kargadan_crawl_failed')
        final_path = '/' + urlsplit(str(response.url)).path.strip('/') + '/'
        if imdb_from_path(final_path)[1] != imdb_id:
            # WordPress answers an unknown slug by redirecting to a search or home.
            raise ProviderImportError('Title is not on Kargadan.', code='kargadan_page_missing')
        parsed = parse_download_links(response.text or '', page_path=final_path, base_host=self.base_host)
        record_session_state(parsed.get('logged_in'), detail=parsed.get('code') or 'links')
        parsed['available_links'] = self._resolve_redirectors(parsed.get('available_links') or [])
        parsed['page_path'] = final_path
        parsed['page_url'] = urljoin(self.base_url + '/', final_path.lstrip('/'))
        return parsed
