"""HTML parser for kargadanmovie.com (WordPress, ``kargadanmovie`` theme).

Page shapes (read off the live site on 2026-09-25):

* Movie   ``/movies/tt<imdb>/``  — ``div.download-box.movies`` holds one
  ``ul.type-list[data-type=sub|dub]`` of ``li.item-type`` rows. Each row has a
  ``div.side`` of ``span.q-info`` badges (کیفیت / حجم / انکودر / sub-type) and a
  second ``div.side`` with the link — or, for an anonymous visitor, a
  ``div.need-vip`` sign-in prompt instead.
* Series  ``/series/tt<imdb>/`` — ``ul.episode-list[data-seasonid="فصل N"]`` →
  ``div.type-list[data-type]`` → ``li.ep-item`` («قسمت N») →
  ``li.item-q[data-quality][data-subtype][data-type][data-episode]``, each with the
  same two ``div.side`` halves.

The IMDb id is the page's own URL, so identity never depends on a title search.
Download links are only rendered for a signed-in account; the parser reports
that as ``login_required`` / ``locked_rows`` rather than as an empty title, so a
lapsed session can never be mistaken for a provider that has nothing.
"""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.parse import urlsplit

from .cdn_link_parse import _quality_from, stamp_season_episode

IMDB_PATH_RE = re.compile(r'/(?P<kind>movies|series)/(?P<imdb>tt\d{7,10})/?', re.I)
CANONICAL_RE = re.compile(r'<link[^>]+rel="canonical"[^>]+href="(?P<href>[^"]+)"', re.I)
H1_RE = re.compile(r'<h1[^>]*>(?P<title>.*?)</h1>', re.I | re.S)
YEAR_TAG_RE = re.compile(r'href="[^"]*/release/(?P<year>(?:19|20)\d{2})/?"', re.I)
IMDB_RATE_RE = re.compile(r'class="imdb-rate[^"]*".*?<span class="rate">\s*(?P<rate>\d+(?:\.\d+)?)\s*</span>', re.I | re.S)
AJAX_VAR_RE = re.compile(r'var\s+ajax_var\s*=\s*(?P<json>\{.*?\});', re.S)

BOX_RE = re.compile(r'<div class="main-side-item download-box[^"]*"', re.I)
MOVIE_TYPE_LIST_RE = re.compile(r'<ul class="type-list"[^>]*data-type="(?P<type>[^"]*)"', re.I)
ITEM_TYPE_RE = re.compile(r'<li class="item-type"', re.I)
SEASON_LIST_RE = re.compile(r'<ul class="episode-list"[^>]*data-seasonid="(?P<season>[^"]*)"', re.I)
SERIES_TYPE_LIST_RE = re.compile(r'<div class="type-list"[^>]*data-type="(?P<type>[^"]*)"', re.I)
EP_ITEM_RE = re.compile(r'<li class="ep-item"', re.I)
EP_LABEL_RE = re.compile(r'<span class="item-info">(?P<label>.*?)</span>', re.I | re.S)
# Attributes are required: the theme's own inline script mentions a bare
# ``<li class="item-q">`` in a comment, which must not read as a row.
ITEM_Q_RE = re.compile(r'<li class="item-q"(?P<attrs>\s[^>]*)>', re.I)
ATTR_RE = re.compile(r'data-(?P<key>[a-z]+)="(?P<value>[^"]*)"', re.I)
Q_INFO_RE = re.compile(r'<span class="q-info(?P<cls>[^"]*)">(?P<text>.*?)</span>', re.I | re.S)
HREF_RE = re.compile(r'<a\b[^>]*\bhref="(?P<href>[^"]+)"', re.I)
# The theme's bulk "copy links" script reads ``li.item-q a.dllink[href]`` — the
# link a signed-in account sees. Files sit on ``dlN.kargadandl1.com``.
DLLINK_RE = re.compile(r'<a\b(?=[^>]*\bclass="[^"]*\bdllink\b)[^>]*\bhref="(?P<href>[^"]+)"', re.I)
DATA_LINK_RE = re.compile(r'\bdata-(?:link|url|href|download)="(?P<href>https?://[^"]+)"', re.I)
NEED_VIP_RE = re.compile(r'class="need-vip"', re.I)
SIZE_RE = re.compile(r'(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>GB|MB|KB|گیگ|مگ)', re.I)

# Links in a row that are never the file: account prompts, subtitle search
# sites, the theme's own social/help links.
NON_MEDIA_HOST_RE = re.compile(r'(?:^|\.)(?:subsource\.net|subf2m\.co|imdb\.com|t\.me|instagram\.com)$', re.I)
NON_MEDIA_PATH_RE = re.compile(r'^/(?:sign-in|sign-up|signin|signup|login|register|vip|plans?|pricing|my-account|wp-login\.php)(?:/|$)', re.I)

PERSIAN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def _text(value: str) -> str:
    return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]+>', ' ', value or ''))).strip()


def _number(label: str) -> int | None:
    match = re.search(r'\d+', (label or '').translate(PERSIAN_DIGITS))
    return int(match.group(0)) if match else None


def _chunks(text: str, opener: re.Pattern) -> list[tuple[re.Match, str]]:
    """Split ``text`` at every ``opener``; each chunk runs to the next opener."""
    matches = list(opener.finditer(text or ''))
    out = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        out.append((match, text[match.start():end]))
    return out


def _row_only(chunk: str) -> str:
    """A row runs to its own ``</li>``: rows hold no nested list items, and the
    last row of a page must not swallow the footer's links."""
    end = chunk.find('</li>')
    return chunk if end < 0 else chunk[:end]


def imdb_from_path(value: str) -> tuple[str, str]:
    """``('movie'|'series', 'tt…')`` from a Kargadan URL or path, else ``('', '')``."""
    match = IMDB_PATH_RE.search(value or '')
    if not match:
        return '', ''
    return ('series' if match.group('kind').lower() == 'series' else 'movie'), match.group('imdb').lower()


def detail_path(imdb_id: str, *, content_type: str) -> str:
    root = 'series' if content_type == 'series' else 'movies'
    return f'/{root}/{(imdb_id or "").strip().lower()}/'


def login_state(html: str) -> bool | None:
    """``True``/``False`` from the theme's ``ajax_var.logged``; ``None`` when absent.

    The theme prints ``"logged":""`` for an anonymous visitor. Absence means the
    template changed, which callers must not read as either state.
    """
    match = AJAX_VAR_RE.search(html or '')
    if not match:
        return None
    try:
        payload = json.loads(match.group('json'))
    except ValueError:
        logged = re.search(r'"logged"\s*:\s*"(?P<v>[^"]*)"', match.group('json'))
        if not logged:
            return None
        return bool(logged.group('v').strip())
    if 'logged' not in payload:
        return None
    return bool(str(payload.get('logged') or '').strip() not in {'', '0', 'false'})


def parse_page_meta(html: str, *, page_path: str = '') -> dict[str, Any]:
    """Identity + light metadata a detail page carries."""
    canonical = CANONICAL_RE.search(html or '')
    kind, imdb_id = imdb_from_path(canonical.group('href') if canonical else '')
    if not imdb_id:
        kind, imdb_id = imdb_from_path(page_path)
    heading = H1_RE.search(html or '')
    title = _text(heading.group('title')) if heading else ''
    title_en = re.sub(r'^(?:دانلود\s+)?(?:فیلم|سریال|انیمیشن|انیمه|مستند)\s+', '', title).strip()
    year_tag = YEAR_TAG_RE.search(html or '')
    year = int(year_tag.group('year')) if year_tag else None
    if year is None:
        tail = re.search(r'\b((?:19|20)\d{2})\s*$', title_en)
        year = int(tail.group(1)) if tail else None
    if year is not None:
        title_en = re.sub(rf'\s*\b{year}\s*$', '', title_en).strip()
    rate = IMDB_RATE_RE.search(html or '')
    return {
        'content_type': kind,
        'imdb_id': imdb_id,
        'title': title,
        'title_en': title_en,
        'year': year,
        'imdb_rating': float(rate.group('rate')) if rate else None,
    }


def _badges(chunk: str) -> dict[str, str]:
    out = {'quality': '', 'size': '', 'encoder': '', 'subtype': '', 'type': ''}
    for match in Q_INFO_RE.finditer(chunk or ''):
        cls = match.group('cls') or ''
        text = _text(match.group('text'))
        if 'sub-type' in cls:
            out['subtype'] = text
        elif ' type' in f' {cls}':
            out['type'] = text
        elif text.startswith('کیفیت'):
            out['quality'] = text.split(':', 1)[-1].strip()
        elif text.startswith('حجم'):
            out['size'] = text.split(':', 1)[-1].strip()
        elif text.startswith('انکودر'):
            out['encoder'] = text.split(':', 1)[-1].strip()
    return out


def _size_label(raw: str) -> str:
    match = SIZE_RE.search((raw or '').translate(PERSIAN_DIGITS))
    if not match:
        return ''
    unit = match.group('unit').upper()
    unit = {'گیگ': 'GB', 'مگ': 'MB'}.get(match.group('unit'), unit)
    return f"{match.group('num').replace(',', '.')} {unit}"


def _media_links(chunk: str, *, base_host: str) -> list[str]:
    """Every candidate file URL in one row, in page order, without prompts.

    ``a.dllink`` is authoritative when present; any other anchor or ``data-*``
    URL is only a fallback for a template change.
    """
    found: list[str] = []
    matches = list(DLLINK_RE.finditer(chunk or ''))
    if not matches:
        matches = list(HREF_RE.finditer(chunk or '')) + list(DATA_LINK_RE.finditer(chunk or ''))
    for match in matches:
        href = unescape(match.group('href') or '').strip()
        if not href.startswith(('http://', 'https://')):
            continue
        parts = urlsplit(href)
        host = (parts.hostname or '').lower()
        if NON_MEDIA_HOST_RE.search(host):
            continue
        if base_host and host.endswith(base_host) and NON_MEDIA_PATH_RE.match(parts.path or '/'):
            continue
        if href not in found:
            found.append(href)
    return found


def _hinted_kind(data_type: str, subtype: str) -> str:
    data_type = (data_type or '').strip().lower()
    subtype = (subtype or '').strip().lower()
    if data_type in {'dub', 'dubbed', 'duble'} or 'دوبله' in subtype:
        return 'dubbed'
    if 'hard' in subtype or 'چسبیده' in subtype:
        return 'hardsub'
    if 'soft' in subtype or 'نرم' in subtype:
        return 'softsub'
    if data_type in {'nosub', 'raw'}:
        return 'nosub'
    return 'sub'


def _row(
    url: str,
    *,
    page_path: str,
    badges: dict[str, str],
    data_type: str,
    base_host: str,
    season_number: int | None = None,
    episode_number: int | None = None,
) -> dict[str, Any]:
    from apps.catalog.subtitle_extract import classify_download_link_kind

    surrounding = ' '.join(v for v in badges.values() if v)
    kind, subtitle_type = classify_download_link_kind(
        url, surrounding=surrounding, hinted_kind=_hinted_kind(data_type, badges.get('subtype', '')),
    )
    quality = _quality_from(url, badges.get('quality') or '')[:40] or (badges.get('quality') or '')[:40]
    label_parts = [quality or 'دانلود']
    prefix = {'dubbed': 'دوبله فارسی', 'softsub': 'زیرنویس نرم', 'hardsub': 'زیرنویس چسبیده',
              'nosub': 'بدون زیرنویس'}.get(kind)
    if prefix:
        label_parts.insert(0, prefix)
    row: dict[str, Any] = {
        'label': ' · '.join(label_parts)[:80],
        'url': url,
        'quality': quality,
        'kind': kind,
        'type': kind,
        'subtitle_type': subtitle_type,
        'page_path': page_path,
        'has_link': True,
        'section_kind': (data_type or '').lower(),
        'source': 'kargadan',
    }
    size = _size_label(badges.get('size', ''))
    if size:
        row['size_label'] = size
    if badges.get('encoder'):
        row['encoder'] = badges['encoder'][:40]
    # A link back into kargadanmovie.com is a redirector, not the file. The
    # connector swaps it for the CDN URL it lands on before anything is stored.
    host = (urlsplit(url).hostname or '').lower()
    if base_host and host.endswith(base_host):
        row['needs_resolve'] = True
    if season_number is not None or episode_number is not None:
        row = stamp_season_episode(
            row, season_number=season_number, episode_number=episode_number, quality=quality,
        )
    return row


def parse_download_links(html: str, *, page_path: str = '', base_host: str = 'kargadanmovie.com') -> dict[str, Any]:
    """Parse a movie or series detail page into the shared ``available_links`` shape."""
    text = html or ''
    meta = parse_page_meta(text, page_path=page_path)
    rows: list[dict] = []
    locked = 0
    offered = 0
    seen: set[tuple] = set()

    def add(row: dict) -> None:
        key = (row['url'], row.get('season_number'), row.get('episode_number'))
        if key not in seen:
            seen.add(key)
            rows.append(row)

    seasons = _chunks(text, SEASON_LIST_RE)
    if seasons:
        for season_match, season_chunk in seasons:
            season_number = _number(unescape(season_match.group('season')))
            type_lists = _chunks(season_chunk, SERIES_TYPE_LIST_RE) or [(None, season_chunk)]
            for type_match, type_chunk in type_lists:
                data_type = type_match.group('type') if type_match else ''
                for _ep_match, ep_chunk in _chunks(type_chunk, EP_ITEM_RE):
                    label = EP_LABEL_RE.search(ep_chunk)
                    ep_label = _text(label.group('label')) if label else ''
                    for q_match, q_chunk in _chunks(ep_chunk, ITEM_Q_RE):
                        q_chunk = _row_only(q_chunk)
                        attrs = {m.group('key').lower(): unescape(m.group('value')) for m in ATTR_RE.finditer(q_match.group('attrs'))}
                        badges = _badges(q_chunk)
                        badges['quality'] = badges['quality'] or attrs.get('quality', '')
                        badges['subtype'] = badges['subtype'] or attrs.get('subtype', '')
                        episode_number = _number(attrs.get('episode') or ep_label)
                        offered += 1
                        links = _media_links(q_chunk, base_host=base_host)
                        if not links:
                            if NEED_VIP_RE.search(q_chunk):
                                locked += 1
                            continue
                        for url in links:
                            add(_row(
                                url, page_path=page_path, badges=badges,
                                data_type=attrs.get('type') or data_type, base_host=base_host,
                                season_number=season_number, episode_number=episode_number,
                            ))
    else:
        for _box_match, box in _chunks(text, BOX_RE):
            heading = re.search(r'<h3 class="title">(?P<t>.*?)</h3>', box, re.S)
            # The second box only points at subtitle search sites.
            if heading and 'زیرنویس انگلیسی' in _text(heading.group('t')):
                continue
            for type_match, type_chunk in _chunks(box, MOVIE_TYPE_LIST_RE):
                for _item_match, item_chunk in _chunks(type_chunk, ITEM_TYPE_RE):
                    item_chunk = _row_only(item_chunk)
                    badges = _badges(item_chunk)
                    offered += 1
                    links = _media_links(item_chunk, base_host=base_host)
                    if not links:
                        if NEED_VIP_RE.search(item_chunk):
                            locked += 1
                        continue
                    for url in links:
                        add(_row(
                            url, page_path=page_path, badges=badges,
                            data_type=type_match.group('type'), base_host=base_host,
                        ))

    logged = login_state(text)
    if rows:
        code, message = '', ''
    elif locked and logged is False:
        code, message = 'kargadan_login_required', 'Kargadan only shows download links to a signed-in account.'
    elif locked:
        # Signed in (or unknown) and still behind the prompt: the account lacks
        # the subscription tier this title needs.
        code, message = 'kargadan_vip_required', 'The Kargadan account cannot open these downloads.'
    else:
        code, message = 'kargadan_links_empty', 'No download links were found on the Kargadan page.'
    return {
        **meta,
        'ok': bool(rows),
        'available_links': rows,
        'filled_links': len(rows),
        'total_entries': offered,
        'locked_rows': locked,
        'logged_in': logged,
        'page_path': page_path,
        'code': code,
        'message': message,
    }


SITEMAP_LOC_RE = re.compile(r'<loc>\s*(?P<loc>[^<\s]+)\s*</loc>(?:\s*<lastmod>\s*(?P<lastmod>[^<\s]+)\s*</lastmod>)?', re.I)
SITEMAP_INDEX_PART_RE = re.compile(r'wp-sitemap-posts-(?P<kind>movies|series)-(?P<n>\d+)\.xml$', re.I)


def parse_sitemap_index(xml: str) -> list[tuple[str, str]]:
    """``[(content_type, url)]`` for every movie/series post sitemap in the index."""
    out = []
    for match in SITEMAP_LOC_RE.finditer(xml or ''):
        loc = unescape(match.group('loc'))
        part = SITEMAP_INDEX_PART_RE.search(loc)
        if part:
            out.append(('series' if part.group('kind').lower() == 'series' else 'movie', loc))
    return out


def parse_sitemap(xml: str) -> list[dict[str, str]]:
    """``[{content_type, imdb_id, url, lastmod}]`` for every title in one post sitemap."""
    out = []
    for match in SITEMAP_LOC_RE.finditer(xml or ''):
        loc = unescape(match.group('loc'))
        kind, imdb_id = imdb_from_path(loc)
        if not imdb_id:
            continue
        out.append({
            'content_type': kind,
            'imdb_id': imdb_id,
            'url': loc,
            'lastmod': (match.group('lastmod') or '').strip(),
        })
    return out
