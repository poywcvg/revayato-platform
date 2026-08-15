"""Shared CDN download-link parsing helpers for myf2m / Dornatv crawlers.

Extracts quality, encode kind, and season/episode indexes from filenames,
URL paths, and surrounding Persian/English labels.
"""

from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import urlsplit, urlunsplit

MEDIA_URL_RE = re.compile(
    r'https?://[^\s"\'<>]+?\.(?:mkv|mp4|m4v|webm)(?:\?[^\s"\'<>]*)?',
    re.I,
)
IMDB_RE = re.compile(r'(tt\d{5,10})', re.I)
EPISODE_RE = re.compile(r'[Ss](\d{1,2})[Ee](\d{1,3})')
# Show.1x01 / Show.01x01
ALT_EPISODE_RE = re.compile(r'(?<![A-Za-z0-9])(\d{1,2})[xX](\d{1,3})(?![A-Za-z0-9])')
# /S02/ or /Season.02/ path segments
PATH_SEASON_RE = re.compile(r'(?:^|/)(?:[Ss](?:eason)?)[._\-\s]?0*(\d{1,2})(?:/|$)', re.I)
# E01 / EP01 / Episode 01 when season is known from context
EPISODE_ONLY_RE = re.compile(
    r'(?:^|[^A-Za-z0-9])(?:[Ee](?:p(?:isode)?)?[.\s_\-]*)0*(\d{1,3})(?![A-Za-z0-9])',
)
# Anime and a few TV encodes omit E/S tokens and use ``Show.01.1080p``.
# Only use this when the caller already knows the season context, and require
# a resolution immediately after the number so years and title numbers do not
# become episode indexes.
BARE_EPISODE_BEFORE_QUALITY_RE = re.compile(
    r'(?:^|[._\- ])0*([1-9]\d{0,2})'
    r'(?=[._\- ](?:2160|1080|720|540|480|360)p(?:[._\- ]|$))',
    re.I,
)
PERSIAN_EPISODE_RE = re.compile(r'(?:قسمت|episode)\s*([0-9۰-۹]{1,3})', re.I)
PERSIAN_SEASON_RE = re.compile(r'(?:فصل|season)\s*([0-9۰-۹]{1,3}|اول|دوم|سوم|چهارم|پنجم|ششم|هفتم|هشتم|نهم|دهم)', re.I)
QUALITY_RE = re.compile(
    r'(?P<q>'
    r'\d{3,4}p(?:\s*10bit)?(?:\s*x[26]65)?'
    r'|\b2160p\b|\b1080p\b|\b720p\b|\b540p\b|\b480p\b|\b360p\b'
    r'|\b4k\b|\buhd\b|\bfull[\s._-]?hd\b|\bfhd\b'
    r'|\bblu-?ray\b|\bweb-?dl\b|\bwebrip\b|\bhdrip\b|\bremux\b'
    r')',
    re.I,
)
YEAR_RE = re.compile(r'\b((?:19|20)\d{2})\b')
AUDIO_ONLY_RE = re.compile(r'\.(?:mka|aac|mp3)(?:$|\?)', re.I)
SIZE_RE = re.compile(r'(\d+(?:\.\d+)?\s*(?:G|GB|M|MB))\b', re.I)

_PERSIAN_ORDINALS = {
    'اول': 1, 'دوم': 2, 'سوم': 3, 'چهارم': 4, 'پنجم': 5,
    'ششم': 6, 'هفتم': 7, 'هشتم': 8, 'نهم': 9, 'دهم': 10,
}
_DIGIT_MAP = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')


def _strip_tags(html: str) -> str:
    text = re.sub(r'<br\s*/?>', '\n', html or '', flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    return unescape(text).strip()


def _parse_int_token(raw: str | None) -> int | None:
    if raw is None:
        return None
    token = str(raw).translate(_DIGIT_MAP).strip()
    if token in _PERSIAN_ORDINALS:
        return _PERSIAN_ORDINALS[token]
    try:
        value = int(token)
    except ValueError:
        return None
    return value if value > 0 else None


def _clean_media_url(url: str) -> str:
    raw = unescape((url or '').strip())
    if not raw or AUDIO_ONLY_RE.search(raw):
        return ''
    if not MEDIA_URL_RE.match(raw):
        return ''
    parts = urlsplit(raw)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ''))


def _kind_from_url(url: str, surrounding: str = '') -> tuple[str, str]:
    """Classify encode kind; prefer CDN SoftSub evidence over section headings."""
    from apps.catalog.subtitle_extract import classify_download_link_kind

    return classify_download_link_kind(url, surrounding=surrounding)


def _quality_base_and_extras(text: str) -> tuple[str, list[str]]:
    """Extract resolution + codec extras from a URL or Persian quality label."""
    raw_match = QUALITY_RE.search(text or '')
    if not raw_match:
        compact_all = re.sub(r'[\s._-]+', ' ', (text or '').lower()).strip()
        flat_all = compact_all.replace(' ', '')
        base = ''
        if re.search(r'\b(4k|uhd|2160)\b', compact_all):
            base = '2160p'
        elif re.search(r'\b(full\s*hd|fhd)\b', compact_all):
            base = '1080p'
        extras: list[str] = []
        if base:
            if '10bit' in flat_all:
                extras.append('10bit')
            if 'x265' in flat_all or 'hevc' in flat_all:
                extras.append('x265')
            elif 'x264' in flat_all or 'avc' in flat_all:
                extras.append('x264')
        return base, extras

    raw = (raw_match.group('q') if raw_match.lastindex else raw_match.group(0) or '').strip()
    compact = re.sub(r'[\s._-]+', ' ', raw.lower()).strip()
    flat = re.sub(r'[\s._-]+', '', f'{text or ""}'.lower())
    resolution = re.search(r'\b(\d{3,4})\s*p\b', compact)
    if resolution:
        base = f'{resolution.group(1)}p'
    elif re.search(r'\b(4k|uhd|2160)\b', compact):
        base = '2160p'
    elif re.search(r'\b(full\s*hd|fhd)\b', compact):
        base = '1080p'
    else:
        return raw[:40], []

    extras: list[str] = []
    if '10bit' in flat:
        extras.append('10bit')
    if 'x265' in flat or 'hevc' in flat:
        extras.append('x265')
    elif 'x264' in flat or 'avc' in flat:
        extras.append('x264')
    return base, extras


def _quality_from(url: str, label: str = '') -> str:
    """Prefer CDN filename resolution; ignore source tags like WEB-DL when 1080p exists."""
    blob = f'{url or ""} {label or ""}'
    resolution = re.search(r'\b(\d{3,4})\s*p\b', blob, re.I)
    if not resolution and re.search(r'\b(4k|uhd|2160)\b', blob, re.I):
        base = '2160p'
        flat = re.sub(r'[\s._-]+', '', blob.lower())
        extras: list[str] = []
        if '10bit' in flat:
            extras.append('10bit')
        if 'x265' in flat or 'hevc' in flat:
            extras.append('x265')
        elif 'x264' in flat or 'avc' in flat:
            extras.append('x264')
        return (' '.join([base, *extras]))[:40]
    if resolution:
        base = f'{resolution.group(1)}p'
        flat = re.sub(r'[\s._-]+', '', blob.lower())
        extras = []
        if '10bit' in flat:
            extras.append('10bit')
        if 'x265' in flat or 'hevc' in flat:
            extras.append('x265')
        elif 'x264' in flat or 'avc' in flat:
            extras.append('x264')
        return (' '.join([base, *extras]))[:40]

    url_base, url_extras = _quality_base_and_extras(url or '')
    label_base, label_extras = _quality_base_and_extras(label or '')
    base = url_base or label_base
    if not base:
        return ''
    if not re.match(r'^\d{3,4}p$', str(base), re.I) and str(base).lower() not in {'2160p'}:
        return ''
    extras = []
    for token in [*url_extras, *label_extras]:
        if token not in extras:
            extras.append(token)
    return (' '.join([base, *extras]))[:40]


def season_number_from_label(label: str) -> int | None:
    """Parse فصل N / Season N / Persian ordinals from a tab or heading label."""
    match = PERSIAN_SEASON_RE.search(label or '')
    if match:
        return _parse_int_token(match.group(1))
    digit = re.search(r'(\d{1,2})', (label or '').translate(_DIGIT_MAP))
    if digit:
        return _parse_int_token(digit.group(1))
    return None


def episode_number_from_label(label: str) -> int | None:
    match = PERSIAN_EPISODE_RE.search(label or '')
    if match:
        return _parse_int_token(match.group(1))
    return None


def _episode_from_url(
    url: str,
    *,
    surrounding: str = '',
    season_hint: int | None = None,
) -> tuple[int | None, int | None]:
    """Resolve (season, episode) from URL tokens, path segments, and nearby labels."""
    blob = f'{url or ""} {surrounding or ""}'
    match = EPISODE_RE.search(url or '') or EPISODE_RE.search(blob)
    if match:
        season_token = _parse_int_token(match.group(1))
        episode_token = _parse_int_token(match.group(2))
        if season_token is not None and episode_token is not None:
            return season_token, episode_token

    alt = ALT_EPISODE_RE.search(url or '') or ALT_EPISODE_RE.search(blob)
    if alt:
        season_token = _parse_int_token(alt.group(1))
        episode_token = _parse_int_token(alt.group(2))
        if season_token is not None and episode_token is not None:
            return season_token, episode_token

    path = urlsplit(url or '').path or ''
    path_season = PATH_SEASON_RE.search(path)
    season = _parse_int_token(path_season.group(1)) if path_season else None
    if season is None:
        season = season_hint

    label_season = season_number_from_label(surrounding)
    if season is None and label_season is not None:
        season = label_season

    # Prefer filename/path episode tokens over Persian labels in a wide HTML window
    # (wide windows often still contain the previous «قسمت N» link text).
    episode = None
    only = EPISODE_ONLY_RE.search(path) or EPISODE_ONLY_RE.search(url or '')
    if only:
        episode = _parse_int_token(only.group(1))
    if episode is None and season_hint is not None:
        filename = path.rsplit('/', 1)[-1]
        bare = BARE_EPISODE_BEFORE_QUALITY_RE.search(filename)
        if bare:
            episode = _parse_int_token(bare.group(1))
    if episode is None:
        episode = episode_number_from_label(surrounding)

    if episode is None:
        return None, None
    return (season if season is not None else 1), episode


def _imdb_from_urls(urls: list[str]) -> str:
    for url in urls:
        match = IMDB_RE.search(url or '')
        if match:
            return match.group(1).lower()
    return ''


def _year_from_urls(urls: list[str], title: str = '') -> int | None:
    for url in urls:
        match = re.search(r'/movie\d*/((?:19|20)\d{2})/tt\d+', url or '', re.I)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
    match = YEAR_RE.search(title or '')
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def stamp_season_episode(
    row: dict[str, Any],
    *,
    season_number: int | None = None,
    episode_number: int | None = None,
    quality: str = '',
) -> dict[str, Any]:
    """Attach structured S/E fields and a stable Persian label."""
    out = dict(row)
    if season_number is not None:
        out['season_number'] = int(season_number)
        out['season'] = f'فصل {int(season_number)}'
    if episode_number is not None:
        out['episode_number'] = int(episode_number)
        out['episode'] = f'قسمت {int(episode_number)}'
        q = (quality or out.get('quality') or '').strip()
        if season_number is not None:
            out['label'] = (
                f'فصل {int(season_number)} · قسمت {int(episode_number)}'
                + (f' · {q}' if q else '')
            )[:80]
        else:
            out['label'] = (
                f'قسمت {int(episode_number)}' + (f' · {q}' if q else '')
            )[:80]
    return out
