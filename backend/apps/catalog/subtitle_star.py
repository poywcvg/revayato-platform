"""Conservative SubtitleStar lookup for Persian movie/series sidecar subtitles.

SubtitleStar is subtitle-only (typically ZIP packs of SRT/VTT). Film2Media /
myf2m remains the source of movie and series video URLs; tracks returned here
are bound to those playback URLs and never replace the video itself.

The provider is deliberately strict: an IMDb id on the catalog row must also
exist on the SubtitleStar detail page.  That prevents a similarly named remake
or series from silently receiving the wrong subtitle.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import ssl
import time
import unicodedata
import zipfile
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_IMDB_RE = re.compile(r'(?<![a-z0-9])(tt\d{6,10})(?!\d)', re.I)
_EPISODE_MARKER_RE = re.compile(
    r'(?:'
    r'[sS](?P<s1>\d{1,2})\s*[._\-\s]*[eE](?P<e1>\d{1,3})'
    r'|(?P<s2>\d{1,2})\s*[xX]\s*(?P<e2>\d{1,3})'
    r'|(?:season|فصل)\s*(?P<s3>\d{1,2})\D{0,16}(?:episode|قسمت|ep)\s*(?P<e3>\d{1,3})'
    r')',
    re.I,
)
_SEASON_DIR_RE = re.compile(r'(?:^|[/_\-.])(?:season|فصل|s)[._\-\s]*(\d{1,2})(?:$|[/_\-.])', re.I)
_EPISODE_ONLY_RE = re.compile(r'(?:^|[/_\-.])[eE](\d{1,3})(?:[._\-]|$)')
_SERIES_SEGMENT_RE = re.compile(
    r'(?i)(?:^|[\s._\-/])'
    r'(?:s\d{1,2}(?:\s*[._\-/]?\s*e\d{1,3})?|\d{1,2}\s*[xX]\s*\d{1,3}|e\d{1,3})'
    r'(?:$|[\s._\-/])',
)
_SUBTITLE_EXTENSIONS = frozenset({'.srt', '.vtt', '.webvtt', '.ass', '.ssa'})
_ARCHIVE_EXTENSIONS = frozenset({'.zip'})
_REJECTED_EXTENSIONS = frozenset({
    '.exe', '.com', '.bat', '.cmd', '.js', '.jar', '.msi', '.php', '.py', '.sh',
})
_SOURCE_ALIASES = {
    'bluray': 'bluray',
    'blu-ray': 'bluray',
    'brrip': 'bluray',
    'bdrip': 'bluray',
    'webdl': 'web',
    'web-dl': 'web',
    'webrip': 'web',
    'web': 'web',
    'hdtv': 'hdtv',
    'hdrip': 'hdtv',
    'dvdrip': 'dvd',
    'dvd': 'dvd',
    'cam': 'cam',
    'telesync': 'cam',
}
_NOISE_TOKENS = frozenset({
    'persian', 'farsi', 'fa', 'subtitle', 'subtitles', 'sub', 'softsub',
    'download', 'film', 'movie', 'series', 'season', 'episode', 'www', 'com',
    'org', 'net', 'ir', 'x264', 'x265', 'h264', 'h265', 'hevc', 'aac', 'dts',
    'ddp', '10bit', '480p', '720p', '1080p', '2160p', '4k',
})
# Strip release tags when recovering an English title from Film2Media CDN paths.
# The trailing boundary is a lookahead so adjacent tags (…1080p.WEB-DL.…,
# …720p.BluRay.…) each keep their leading delimiter and all get stripped.
_RELEASE_TAG_RE = re.compile(
    r'(?i)(?:^|[._\-\s])(?:'
    r'2160p|1080p|720p|480p|360p|4k|uhd|10bit|8bit|x264|x265|h264|h265|hevc|avc|'
    r'web[ ._-]?dl|bluray|blu-?ray|webrip|hdrip|brrip|bdrip|remux|proper|repack|internal|'
    r'yify|yts|pahe|rarbg|psa|amzn|nf|dsnp|atvp|hmax|film2media|f2m|bmb|poke|'
    r'farsi[\._\-\s]?sub|fa[\._\-\s]?sub|softsub|soft[\._\-\s]?sub|hardsub|hard[\._\-\s]?sub|'
    r'blusub|subblu|rsub|dubbed|dual|multi|'
    r'malayalam|hindi|tamil|telugu|kannada|bengali|korean|japanese|chinese|thai'
    r')(?:$|(?=[._\-\s]))'
)
_YEAR_IN_RELEASE_RE = re.compile(r'(?i)^(.+?)[._\-\s]((?:19|20)\d{2})(?:$|[._\-\s])')
_CDN_FOLDER_NOISE = frozenset({
    'soft', 'softsub', 'soft-sub', 'soft_sub', 'blusub', 'subblu', 'softblu',
    'rsub', 'sub', 'hard', 'hardsub', 'hard-sub', 'hard_sub', 'dub', 'dubbed',
    'dual', 'multi', 'movie', 'movies', 'film', 'films', 'series', 'tv', 'anime',
    'fullhd', 'hd', 'uhd', '4k', 'cam', 'trailer', 'sample',
})


class SubtitleStarError(RuntimeError):
    """Base provider error."""


class SubtitleStarBlocked(SubtitleStarError):
    """The provider asked this crawler to stop (Cloudflare/429/403)."""


@dataclass(frozen=True)
class SubtitleStarMatch:
    payload: bytes
    filename: str
    page_url: str
    download_url: str
    release_name: str
    source_urls: tuple[str, ...]
    imdb_id: str


@dataclass(frozen=True)
class SubtitleStarEpisodeMatch:
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
class _Link:
    url: str
    text: str
    attributes: dict[str, str]


@dataclass(frozen=True)
class _Response:
    body: bytes
    url: str
    content_type: str
    filename: str


class _HTMLLinks(HTMLParser):
    _URL_ATTRIBUTES = (
        'data-href', 'data-url', 'data-link', 'data-download', 'data-file',
        'href', 'action',
    )

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[_Link] = []
        self._anchor_attrs: dict[str, str] | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        values = {
            str(key).lower(): str(value or '').strip()
            for key, value in attrs
            if key
        }
        if tag.lower() == 'a':
            self._anchor_attrs = values
            self._anchor_text = []
            return
        for key in self._URL_ATTRIBUTES:
            if values.get(key):
                self.links.append(_Link(values[key], '', values))

    def handle_data(self, data: str):
        if self._anchor_attrs is not None:
            self._anchor_text.append(data)

    def handle_endtag(self, tag: str):
        if tag.lower() != 'a' or self._anchor_attrs is None:
            return
        url = next(
            (self._anchor_attrs.get(key, '') for key in self._URL_ATTRIBUTES if self._anchor_attrs.get(key)),
            '',
        )
        if not url or url.startswith(('#', 'javascript:')):
            onclick = self._anchor_attrs.get('onclick', '')
            match = re.search(r"""['"]((?:https://|/)[^'"]+)['"]""", onclick, re.I)
            url = match.group(1) if match else ''
        if url:
            text = ' '.join(''.join(self._anchor_text).split())
            self.links.append(_Link(url, text, self._anchor_attrs))
        self._anchor_attrs = None
        self._anchor_text = []


def normalize_imdb_id(value: object) -> str:
    raw = str(value or '').strip().lower()
    match = _IMDB_RE.search(raw)
    if match:
        return match.group(1).lower()
    if re.fullmatch(r'\d{6,10}', raw):
        return f'tt{raw}'
    return ''


def _normalize_title(value: object) -> str:
    text = unicodedata.normalize('NFKC', unescape(str(value or ''))).casefold()
    text = text.replace('&', ' and ')
    return ' '.join(re.findall(r'[a-z0-9\u0600-\u06ff]+', text))


def _clean_release_title(value: object) -> str:
    """Turn ``Marco.2024.1080p...`` / folder names into a Latin search title."""
    raw = unquote(str(value or '')).strip()
    if not raw:
        return ''
    # Only strip a real media/subtitle suffix. Pathlib treats ``.Black`` in
    # ``Orange.Is.the.New.Black`` as an extension and would drop the last word.
    path_name = raw.replace('\\', '/').split('/')[-1]
    suffix = PurePosixPath(path_name).suffix.casefold()
    if suffix in _SUBTITLE_EXTENSIONS | _ARCHIVE_EXTENSIONS | {
        '.mkv', '.mp4', '.avi', '.mov', '.m4v', '.wmv', '.ts', '.m2ts',
    }:
        raw = PurePosixPath(path_name).stem
    else:
        raw = path_name
    year_match = _YEAR_IN_RELEASE_RE.match(raw)
    if year_match:
        raw = year_match.group(1)
    cleaned = raw.replace('.', ' ').replace('_', ' ').replace('-', ' ')
    cleaned = _RELEASE_TAG_RE.sub(' ', f' {cleaned} ')
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' ._-')
    if not cleaned or not re.search(r'[A-Za-z]', cleaned):
        return ''
    # Ignore junk folder names like Soft / BluSUB / 2024.
    if cleaned.casefold() in _NOISE_TOKENS or re.fullmatch(r'(?:19|20)\d{2}', cleaned):
        return ''
    if len(cleaned) < 2 or len(cleaned.split()) > 10:
        return ''
    return cleaned


def latin_title_hint_from_urls(video_urls: list[str] | None) -> str:
    """Best-effort English title from Soft/Hard CDN paths when TMDB title is non-Latin."""
    for url in video_urls or []:
        path = unquote(urlsplit(str(url or '')).path)
        parts = [part for part in path.split('/') if part]
        # Prefer Title.Year parent folder, then the filename stem.
        candidates: list[str] = []
        if len(parts) >= 2:
            candidates.append(parts[-2])
        if len(parts) >= 3:
            candidates.append(parts[-3])
        if len(parts) >= 4:
            candidates.append(parts[-4])
        if parts:
            candidates.append(PurePosixPath(parts[-1]).stem)
        for candidate in candidates:
            folder = str(candidate or '').strip().casefold()
            if folder in _CDN_FOLDER_NOISE or folder in _NOISE_TOKENS:
                continue
            if re.fullmatch(r'(?:19|20)\d{2}', folder):
                continue
            hint = _clean_release_title(candidate)
            if hint:
                # Drop episode segments (S01E02, e03, …) so a CDN hint stays a
                # plain series title instead of out-ranking “Example Series”
                # during title resolution with a token superset (…+s01e02).
                hint = re.sub(r'\s+', ' ', _SERIES_SEGMENT_RE.sub(' ', hint)).strip(' ._-')
            if hint and hint.casefold() not in _CDN_FOLDER_NOISE:
                return hint
    return ''


def _ascii_primary_title(title: str) -> str:
    """Prefer the English head before a non-ASCII / translation colon tail.

    TMDB often stores ``Dreams: Sueños`` while SubtitleStar indexes ``Dreams 2025``.
    Keep ASCII alternate titles like ``Spider-Man: No Way Home``.
    """
    text = str(title or '').strip()
    if not text or ':' not in text:
        return text
    left, right = text.split(':', 1)
    left = left.strip()
    right = right.strip()
    if len(left) < 2 or not re.search(r'[A-Za-z]', left):
        return text
    # Drop translation / accented tails that poison ``?s=`` lookups.
    if right and re.search(r'[^\x00-\x7f]', right):
        return left
    if right and not re.search(r'[A-Za-z]', right):
        return left
    return text


def resolve_subtitlestar_search_title(
    *,
    original_title: str = '',
    display_title: str = '',
    video_urls: list[str] | None = None,
) -> tuple[str, str]:
    """Return ``(latin_or_best_title, persian_display_title)`` for SubtitleStar search.

    Non-Latin originals (Malayalam, CJK, …) fail SubtitleStar ``?s=`` lookups; Film2Media
    URLs almost always carry the English release name. Prefer that CDN hint when it
    agrees with a Latin TMDB title so ``Dreams: Sueños`` becomes searchable ``Dreams``.
    """
    from apps.catalog.localization import contains_disallowed_catalog_script, contains_persian, is_latin_text

    original = str(original_title or '').strip()
    display = str(display_title or '').strip()
    url_hint = latin_title_hint_from_urls(video_urls)
    fa_title = display if contains_persian(display) else ''

    if is_latin_text(original):
        primary = _ascii_primary_title(original) or original
        if url_hint:
            hint_tokens = _tokens(url_hint)
            primary_tokens = _tokens(primary)
            if hint_tokens and primary_tokens and (
                hint_tokens <= primary_tokens
                or primary_tokens <= hint_tokens
                or bool(hint_tokens & primary_tokens)
            ):
                # Prefer the more complete title when one token set contains the other
                # (CDN hints can truncate: ``Orange Is the New`` vs full TMDB title).
                if primary_tokens < hint_tokens:
                    title = url_hint
                elif hint_tokens < primary_tokens:
                    title = primary
                else:
                    title = primary if len(primary) >= len(url_hint) else url_hint
            else:
                title = primary
        else:
            title = primary
    elif url_hint:
        title = url_hint
    elif is_latin_text(display):
        title = _ascii_primary_title(display) or display
    elif original and not contains_disallowed_catalog_script(original):
        title = original
    else:
        title = url_hint or display or original
    return title, fa_title


def _subtitlestar_search_terms(
    *,
    title: str,
    fa_title: str = '',
    year: int | None = None,
    imdb_id: str = '',
    video_urls: list[str] | None = None,
) -> list[str]:
    """Ordered ``?s=`` terms — CDN ``Title Year`` first, IMDb last (noisy widgets)."""
    clean_title = re.sub(r'[:\-_/]+', ' ', title or '')
    clean_title = re.sub(r'\s+', ' ', clean_title).strip()
    title_year = ' '.join(part for part in (clean_title, str(year or '')) if part)
    url_hint = latin_title_hint_from_urls(video_urls)
    url_year = ' '.join(part for part in (url_hint, str(year or '')) if part)
    terms: list[str] = []
    for candidate in (url_year, title_year, url_hint, clean_title, fa_title, imdb_id):
        if candidate and candidate not in terms:
            terms.append(candidate)
    return terms


def _tokens(value: object) -> set[str]:
    return {
        token
        for token in _normalize_title(unquote(str(value or ''))).split()
        if len(token) > 1 and token not in _NOISE_TOKENS
    }


def _source_kind(value: object) -> str:
    normalized = re.sub(r'[^a-z0-9]+', '-', unquote(str(value or '')).casefold())
    for marker, canonical in _SOURCE_ALIASES.items():
        if re.search(rf'(?:^|-){re.escape(marker)}(?:-|$)', normalized):
            return canonical
    return ''


def _quality(value: object) -> str:
    match = re.search(r'(?<!\d)(2160|1080|720|480)p?(?!\d)', str(value or ''), re.I)
    return match.group(1) if match else ''


def _fps(value: object) -> str:
    match = re.search(r'(?<!\d)(23(?:\.976)?|24|25|29(?:\.97)?|30|50|59(?:\.94)?|60)\s*fps', str(value or ''), re.I)
    return match.group(1) if match else ''


def episode_key_from_name(value: object) -> tuple[int, int] | None:
    """Parse (season, episode) from a release name or playback URL path."""
    text = unquote(str(value or '')).replace('\\', '/')
    if not text:
        return None
    match = _EPISODE_MARKER_RE.search(text)
    if match:
        season = int(next(group for group in (match.group('s1'), match.group('s2'), match.group('s3')) if group))
        episode = int(next(group for group in (match.group('e1'), match.group('e2'), match.group('e3')) if group))
        if season >= 1 and episode >= 1:
            return season, episode

    season_match = _SEASON_DIR_RE.search(text)
    episode_match = _EPISODE_ONLY_RE.search(PurePosixPath(text).name)
    if season_match and episode_match:
        season = int(season_match.group(1))
        episode = int(episode_match.group(1))
        if season >= 1 and episode >= 1:
            return season, episode
    return None


def _release_score(
    subtitle_name: str,
    video_url: str,
    *,
    strict: bool = True,
) -> int | None:
    """Score a subtitle release against one video URL; None means known mismatch.

    Strict mode rejects source/FPS conflicts so Soft encodes stay synced when a
    matching pack exists. Soft mode still scores those pairs so movies are not
    left subtitle-less when SubtitleStar only ships a BluRay pack for a WEB Soft
    encode (common on Film2Media).
    """
    subtitle_episode = episode_key_from_name(subtitle_name)
    video_episode = episode_key_from_name(video_url)
    if subtitle_episode and video_episode and subtitle_episode != video_episode:
        return None

    subtitle_source = _source_kind(subtitle_name)
    video_source = _source_kind(video_url)
    source_conflict = bool(subtitle_source and video_source and subtitle_source != video_source)
    if strict and source_conflict:
        return None
    subtitle_fps = _fps(subtitle_name)
    video_fps = _fps(video_url)
    fps_conflict = bool(subtitle_fps and video_fps and subtitle_fps != video_fps)
    if strict and fps_conflict:
        return None

    subtitle_tokens = _tokens(PurePosixPath(urlsplit(subtitle_name).path).name)
    video_tokens = _tokens(PurePosixPath(urlsplit(video_url).path).name)
    score = len(subtitle_tokens & video_tokens) * 4
    if subtitle_episode and video_episode and subtitle_episode == video_episode:
        score += 35
    if subtitle_source and subtitle_source == video_source:
        score += 45
    elif source_conflict:
        score -= 20
    if subtitle_fps and subtitle_fps == video_fps:
        score += 25
    elif fps_conflict:
        score -= 15
    if _quality(subtitle_name) and _quality(subtitle_name) == _quality(video_url):
        score += 4
    if any(marker in subtitle_name.casefold() for marker in ('farsi', 'persian', 'فارسی', 'پارسی')):
        score += 5
    return score


def _allowed_hosts() -> tuple[str, ...]:
    configured = getattr(
        settings,
        'SUBTITLESTAR_ALLOWED_DOWNLOAD_HOSTS',
        ('subtitlestar.com', 'file-share.io'),
    )
    if isinstance(configured, str):
        configured = configured.split(',')
    return tuple(str(host).strip().lower().lstrip('.') for host in configured if str(host).strip())


def _host_allowed(host: str) -> bool:
    host = (host or '').split(':', 1)[0].lower().rstrip('.')
    base_host = (
        urlsplit(getattr(settings, 'SUBTITLESTAR_BASE_URL', 'https://subtitlestar.com')).hostname or ''
    ).lower()
    allowed_hosts = (*_allowed_hosts(), base_host)
    return any(
        allowed and (host == allowed or host.endswith(f'.{allowed}'))
        for allowed in allowed_hosts
    )


def _safe_external_url(url: str) -> bool:
    parsed = urlsplit(str(url or '').strip())
    return parsed.scheme == 'https' and bool(parsed.hostname) and _host_allowed(parsed.hostname)


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        if not _safe_external_url(target):
            raise SubtitleStarError('Subtitle provider redirected to a non-allowlisted host.')
        redirected = super().redirect_request(req, fp, code, msg, headers, target)
        if redirected is not None and not _provider_host(target):
            redirected.remove_header('Cookie')
        return redirected


def _provider_host(url: str) -> bool:
    base_host = urlsplit(getattr(settings, 'SUBTITLESTAR_BASE_URL', 'https://subtitlestar.com')).hostname or ''
    return (urlsplit(url).hostname or '').lower() == base_host.lower()


def _throttle(url: str, *, urgent: bool = False) -> None:
    if not _provider_host(url):
        return
    default_interval = float(getattr(settings, 'SUBTITLESTAR_REQUEST_INTERVAL_SECONDS', 2.0))
    interval = max(0.25, 0.35 if urgent else default_interval)
    key = 'catalog:subtitlestar:next-request'
    now = time.time()
    next_at = float(cache.get(key) or 0)
    if next_at > now:
        time.sleep(min(interval, next_at - now))
    cache.set(key, time.time() + interval, timeout=max(10, int(interval * 4)))


def _content_disposition_filename(value: str) -> str:
    utf8_match = re.search(r"filename\*=UTF-8''([^;]+)", value or '', re.I)
    if utf8_match:
        return PurePosixPath(unquote(utf8_match.group(1))).name
    match = re.search(r'filename="?([^";]+)"?', value or '', re.I)
    return PurePosixPath(match.group(1).strip()).name if match else ''


def _fetch(url: str, *, max_bytes: int, timeout_seconds: int, urgent: bool = False) -> _Response:
    if not _safe_external_url(url):
        raise SubtitleStarError('Subtitle URL host is not allowlisted.')
    if _provider_host(url) and cache.get('catalog:subtitlestar:circuit-open'):
        raise SubtitleStarBlocked('SubtitleStar circuit breaker is open.')

    _throttle(url, urgent=urgent)
    headers = {
            'User-Agent': str(getattr(
            settings,
            'SUBTITLESTAR_USER_AGENT',
            (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ),
        )),
        'Accept': 'text/html,application/xhtml+xml,application/zip,text/plain;q=0.9,*/*;q=0.5',
        'Accept-Language': 'fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'identity',
    }
    if _provider_host(url):
        base = str(getattr(settings, 'SUBTITLESTAR_BASE_URL', 'https://subtitlestar.com')).rstrip('/')
        headers['Referer'] = f'{base}/'
        cookie = str(getattr(settings, 'SUBTITLESTAR_COOKIE', '') or '').strip()
        if cookie:
            headers['Cookie'] = cookie
    request = Request(url, headers=headers)
    verify_ssl = bool(getattr(settings, 'SUBTITLESTAR_VERIFY_SSL', True))
    context = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()  # noqa: SLF001
    opener = build_opener(_SafeRedirectHandler(), HTTPSHandler(context=context))
    try:
        with opener.open(request, timeout=max(5, int(timeout_seconds or 20))) as response:
            try:
                content_length = int(response.headers.get('Content-Length') or 0)
            except (TypeError, ValueError):
                content_length = 0
            if content_length > max_bytes:
                raise SubtitleStarError('Subtitle response exceeds the configured size limit.')
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise SubtitleStarError('Subtitle response exceeds the configured size limit.')
            content_type = str(response.headers.get('Content-Type') or '').split(';', 1)[0].lower()
            filename = _content_disposition_filename(response.headers.get('Content-Disposition') or '')
            final_url = str(response.geturl() or url)
    except HTTPError as exc:
        if exc.code in {403, 429, 503} and _provider_host(url):
            cooldown = max(300, int(getattr(settings, 'SUBTITLESTAR_BLOCKED_COOLDOWN_SECONDS', 20 * 60)))
            cache.set('catalog:subtitlestar:circuit-open', True, timeout=cooldown)
            raise SubtitleStarBlocked(f'SubtitleStar returned HTTP {exc.code}.') from exc
        raise SubtitleStarError(f'Subtitle provider returned HTTP {exc.code}.') from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SubtitleStarError(f'Subtitle provider request failed: {exc}.') from exc

    challenge_markers = (
        b'cf-mitigated',
        b'challenges.cloudflare.com',
        b'Just a moment...',
        b'cf-browser-verification',
        b'Attention Required! | Cloudflare',
    )
    head = body[:12000]
    if any(marker in head for marker in challenge_markers):
        cooldown = max(300, int(getattr(settings, 'SUBTITLESTAR_BLOCKED_COOLDOWN_SECONDS', 20 * 60)))
        cache.set('catalog:subtitlestar:circuit-open', True, timeout=cooldown)
        raise SubtitleStarBlocked('SubtitleStar returned a browser challenge.')
    return _Response(body=body, url=final_url, content_type=content_type, filename=filename)


def _decode_html(payload: bytes) -> str:
    for encoding in ('utf-8-sig', 'utf-16', 'windows-1256'):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode('utf-8', errors='replace')


def _parse_links(html: str, base_url: str) -> list[_Link]:
    parser = _HTMLLinks()
    parser.feed(html)
    links: list[_Link] = []
    seen: set[str] = set()
    for link in parser.links:
        url = urljoin(base_url, unescape(link.url).strip())
        if not _safe_external_url(url) or url in seen:
            continue
        seen.add(url)
        links.append(_Link(url=url, text=link.text, attributes=link.attributes))
    return links


def _title_match_ratio(url: str, title: str) -> float:
    wanted = _tokens(title) - {'the', 'a', 'an', 'and'}
    if not wanted:
        wanted = _tokens(title)
    if not wanted:
        return 0.0
    path = unquote(urlsplit(url).path)
    actual = _tokens(path)
    overlap = len(wanted & actual) / len(wanted)
    if overlap <= 0:
        return 0.0
    # Penalize longer slugs (Train Dreams / In Your Dreams) when the catalog
    # title is the short form ``Dreams`` — otherwise every *Dreams* post ties at 1.0.
    noise = {
        'persian', 'subtitles', 'subtitle', 'دانلود', 'زیرنویس', 'فارسی',
        'pfdm', 'movie', 'film', 'series', 'season', 'complete', 'all',
    }
    year_tokens = {tok for tok in actual if re.fullmatch(r'(?:19|20)\d{2}', tok)}
    extra = actual - wanted - noise - year_tokens
    if extra:
        overlap *= max(0.15, 1.0 - 0.35 * len(extra))
    return overlap


def _candidate_pages(html: str, base_url: str, *, expected_title: str = '') -> list[str]:
    base_host = (urlsplit(getattr(settings, 'SUBTITLESTAR_BASE_URL', base_url)).hostname or '').lower()
    candidates: list[tuple[int, str]] = []
    for link in _parse_links(html, base_url):
        parsed = urlsplit(link.url)
        if (parsed.hostname or '').lower() != base_host:
            continue
        # Fragment-only comment anchors (#respond) waste detail fetches.
        if parsed.fragment and not parsed.path.rstrip('/'):
            continue
        path = unquote(parsed.path).casefold()
        text = link.text.casefold()
        if path in {'', '/'} or any(segment in path for segment in ('/page/', '/years/', '/genres/', '/tag/', '/category/')):
            continue
        if parsed.fragment in {'respond', 'comments'}:
            continue
        score = 0
        # English slugs + Persian/PFDM post slugs used by SubtitleStar.
        if (
            'persian-subtitles-' in path
            or 'زیرنویس-فارسی' in path
            or 'زیرنویس-pfdm-' in path
            or re.search(r'/زیرنویس[^/]*/?$', path)
            or path.startswith('/زیرنویس')
        ):
            score += 80
        if any(token in path or token in text for token in ('series', 'سریال', 'season', 'فصل')):
            score += 20
        if 'دانلود زیرنویس فارسی' in text or 'زیرنویس فارسی' in text:
            score += 35
        if expected_title:
            score += int(_title_match_ratio(link.url, expected_title) * 60)
            # Persian display titles often appear only in link text / slug.
            score += int(_title_match_ratio(f'{link.text} {path}', expected_title) * 40)
        if score:
            # Drop fragment so #respond does not duplicate the real post.
            clean = parsed._replace(fragment='').geturl()
            candidates.append((score, clean))
    candidates.sort(key=lambda row: row[0], reverse=True)
    return list(dict.fromkeys(url for _, url in candidates))


def _download_link_score(link: _Link) -> int:
    parsed = urlsplit(link.url)
    path = unquote(parsed.path).casefold()
    suffix = PurePosixPath(path).suffix
    query = parse_qs(parsed.query)
    text = f'{link.text} {path}'.casefold()
    attribute_text = ' '.join(f'{key} {value}' for key, value in link.attributes.items()).casefold()
    rel = link.attributes.get('rel', '').casefold()
    if any(token in rel for token in ('preconnect', 'dns-prefetch', 'canonical', 'stylesheet')):
        return -1000
    score = 0
    if suffix in _SUBTITLE_EXTENSIONS | _ARCHIVE_EXTENSIONS:
        score += 120
    if (parsed.hostname or '').lower().endswith('file-share.io'):
        score += 20
    if 'download' in path or 'download' in query or 'دانلود' in text:
        score += 40
    if 'download' in link.attributes:
        score += 30
    if any(link.attributes.get(key) for key in ('data-href', 'data-url', 'data-link', 'data-download', 'data-file')):
        score += 25
    if 'download' in attribute_text:
        score += 20
    if suffix in _REJECTED_EXTENSIONS or any(token in path for token in ('/wp-admin/', '/wp-login', '/feed/')):
        return -1000
    return score


def _download_links(html: str, base_url: str) -> list[str]:
    ranked = [
        (_download_link_score(link), link.url)
        for link in _parse_links(html, base_url)
    ]
    ranked = [row for row in ranked if row[0] >= 40]
    ranked.sort(key=lambda row: row[0], reverse=True)
    return list(dict.fromkeys(url for _, url in ranked))


_SEASON_PACK_RE = re.compile(
    r'(?:all[-_\s]?s|s(?:eason)?|فصل)[-_\s]?(\d{1,2})|(?:^|[^0-9])s(\d{1,2})(?:[^0-9]|$)',
    re.I,
)


def _season_number_from_download_url(url: str) -> int | None:
    text = unquote(str(url or ''))
    match = _SEASON_PACK_RE.search(text)
    if not match:
        return None
    for group in match.groups():
        if group:
            try:
                value = int(group)
            except (TypeError, ValueError):
                continue
            if 1 <= value <= 40:
                return value
    return None


def _download_links_for_seasons(
    html: str,
    base_url: str,
    *,
    needed_seasons: set[int] | None = None,
) -> list[str]:
    """Prefer season packs that match the open episode(s) over newest-season zips."""
    links = _download_links(html, base_url)
    # Skip tag/category pages that only matched because of «فصل N» in the URL.
    links = [
        url for url in links
        if '/tag/' not in urlsplit(url).path.casefold()
        and '/category/' not in urlsplit(url).path.casefold()
    ]
    if not needed_seasons:
        return links
    preferred: list[str] = []
    other: list[str] = []
    for url in links:
        season = _season_number_from_download_url(url)
        if season in needed_seasons:
            preferred.append(url)
        else:
            other.append(url)
    return list(dict.fromkeys([*preferred, *other]))


def _has_exact_identity(html: str, *, imdb_id: str, title: str, year: int | None) -> bool:
    ids = {match.lower() for match in _IMDB_RE.findall(html)}
    if imdb_id:
        return imdb_id in ids
    # Rows without IMDb are accepted only with both a strong title and exact year.
    normalized_title = _normalize_title(title)
    if not normalized_title or not year:
        return False
    normalized_html = _normalize_title(re.sub(r'<[^>]+>', ' ', html))
    return normalized_title in normalized_html and re.search(rf'(?<!\d){int(year)}(?!\d)', html) is not None


def _looks_like_html(response: _Response) -> bool:
    return response.content_type in {'text/html', 'application/xhtml+xml'} or response.body.lstrip().startswith(
        (b'<!DOCTYPE html', b'<html', b'<!doctype html'),
    )


def _decode_subtitle_text(payload: bytes) -> str:
    # Prefer clean UTF-8 — CP1256 scoring of UTF-8 bytes invents false Persian glyphs.
    for encoding in ('utf-8-sig', 'utf-8'):
        try:
            text = payload.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        if '\ufffd' in text or '\x00' in text[:4000]:
            continue
        if re.search(r'[\u0600-\u06ff]', text):
            return text.replace('ي', 'ی').replace('ى', 'ی').replace('ك', 'ک')

    best = ''
    best_score = -10**9
    for encoding in ('utf-16', 'windows-1256', 'cp1256'):
        try:
            text = payload.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        persian = len(re.findall(r'[\u0600-\u06ff]', text))
        replacement = text.count('\ufffd')
        nul = text.count('\x00')
        mojibake = len(re.findall(r'ظ.|ط.|غŒ|â€', text[:4000]))
        score = persian * 3 - replacement * 20 - nul * 10 - mojibake * 8
        if score > best_score:
            best = text.replace('ي', 'ی').replace('ى', 'ی').replace('ك', 'ک')
            best_score = score
    return best


def _has_persian_text(payload: bytes) -> bool:
    text = _decode_subtitle_text(payload[:512_000])
    return len(re.findall(r'[\u0600-\u06ff]', text)) >= 8


def _safe_zip_members(
    payload: bytes,
    *,
    max_members: int | None = None,
    keep_relative_path: bool = False,
) -> list[tuple[str, bytes]]:
    max_member = max(128 * 1024, int(getattr(settings, 'SUBTITLESTAR_MAX_MEMBER_BYTES', 5 * 1024 * 1024)))
    max_total = max(max_member, int(getattr(settings, 'SUBTITLESTAR_MAX_EXTRACTED_BYTES', 20 * 1024 * 1024)))
    configured_members = int(getattr(settings, 'SUBTITLESTAR_MAX_ARCHIVE_MEMBERS', 60))
    limit = max(1, min(200, int(max_members or configured_members)))
    selected: list[tuple[str, bytes]] = []
    total = 0
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except (zipfile.BadZipFile, OSError):
        return []
    with archive:
        infos = archive.infolist()
        for info in infos:
            path = PurePosixPath(info.filename.replace('\\', '/'))
            if info.is_dir() or path.is_absolute() or '..' in path.parts or info.flag_bits & 0x1:
                continue
            suffix = path.suffix.casefold()
            if suffix not in _SUBTITLE_EXTENSIONS:
                continue
            if info.file_size < 32 or info.file_size > max_member:
                continue
            if total + info.file_size > max_total:
                break
            try:
                member = archive.read(info)
            except (RuntimeError, OSError, zipfile.BadZipFile):
                continue
            if _has_persian_text(member):
                label = str(path) if keep_relative_path else path.name
                selected.append((label, member))
                total += info.file_size
                if len(selected) >= limit:
                    break
    return selected


def _raw_subtitle(response: _Response) -> tuple[str, bytes] | None:
    filename = response.filename or PurePosixPath(unquote(urlsplit(response.url).path)).name
    suffix = PurePosixPath(filename).suffix.casefold()
    if suffix in _SUBTITLE_EXTENSIONS and _has_persian_text(response.body):
        return (filename, response.body)
    return None


def _safe_bind_videos(filename: str, videos: list[str]) -> list[str]:
    """Bind a sidecar release only to playback URLs it can plausibly sync with.

    A single URL is always kept — it is the only target the player can play and
    the pack must not be lost over weak evidence. With several URLs, rank pairs
    with strict release evidence and keep URLs close to the best pair, so
    source/FPS conflicts never inherit cues that throw the player out of sync.
    """
    candidates = [url for url in videos if str(url).startswith(('https://', 'http://'))]
    if len(candidates) <= 1:
        return list(candidates)
    scored: list[tuple[int, str]] = []
    for url in candidates:
        score = _release_score(filename, url, strict=True)
        if score is not None:
            scored.append((score, url))
    if not scored:
        return []
    scored.sort(key=lambda row: row[0], reverse=True)
    best_score = scored[0][0]
    if best_score < 8:
        # Weak evidence: keep only the best pair so other qualities do not
        # inherit a release that may not line up on their encodes.
        return [scored[0][1]]
    floor = max(4, best_score - 20)
    return list(dict.fromkeys(url for score, url in scored if score >= floor))


def _choose_release(
    members: list[tuple[str, bytes]],
    *,
    video_urls: list[str],
) -> tuple[str, bytes, tuple[str, ...]] | None:
    if not members:
        return None
    videos = [url for url in video_urls if str(url).startswith(('https://', 'http://'))]
    if not videos:
        # A subtitle without a video binding is never attached to online playback.
        return None

    best: tuple[int, str, bytes, str] | None = None
    for filename, payload in members:
        lowered = filename.casefold()
        if any(token in lowered for token in ('english', '.eng.', '-eng-', 'sample', 'trailer')):
            continue
        for video_url in videos:
            score = _release_score(filename, video_url, strict=True)
            if score is None:
                continue
            candidate = (score, filename, payload, video_url)
            if best is None or candidate[0] > best[0]:
                best = candidate

    # Movies often only have a BluRay/WEB pack while Film2Media Soft encodes omit
    # those tags (or use the other source). Prefer an exact sync match, then fall
    # back to the best Persian member bound only to URLs it can sync with —
    # never every URL, which desyncs the other encodes.
    if best is None or best[0] < 8:
        soft_best: tuple[int, str, bytes] | None = None
        for filename, payload in members:
            lowered = filename.casefold()
            if any(token in lowered for token in ('english', '.eng.', '-eng-', 'sample', 'trailer')):
                continue
            member_score = 0
            for video_url in videos:
                score = _release_score(filename, video_url, strict=False)
                if score is not None:
                    member_score = max(member_score, score)
            if soft_best is None or member_score > soft_best[0]:
                soft_best = (member_score, filename, payload)
        if soft_best is None:
            return None
        _, filename, payload = soft_best
        return filename, payload, tuple(_safe_bind_videos(filename, videos))

    best_score, filename, payload, paired_url = best
    compatible = [paired_url]
    for video_url in videos:
        if video_url == paired_url:
            continue
        score = _release_score(filename, video_url, strict=True)
        # Source/FPS mismatches already return None. Keep only reasonably similar
        # release names when duplicating the track for another playback quality.
        if score is not None and score >= max(4, best_score - 20):
            compatible.append(video_url)
    return filename, payload, tuple(dict.fromkeys(compatible))


def _choose_episode_releases(
    members: list[tuple[str, bytes]],
    *,
    episode_videos: dict[tuple[int, int], list[str]],
) -> list[tuple[int, int, str, bytes, tuple[str, ...]]]:
    """Pick one Persian release per requested episode key."""
    if not members or not episode_videos:
        return []

    by_episode: dict[tuple[int, int], list[tuple[str, bytes]]] = {}
    for filename, payload in members:
        lowered = filename.casefold()
        if any(token in lowered for token in ('english', '.eng.', '-eng-', 'sample', 'trailer')):
            continue
        key = episode_key_from_name(filename)
        if not key or key not in episode_videos:
            continue
        by_episode.setdefault(key, []).append((filename, payload))

    chosen: list[tuple[int, int, str, bytes, tuple[str, ...]]] = []
    for key, episode_members in sorted(by_episode.items()):
        videos = [
            url for url in (episode_videos.get(key) or [])
            if str(url).startswith(('https://', 'http://'))
        ]
        if not videos:
            continue
        selection = _choose_release(episode_members, video_urls=videos)
        if selection is None:
            # Episode packs often omit BluRay/WEB tags that the CDN path includes.
            # Bind the first Persian member for this episode so online playback still
            # gets a sidecar rather than staying subtitle-less — only to URLs that
            # can plausibly sync with it.
            filename, payload = episode_members[0]
            selection = (filename, payload, tuple(_safe_bind_videos(filename, videos)))
        filename, payload, source_urls = selection
        season_number, episode_number = key
        chosen.append((season_number, episode_number, filename, payload, source_urls))
    return chosen


def _response_members(
    response: _Response,
    *,
    max_members: int | None = None,
    keep_relative_path: bool = False,
) -> list[tuple[str, bytes]]:
    filename = response.filename or PurePosixPath(unquote(urlsplit(response.url).path)).name
    suffix = PurePosixPath(filename).suffix.casefold()
    if response.body.startswith(b'PK\x03\x04') or suffix == '.zip':
        return _safe_zip_members(
            response.body,
            max_members=max_members,
            keep_relative_path=keep_relative_path,
        )
    raw = _raw_subtitle(response)
    return [raw] if raw else []


def _download_response(
    url: str,
    *,
    timeout_seconds: int,
    max_bytes: int,
    urgent: bool = False,
) -> tuple[_Response, str] | None:
    response = _fetch(url, max_bytes=max_bytes, timeout_seconds=timeout_seconds, urgent=urgent)
    if not _looks_like_html(response):
        return response, url
    # File-share landing pages commonly expose the final file after one hop.
    html = _decode_html(response.body)
    for nested_url in _download_links(html, response.url)[:2]:
        if nested_url == url:
            continue
        nested = _fetch(nested_url, max_bytes=max_bytes, timeout_seconds=timeout_seconds, urgent=urgent)
        if not _looks_like_html(nested):
            return nested, nested_url
    return None


def find_movie_subtitle(
    movie,
    *,
    video_urls: list[str],
    timeout_seconds: int | None = None,
) -> SubtitleStarMatch | None:
    """Find an exact Persian subtitle and bind it to compatible playback URLs."""
    if not bool(getattr(settings, 'SUBTITLESTAR_ENABLED', True)):
        return None

    imdb_id = normalize_imdb_id(getattr(movie, 'imdb_id', ''))
    year = getattr(movie, 'release_year', None)
    title, fa_title = resolve_subtitlestar_search_title(
        original_title=str(getattr(movie, 'original_title', '') or ''),
        display_title=str(getattr(movie, 'title', '') or ''),
        video_urls=video_urls,
    )
    if not imdb_id and (not title or not year):
        return None

    identity = imdb_id or hashlib.sha256(f'{title}|{year}'.encode()).hexdigest()[:24]
    miss_key = f'catalog:subtitlestar:miss:{identity}'
    if cache.get(miss_key):
        return None

    base_url = str(getattr(settings, 'SUBTITLESTAR_BASE_URL', 'https://subtitlestar.com')).rstrip('/')
    timeout = max(5, int(timeout_seconds or getattr(settings, 'SUBTITLESTAR_TIMEOUT_SECONDS', 20)))
    html_limit = max(256 * 1024, int(getattr(settings, 'SUBTITLESTAR_MAX_HTML_BYTES', 2 * 1024 * 1024)))
    archive_limit = max(512 * 1024, int(getattr(settings, 'SUBTITLESTAR_MAX_ARCHIVE_BYTES', 16 * 1024 * 1024)))
    # Playback ensure passes a short budget — keep the lookup to a few fetches,
    # but go one deeper than before so weak first pages do not hide the exact one.
    snappy = timeout <= 20
    max_pages = 3 if snappy else max(1, min(5, int(getattr(settings, 'SUBTITLESTAR_MAX_RESULTS_PER_LOOKUP', 3))))
    max_terms = 3 if snappy else 3
    max_downloads = 3 if snappy else 4
    deadline = time.monotonic() + timeout

    def _remaining() -> int:
        return max(3, int(deadline - time.monotonic()))

    def _timed_out() -> bool:
        return time.monotonic() >= deadline

    terms = _subtitlestar_search_terms(
        title=title,
        fa_title=fa_title,
        year=year,
        imdb_id=imdb_id,
        video_urls=video_urls,
    )

    pages: list[str] = []
    # Rank/break on Latin title only — mixing Persian tokens dilutes URL slug ratios.
    ranking_title = title or fa_title
    lookup_incomplete = False
    try:
        for term in terms[:max_terms]:
            if _timed_out():
                lookup_incomplete = True
                break
            search_url = f'{base_url}/?s={quote_plus(term)}&post_type=post'
            try:
                search = _fetch(
                    search_url,
                    max_bytes=html_limit,
                    timeout_seconds=_remaining(),
                    urgent=snappy,
                )
            except SubtitleStarBlocked:
                raise
            except SubtitleStarError as exc:
                logger.info('SubtitleStar search failed for %s: %s', identity, exc)
                continue
            found = _candidate_pages(
                _decode_html(search.body),
                search.url,
                expected_title=ranking_title,
            )
            pages.extend(found)
            # Search pages contain unrelated "latest" widgets. Only stop after
            # finding a URL whose slug strongly resembles this movie title —
            # weak 0.45-ish slug hits otherwise stop the search before the
            # exact page shows up in a later term.
            if any(_title_match_ratio(url, ranking_title) >= 0.75 for url in found):
                break
            if imdb_id and any('زیرنویس-pfdm-' in unquote(urlsplit(url).path) for url in found):
                # Persian PFDM posts are usually the exact movie page.
                break

        unique_pages = list(dict.fromkeys(pages))
        unique_pages.sort(key=lambda url: _title_match_ratio(url, ranking_title), reverse=True)
        for page_url in unique_pages[:max_pages]:
            if _timed_out():
                lookup_incomplete = True
                break
            try:
                page = _fetch(
                    page_url,
                    max_bytes=html_limit,
                    timeout_seconds=_remaining(),
                    urgent=snappy,
                )
            except SubtitleStarBlocked:
                raise
            except SubtitleStarError as exc:
                logger.info('SubtitleStar detail failed for %s: %s', page_url, exc)
                continue
            html = _decode_html(page.body)
            if not _has_exact_identity(html, imdb_id=imdb_id, title=title, year=year):
                continue
            for download_url in _download_links(html, page.url)[:max_downloads]:
                if _timed_out():
                    lookup_incomplete = True
                    break
                try:
                    fetched = _download_response(
                        download_url,
                        timeout_seconds=_remaining(),
                        max_bytes=archive_limit,
                        urgent=snappy,
                    )
                except SubtitleStarBlocked:
                    raise
                except SubtitleStarError as exc:
                    logger.info('SubtitleStar download failed for %s: %s', download_url, exc)
                    continue
                if fetched is None:
                    continue
                response, final_download_url = fetched
                choice = _choose_release(_response_members(response), video_urls=video_urls)
                if not choice:
                    continue
                filename, payload, source_urls = choice
                return SubtitleStarMatch(
                    payload=payload,
                    filename=filename,
                    page_url=page.url,
                    download_url=final_download_url,
                    release_name=filename,
                    source_urls=source_urls,
                    imdb_id=imdb_id,
                )
            if lookup_incomplete:
                break
    except SubtitleStarBlocked as exc:
        logger.warning('SubtitleStar lookup paused: %s', exc)
        return None
    except SubtitleStarError as exc:
        logger.info('SubtitleStar lookup failed for %s: %s', identity, exc)
        return None
    except Exception:
        logger.exception('Unexpected SubtitleStar lookup failure for %s', identity)
        return None

    # Never 24h-cache a miss after a snappy/partial lookup — that blocks the
    # urgent SoftSub worker from retrying with a fuller budget.
    if not snappy and not lookup_incomplete and not _timed_out():
        negative_ttl = max(300, int(getattr(settings, 'SUBTITLESTAR_NEGATIVE_CACHE_SECONDS', 24 * 60 * 60)))
        cache.set(miss_key, True, timeout=negative_ttl)
    return None


def find_series_episode_subtitles(
    series,
    *,
    episode_videos: dict[tuple[int, int], list[str]],
    timeout_seconds: int | None = None,
) -> list[SubtitleStarEpisodeMatch]:
    """Find exact IMDb-matched Persian episode subtitles for online playback."""
    if not bool(getattr(settings, 'SUBTITLESTAR_ENABLED', True)):
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
    # Soft/Hard CDN paths embed the release IMDb (…/Title.tt1234567/…). Prefer that
    # when the catalog row was mis-tagged — otherwise SubtitleStar misses the pack.
    url_imdb_counts: dict[str, int] = {}
    for url in all_urls:
        for match in _IMDB_RE.findall(unquote(str(url or ''))):
            key = normalize_imdb_id(match)
            if key:
                url_imdb_counts[key] = url_imdb_counts.get(key, 0) + 1
    if url_imdb_counts:
        dominant = max(url_imdb_counts.items(), key=lambda row: row[1])[0]
        if not imdb_id or (dominant != imdb_id and url_imdb_counts[dominant] >= 2):
            imdb_id = dominant
    title, fa_title = resolve_subtitlestar_search_title(
        original_title=str(getattr(series, 'original_title', '') or ''),
        display_title=str(getattr(series, 'title', '') or ''),
        video_urls=all_urls,
    )
    if not imdb_id and (not title or not year):
        return []

    identity = imdb_id or hashlib.sha256(f'{title}|{year}|series'.encode()).hexdigest()[:24]
    miss_key = f'catalog:subtitlestar:series-miss:{identity}'
    if cache.get(miss_key):
        return []

    base_url = str(getattr(settings, 'SUBTITLESTAR_BASE_URL', 'https://subtitlestar.com')).rstrip('/')
    timeout = max(5, int(timeout_seconds or getattr(settings, 'SUBTITLESTAR_TIMEOUT_SECONDS', 20)))
    html_limit = max(256 * 1024, int(getattr(settings, 'SUBTITLESTAR_MAX_HTML_BYTES', 2 * 1024 * 1024)))
    archive_limit = max(
        512 * 1024,
        int(getattr(settings, 'SUBTITLESTAR_MAX_ARCHIVE_BYTES', 16 * 1024 * 1024)),
        # Season packs (All-S0N.zip) regularly exceed 32 MiB.
        96 * 1024 * 1024,
    )
    # Playback ensure for one/few episodes must stay under a hard wall-clock budget.
    snappy = timeout <= 20 or len(needed) <= 2
    max_pages = 3 if snappy else max(1, min(5, int(getattr(settings, 'SUBTITLESTAR_MAX_RESULTS_PER_LOOKUP', 3))))
    max_terms = 3 if snappy else 5
    needed_seasons = {int(season) for season, _episode in needed}
    # Always try at least one pack per needed season (snappy used to stop at S07/S06).
    max_downloads = max(3, min(6, len(needed_seasons) + (1 if snappy else 3)))
    if not snappy:
        max_downloads = max(max_downloads, 6)
    max_members = max(
        int(getattr(settings, 'SUBTITLESTAR_MAX_ARCHIVE_MEMBERS', 60)),
        min(200, max(120, len(needed) * 8)),
    )
    deadline = time.monotonic() + timeout

    def _remaining() -> int:
        return max(3, int(deadline - time.monotonic()))

    def _timed_out() -> bool:
        return time.monotonic() >= deadline

    terms = _subtitlestar_search_terms(
        title=title,
        fa_title=fa_title,
        year=year,
        imdb_id=imdb_id,
        video_urls=all_urls,
    )

    pages: list[str] = []
    ranking_title = title or fa_title
    matches: list[SubtitleStarEpisodeMatch] = []
    matched_keys: set[tuple[int, int]] = set()
    try:
        for term in terms[:max_terms]:
            if _timed_out():
                break
            search_url = f'{base_url}/?s={quote_plus(term)}&post_type=post'
            try:
                search = _fetch(
                    search_url,
                    max_bytes=html_limit,
                    timeout_seconds=_remaining(),
                    urgent=snappy,
                )
            except SubtitleStarBlocked:
                raise
            except SubtitleStarError as exc:
                logger.info('SubtitleStar series search failed for %s: %s', identity, exc)
                continue
            found = _candidate_pages(
                _decode_html(search.body),
                search.url,
                expected_title=ranking_title,
            )
            pages.extend(found)
            if imdb_id and any(_title_match_ratio(url, ranking_title) >= 0.75 for url in found):
                break
            if imdb_id and any('زیرنویس-pfdm-' in unquote(urlsplit(url).path) for url in found):
                break

        unique_pages = list(dict.fromkeys(pages))
        unique_pages.sort(key=lambda url: _title_match_ratio(url, ranking_title), reverse=True)
        for page_url in unique_pages[:max_pages]:
            if _timed_out():
                break
            remaining = {key: urls for key, urls in needed.items() if key not in matched_keys}
            if not remaining:
                break
            try:
                page = _fetch(
                    page_url,
                    max_bytes=html_limit,
                    timeout_seconds=_remaining(),
                    urgent=snappy,
                )
            except SubtitleStarBlocked:
                raise
            except SubtitleStarError as exc:
                logger.info('SubtitleStar series detail failed for %s: %s', page_url, exc)
                continue
            html = _decode_html(page.body)
            if not _has_exact_identity(html, imdb_id=imdb_id, title=title, year=year):
                continue

            collected: list[tuple[str, bytes, str]] = []
            for download_url in _download_links_for_seasons(
                html,
                page.url,
                needed_seasons=needed_seasons,
            )[:max_downloads]:
                if _timed_out():
                    break
                try:
                    fetched = _download_response(
                        download_url,
                        timeout_seconds=_remaining(),
                        max_bytes=archive_limit,
                        urgent=snappy,
                    )
                except SubtitleStarBlocked:
                    raise
                except SubtitleStarError as exc:
                    logger.info('SubtitleStar series download failed for %s: %s', download_url, exc)
                    continue
                if fetched is None:
                    continue
                response, final_download_url = fetched
                for filename, payload in _response_members(
                    response,
                    max_members=max_members,
                    keep_relative_path=True,
                ):
                    collected.append((filename, payload, final_download_url))

            if not collected:
                continue
            members = [(filename, payload) for filename, payload, _ in collected]
            origin_by_name = {filename: download_url for filename, _, download_url in collected}
            for season_number, episode_number, filename, payload, source_urls in _choose_episode_releases(
                members,
                episode_videos=remaining,
            ):
                key = (season_number, episode_number)
                if key in matched_keys:
                    continue
                matched_keys.add(key)
                matches.append(SubtitleStarEpisodeMatch(
                    season_number=season_number,
                    episode_number=episode_number,
                    payload=payload,
                    filename=PurePosixPath(filename).name,
                    page_url=page.url,
                    download_url=origin_by_name.get(filename, page.url),
                    release_name=PurePosixPath(filename).name,
                    source_urls=source_urls,
                    imdb_id=imdb_id,
                ))
            if len(matched_keys) >= len(needed):
                break
    except SubtitleStarBlocked as exc:
        logger.warning('SubtitleStar series lookup paused: %s', exc)
        return matches
    except SubtitleStarError as exc:
        logger.info('SubtitleStar series lookup failed for %s: %s', identity, exc)
        return matches
    except Exception:
        logger.exception('Unexpected SubtitleStar series lookup failure for %s', identity)
        return matches

    if not matches and not snappy and not _timed_out():
        negative_ttl = max(300, int(getattr(settings, 'SUBTITLESTAR_NEGATIVE_CACHE_SECONDS', 24 * 60 * 60)))
        cache.set(miss_key, True, timeout=negative_ttl)
    return matches

