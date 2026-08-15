"""Parse Dornatv (dornatv.com) BartarTheme WordPress pages.

Site shape:
  Movies + series are both WP posts.
  Movies  → category id 27 (`movie`)
  Series  → category id 28 (`seris`) / 26 (`animiton`)
  REST    → /wp-json/wp/v2/posts?categories=27|28

Download boxes embed public CDN URLs (dlyar.top) as .mkv/.mp4;
online play uses the same CDN URL (player?file=base64).
Titles look like: «دانلود فیلم ضربهٔ شانس Lucky Strike 2026».
"""

from __future__ import annotations

import base64
import re
from html import unescape
from typing import Any
from urllib.parse import parse_qs, urlsplit, urlunsplit

from .cdn_link_parse import (
    AUDIO_ONLY_RE,
    IMDB_RE,
    MEDIA_URL_RE,
    YEAR_RE,
    _episode_from_url as _shared_episode_from_url,
    _kind_from_url,
    _quality_from,
    _strip_tags,
    season_number_from_label,
    stamp_season_episode,
)
from ..media_links import is_trailer_media_url

# Stable WP category IDs on dornatv.com
MOVIE_CATEGORY_IDS = frozenset({27})
SERIES_CATEGORY_IDS = frozenset({28, 26})  # seris + animiton

DOWNLOAD_A_RE = re.compile(
    r'<a[^>]+class=["\'][^"\']*\bdownload\b[^"\']*["\'][^>]+href=["\'](?P<href>https?://[^"\']+)["\'][^>]*>'
    r'|<a[^>]+href=["\'](?P<href2>https?://[^"\']+\.(?:mkv|mp4|m4v|webm)(?:\?[^"\']*)?)["\'][^>]*>',
    re.I,
)
BOX_HEAD_RE = re.compile(r'class=["\']boxHead["\'][^>]*>\s*<p>(?P<body>.*?)</p>', re.I | re.S)
INFO_ROW_RE = re.compile(
    r'<span class=["\']title["\']>\s*(?P<label>[^:<]+)\s*:\s*</span>\s*(?P<body>.*?)(?:</p>|<p>)',
    re.I | re.S,
)
PLOT_RE = re.compile(
    r'خلاصه\s*داستان\s*:\s*(?P<body>[\s\S]{20,4000}?)(?:</(?:p|div)>|زیرنویس|دوبله|<div class=["\']download)',
    re.I,
)
POSTER_RE = re.compile(
    r'<img[^>]+class=["\'][^"\']*wp-post-image[^"\']*["\'][^>]+src=["\'](?P<src>https?://[^"\']+)["\']'
    r'|<img[^>]+src=["\'](?P<src2>https?://[^"\']+)["\'][^>]+class=["\'][^"\']*wp-post-image[^"\']*["\']',
    re.I,
)
RATE_RE = re.compile(r'class=["\']rate["\']>\s*(?P<rate>\d+(?:\.\d+)?)', re.I)
H1_RE = re.compile(r'<h1[^>]*>(?P<body>.*?)</h1>', re.I | re.S)
TITLE_TAG_RE = re.compile(r'<title>(?P<body>.*?)</title>', re.I | re.S)
DURATION_RE = re.compile(r'(\d+)\s*دقیقه')
SIZE_RE = re.compile(r'(\d+(?:\.\d+)?\s*(?:G|GB|M|MB))\b', re.I)
HEADING_PREFIX_RE = re.compile(
    r'^دانلود\s+(?:فیلم|سریال|انیمه|انیمیشن)\s+',
    re.I,
)
PERSIAN_CHUNK_RE = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+(?:\s+[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+)*')
LATIN_CHUNK_RE = re.compile(
    r'[A-Za-z][A-Za-z0-9]*(?:[ .:&\'\-!][A-Za-z0-9]+)*',
)
HREF_DETAIL_RE = re.compile(
    r'href=["\'](?P<href>(?:https?://(?:www\.)?dornatv\.com)?/(?:[^"\'#?]+/)?[^"\'#?/]+/)["\']',
    re.I,
)
SKIP_PATH_PREFIXES = frozenset({
    'category', 'tag', 'release', 'country', 'director', 'writer', 'actor',
    'collection', 'page', 'author', 'wp-content', 'wp-json', 'wp-admin',
    'feed', 'comments', 'sign-in', 'notifications', 'app-landing', 'player',
})


def slugify_title(value: str) -> str:
    text = (value or '').strip().lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')


def normalize_detail_path(value: str, *, content_type: str = 'movie') -> str:
    raw = (value or '').strip()
    if not raw:
        raise ValueError('dornatv page URL or slug is required.')
    if raw.startswith('http://') or raw.startswith('https://'):
        path = urlsplit(raw).path or '/'
    else:
        path = raw if raw.startswith('/') else f'/{raw}'
    path = '/' + path.strip('/') + '/'
    return path


def build_slug_candidates(*, title: str = '', original_title: str = '', year=None) -> list[str]:
    titles: list[str] = []
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
        for candidate in (slug, f'{slug}-{year_s}' if year_s else ''):
            if candidate and candidate not in out:
                out.append(candidate)
    return out


def _clean_media_url(url: str) -> str:
    raw = unescape((url or '').strip())
    if not raw or AUDIO_ONLY_RE.search(raw):
        return ''
    if is_trailer_media_url(raw):
        return ''
    if not MEDIA_URL_RE.match(raw):
        return ''
    parts = urlsplit(raw)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ''))


def _upgrade_wp_image(url: str) -> str:
    raw = (url or '').strip()
    if not raw:
        return ''
    return re.sub(r'-\d+x\d+(?=\.\w+(?:$|\?))', '', raw)


def split_fa_en_titles(heading: str) -> dict[str, Any]:
    """Split Dornatv headings into Persian + English titles (both required for import)."""
    text = re.sub(r'\s+', ' ', _strip_tags(heading or '')).strip()
    text = re.sub(r'\s*[|\-–—]\s*درنا.*$', '', text).strip()
    text = HEADING_PREFIX_RE.sub('', text).strip()
    text = re.sub(r'\s+با\s+دوبله(?:\s+فارسی)?\s*$', '', text).strip()
    text = re.sub(r'\s+دوبله(?:\s+فارسی)?\s*$', '', text).strip()
    year = None
    year_match = re.search(r'\b((?:19|20)\d{2})\b\s*$', text)
    if year_match:
        try:
            year = int(year_match.group(1))
        except ValueError:
            year = None
        text = text[: year_match.start()].strip()

    fa_parts = [m.group(0).strip() for m in PERSIAN_CHUNK_RE.finditer(text) if m.group(0).strip()]
    en_parts = [m.group(0).strip(' -–—،,') for m in LATIN_CHUNK_RE.finditer(text) if len(m.group(0).strip()) >= 2]
    # Drop leftover year-like tokens already stripped
    en_parts = [p for p in en_parts if not re.fullmatch(r'(?:19|20)\d{2}', p)]

    title_fa = ' '.join(fa_parts).strip(' -–—،,')[:255]
    title_en = max(en_parts, key=len).strip()[:255] if en_parts else ''
    # Prefer last Latin island (usually the English title after Persian)
    if len(en_parts) >= 2:
        title_en = en_parts[-1].strip()[:255]

    return {
        'title_fa': title_fa,
        'title_en': title_en,
        'year': year,
        'has_both': bool(title_fa and title_en),
        'raw': (heading or '')[:300],
    }


def _heading_kind(title: str) -> str:
    text = (title or '').strip()
    lower = text.lower()
    if 'دوبله' in text or 'dubbed' in lower:
        return 'dubbed'
    if 'چسبیده' in text or 'hardsub' in lower or 'hard sub' in lower:
        return 'hardsub'
    if 'بدون زیرنویس' in text or 'nosub' in lower:
        return 'nosub'
    if 'سافت' in text or 'softsub' in lower or 'soft sub' in lower:
        return 'softsub'
    return ''


def _episode_from_url(
    url: str,
    *,
    surrounding: str = '',
    season_hint: int | None = None,
) -> tuple[int | None, int | None]:
    return _shared_episode_from_url(url, surrounding=surrounding, season_hint=season_hint)


def _row_for_link(
    url: str,
    *,
    label: str = '',
    surrounding: str = '',
    page_path: str = '',
    section_kind: str = '',
    season_hint: int | None = None,
) -> dict[str, Any]:
    from apps.catalog.subtitle_extract import canonicalize_download_link

    context = ' '.join(part for part in (section_kind, surrounding) if part)
    kind, subtitle_type = _kind_from_url(url, context)
    quality = _quality_from(url, label or surrounding)
    season_number, episode_number = _episode_from_url(
        url, surrounding=surrounding or label, season_hint=season_hint,
    )
    size_match = SIZE_RE.search(surrounding or label or '')
    size_label = (size_match.group(1) if size_match else '')[:40]
    label_parts = [quality or 'دانلود']
    if kind == 'dubbed':
        label_parts.insert(0, 'دوبله فارسی')
    elif kind == 'softsub':
        label_parts.insert(0, 'زیرنویس نرم')
    elif kind == 'hardsub':
        label_parts.insert(0, 'زیرنویس چسبیده')
    elif kind == 'nosub':
        label_parts.insert(0, 'بدون زیرنویس')
    row: dict[str, Any] = {
        'label': ' · '.join(label_parts)[:80],
        'url': url,
        'quality': quality,
        'kind': kind,
        'type': kind,
        'subtitle_type': subtitle_type,
        'page_path': page_path,
        'has_link': True,
        'source': 'dornatv',
        'stream_url': url,  # CDN is directly playable
        'section_kind': section_kind,
    }
    if size_label:
        row['size_label'] = size_label
    row = stamp_season_episode(
        row,
        season_number=season_number,
        episode_number=episode_number,
        quality=quality,
    )
    return canonicalize_download_link(row)


def _decode_player_vtt(encoded: str) -> str:
    """Decode a ``player?...&sub=<base64(signed vtt url)>`` payload.

    Returns the decoded signed .vtt URL or an empty string. Base64 payloads may
    contain url-encoded chars (``%2F`` etc.) before decoding.
    """
    raw = str(encoded or '').strip()
    if not raw:
        return ''
    from urllib.parse import unquote as _urlunquote

    token = _urlunquote(raw)
    if not token:
        return ''
    try:
        decoded = base64.b64decode(token, validate=False).decode('utf-8', 'replace')
    except Exception:
        return ''
    decoded = _urlunquote(decoded)
    if decoded.startswith('http://') or decoded.startswith('https://'):
        return decoded[:2000]
    return decoded if decoded and '.' in decoded and '//' in decoded else ''


def extract_embedded_subtitle_tracks(html: str, *, rows: list[dict]) -> list[dict]:
    """Capture the signed .vtt sidecar subtitles embedded in player links.

    Dornatv player links look like
    ``https://dornatv.com/player?pid=NNN&file=<base64>&sub=<base64(signed .vtt)>``.
    The ``sub`` payload is the direct CDN .vtt URL for that episode. We return
    subtitle-track dicts following the subtitle_contract shape (``source_url``
    set, ``key`` empty) so an extractor can later download them.
    """
    if not html:
        return []
    tracks: list[dict] = []
    seen: dict[tuple, bool] = {}

    # Match any base64-ish sub= parameter (handles &amp; and & both, and
    # parameter order variations). Require a decoded http(s) value.
    subs = re.findall(r'(?:(?:\?|&|&#038;|&amp;)[\w-]*sub=)([A-Za-z0-9+/=%_.\-~]{16,})', html, re.I)
    unique_vals: list[str] = []
    for token in subs:
        vtt = _decode_player_vtt(token)
        if vtt and vtt not in unique_vals:
            unique_vals.append(vtt)

    for vtt in unique_vals:
        season_number, episode_number = _shared_episode_from_url(vtt)
        s_e_key = (season_number, episode_number)
        if s_e_key in seen and episode_number is not None:
            continue
        seen[s_e_key] = True
        track_id = f'dornatv-{episode_number or "0"}'
        if season_number is not None:
            track_id = f'dornatv-S{int(season_number)}E{int(episode_number or 0)}'
        track: dict[str, Any] = {
            'id': track_id,
            'label': 'فارسی',
            'language': 'fa',
            'source_url': vtt,
            'provider': 'dornatv',
        }
        if season_number is not None:
            track['season_number'] = int(season_number)
        if episode_number is not None:
            track['episode_number'] = int(episode_number)
        tracks.append(track)

    return tracks[:60]


def _extract_heading(html: str) -> str:
    match = H1_RE.search(html or '')
    if match:
        title = re.sub(r'\s+', ' ', _strip_tags(match.group('body') or '')).strip()
        if title:
            return title[:300]
    match = TITLE_TAG_RE.search(html or '')
    if match:
        title = re.sub(r'\s+', ' ', _strip_tags(match.group('body') or '')).strip()
        title = re.sub(r'\s*[|\-–—].*$', '', title).strip()
        return title[:300]
    return ''


def _extract_poster(html: str) -> str:
    match = POSTER_RE.search(html or '')
    if not match:
        return ''
    src = (match.group('src') or match.group('src2') or '').strip()
    return _upgrade_wp_image(src)[:500]


def _extract_description(html: str) -> str:
    match = PLOT_RE.search(html or '')
    if not match:
        return ''
    text = re.sub(r'\s+', ' ', _strip_tags(match.group('body') or '')).strip()
    return text[:4000]


def _extract_info_map(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for match in INFO_ROW_RE.finditer(html or ''):
        label = re.sub(r'\s+', ' ', (match.group('label') or '').strip())
        body = re.sub(r'\s+', ' ', _strip_tags(match.group('body') or '')).strip()
        if label and body:
            out[label] = body[:500]
    return out


def _split_people(value: str) -> list[str]:
    parts = re.split(r'\s*[,،|/]\s*', value or '')
    out: list[str] = []
    for part in parts:
        name = part.strip(' -–—')
        if name and name not in out:
            out.append(name[:120])
    return out[:30]


def _content_type_from_categories(categories) -> str:
    ids = set()
    for item in categories or []:
        try:
            ids.add(int(item))
        except (TypeError, ValueError):
            continue
    if ids & SERIES_CATEGORY_IDS:
        return 'series'
    if ids & MOVIE_CATEGORY_IDS:
        return 'movie'
    return ''


def _content_type_from_path_or_urls(path: str, urls: list[str] | None = None, heading: str = '') -> str:
    blob = f'{path} {heading}'.lower()
    if 'سریال' in heading or 'انیمه' in heading or 'انیمیشن' in heading:
        return 'series'
    if 'فیلم' in heading:
        return 'movie'
    for url in urls or []:
        lower = (url or '').lower()
        if '/series' in lower or '/seris' in lower:
            return 'series'
        if '/movie' in lower:
            return 'movie'
    if 'series' in blob or 'seris' in blob:
        return 'series'
    return 'movie'


def _dedupe_download_rows(rows: list[dict]) -> list[dict]:
    """Collapse repeated encodes so a detail page stays compact.

    A Dornatv series page can list the *same* episode encode across several
    release groups (e.g. 720p PSA + 720p RMTeam + SoftSub mirrors of the same
    file). We keep one best row per (episode, kind, quality) and one best row
    per (quality, kind) for movies, dropping repeat groups.

    Row identity is the CDN path (query string stripped — signatures differ per
    refresh) combined with season/episode so signed-URL refreshes and duplicate
    groups are unified.
    """
    from django.conf import settings

    out: list[dict] = []
    seen_best: dict[tuple, dict] = {}

    def _row_rank(row: dict) -> int:
        q = str(row.get('quality') or '').lower()
        rank = 0
        for token, weight in (('2160', 60), ('4k', 60), ('1080', 40),
                              ('720', 30), ('480', 20), ('360', 10)):
            if token in q:
                rank = weight
                break
        if 'x265' in q or 'hevc' in q or '10bit' in q:
            rank -= 5
        return rank

    def _path_identity(row: dict) -> str:
        url = str(row.get('url') or '').strip()
        if not url:
            return ''
        try:
            parts = urlsplit(url)
        except ValueError:
            return url
        return (parts.scheme + '://' + parts.netloc + parts.path).lower() or url

    for row in rows:
        if not isinstance(row, dict):
            continue
        path_id = _path_identity(row)
        if not path_id:
            out.append(row)
            continue
        season = row.get('season_number')
        episode = row.get('episode_number')
        kind = str(row.get('kind') or row.get('type') or '').strip().lower() or 'full'
        quality = str(row.get('quality') or '').strip().lower() or ''
        # Unique identity: same file per episode and same (quality, kind) — a
        # release group repeating the identical encode collapses into one row.
        key = (path_id, season if season is not None else 0, episode if episode is not None else -1, kind, quality)
        existing = seen_best.get(key)
        if existing is None:
            seen_best[key] = row
            out.append(row)
            continue
        # Same path+quality+kind across groups — keep whichever has a better
        # size/extras, otherwise the first.
        if _row_rank(row) > _row_rank(existing) or len(str(row.get('url') or '')) < len(str(existing.get('url') or '')):
            idx = out.index(existing)
            seen_best[key] = row
            out[idx] = row

    attrs = getattr(settings, 'DORNATV_DEDUPE', None)
    if attrs:
        # Honor a runtime toggle if ever configured (default keeps dedup on).
        _ = attrs
    return out


def parse_download_links(html: str, *, page_path: str = '') -> dict[str, Any]:
    """Parse BartarTheme download boxes into normalized link rows + metadata."""
    body = re.sub(r'<script[\s\S]*?</script>', '', html or '', flags=re.I)
    headings: list[tuple[int, str]] = []
    for match in BOX_HEAD_RE.finditer(body):
        kind = _heading_kind(_strip_tags(match.group('body') or ''))
        if kind:
            headings.append((match.start(), kind))

    # Season hints from box heads / Persian labels near download regions.
    season_marks: list[tuple[int, int]] = []
    for match in BOX_HEAD_RE.finditer(body):
        text = _strip_tags(match.group('body') or '')
        season_no = season_number_from_label(text)
        if season_no is not None:
            season_marks.append((match.start(), season_no))
    for match in re.finditer(r'(?:فصل|season)\s*[0-9۰-۹]{1,2}', body, re.I):
        season_no = season_number_from_label(match.group(0))
        if season_no is not None:
            season_marks.append((match.start(), season_no))
    season_marks.sort(key=lambda row: row[0])

    def _season_at(pos: int) -> int | None:
        hint = None
        for mark_pos, season_no in season_marks:
            if mark_pos <= pos:
                hint = season_no
            else:
                break
        return hint

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in DOWNLOAD_A_RE.finditer(body):
        raw_href = match.group('href') or match.group('href2') or ''
        url = _clean_media_url(raw_href)
        if not url or url in seen:
            continue
        start = max(0, match.start() - 220)
        surrounding = _strip_tags(body[start: match.end() + 120])
        section_kind = ''
        for pos, kind in headings:
            if pos <= match.start():
                section_kind = kind
            else:
                break
        seen.add(url)
        rows.append(
            _row_for_link(
                url,
                surrounding=surrounding,
                page_path=page_path,
                section_kind=section_kind,
                season_hint=_season_at(match.start()),
            )
        )

    if not rows:
        for match in MEDIA_URL_RE.finditer(body):
            url = _clean_media_url(match.group(0))
            if url and url not in seen:
                seen.add(url)
                rows.append(
                    _row_for_link(
                        url,
                        page_path=page_path,
                        season_hint=_season_at(match.start()),
                    )
                )

    rows = _dedupe_download_rows(rows)

    urls = [r['url'] for r in rows]
    heading = _extract_heading(html)
    titles = split_fa_en_titles(heading)
    info = _extract_info_map(html)
    year = titles.get('year')
    if not year:
        release = info.get('سال انتشار') or ''
        found = YEAR_RE.search(release)
        if found:
            year = int(found.group(1))
    duration = None
    dur_match = DURATION_RE.search(info.get('مدت زمان') or '')
    if dur_match:
        duration = int(dur_match.group(1))
    rating = None
    rate_match = RATE_RE.search(html or '')
    if rate_match:
        try:
            rating = float(rate_match.group('rate'))
        except ValueError:
            rating = None

    imdb_id = ''
    for url in urls:
        found = IMDB_RE.search(url or '')
        if found:
            imdb_id = found.group(1).lower()
            break
    imdb_href = re.search(r'imdb\.com/title/(tt\d+)', html or '', re.I)
    if imdb_href:
        imdb_id = imdb_href.group(1).lower()

    content_type = _content_type_from_path_or_urls(page_path, urls, heading)
    title_fa = titles.get('title_fa') or ''
    title_en = titles.get('title_en') or ''

    return {
        'available_links': rows,
        'total_entries': len(rows),
        'page_path': page_path,
        'imdb_id': imdb_id,
        'content_type': content_type,
        'title': title_fa or heading,
        'title_fa': title_fa,
        'title_en': title_en,
        'original_title': title_en or title_fa or heading,
        'year': year,
        'description': _extract_description(html),
        'poster_url': _extract_poster(html),
        'duration_minutes': duration,
        'rating': rating,
        'directors': _split_people(info.get('کارگردان') or ''),
        'writers': _split_people(info.get('نویسنده') or ''),
        'actors': _split_people(info.get('ستارگان') or ''),
        'countries': _split_people(info.get('محصول') or ''),
        'genres': _split_people(info.get('ژانر') or ''),
        'has_both_titles': bool(title_fa and title_en),
        'subtitle_tracks': extract_embedded_subtitle_tracks(html, rows=rows),
        'code': 'ok' if rows else 'dornatv_links_empty',
        'message': '' if rows else 'No download links found on Dornatv page.',
    }


def parse_wp_rest_item(item: dict, *, content_type: str = '') -> dict[str, Any]:
    """Normalize one WP REST post into a provider candidate dict."""
    payload = item or {}
    link = str(payload.get('link') or '').strip()
    path = urlsplit(link).path if link else ''
    path = normalize_detail_path(path or f"/{payload.get('slug') or ''}/")
    title_raw = payload.get('title') or {}
    if isinstance(title_raw, dict):
        title = _strip_tags(str(title_raw.get('rendered') or ''))
    else:
        title = _strip_tags(str(title_raw or ''))
    title = re.sub(r'\s+', ' ', title).strip()
    titles = split_fa_en_titles(title)
    categories = payload.get('categories') or []
    ctype = content_type or _content_type_from_categories(categories) or _content_type_from_path_or_urls(path, [], title)
    year = titles.get('year')
    slug = str(payload.get('slug') or path.strip('/').split('/')[-1] or '')
    imdb_id = ''
    poster_url = ''
    embedded = payload.get('_embedded') or {}
    media_list = embedded.get('wp:featuredmedia') or []
    if media_list and isinstance(media_list[0], dict):
        src = str(media_list[0].get('source_url') or '')
        poster_url = _upgrade_wp_image(src)[:500]
        found = IMDB_RE.search(src)
        if found:
            imdb_id = found.group(1).lower()

    # Resolve release year from taxonomy ids when present in class_list
    for cls in payload.get('class_list') or []:
        if isinstance(cls, str) and cls.startswith('release-') and not year:
            # need name — year often in title already
            pass

    return {
        'provider_item_id': path,
        'content_type': ctype,
        'title': titles.get('title_fa') or title,
        'title_fa': titles.get('title_fa') or '',
        'title_en': titles.get('title_en') or '',
        'original_title': titles.get('title_en') or titles.get('title_fa') or title,
        'year': year,
        'imdb_id': imdb_id,
        'poster_url': poster_url,
        'has_both_titles': bool(titles.get('title_fa') and titles.get('title_en')),
        'categories': list(categories),
        'wp_id': payload.get('id'),
        'slug': slug,
        'link': link or path,
        'modified': payload.get('modified') or payload.get('date') or '',
        'directors': [],
        'actors': [],
        'countries': [],
        'genres': [],
    }


def parse_search_results(html: str, *, content_type: str = '') -> list[dict[str, Any]]:
    """Extract detail-page candidates from a Dornatv listing / search page."""
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in HREF_DETAIL_RE.finditer(html or ''):
        href = match.group('href') or ''
        if href.startswith('http'):
            path = urlsplit(href).path
        else:
            path = href
        path = '/' + path.strip('/') + '/'
        parts = [p for p in path.split('/') if p]
        if not parts or len(parts) != 1:
            continue
        first = parts[0].lower()
        if first in SKIP_PATH_PREFIXES:
            continue
        if path in seen:
            continue
        # Heuristic: movie/series detail slugs are long or contain download words
        if 'دانلود' not in path and len(first) < 8 and not re.search(r'[a-z]{3,}', first):
            continue
        seen.add(path)
        titles = split_fa_en_titles(first.replace('-', ' '))
        ctype = content_type or 'movie'
        results.append({
            'provider_item_id': path,
            'content_type': ctype,
            'title': titles.get('title_fa') or first.replace('-', ' '),
            'original_title': titles.get('title_en') or first.replace('-', ' '),
            'year': titles.get('year'),
            'imdb_id': '',
        })
    return results
