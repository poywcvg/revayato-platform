"""SubDL (subdl.com) Persian sidecar subtitles through the official API.

SubDL publishes a documented JSON API keyed by IMDb/TMDb id, so a lookup is an
exact identity match instead of a title guess — the precise, fast provider for
the open-player lane. It needs a free account key in ``SUBDL_API_KEY``; with no
key the provider is simply off. The key travels in the query string, so request
URLs are never logged or put into exception text. Only ``api.subdl.com`` and
``dl.subdl.com`` are ever contacted (redirects included).
"""

from __future__ import annotations

import json
import logging
import ssl
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from django.conf import settings
from django.core.cache import cache

from apps.catalog.subtitle_star import (
    _choose_release,
    _has_persian_text,
    _release_score,
    _safe_bind_videos,
    _safe_zip_members,
    episode_key_from_name,
    normalize_imdb_id,
)

logger = logging.getLogger(__name__)

API_URL = 'https://api.subdl.com/api/v1/subtitles'
DOWNLOAD_BASE = 'https://dl.subdl.com'
SITE_BASE = 'https://subdl.com'
_ALLOWED_HOSTS = ('api.subdl.com', 'dl.subdl.com')
CIRCUIT_OPEN_KEY = 'catalog:subdl:circuit-open'
_PERSIAN_LANGS = {'fa', 'farsi', 'persian', 'farsi_persian', 'farsi/persian'}
_SUB_SUFFIXES = {'.srt', '.vtt', '.webvtt', '.ass', '.ssa'}


class SubdlError(RuntimeError):
    """Base SubDL provider error (never carries the request URL)."""


class SubdlBlocked(SubdlError):
    """Provider rejected the key or asked us to back off."""


@dataclass(frozen=True)
class SubdlMatch:
    payload: bytes
    filename: str
    page_url: str
    download_url: str
    release_name: str
    source_urls: tuple[str, ...]
    imdb_id: str


@dataclass(frozen=True)
class SubdlEpisodeMatch:
    season_number: int
    episode_number: int
    payload: bytes
    filename: str
    page_url: str
    download_url: str
    release_name: str
    source_urls: tuple[str, ...]
    imdb_id: str


@dataclass(frozen=True)
class _Entry:
    """One Persian subtitle row from the API response."""
    url: str
    release_name: str
    season: int | None
    episode: int | None
    full_season: bool
    episode_from: int | None
    episode_end: int | None
    page_url: str

    def covers(self, season: int, episode: int) -> bool:
        if self.season is not None and self.season != season:
            return False
        if self.episode is not None and not self.full_season:
            return self.episode == episode
        if self.episode_from is not None and self.episode_end is not None:
            return self.episode_from <= episode <= self.episode_end
        return True  # season pack (or unlabeled row inside a season query)

    def exact(self, season: int, episode: int) -> bool:
        return self.season == season and self.episode == episode and not self.full_season


def _api_key() -> str:
    return str(getattr(settings, 'SUBDL_API_KEY', '') or '').strip()


def subdl_enabled() -> bool:
    return bool(getattr(settings, 'SUBDL_ENABLED', True)) and bool(_api_key())


def _host_allowed(url: str) -> bool:
    parsed = urlsplit(str(url or ''))
    return parsed.scheme == 'https' and (parsed.hostname or '').lower() in _ALLOWED_HOSTS


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        if not _host_allowed(target):
            raise SubdlError('SubDL redirected to a non-allowlisted host.')
        return super().redirect_request(req, fp, code, msg, headers, target)


def _throttle(*, urgent: bool = False) -> None:
    interval = max(0.1, 0.15 if urgent else float(getattr(settings, 'SUBDL_REQUEST_INTERVAL_SECONDS', 0.5)))
    key = 'catalog:subdl:next-request'
    now = time.time()
    next_at = float(cache.get(key) or 0)
    if next_at > now:
        time.sleep(min(interval, next_at - now))
    cache.set(key, time.time() + interval, timeout=max(8, int(interval * 4)))


def _open_circuit(code: int) -> None:
    # A rejected key will not fix itself in minutes; rate limits clear quickly.
    cooldown = 60 * 60 if code in {401, 403} else 15 * 60
    cache.set(CIRCUIT_OPEN_KEY, True, timeout=cooldown)


def _fetch(url: str, *, max_bytes: int, timeout_seconds: float, urgent: bool) -> tuple[bytes, str]:
    if not _host_allowed(url):
        raise SubdlError('SubDL URL host is not allowlisted.')
    if cache.get(CIRCUIT_OPEN_KEY):
        raise SubdlBlocked('SubDL circuit breaker is open.')
    _throttle(urgent=urgent)
    request = Request(url, headers={
        'User-Agent': 'Revayato/1.0 (+https://revayato.com)',
        'Accept': 'application/json,application/zip,*/*;q=0.5',
        'Accept-Encoding': 'identity',
    })
    opener = build_opener(_SafeRedirectHandler(), HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(request, timeout=max(2.0, float(timeout_seconds))) as response:
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise SubdlError('SubDL response exceeded size limit.')
            return body, response.geturl()
    except HTTPError as exc:
        if exc.code in {401, 403, 429}:
            _open_circuit(exc.code)
            raise SubdlBlocked(f'SubDL rejected request with HTTP {exc.code}') from None
        if exc.code == 404:
            return b'', ''
        raise SubdlError(f'SubDL HTTP {exc.code}') from None
    except URLError as exc:
        raise SubdlError(f'SubDL network error: {type(exc.reason).__name__}') from None
    except (TimeoutError, OSError) as exc:
        raise SubdlError(f'SubDL network error: {type(exc).__name__}') from None


def _as_int(value) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _query(params: dict, *, timeout_seconds: float, urgent: bool) -> dict:
    query = {'api_key': _api_key(), 'languages': 'FA', 'subs_per_page': 30, **params}
    body, _url = _fetch(
        f'{API_URL}?{urlencode({k: v for k, v in query.items() if v not in (None, "")})}',
        max_bytes=2 * 1024 * 1024,
        timeout_seconds=timeout_seconds,
        urgent=urgent,
    )
    if not body:
        return {}
    try:
        data = json.loads(body.decode('utf-8', 'replace'))
    except ValueError:
        raise SubdlError('SubDL returned non-JSON.') from None
    if not isinstance(data, dict):
        return {}
    if data.get('status') is False:
        error = str(data.get('error') or '').casefold()
        if ('api' in error and 'key' in error) or 'not_authorized' in error or 'limit' in error:
            _open_circuit(403)
            raise SubdlBlocked('SubDL rejected the API key or quota.')
        return {}  # "can't find movie or tv" is an ordinary miss
    return data


def _identity_confirmed(data: dict, *, imdb_id: str, tmdb_id: int | None) -> bool:
    """The API answered for *our* title: a result row carries our IMDb/TMDb id."""
    results = [row for row in (data.get('results') or []) if isinstance(row, dict)]
    if not results:
        # No result metadata; the request itself was keyed by an exact id.
        return True
    for row in results:
        if imdb_id and normalize_imdb_id(row.get('imdb_id')) == imdb_id:
            return True
        if tmdb_id and _as_int(row.get('tmdb_id')) == tmdb_id:
            return True
    return False


def _entries(data: dict) -> list[_Entry]:
    rows: list[_Entry] = []
    seen: set[str] = set()
    for row in data.get('subtitles') or []:
        if not isinstance(row, dict):
            continue
        lang = str(row.get('lang') or row.get('language') or '').strip().casefold()
        if lang and lang not in _PERSIAN_LANGS:
            continue
        path = str(row.get('url') or '').strip()
        if not path:
            continue
        url = path if path.startswith('https://') else f'{DOWNLOAD_BASE}/{path.lstrip("/")}'
        if not _host_allowed(url) or url in seen:
            continue
        seen.add(url)
        release = str(row.get('release_name') or row.get('name') or '').strip()
        subtitle_page = str(row.get('subtitlePage') or '').strip()
        page = f'{SITE_BASE}/{subtitle_page.lstrip("/")}' if subtitle_page else url
        rows.append(_Entry(
            url=url,
            release_name=release or PurePosixPath(urlsplit(url).path).name,
            season=_as_int(row.get('season')) or None,
            episode=_as_int(row.get('episode')) or None,
            full_season=bool(row.get('full_season')),
            episode_from=_as_int(row.get('episode_from')),
            episode_end=_as_int(row.get('episode_end')),
            page_url=page,
        ))
    return rows


def _entry_score(entry: _Entry, videos: list[str]) -> int:
    best = -1
    for video in videos:
        score = _release_score(entry.release_name, video, strict=False)
        if score is not None:
            best = max(best, score)
    return best


def _members(body: bytes, filename: str) -> list[tuple[str, bytes]]:
    if body.startswith(b'PK\x03\x04'):
        return [(n, p) for n, p in _safe_zip_members(body, keep_relative_path=True) if p]
    if PurePosixPath(filename).suffix.casefold() in _SUB_SUFFIXES and _has_persian_text(body):
        return [(filename, body)]
    return []


def _identity(imdb_id: str, tmdb_id: int | None) -> str:
    return imdb_id or (f'tmdb{tmdb_id}' if tmdb_id else '')


def find_movie_subtitle(
    movie,
    *,
    video_urls: list[str],
    timeout_seconds: int | None = None,
) -> SubdlMatch | None:
    """Exact-id SubDL lookup for a movie, bound to compatible playback URLs."""
    if not subdl_enabled():
        return None
    videos = [url for url in video_urls if str(url).startswith(('https://', 'http://'))]
    imdb_id = normalize_imdb_id(getattr(movie, 'imdb_id', ''))
    tmdb_id = _as_int(getattr(movie, 'tmdb_id', None)) or None
    identity = _identity(imdb_id, tmdb_id)
    if not videos or not identity:
        return None  # never a fuzzy title search: exact ids only
    miss_key = f'catalog:subdl:miss:{identity}'
    if cache.get(miss_key):
        return None

    timeout = max(3, int(timeout_seconds or getattr(settings, 'SUBDL_TIMEOUT_SECONDS', 12)))
    snappy = timeout <= 16
    deadline = time.monotonic() + timeout
    zip_limit = int(getattr(settings, 'SUBDL_MAX_ZIP_BYTES', 8 * 1024 * 1024))
    complete = False

    def _remaining() -> float:
        return max(2.0, deadline - time.monotonic())

    try:
        params = {'type': 'movie'}
        params.update({'imdb_id': imdb_id} if imdb_id else {'tmdb_id': tmdb_id})
        data = _query(params, timeout_seconds=_remaining(), urgent=snappy)
        if data and not _identity_confirmed(data, imdb_id=imdb_id, tmdb_id=tmdb_id):
            logger.info('SubDL identity mismatch for movie=%s', getattr(movie, 'pk', None))
            return None
        entries = sorted(_entries(data), key=lambda e: _entry_score(e, videos), reverse=True)
        complete = True
        for entry in entries[: 3 if snappy else 5]:
            if time.monotonic() >= deadline:
                complete = False
                break
            try:
                body, final_url = _fetch(entry.url, max_bytes=zip_limit, timeout_seconds=_remaining(), urgent=snappy)
            except SubdlBlocked:
                raise
            except SubdlError as exc:
                logger.info('SubDL download failed for movie=%s: %s', getattr(movie, 'pk', None), exc)
                complete = False
                continue
            members = [(n, p) for n, p in _members(body, entry.url) if _has_persian_text(p)]
            if not members:
                continue
            choice = _choose_release(members, video_urls=videos)
            if choice:
                filename, payload, source_urls = choice
            else:
                filename, payload = members[0]
                source_urls = tuple(_safe_bind_videos(filename, videos))
            if not payload or not _has_persian_text(payload):
                continue
            return SubdlMatch(
                payload=payload,
                filename=filename,
                page_url=entry.page_url[:1000],
                download_url=final_url or entry.url,
                release_name=entry.release_name or filename,
                source_urls=source_urls,
                imdb_id=imdb_id,
            )
    except SubdlBlocked as exc:
        logger.warning('SubDL lookup paused: %s', exc)
        return None
    except SubdlError as exc:
        logger.info('SubDL lookup failed for movie=%s: %s', getattr(movie, 'pk', None), exc)
        return None
    except Exception:
        logger.exception('Unexpected SubDL lookup failure for movie=%s', getattr(movie, 'pk', None))
        return None

    if complete:
        ttl = max(300, int(getattr(settings, 'SUBDL_NEGATIVE_CACHE_SECONDS', 6 * 60 * 60)))
        cache.set(miss_key, True, timeout=ttl)
    return None


def find_series_episode_subtitles(
    series,
    *,
    episode_videos: dict[tuple[int, int], list[str]],
    timeout_seconds: int | None = None,
) -> list[SubdlEpisodeMatch]:
    """Exact-id SubDL lookups per season; the first key's season goes first."""
    if not subdl_enabled():
        return []
    needed = {
        key: [url for url in urls if str(url).startswith(('https://', 'http://'))]
        for key, urls in (episode_videos or {}).items()
        if isinstance(key, tuple) and len(key) == 2 and urls
    }
    needed = {key: urls for key, urls in needed.items() if urls}
    imdb_id = normalize_imdb_id(getattr(series, 'imdb_id', ''))
    tmdb_id = _as_int(getattr(series, 'tmdb_id', None)) or None
    identity = _identity(imdb_id, tmdb_id)
    if not needed or not identity:
        return []
    miss_key = f'catalog:subdl:series-miss:{identity}'
    if cache.get(miss_key):
        return []

    timeout = max(3, int(timeout_seconds or getattr(settings, 'SUBDL_TIMEOUT_SECONDS', 12)))
    snappy = timeout <= 16
    deadline = time.monotonic() + timeout
    zip_limit = int(getattr(settings, 'SUBDL_MAX_ZIP_BYTES', 8 * 1024 * 1024))
    results: list[SubdlEpisodeMatch] = []
    remaining = set(needed)
    downloaded: dict[str, list[tuple[str, bytes]]] = {}
    complete = True

    def _remaining() -> float:
        return max(2.0, deadline - time.monotonic())

    def _pack(entry: _Entry) -> list[tuple[str, bytes]]:
        nonlocal complete
        if entry.url not in downloaded:
            try:
                body, _final = _fetch(entry.url, max_bytes=zip_limit, timeout_seconds=_remaining(), urgent=snappy)
            except SubdlBlocked:
                raise
            except SubdlError as exc:
                logger.info('SubDL download failed for series=%s: %s', getattr(series, 'pk', None), exc)
                complete = False
                body = b''
            downloaded[entry.url] = [(n, p) for n, p in _members(body, entry.url) if _has_persian_text(p)]
        return downloaded[entry.url]

    base = {'type': 'tv'}
    base.update({'imdb_id': imdb_id} if imdb_id else {'tmdb_id': tmdb_id})
    try:
        for season in dict.fromkeys(season for season, _episode in needed):
            if time.monotonic() >= deadline:
                complete = False
                break
            data = _query({**base, 'season_number': season}, timeout_seconds=_remaining(), urgent=snappy)
            if data and not _identity_confirmed(data, imdb_id=imdb_id, tmdb_id=tmdb_id):
                logger.info('SubDL identity mismatch for series=%s', getattr(series, 'pk', None))
                return results
            entries = _entries(data)
            for key in [k for k in needed if k[0] == season]:
                if key not in remaining:
                    continue
                season_no, episode_no = key
                urls = needed[key]
                covering = [e for e in entries if e.covers(season_no, episode_no)]
                # Exact single-episode releases first, then packs; best sync inside each.
                covering.sort(key=lambda e: (e.exact(season_no, episode_no), _entry_score(e, urls)), reverse=True)
                for entry in covering[: 3 if snappy else 5]:
                    if time.monotonic() >= deadline:
                        complete = False
                        break
                    members = _pack(entry)
                    if not members:
                        continue
                    mine = [(n, p) for n, p in members if episode_key_from_name(n) == key]
                    if not mine:
                        # A single-file release for exactly this episode needs no marker.
                        if entry.exact(season_no, episode_no) and len(members) == 1:
                            mine = members
                        else:
                            continue
                    choice = _choose_release(mine, video_urls=urls)
                    if choice:
                        filename, payload, source_urls = choice
                    else:
                        filename, payload = mine[0]
                        source_urls = tuple(_safe_bind_videos(filename, urls))
                    results.append(SubdlEpisodeMatch(
                        season_number=season_no,
                        episode_number=episode_no,
                        payload=payload,
                        filename=filename,
                        page_url=entry.page_url[:1000],
                        download_url=entry.url,
                        release_name=entry.release_name or filename,
                        source_urls=source_urls,
                        imdb_id=imdb_id,
                    ))
                    remaining.discard(key)
                    break
    except SubdlBlocked as exc:
        logger.warning('SubDL series lookup paused: %s', exc)
        return results
    except SubdlError as exc:
        logger.info('SubDL series lookup failed for series=%s: %s', getattr(series, 'pk', None), exc)
        return results
    except Exception:
        logger.exception('Unexpected SubDL series lookup failure for series=%s', getattr(series, 'pk', None))
        return results

    if not results and complete and time.monotonic() < deadline:
        ttl = max(300, int(getattr(settings, 'SUBDL_NEGATIVE_CACHE_SECONDS', 6 * 60 * 60)))
        cache.set(miss_key, True, timeout=ttl)
    return results


def _clear(obj, prefix: str) -> None:
    imdb_id = normalize_imdb_id(getattr(obj, 'imdb_id', ''))
    tmdb_id = _as_int(getattr(obj, 'tmdb_id', None)) or None
    for identity in {imdb_id, f'tmdb{tmdb_id}' if tmdb_id else ''} - {''}:
        cache.delete(f'catalog:subdl:{prefix}:{identity}')


def clear_subdl_miss_for_movie(movie) -> None:
    _clear(movie, 'miss')


def clear_subdl_miss_for_series(series) -> None:
    _clear(series, 'series-miss')
