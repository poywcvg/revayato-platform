"""Subzone.ir (Subf2m mirror) Persian sidecar subtitle crawler.

Used as a fast fallback after SubtitleStar misses during online playback ensure.
Search is title/IMDb based; downloads are ZIP/SRT packs from allowlisted hosts.
"""

from __future__ import annotations

import hashlib
import logging
import re
import ssl
import time
from dataclasses import dataclass
from html import unescape
from pathlib import PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, unquote, urljoin, urlsplit
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
    resolve_subtitlestar_search_title,
)

logger = logging.getLogger(__name__)

_IMDB_RE = re.compile(r'(?<![a-z0-9])(tt\d{6,10})(?!\d)', re.I)
_YEAR_RE = re.compile(r'\((20\d{2}|19\d{2})\)')
_ITEM_RE = re.compile(
    r"<li class='item[^']*'>\s*(.*?)<a class='download icon-download' href='(/subtitles/[^']+/farsi_persian/\d+)'>",
    re.I | re.S,
)
_ITEM_RE_DQ = re.compile(
    r'<li class="item[^"]*">\s*(.*?)<a class="download icon-download" href="(/subtitles/[^"]+/farsi_persian/\d+)">',
    re.I | re.S,
)
_RELEASE_LI_RE = re.compile(r'<li>([^<]{3,240})</li>', re.I)
_SEARCH_HIT_RE = re.compile(
    r'href="(/subtitles/[^"/?]+)"[^>]*>\s*([^<]{2,160})',
    re.I,
)
_SEASON_ORDINAL = {
    1: ('first', '1st', 'season-1', 'season1', 's01', 's1'),
    2: ('second', '2nd', 'season-2', 'season2', 's02', 's2'),
    3: ('third', '3rd', 'season-3', 'season3', 's03', 's3'),
    4: ('fourth', '4th', 'season-4', 'season4', 's04', 's4'),
    5: ('fifth', '5th', 'season-5', 'season5', 's05', 's5'),
    6: ('sixth', '6th', 'season-6', 'season6', 's06', 's6'),
    7: ('seventh', '7th', 'season-7', 'season7', 's07', 's7'),
    8: ('eighth', '8th', 'season-8', 'season8', 's08', 's8'),
    9: ('ninth', '9th', 'season-9', 'season9', 's09', 's9'),
    10: ('tenth', '10th', 'season-10', 'season10', 's10'),
}


class SubzoneError(RuntimeError):
    """Base Subzone provider error."""


class SubzoneBlocked(SubzoneError):
    """Provider asked this crawler to back off."""


@dataclass(frozen=True)
class SubzoneMatch:
    payload: bytes
    filename: str
    page_url: str
    download_url: str
    release_name: str
    source_urls: tuple[str, ...]
    imdb_id: str


@dataclass(frozen=True)
class SubzoneEpisodeMatch:
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
class _Response:
    body: bytes
    url: str
    content_type: str
    filename: str


@dataclass(frozen=True)
class _Candidate:
    detail_path: str
    releases: tuple[str, ...]
    score: int


def _base_url() -> str:
    return str(getattr(settings, 'SUBZONE_BASE_URL', 'https://subzone.ir')).rstrip('/')


def _allowed_hosts() -> tuple[str, ...]:
    configured = getattr(
        settings,
        'SUBZONE_ALLOWED_DOWNLOAD_HOSTS',
        ('subzone.ir', 'subf2m.co', 'sub-api.ir', 'media.sub-api.ir'),
    )
    if isinstance(configured, str):
        configured = configured.split(',')
    base_host = (urlsplit(_base_url()).hostname or '').lower()
    hosts = [str(host).strip().lower().lstrip('.') for host in configured if str(host).strip()]
    if base_host:
        hosts.append(base_host)
    return tuple(dict.fromkeys(hosts))


def _host_allowed(host: str) -> bool:
    host = (host or '').split(':', 1)[0].lower().rstrip('.')
    return any(allowed and (host == allowed or host.endswith(f'.{allowed}')) for allowed in _allowed_hosts())


def _safe_external_url(url: str) -> bool:
    parsed = urlsplit(str(url or '').strip())
    return parsed.scheme == 'https' and bool(parsed.hostname) and _host_allowed(parsed.hostname)


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        if not _safe_external_url(target):
            raise SubzoneError('Subzone redirected to a non-allowlisted host.')
        return super().redirect_request(req, fp, code, msg, headers, target)


def _content_disposition_filename(value: str) -> str:
    utf8_match = re.search(r"filename\*=UTF-8''([^;]+)", value or '', re.I)
    if utf8_match:
        return PurePosixPath(unquote(utf8_match.group(1))).name
    match = re.search(r'filename="?([^";]+)"?', value or '', re.I)
    return PurePosixPath(match.group(1).strip()).name if match else ''


def _throttle(*, urgent: bool = False) -> None:
    default_interval = float(getattr(settings, 'SUBZONE_REQUEST_INTERVAL_SECONDS', 0.8))
    interval = max(0.15, 0.2 if urgent else default_interval)
    key = 'catalog:subzone:next-request'
    now = time.time()
    next_at = float(cache.get(key) or 0)
    if next_at > now:
        time.sleep(min(interval, next_at - now))
    cache.set(key, time.time() + interval, timeout=max(8, int(interval * 4)))


def _fetch(url: str, *, max_bytes: int, timeout_seconds: int, urgent: bool = False) -> _Response:
    if not _safe_external_url(url):
        raise SubzoneError('Subzone URL host is not allowlisted.')
    if cache.get('catalog:subzone:circuit-open'):
        raise SubzoneBlocked('Subzone circuit breaker is open.')

    _throttle(urgent=urgent)
    headers = {
        'User-Agent': str(getattr(
            settings,
            'SUBZONE_USER_AGENT',
            (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ),
        )),
        'Accept': 'text/html,application/xhtml+xml,application/zip,text/plain;q=0.9,*/*;q=0.5',
        'Accept-Language': 'fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'identity',
        'Referer': f'{_base_url()}/',
    }
    request = Request(url, headers=headers)
    verify_ssl = bool(getattr(settings, 'SUBZONE_VERIFY_SSL', True))
    context = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()  # noqa: SLF001
    opener = build_opener(_SafeRedirectHandler(), HTTPSHandler(context=context))
    try:
        with opener.open(request, timeout=max(3, int(timeout_seconds))) as response:
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise SubzoneError('Subzone response exceeded size limit.')
            return _Response(
                body=body,
                url=response.geturl(),
                content_type=str(response.headers.get('Content-Type') or ''),
                filename=_content_disposition_filename(str(response.headers.get('Content-Disposition') or '')),
            )
    except HTTPError as exc:
        if exc.code in {403, 429, 503}:
            cooldown = max(60, int(getattr(settings, 'SUBZONE_BLOCKED_COOLDOWN_SECONDS', 15 * 60)))
            cache.set('catalog:subzone:circuit-open', True, timeout=cooldown)
            raise SubzoneBlocked(f'Subzone blocked request with HTTP {exc.code}') from exc
        raise SubzoneError(f'Subzone HTTP {exc.code}') from exc
    except URLError as exc:
        raise SubzoneError(f'Subzone network error: {exc}') from exc


def _decode_html(payload: bytes) -> str:
    for encoding in ('utf-8-sig', 'utf-8', 'windows-1256'):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode('utf-8', errors='replace')


def _looks_like_html(response: _Response) -> bool:
    ctype = (response.content_type or '').lower()
    if 'html' in ctype:
        return True
    head = response.body[:200].lstrip().lower()
    return head.startswith((b'<!doctype', b'<html', b'<head'))


def _response_members(response: _Response) -> list[tuple[str, bytes]]:
    filename = response.filename or PurePosixPath(unquote(urlsplit(response.url).path)).name
    suffix = PurePosixPath(filename).suffix.casefold()
    if response.body.startswith(b'PK\x03\x04') or suffix == '.zip':
        return _safe_zip_members(response.body, keep_relative_path=True)
    if suffix in {'.srt', '.vtt', '.webvtt', '.ass', '.ssa'} and _has_persian_text(response.body):
        return [(filename, response.body)]
    if _has_persian_text(response.body) and not _looks_like_html(response):
        return [(filename or 'subtitle.srt', response.body)]
    return []


def _slugify_title(title: str) -> str:
    text = re.sub(r'[^a-z0-9]+', '-', str(title or '').casefold())
    return text.strip('-')


def _title_tokens(value: str) -> set[str]:
    return {tok for tok in re.findall(r'[a-z0-9]+', str(value or '').casefold()) if len(tok) > 1}


def _score_search_hit(path: str, label: str, *, title: str, year: int | None) -> int:
    wanted = _title_tokens(title) - {'the', 'a', 'an', 'and'}
    blob = f'{path} {label}'.casefold()
    actual = _title_tokens(blob)
    if not wanted:
        return 0
    overlap = len(wanted & actual)
    if overlap <= 0:
        return -100
    score = overlap * 10
    # Prefer exact-ish slug length (avoid "Interstellar Wars").
    extra = len(actual - wanted - {str(year or ''), 'season', 'complete'})
    score -= min(20, extra * 3)
    if year:
        if str(year) in blob:
            score += 25
        elif re.search(r'(?:19|20)\d{2}', blob) and str(year) not in blob:
            score -= 15
    return score


def _parse_farsi_items(html: str) -> list[tuple[str, tuple[str, ...]]]:
    items: list[tuple[str, tuple[str, ...]]] = []
    for pattern in (_ITEM_RE, _ITEM_RE_DQ):
        for inner, href in pattern.findall(html or ''):
            releases = tuple(
                unescape(name).replace('&amp;', '&').strip()
                for name in _RELEASE_LI_RE.findall(inner)
                if name.strip()
            )
            if href:
                items.append((href, releases or (PurePosixPath(href).name,)))
    # Deduplicate by detail path, keep first (usually highest rated / newest).
    seen: set[str] = set()
    unique: list[tuple[str, tuple[str, ...]]] = []
    for href, releases in items:
        if href in seen:
            continue
        seen.add(href)
        unique.append((href, releases))
    return unique


def _page_imdb_id(html: str) -> str:
    match = _IMDB_RE.search(html or '')
    return normalize_imdb_id(match.group(1)) if match else ''


def _page_year(html: str) -> int | None:
    match = _YEAR_RE.search(html or '')
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _rank_candidates(
    items: list[tuple[str, tuple[str, ...]]],
    *,
    video_urls: list[str],
) -> list[_Candidate]:
    ranked: list[_Candidate] = []
    for href, releases in items:
        best = -10**9
        for release in releases:
            for video_url in video_urls:
                score = _release_score(release, video_url, strict=False)
                if score is None:
                    continue
                best = max(best, score)
            # Also score the release name alone lightly so packs still rank.
            best = max(best, 1 if re.search(r'(?i)farsi|persian|فارسی', release) else 0)
        if best <= -10**8:
            best = 0
        ranked.append(_Candidate(detail_path=href, releases=releases, score=int(best)))
    ranked.sort(key=lambda row: row.score, reverse=True)
    return ranked


def _download_pack(detail_url: str, *, timeout_seconds: int, urgent: bool) -> tuple[_Response, str] | None:
    download_url = detail_url.rstrip('/') + '/download'
    archive_limit = max(512 * 1024, int(getattr(settings, 'SUBZONE_MAX_ARCHIVE_BYTES', 16 * 1024 * 1024)))
    response = _fetch(download_url, max_bytes=archive_limit, timeout_seconds=timeout_seconds, urgent=urgent)
    if _looks_like_html(response):
        return None
    return response, response.url


def _search_title_pages(
    *,
    title: str,
    year: int | None,
    imdb_id: str,
    timeout_seconds: int,
    urgent: bool,
) -> list[str]:
    html_limit = max(256 * 1024, int(getattr(settings, 'SUBZONE_MAX_HTML_BYTES', 2 * 1024 * 1024)))
    queries: list[str] = []
    if imdb_id:
        queries.append(imdb_id)
    if title and year:
        queries.append(f'{title} {year}')
    if title:
        queries.append(title)

    pages: list[tuple[int, str]] = []
    seen: set[str] = set()
    for query in queries:
        if not query.strip():
            continue
        search_url = f'{_base_url()}/subtitles/searchbytitle?query={quote_plus(query.strip())}'
        try:
            search = _fetch(search_url, max_bytes=html_limit, timeout_seconds=timeout_seconds, urgent=urgent)
        except SubzoneBlocked:
            raise
        except SubzoneError as exc:
            logger.info('Subzone search failed for %s: %s', query, exc)
            continue
        html = _decode_html(search.body)
        for path, label in _SEARCH_HIT_RE.findall(html):
            if 'searchbytitle' in path:
                continue
            score = _score_search_hit(path, label, title=title, year=year)
            if score < 8:
                continue
            absolute = urljoin(_base_url() + '/', path)
            if absolute in seen:
                continue
            seen.add(absolute)
            pages.append((score, absolute))
        # Weak hits (score < 30) must not stop the search — the exact page only
        # shows up under the IMDb query or a later title term.
        if pages and max(score for score, _ in pages) >= 30:
            break

    # Direct slug guess as last resort (common Subf2m pattern).
    slug = _slugify_title(title)
    if slug:
        guess = f'{_base_url()}/subtitles/{slug}'
        if guess not in seen:
            pages.append((5, guess))

    pages.sort(key=lambda row: row[0], reverse=True)
    return [url for _, url in pages]


def find_movie_subtitle(
    movie,
    *,
    video_urls: list[str],
    timeout_seconds: int | None = None,
) -> SubzoneMatch | None:
    """Find a Persian Subzone sidecar and bind it to compatible playback URLs."""
    if not bool(getattr(settings, 'SUBZONE_ENABLED', True)):
        return None

    videos = [url for url in video_urls if str(url).startswith(('https://', 'http://'))]
    if not videos:
        return None

    imdb_id = normalize_imdb_id(getattr(movie, 'imdb_id', ''))
    year = getattr(movie, 'release_year', None)
    title, _fa = resolve_subtitlestar_search_title(
        original_title=str(getattr(movie, 'original_title', '') or ''),
        display_title=str(getattr(movie, 'title', '') or ''),
        video_urls=videos,
    )
    if not title and not imdb_id:
        return None

    identity = imdb_id or hashlib.sha256(f'{title}|{year}'.encode()).hexdigest()[:24]
    miss_key = f'catalog:subzone:miss:{identity}'
    if cache.get(miss_key):
        return None

    timeout = max(5, int(timeout_seconds or getattr(settings, 'SUBZONE_TIMEOUT_SECONDS', 12)))
    snappy = timeout <= 16
    deadline = time.monotonic() + timeout
    html_limit = max(256 * 1024, int(getattr(settings, 'SUBZONE_MAX_HTML_BYTES', 2 * 1024 * 1024)))
    # Snappy playback ensure historically stopped after 2 pages/downloads;
    # one more of each keeps the exact page from being hidden by weak hits.
    max_pages = 3
    max_downloads = 3 if snappy else 4

    def _remaining() -> int:
        return max(3, int(deadline - time.monotonic()))

    def _timed_out() -> bool:
        return time.monotonic() >= deadline

    lookup_incomplete = False
    try:
        pages = _search_title_pages(
            title=title,
            year=int(year) if year else None,
            imdb_id=imdb_id,
            timeout_seconds=_remaining(),
            urgent=snappy,
        )
        for page_url in pages[:max_pages]:
            if _timed_out():
                lookup_incomplete = True
                break
            try:
                page = _fetch(page_url, max_bytes=html_limit, timeout_seconds=_remaining(), urgent=snappy)
            except SubzoneBlocked:
                raise
            except SubzoneError as exc:
                logger.info('Subzone title page failed for %s: %s', page_url, exc)
                continue
            html = _decode_html(page.body)
            page_imdb = _page_imdb_id(html)
            if imdb_id and page_imdb and page_imdb != imdb_id:
                continue
            page_year = _page_year(html)
            if year and page_year and abs(int(year) - page_year) > 1 and not (imdb_id and page_imdb == imdb_id):
                continue

            farsi_url = page.url.rstrip('/') + '/farsi_persian'
            try:
                farsi = _fetch(farsi_url, max_bytes=html_limit, timeout_seconds=_remaining(), urgent=snappy)
            except SubzoneBlocked:
                raise
            except SubzoneError as exc:
                logger.info('Subzone Farsi list failed for %s: %s', farsi_url, exc)
                continue

            items = _parse_farsi_items(_decode_html(farsi.body))
            if not items:
                continue
            ranked = _rank_candidates(items, video_urls=videos)
            for candidate in ranked[:max_downloads]:
                if _timed_out():
                    lookup_incomplete = True
                    break
                detail_url = urljoin(_base_url() + '/', candidate.detail_path)
                try:
                    fetched = _download_pack(detail_url, timeout_seconds=_remaining(), urgent=snappy)
                except SubzoneBlocked:
                    raise
                except SubzoneError as exc:
                    logger.info('Subzone download failed for %s: %s', detail_url, exc)
                    continue
                if fetched is None:
                    continue
                response, final_url = fetched
                real_members = [(name, payload) for name, payload in _response_members(response) if payload]
                choice = _choose_release(real_members, video_urls=videos)
                if not choice:
                    # Prefer a member whose name overlaps a listed release tag.
                    persian = [(n, p) for n, p in real_members if _has_persian_text(p)]
                    if candidate.releases and persian:
                        release_blob = ' '.join(candidate.releases).casefold()
                        ranked_persian = sorted(
                            persian,
                            key=lambda row: sum(
                                1 for tok in re.findall(r'[a-z0-9]+', row[0].casefold())
                                if tok in release_blob and len(tok) > 2
                            ),
                            reverse=True,
                        )
                        persian = ranked_persian
                    if not persian:
                        continue
                    filename, payload = persian[0]
                    source_urls = tuple(_safe_bind_videos(filename, videos))
                else:
                    filename, payload, source_urls = choice
                if not payload or not _has_persian_text(payload):
                    continue
                return SubzoneMatch(
                    payload=payload,
                    filename=filename,
                    page_url=detail_url,
                    download_url=final_url,
                    release_name=candidate.releases[0] if candidate.releases else filename,
                    source_urls=source_urls,
                    imdb_id=imdb_id or page_imdb,
                )
            if lookup_incomplete:
                break
    except SubzoneBlocked as exc:
        logger.warning('Subzone lookup paused: %s', exc)
        return None
    except SubzoneError as exc:
        logger.info('Subzone lookup failed for %s: %s', identity, exc)
        return None
    except Exception:
        logger.exception('Unexpected Subzone lookup failure for %s', identity)
        return None

    if not snappy and not lookup_incomplete and not _timed_out():
        negative_ttl = max(300, int(getattr(settings, 'SUBZONE_NEGATIVE_CACHE_SECONDS', 12 * 60 * 60)))
        cache.set(miss_key, True, timeout=negative_ttl)
    return None


def _season_search_queries(title: str, season: int) -> list[str]:
    queries = [
        f'{title} Season {season}',
        f'{title} S{season:02d}',
    ]
    for token in _SEASON_ORDINAL.get(int(season), ()):
        if token.startswith('season'):
            queries.append(f'{title} {token.replace("-", " ")}')
        elif token.endswith(('st', 'nd', 'rd', 'th')) or token in {
            'first', 'second', 'third', 'fourth', 'fifth',
            'sixth', 'seventh', 'eighth', 'ninth', 'tenth',
        }:
            queries.append(f'{title} {token} season')
    return list(dict.fromkeys(queries))


def _season_slug_matches(path: str, *, title: str, season: int) -> bool:
    blob = unquote(path).casefold()
    wanted = _title_tokens(title) - {'the', 'a', 'an', 'and'}
    if wanted and len(wanted & _title_tokens(blob)) < max(1, len(wanted) // 2):
        return False
    markers = {
        f'season-{season}', f'season{season}', f's{season:02d}', f's{season}',
        f'-{season}-season', f'season-{season:02d}',
        *_SEASON_ORDINAL.get(int(season), ()),
    }
    return any(marker in blob for marker in markers)


def find_series_episode_subtitles(
    series,
    *,
    episode_videos: dict[tuple[int, int], list[str]],
    timeout_seconds: int | None = None,
) -> list[SubzoneEpisodeMatch]:
    """Find Persian Subzone sidecars for specific season/episode playback URLs."""
    if not bool(getattr(settings, 'SUBZONE_ENABLED', True)):
        return []

    needed = {
        key: [url for url in urls if str(url).startswith(('https://', 'http://'))]
        for key, urls in (episode_videos or {}).items()
        if isinstance(key, tuple) and len(key) == 2 and urls
    }
    needed = {key: urls for key, urls in needed.items() if urls}
    if not needed:
        return []

    imdb_id = normalize_imdb_id(getattr(series, 'imdb_id', ''))
    year = getattr(series, 'start_year', None) or getattr(series, 'release_year', None)
    all_urls = [url for urls in needed.values() for url in urls]
    title, _fa = resolve_subtitlestar_search_title(
        original_title=str(getattr(series, 'original_title', '') or ''),
        display_title=str(getattr(series, 'title', '') or ''),
        video_urls=all_urls,
    )
    if not title and not imdb_id:
        return []

    identity = imdb_id or hashlib.sha256(f'{title}|{year}'.encode()).hexdigest()[:24]
    miss_key = f'catalog:subzone:series-miss:{identity}'
    if cache.get(miss_key):
        return []

    timeout = max(5, int(timeout_seconds or getattr(settings, 'SUBZONE_TIMEOUT_SECONDS', 12)))
    snappy = timeout <= 16
    deadline = time.monotonic() + timeout
    html_limit = max(256 * 1024, int(getattr(settings, 'SUBZONE_MAX_HTML_BYTES', 2 * 1024 * 1024)))
    results: list[SubzoneEpisodeMatch] = []
    remaining_keys = set(needed.keys())

    def _remaining() -> int:
        return max(3, int(deadline - time.monotonic()))

    def _timed_out() -> bool:
        return time.monotonic() >= deadline

    seasons = sorted({season for season, _episode in remaining_keys})
    lookup_incomplete = False
    try:
        for season in seasons:
            if _timed_out() or not remaining_keys:
                lookup_incomplete = _timed_out()
                break
            season_pages: list[str] = []
            for query in _season_search_queries(title, season)[:3]:
                if _timed_out():
                    lookup_incomplete = True
                    break
                search_url = f'{_base_url()}/subtitles/searchbytitle?query={quote_plus(query)}'
                try:
                    search = _fetch(search_url, max_bytes=html_limit, timeout_seconds=_remaining(), urgent=snappy)
                except SubzoneBlocked:
                    raise
                except SubzoneError:
                    continue
                for path, _label in _SEARCH_HIT_RE.findall(_decode_html(search.body)):
                    if 'searchbytitle' in path:
                        continue
                    if _season_slug_matches(path, title=title, season=season):
                        season_pages.append(urljoin(_base_url() + '/', path))
                if season_pages:
                    break
            season_pages = list(dict.fromkeys(season_pages))[:3]
            for page_url in season_pages:
                if _timed_out() or not remaining_keys:
                    break
                try:
                    farsi = _fetch(
                        page_url.rstrip('/') + '/farsi_persian',
                        max_bytes=html_limit,
                        timeout_seconds=_remaining(),
                        urgent=snappy,
                    )
                except SubzoneBlocked:
                    raise
                except SubzoneError:
                    continue
                items = _parse_farsi_items(_decode_html(farsi.body))
                if not items:
                    continue
                # Prefer packs that mention this season's remaining episodes.
                season_videos = {
                    key: urls for key, urls in needed.items()
                    if key[0] == season and key in remaining_keys
                }
                flat_videos = [url for urls in season_videos.values() for url in urls]
                ranked = _rank_candidates(items, video_urls=flat_videos or all_urls)
                for candidate in ranked[: 3 if snappy else 5]:
                    if _timed_out() or not remaining_keys:
                        lookup_incomplete = _timed_out()
                        break
                    detail_url = urljoin(_base_url() + '/', candidate.detail_path)
                    try:
                        fetched = _download_pack(detail_url, timeout_seconds=_remaining(), urgent=snappy)
                    except SubzoneBlocked:
                        raise
                    except SubzoneError:
                        continue
                    if fetched is None:
                        continue
                    response, final_url = fetched
                    members = [(n, p) for n, p in _response_members(response) if p and _has_persian_text(p)]
                    if not members:
                        continue
                    for (season_no, episode_no), urls in list(season_videos.items()):
                        if (season_no, episode_no) not in remaining_keys:
                            continue
                        episode_members = [
                            (name, payload) for name, payload in members
                            if episode_key_from_name(name) in {(season_no, episode_no), None}
                        ] or members
                        choice = _choose_release(episode_members, video_urls=urls)
                        if not choice:
                            continue
                        filename, payload, source_urls = choice
                        # Require episode marker when the pack has many files.
                        marker = episode_key_from_name(filename)
                        if marker and marker != (season_no, episode_no) and len(members) > 1:
                            continue
                        results.append(SubzoneEpisodeMatch(
                            season_number=season_no,
                            episode_number=episode_no,
                            payload=payload,
                            filename=filename,
                            page_url=detail_url,
                            download_url=final_url,
                            release_name=candidate.releases[0] if candidate.releases else filename,
                            source_urls=source_urls,
                            imdb_id=imdb_id,
                        ))
                        remaining_keys.discard((season_no, episode_no))
                    if not remaining_keys:
                        break
    except SubzoneBlocked as exc:
        logger.warning('Subzone series lookup paused: %s', exc)
        return results
    except SubzoneError as exc:
        logger.info('Subzone series lookup failed for %s: %s', identity, exc)
        return results
    except Exception:
        logger.exception('Unexpected Subzone series lookup failure for %s', identity)
        return results

    if not results and not snappy and not lookup_incomplete and not _timed_out():
        negative_ttl = max(300, int(getattr(settings, 'SUBZONE_NEGATIVE_CACHE_SECONDS', 12 * 60 * 60)))
        cache.set(miss_key, True, timeout=negative_ttl)
    return results


def clear_subzone_miss_for_movie(movie) -> None:
    imdb_id = normalize_imdb_id(getattr(movie, 'imdb_id', ''))
    year = getattr(movie, 'release_year', None)
    links = [item for item in (getattr(movie, 'download_links', None) or []) if isinstance(item, dict)]
    video_urls = [str(item.get('url') or '') for item in links if item.get('url')]
    title, _fa = resolve_subtitlestar_search_title(
        original_title=str(getattr(movie, 'original_title', '') or ''),
        display_title=str(getattr(movie, 'title', '') or ''),
        video_urls=video_urls,
    )
    identity = imdb_id or hashlib.sha256(f'{title}|{year}'.encode()).hexdigest()[:24]
    cache.delete(f'catalog:subzone:miss:{identity}')
    if imdb_id:
        cache.delete(f'catalog:subzone:miss:{imdb_id}')


def clear_subzone_miss_for_series(series) -> None:
    imdb_id = normalize_imdb_id(getattr(series, 'imdb_id', ''))
    title = str(getattr(series, 'original_title', '') or getattr(series, 'title', '') or '').strip()
    year = getattr(series, 'start_year', None)
    identity = imdb_id or hashlib.sha256(f'{title}|{year}'.encode()).hexdigest()[:24]
    cache.delete(f'catalog:subzone:series-miss:{identity}')
    cache.delete(f'catalog:subzone:miss:{identity}')
