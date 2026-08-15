"""Parse Film2Media / myf2m.info download boxes from public HTML.

Page shapes:
  Movie:  /{id}/{slug}/   or search hit cards
  Series: /series/{slug}/ (also accepts /{slug}/)

Download sections:
  .download-list.dubbled  → Persian dub encodes
  .download-list.hardsub  → Farsi.Sub / hardsub encodes
  .download-season / #season-dlboxN → series packs with SxxExx filenames
"""

from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .cdn_link_parse import (
    _episode_from_url as _shared_episode_from_url,
    season_number_from_label,
    stamp_season_episode,
)
from ..media_links import is_trailer_media_url

MEDIA_URL_RE = re.compile(
    r'https?://[^\s"\'<>]+?\.(?:mkv|mp4|m4v|webm)(?:\?[^\s"\'<>]*)?',
    re.I,
)
QUALITY_RE = re.compile(
    r'(?:کیفیت\s*:?\s*)?(?:</span>\s*)?<span[^>]*class="text"[^>]*>(?P<q>[^<]+)</span>',
    re.I,
)
QUALITY_FALLBACK_RE = re.compile(
    r'(?P<q>'
    r'\d{3,4}p(?:\s*10bit)?(?:\s*x[26]65)?'
    r'|\b2160p\b|\b1080p\b|\b720p\b|\b480p\b|\b360p\b'
    r'|\b4k\b|\buhd\b|\bfull[\s._-]?hd\b|\bfhd\b'
    r'|\bblu-?ray\b|\bweb-?dl\b|\bwebrip\b|\bhdrip\b|\bremux\b'
    r'|\bcam(?:rip)?\b|\bhdcam\b'
    r')',
    re.I,
)
SEASON_BUTTON_RE = re.compile(
    r'data-bs-target="#(?P<id>season-dlbox\d+)"[^>]*>\s*(?P<label>[^<]+)',
    re.I,
)
SEASON_PANE_RE = re.compile(
    r'<div[^>]+id="(?P<id>season-dlbox\d+)"[^>]*>(?P<body>.*?)</div>\s*(?=<div[^>]+id="season-dlbox|$)',
    re.I | re.S,
)
SEASON_PANE_ALT_RE = re.compile(
    r'<div[^>]*class="[^"]*\bdownload-season\b[^"]*"[^>]*(?:id="(?P<id>[^"]+)")?[^>]*>(?P<body>.*?)</div>',
    re.I | re.S,
)
LIST_START_RE = re.compile(
    r'<div[^>]*class="[^"]*\bdownload-list\b[^"]*\b'
    r'(?P<kind>dubbled|dubbed|hardsub|softsub|soft-sub|soft_sub|soft)\b[^"]*"',
    re.I,
)
LI_RE = re.compile(r'<li\b[^>]*>(?P<body>.*?)</li>', re.I | re.S)
DIRECT_A_RE = re.compile(
    r'<a[^>]+href="(?P<href>https?://[^"]+)"[^>]*>\s*دانلود مستقیم',
    re.I | re.S,
)
HANDLE_DOWNLOAD_RE = re.compile(
    r"""handleDownloadClick\(\s*['"](?P<href>https?://[^'"]+)['"]\s*\)""",
    re.I,
)
QUALITY_NEAR_RE = re.compile(
    r'quality=(?P<q>[^&"\'<>]+)|کیفیت\s*:?\s*</span>\s*<span[^>]*class="text"[^>]*>(?P<q2>[^<]+)',
    re.I,
)
AUDIO_ONLY_RE = re.compile(r'\.(?:mka|aac|mp3)(?:$|\?)', re.I)
TRAILER_FILE_RE = re.compile(
    r'(?:trailer|official[._\- ]?trailer|teaser|preview|sample)'
    r'|(?:[._\-](?:t|tr))\.mp4$',
    re.I,
)
# Size tokens that occasionally appear near download rows (filenames / labels).
SIZE_RE = re.compile(
    r'(?P<size>\d+(?:\.\d+)?\s*'
    r'(?:گیگابایت|مگابایت|گیگ|مگ|GIB|GB|MIB|MB|KIB|KB)\b)',
    re.I,
)
_PERSIAN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
POST_PATH_RE = re.compile(r'^/(?:series/)?(?:\d+/)?(?P<slug>[a-z0-9][a-z0-9\-]+)/?$', re.I)
SEARCH_CARD_RE = re.compile(
    r'<a[^>]+href="(?P<href>https?://[^"]+/?(?:series/)?(?:\d+/)?[^"/]+/?)"[^>]*class="[^"]*stretched-link[^"]*"[^>]*>\s*'
    r'<h2[^>]*class="[^"]*entry-title[^"]*"[^>]*>(?P<title>.*?)</h2>',
    re.I | re.S,
)
SEARCH_CARD_RE_ALT = re.compile(
    r'<a[^>]+href="(?P<href>https?://www\.myf2m\.info/\d+/[^"]+/)"[^>]*>',
    re.I,
)


def slugify_title(value: str) -> str:
    text = (value or '').strip().lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')


def normalize_detail_path(value: str, *, content_type: str = 'movie') -> str:
    raw = (value or '').strip()
    if not raw:
        raise ValueError('myf2m page URL or slug is required.')
    if raw.startswith('http://') or raw.startswith('https://'):
        path = urlsplit(raw).path or '/'
    else:
        path = raw if raw.startswith('/') else f'/{raw}'
    path = '/' + path.strip('/') + '/'
    if content_type == 'series':
        if path.startswith('/series/'):
            return path
        slug = path.strip('/')
        if '/' not in slug:
            return f'/series/{slug}/'
        return path
    # Movies commonly use /{id}/{slug}/
    return path


def build_slug_candidates(*, title: str = '', original_title: str = '', year=None) -> list[str]:
    titles = []
    for value in (original_title, title):
        cleaned = re.sub(r'\(\d{4}\)', '', value or '').strip()
        if cleaned and cleaned not in titles:
            titles.append(cleaned)
    year_s = str(year) if year else ''
    out: list[str] = []
    for base in titles:
        slug = slugify_title(base)
        if not slug:
            continue
        for candidate in (
            slug,
            f'{slug}-{year_s}' if year_s else '',
            slugify_title(f'{base} {year_s}') if year_s else '',
        ):
            if candidate and candidate not in out:
                out.append(candidate)
    return out


def _kind_from_section(section_kind: str, url: str) -> tuple[str, str]:
    from apps.catalog.subtitle_extract import classify_download_link_kind

    return classify_download_link_kind(url, section_kind=section_kind)


def _row_for_url(
    url: str,
    *,
    section_kind: str,
    page_path: str,
    quality: str = '',
    surrounding: str = '',
    season_hint: int | None = None,
) -> dict:
    from apps.catalog.subtitle_extract import apply_kind_label, canonicalize_download_link

    kind, subtitle_type = _kind_from_section(section_kind, url)
    quality = (quality or _quality_from_li(surrounding, url))[:40]
    season_number, episode_number = _shared_episode_from_url(
        url, surrounding=surrounding, season_hint=season_hint,
    )
    # Season tab context wins when the filename has no Sxx token.
    if season_hint is not None and season_number is None and episode_number is not None:
        season_number = season_hint
    elif season_hint is not None and season_number is None and episode_number is None:
        # Still stamp season; episode may come from surrounding «قسمت N».
        season_number = season_hint
        _, episode_number = _shared_episode_from_url(
            url, surrounding=surrounding, season_hint=season_hint,
        )

    label_parts = [quality or 'دانلود']
    if kind == 'dubbed':
        label_parts.insert(0, 'دوبله فارسی')
    elif kind == 'softsub':
        label_parts.insert(0, 'زیرنویس نرم')
    elif kind == 'hardsub':
        label_parts.insert(0, 'زیرنویس چسبیده')
    elif kind == 'nosub':
        label_parts.insert(0, 'بدون زیرنویس')
    row = {
        'label': ' · '.join(label_parts)[:80],
        'url': url,
        'quality': quality,
        'kind': kind,
        'type': kind,
        'subtitle_type': subtitle_type,
        'page_path': page_path,
        'has_link': True,
        'section_kind': section_kind,
        'source': 'myf2m',
    }
    size_label = _size_label_from_surrounding(surrounding, url)
    if size_label:
        row['size_label'] = size_label
    row = stamp_season_episode(
        row,
        season_number=season_number,
        episode_number=episode_number,
        quality=quality,
    )
    return canonicalize_download_link(apply_kind_label(row))


def _normalize_quality(raw: str) -> str:
    """Keep the provider's release source plus resolution/codec precisely."""
    text = unescape((raw or '').strip())
    if not text:
        return ''
    compact = re.sub(r'[\s._-]+', ' ', text.lower()).strip()
    resolution = re.search(r'\b(\d{3,4})\s*p\b', compact)
    if not resolution:
        if re.search(r'\b(4k|uhd|2160)\b', compact):
            resolution_label = '2160p'
        elif re.search(r'\b(full\s*hd|fhd)\b', compact):
            resolution_label = '1080p'
        elif re.search(r'\bhd\b', compact) and 'cam' not in compact:
            resolution_label = '720p'
        else:
            return text[:40]
    else:
        resolution_label = f'{resolution.group(1)}p'

    source = ''
    if re.search(r'\bblu[\s._-]?ray\b', compact):
        source = 'BluRay'
    elif re.search(r'\bweb[\s._-]?dl\b', compact):
        source = 'WEB-DL'
    elif re.search(r'\bweb[\s._-]?rip\b', compact):
        source = 'WEBRip'
    elif re.search(r'\bremux\b', compact):
        source = 'Remux'
    elif re.search(r'\bhd(?:tv|rip)\b', compact):
        source = 'HDTV' if 'hdtv' in compact.replace(' ', '') else 'HDRip'
    elif re.search(r'\b(?:hd[\s._-]?tc|hdcam|camrip|cam)\b', compact):
        source = 'HDTC' if 'hdtc' in compact.replace(' ', '') else 'CAM'

    extras: list[str] = []
    flat = compact.replace(' ', '')
    if '10bit' in flat:
        extras.append('10bit')
    if 'x265' in flat or 'hevc' in flat:
        extras.append('x265')
    elif 'x264' in flat or 'avc' in flat:
        extras.append('x264')
    return (' '.join([source, resolution_label, *extras]).strip())[:40]


def _quality_from_li(body: str, url: str) -> str:
    match = QUALITY_RE.search(body or '')
    if match:
        return _normalize_quality(match.group('q'))
    match = QUALITY_FALLBACK_RE.search(url or '') or QUALITY_FALLBACK_RE.search(body or '')
    if not match:
        return ''
    return _normalize_quality(match.group('q') if match.lastindex else match.group(0))


def _size_label_from_surrounding(surrounding: str, url: str) -> str:
    """Extract a human size label from the row context when the page exposes one."""
    haystack = ' '.join(part for part in (surrounding or '', url or '') if part)
    match = SIZE_RE.search(haystack)
    if not match:
        return ''
    raw = (match.group('size') or '').strip()
    raw = raw.translate(_PERSIAN_DIGITS)
    compact = re.sub(r'\s+', ' ', raw)
    compact = re.sub(r'(?i)\b(gib|gb|گیگابایت|گیگ)\b', 'GB', compact)
    compact = re.sub(r'(?i)\b(mib|mb|مگابایت|مگ)\b', 'MB', compact)
    return compact[:40]


def _clean_media_url(url: str) -> str:
    raw = unescape((url or '').strip())
    if not raw or AUDIO_ONLY_RE.search(raw):
        return ''
    if not MEDIA_URL_RE.match(raw):
        return ''
    parts = urlsplit(raw)
    filename = unescape((parts.path or '').rsplit('/', 1)[-1])
    if TRAILER_FILE_RE.search(filename) or is_trailer_media_url(raw):
        return ''
    # Drop tracking fragments; keep query if CDN needs it.
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ''))


def _extract_urls_from_chunk(chunk: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in HANDLE_DOWNLOAD_RE.finditer(chunk or ''):
        url = _clean_media_url(match.group('href') or '')
        if url and url not in seen:
            seen.add(url)
            found.append(url)
    for match in DIRECT_A_RE.finditer(chunk or ''):
        url = _clean_media_url(match.group('href') or '')
        if url and url not in seen:
            seen.add(url)
            found.append(url)
    for match in MEDIA_URL_RE.finditer(chunk or ''):
        url = _clean_media_url(match.group(0))
        if url and url not in seen:
            seen.add(url)
            found.append(url)
    return found


def _quality_near_url(chunk: str, url: str) -> str:
    # Prefer the exact enclosing list row.  Searching a wide season-pane
    # window can see quality badges from neighbouring episodes.
    for row_match in LI_RE.finditer(chunk or ''):
        if url in row_match.group(0):
            scoped = _quality_from_li(row_match.group('body') or '', url)
            if scoped:
                return scoped
    idx = (chunk or '').find(url)
    window = chunk[max(0, idx - 600): idx + 80] if idx >= 0 else (chunk or '')[:800]
    # A season pane contains many rows.  The last quality marker before this
    # URL belongs to the current row; taking the first one mislabeled every
    # later episode with the pane's first quality.
    matches = list(QUALITY_NEAR_RE.finditer(window))
    if matches:
        match = matches[-1]
        raw = unescape(match.group('q') or match.group('q2') or '').replace('%20', ' ').strip()
        if raw:
            return _normalize_quality(raw)
    return _quality_from_li(window, url)


def _surrounding_for_url(chunk: str, url: str) -> str:
    idx = (chunk or '').find(url)
    if idx < 0:
        return re.sub(r'<[^>]+>', ' ', chunk or '')[:400]
    window = chunk[max(0, idx - 400): idx + len(url) + 200]
    # Prefer the enclosing <li> body when present.
    for match in LI_RE.finditer(chunk or ''):
        body = match.group('body') or ''
        if url in body or url in match.group(0):
            return re.sub(r'<[^>]+>', ' ', body)
    return re.sub(r'<[^>]+>', ' ', window)


def _section_kind_from_chunk(chunk: str) -> str:
    lower = (chunk or '').lower()
    if 'dubbled' in lower or 'dubbed' in lower or 'دوبله' in chunk:
        return 'dubbled'
    if 'hardsub' in lower or 'چسبیده' in chunk:
        return 'hardsub'
    if 'softsub' in lower or 'soft-sub' in lower or 'سافت' in chunk:
        return 'softsub'
    return ''


def _season_tab_map(html: str) -> dict[str, int]:
    """Map season-dlbox ids → season numbers from Bootstrap tab buttons."""
    out: dict[str, int] = {}
    for match in SEASON_BUTTON_RE.finditer(html or ''):
        pane_id = (match.group('id') or '').strip()
        label = unescape(match.group('label') or '').strip()
        season_no = season_number_from_label(label)
        if pane_id and season_no is not None:
            out[pane_id] = season_no
    return out


def _iter_season_panes(html: str) -> list[tuple[str, str, int | None]]:
    """Return (pane_id, body_html, season_hint) for each season download pane."""
    panes: list[tuple[str, str, int | None]] = []
    tab_map = _season_tab_map(html)
    seen_ids: set[str] = set()

    for match in SEASON_PANE_RE.finditer(html or ''):
        pane_id = (match.group('id') or '').strip()
        body = match.group('body') or ''
        if not pane_id or pane_id in seen_ids:
            continue
        seen_ids.add(pane_id)
        panes.append((pane_id, body, tab_map.get(pane_id)))

    if not panes:
        for match in SEASON_PANE_ALT_RE.finditer(html or ''):
            pane_id = (match.group('id') or '').strip() or f'season-alt-{len(panes)}'
            if pane_id in seen_ids:
                continue
            seen_ids.add(pane_id)
            body = match.group('body') or ''
            hint = tab_map.get(pane_id)
            if hint is None:
                hint = season_number_from_label(re.sub(r'<[^>]+>', ' ', body)[:200])
            panes.append((pane_id, body, hint))

    # Fallback: locate id="season-dlboxN" blocks with a simpler split when nested divs break the regex.
    if not panes:
        for pane_id, season_no in tab_map.items():
            pattern = re.compile(
                rf'<div[^>]+id="{re.escape(pane_id)}"[^>]*>(?P<body>[\s\S]*?)(?=<div[^>]+id="season-dlbox|$)',
                re.I,
            )
            match = pattern.search(html or '')
            if match:
                panes.append((pane_id, match.group('body') or '', season_no))

    return panes


def _append_rows_from_chunk(
    rows: list[dict],
    seen: set[str],
    chunk: str,
    *,
    page_path: str,
    section_kind: str = '',
    season_hint: int | None = None,
) -> None:
    kind = section_kind or _section_kind_from_chunk(chunk)
    for url in _extract_urls_from_chunk(chunk):
        if url in seen:
            continue
        seen.add(url)
        surrounding = _surrounding_for_url(chunk, url)
        quality = _quality_near_url(chunk, url)
        rows.append(
            _row_for_url(
                url,
                section_kind=kind,
                page_path=page_path,
                quality=quality,
                surrounding=surrounding,
                season_hint=season_hint,
            )
        )


def parse_download_links(html: str, *, page_path: str = '') -> dict[str, Any]:
    text = html or ''
    rows: list[dict] = []
    seen: set[str] = set()

    # 1) Season panes first so season_hint is applied even when SxxExx is missing.
    for _pane_id, body, season_hint in _iter_season_panes(text):
        starts = list(LIST_START_RE.finditer(body))
        if starts:
            for index, start in enumerate(starts):
                section_kind = (start.group('kind') or '').lower()
                begin = start.end()
                end = starts[index + 1].start() if index + 1 < len(starts) else len(body)
                _append_rows_from_chunk(
                    rows, seen, body[begin:end],
                    page_path=page_path,
                    section_kind=section_kind,
                    season_hint=season_hint,
                )
        else:
            _append_rows_from_chunk(
                rows, seen, body,
                page_path=page_path,
                season_hint=season_hint,
            )

    # 2) Top-level download-list sections (movies + series without season tabs).
    starts = list(LIST_START_RE.finditer(text))
    if starts:
        for index, start in enumerate(starts):
            section_kind = (start.group('kind') or '').lower()
            begin = start.end()
            end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
            chunk = text[begin:end]
            # Skip chunks already covered by season panes (same URLs dedupe via seen).
            _append_rows_from_chunk(
                rows, seen, chunk,
                page_path=page_path,
                section_kind=section_kind,
            )

    # 3) Page-level fallback for orphan media URLs.
    if not rows:
        _append_rows_from_chunk(rows, seen, text, page_path=page_path)
    else:
        # Still pick up any orphan URLs not inside known sections.
        _append_rows_from_chunk(rows, seen, text, page_path=page_path)

    available = [row for row in rows if row.get('url')]
    return {
        'ok': bool(available),
        'available_links': available,
        'filled_links': len(available),
        'total_entries': len(rows),
        'page_path': page_path,
        'code': '' if available else 'myf2m_links_empty',
        'message': '' if available else 'No download links were found on the myf2m page.',
    }


def parse_search_results(html: str, *, content_type: str = 'movie') -> list[dict]:
    text = html or ''
    results: list[dict] = []
    seen: set[str] = set()
    for match in SEARCH_CARD_RE.finditer(text):
        href = unescape(match.group('href') or '').strip()
        title = re.sub(r'<[^>]+>', '', unescape(match.group('title') or '')).strip()
        path = urlsplit(href).path if href.startswith('http') else href
        path = '/' + path.strip('/') + '/'
        if content_type == 'series' and '/series/' not in path and not path.startswith('/series/'):
            # Accept bare series slugs only when listing context is series.
            if re.match(r'^/\d+/', path):
                continue
        if content_type == 'movie' and path.startswith('/series/'):
            continue
        if path in seen:
            continue
        seen.add(path)
        year = None
        year_match = re.search(r'\b(19|20)\d{2}\b', title)
        if year_match:
            year = int(year_match.group(0))
        results.append({
            'provider_item_id': path,
            'content_type': 'series' if path.startswith('/series/') else content_type,
            'title': title,
            'original_title': title,
            'year': year,
        })
    if results:
        return results
    for match in SEARCH_CARD_RE_ALT.finditer(text):
        href = unescape(match.group('href') or '').strip()
        path = '/' + urlsplit(href).path.strip('/') + '/'
        if path in seen:
            continue
        seen.add(path)
        results.append({
            'provider_item_id': path,
            'content_type': content_type,
            'title': path.strip('/').split('/')[-1].replace('-', ' '),
            'original_title': path.strip('/').split('/')[-1].replace('-', ' '),
            'year': None,
        })
    return results
