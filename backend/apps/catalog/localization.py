"""Normalize imported TMDB metadata for catalog display.

Public movie/series titles:
- ``title`` — Persian (required for catalog presentation)
- ``original_title`` — English/Latin

Persian title resolution order:
1. Official TMDB ``fa`` translation title/name
2. Machine translation of the English title
3. Existing Persian text already present on the payload

Overviews and taglines prefer Persian when available (same order as titles).
Non-Latin original titles (CJK, Cyrillic, …) are latinized to English when an
English form exists. Artwork prefers original-language TMDB posters.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

_PERSIAN_RE = re.compile(r'[\u0600-\u06FF]')
# CJK Unified Ideographs + Hiragana/Katakana + Hangul syllables/jamo.
_CJK_RE = re.compile(
    r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff'
    r'\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]'
)
# Scripts we never show as catalog titles (Latin/English only).
_DISALLOWED_SCRIPT_RE = re.compile(
    r'[\u0600-\u06FF'  # Arabic / Persian
    r'\u0750-\u077F'
    r'\u08A0-\u08FF'
    r'\uFB50-\uFDFF'
    r'\uFE70-\uFEFF'
    r'\u0400-\u04FF'  # Cyrillic
    r'\u0500-\u052F'
    r'\u0900-\u097F'  # Devanagari
    r'\u0980-\u09FF'  # Bengali
    r'\u0A00-\u0A7F'  # Gurmukhi
    r'\u0A80-\u0AFF'  # Gujarati
    r'\u0B00-\u0B7F'  # Oriya
    r'\u0B80-\u0BFF'  # Tamil
    r'\u0C00-\u0C7F'  # Telugu
    r'\u0C80-\u0CFF'  # Kannada
    r'\u0D00-\u0D7F'  # Malayalam
    r'\u0D80-\u0DFF'  # Sinhala
    r'\u0E00-\u0E7F'  # Thai
    r'\u0E80-\u0EFF'  # Lao
    r'\u1000-\u109F'  # Myanmar
    r'\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff'
    r'\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]'
)
_LATIN_LETTER_RE = re.compile(r'[A-Za-z\u00C0-\u024F\u1E00-\u1EFF]')
_TRANSLATE_MAX_CHARS = 4500


def contains_persian(value: str | None) -> bool:
    return bool(_PERSIAN_RE.search(value or ''))


def contains_cjk(value: str | None) -> bool:
    return bool(_CJK_RE.search(value or ''))


def contains_disallowed_catalog_script(value: str | None) -> bool:
    """True when the string has non-Latin letters (Persian, CJK, Cyrillic, …)."""
    return bool(_DISALLOWED_SCRIPT_RE.search(value or ''))


_ASCII_TITLE_RE = re.compile(r'^[\x20-\x7E]+$')


def is_latin_text(value: str | None) -> bool:
    """True for English/Latin catalog titles, including ASCII numeric titles (e.g. ``1917``)."""
    text = (value or '').strip()
    if not text or contains_disallowed_catalog_script(text):
        return False
    if _LATIN_LETTER_RE.search(text):
        return True
    # Pure ASCII titles without letters (years, codes) are acceptable English forms.
    return bool(_ASCII_TITLE_RE.fullmatch(text))


def _translation_data(details: dict, lang: str = 'fa') -> dict:
    rows = (details.get('translations') or {}).get('translations') or []
    preferred = None
    for item in rows:
        iso = (item.get('iso_639_1') or '').lower()
        if iso != lang:
            continue
        data = item.get('data') or {}
        country = (item.get('iso_3166_1') or '').upper()
        if country in {'IR', 'AF'} or preferred is None:
            preferred = data
            if country == 'IR':
                return data
    return preferred or {}


def _opener():
    proxy = (
        getattr(settings, 'TMDB_PROXY_URL', '')
        or getattr(settings, 'TMDB_HTTPS_PROXY', '')
        or ''
    ).strip()
    if not proxy:
        return urllib.request.build_opener()
    return urllib.request.build_opener(urllib.request.ProxyHandler({
        'http': proxy,
        'https': proxy,
    }))


def translate_to_persian(text: str, *, timeout: int | None = None) -> str:
    """Best-effort English→Persian translation; returns '' on failure."""
    source = (text or '').strip()
    if not source or contains_persian(source):
        return source if contains_persian(source) else ''
    timeout = max(3, int(timeout or getattr(settings, 'TMDB_TIMEOUT_SECONDS', 12)))
    chunks = []
    remaining = source
    while remaining:
        piece = remaining[:_TRANSLATE_MAX_CHARS]
        remaining = remaining[_TRANSLATE_MAX_CHARS:]
        query = urllib.parse.urlencode({
            'client': 'gtx',
            'sl': 'auto',
            'tl': 'fa',
            'dt': 't',
            'q': piece,
        })
        url = f'https://translate.googleapis.com/translate_a/single?{query}'
        request = urllib.request.Request(url, headers={
            'Accept': 'application/json',
            'User-Agent': 'RevayatoCatalog/1.0',
        })
        try:
            with _opener().open(request, timeout=timeout) as response:  # noqa: S310
                payload = json.loads(response.read().decode('utf-8'))
            parts = []
            for row in (payload[0] or []):
                if row and row[0]:
                    parts.append(str(row[0]))
            translated = ''.join(parts).strip()
            if translated:
                chunks.append(translated)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, TypeError, IndexError) as exc:
            logger.warning('persian_translation_failed error=%s', exc.__class__.__name__)
            return ''
    return ' '.join(chunks).strip()


def _pick_original_image(candidates: list, current: str | None) -> str | None:
    """Prefer null-language (original) posters, then English, else keep current."""
    rows = [item for item in (candidates or []) if isinstance(item, dict) and item.get('file_path')]
    if not rows:
        return current

    def score(item: dict) -> tuple:
        lang = (item.get('iso_639_1') or '').strip().lower()
        # null/empty = original theatrical artwork
        lang_rank = 0 if not lang else (1 if lang == 'en' else 2)
        return (
            lang_rank,
            -(float(item.get('vote_average') or 0)),
            -(int(item.get('vote_count') or 0)),
        )

    rows.sort(key=score)
    best = rows[0].get('file_path') or ''
    return best or current


def prefer_original_artwork(details: dict) -> dict:
    """Force poster/backdrop paths to original (non-localized) TMDB stills when available."""
    images = details.get('images') or {}
    poster = _pick_original_image(images.get('posters') or [], details.get('poster_path'))
    backdrop = _pick_original_image(images.get('backdrops') or [], details.get('backdrop_path'))
    if poster:
        details['poster_path'] = poster
        details['_poster_source'] = 'original'
    if backdrop:
        details['backdrop_path'] = backdrop
        details['_backdrop_source'] = 'original'
    return details


def _resolve_english_title(
    details: dict,
    *,
    content_type: str = 'movie',
    english_details: dict | None = None,
) -> str:
    """Best available English/Latin title from payload, fallback details, or translations."""
    orig_key = 'original_name' if content_type == 'tv' else 'original_title'
    title_key = 'name' if content_type == 'tv' else 'title'
    candidates: list[str] = []
    if isinstance(english_details, dict):
        candidates.extend([
            (english_details.get(title_key) or '').strip(),
            (english_details.get(orig_key) or '').strip(),
        ])
    candidates.append((details.get('_english_title') or '').strip())
    en = _translation_data(details, 'en')
    candidates.extend([
        (en.get('title') or '').strip(),
        (en.get('name') or '').strip(),
    ])
    candidates.extend([
        (details.get(title_key) or '').strip(),
        (details.get(orig_key) or '').strip(),
    ])
    for candidate in candidates:
        if candidate and is_latin_text(candidate) and not contains_disallowed_catalog_script(candidate):
            return candidate[:255]
    return ''


def ensure_latin_original_title(
    details: dict,
    *,
    content_type: str = 'movie',
    english_details: dict | None = None,
) -> dict:
    """Replace non-English original titles with English for catalog display."""
    orig_key = 'original_name' if content_type == 'tv' else 'original_title'
    original = (details.get(orig_key) or '').strip()
    if not original or not contains_disallowed_catalog_script(original):
        return details

    english = _resolve_english_title(
        details,
        content_type=content_type,
        english_details=english_details,
    )
    if english and english != original:
        details['_native_original_title'] = original
        details[orig_key] = english
        details['_original_title_source'] = 'english_latinization'
    return details


def _resolve_persian_title(
    details: dict,
    *,
    content_type: str = 'movie',
    english_title: str = '',
) -> tuple[str, str]:
    """Return (persian_title, source_label)."""
    title_key = 'name' if content_type == 'tv' else 'title'
    fa = _translation_data(details, 'fa')
    for candidate in (
        (fa.get('title') or '').strip(),
        (fa.get('name') or '').strip(),
        (details.get('_persian_title') or '').strip(),
        (details.get(title_key) or '').strip(),
    ):
        if candidate and contains_persian(candidate):
            source = 'tmdb_translation' if candidate in {
                (fa.get('title') or '').strip(),
                (fa.get('name') or '').strip(),
            } else 'existing'
            return candidate[:255], source

    if english_title:
        translated = translate_to_persian(english_title)
        if translated and contains_persian(translated):
            return translated[:255], 'machine_translation'
    return '', ''


def normalize_title_pair(
    title: str | None,
    original_title: str | None,
    *,
    translate: bool = True,
) -> tuple[str, str]:
    """Return ``(persian_title, english_title)`` for catalog storage/display."""
    title = (title or '').strip()
    original = (original_title or '').strip()

    title_fa = contains_persian(title)
    original_fa = contains_persian(original)
    title_en = is_latin_text(title)
    original_en = is_latin_text(original)

    # Mis-ordered rows from the previous English-primary era.
    if title_en and original_fa:
        english = title
        persian = original
    else:
        persian = title if title_fa else (original if original_fa else '')
        english = original if original_en else (title if title_en else '')

    if not english:
        for candidate in (original, title):
            if candidate and is_latin_text(candidate) and not contains_disallowed_catalog_script(candidate):
                english = candidate
                break

    if not persian and translate and english:
        translated = translate_to_persian(english)
        if translated and contains_persian(translated):
            persian = translated

    if not persian:
        persian = title if title_fa else (original if original_fa else (title or original))
    if not english:
        english = original if original_en else (title if title_en else (original or title))

    return (persian or '')[:255], (english or '')[:255]


def secondary_title_for(title: str | None, original_title: str | None) -> str:
    """English/original line shown under the Persian primary title."""
    persian, english = normalize_title_pair(title, original_title, translate=False)
    if english and english != persian:
        return english
    return ''


def normalize_person_names(
    localized: str | None,
    original: str | None,
    *,
    english_name: str | None = None,
) -> tuple[str, str]:
    """Return (display_name, original_name) using only Persian + English/Latin."""
    loc = (localized or '').strip()
    orig = (original or '').strip()
    english = (english_name or '').strip()

    for candidate in (english, orig, loc):
        if candidate and is_latin_text(candidate) and not contains_disallowed_catalog_script(candidate):
            english = candidate
            break
    else:
        english = ''

    if contains_disallowed_catalog_script(orig):
        orig = english
    if not orig and english:
        orig = english

    if contains_disallowed_catalog_script(loc) or not loc:
        if contains_persian(loc):
            pass
        elif english:
            # Prefer Persian display when we can translate; else keep Latin.
            translated = translate_to_persian(english)
            loc = translated or english
        else:
            loc = orig
    elif not contains_persian(loc) and not is_latin_text(loc):
        loc = english or orig

    display = loc or orig or english
    original_out = orig or english or display
    return display[:255], original_out[:255]


def ensure_persian_metadata(
    details: dict,
    *,
    content_type: str = 'movie',
    english_details: dict | None = None,
) -> dict:
    """Mutate TMDB details: Persian title, English original_title, Persian overview."""
    title_key = 'name' if content_type == 'tv' else 'title'
    orig_key = 'original_name' if content_type == 'tv' else 'original_title'
    # Preserve Latin title before any rewrite for original-title fallback.
    current_title = (details.get(title_key) or '').strip()
    if current_title and is_latin_text(current_title):
        details['_english_title'] = current_title
    elif isinstance(english_details, dict):
        fallback_title = (english_details.get(title_key) or '').strip()
        if fallback_title and is_latin_text(fallback_title):
            details['_english_title'] = fallback_title

    prefer_original_artwork(details)
    ensure_latin_original_title(
        details,
        content_type=content_type,
        english_details=english_details,
    )

    english_title = _resolve_english_title(
        details,
        content_type=content_type,
        english_details=english_details,
    )
    if english_title:
        details[orig_key] = english_title
        details['_english_title'] = english_title
        details['_original_title_source'] = details.get('_original_title_source') or 'english'

    persian_title, persian_source = _resolve_persian_title(
        details,
        content_type=content_type,
        english_title=english_title,
    )
    if persian_title:
        details[title_key] = persian_title
        details['_title_source'] = persian_source
        details['_persian_title_source'] = persian_source
    elif english_title:
        # Last resort so imports still have a primary label; backfill can retry.
        details[title_key] = english_title
        details['_title_source'] = 'english_fallback'

    fa = _translation_data(details, 'fa')

    fa_overview = (fa.get('overview') or '').strip()
    if fa_overview and contains_persian(fa_overview):
        details['overview'] = fa_overview
        details['_persian_overview_source'] = 'tmdb_translation'
    elif not contains_persian((details.get('overview') or '').strip()):
        english_overview = (details.get('overview') or '').strip()
        translated_overview = translate_to_persian(english_overview) if english_overview else ''
        if translated_overview:
            details['overview'] = translated_overview
            details['_persian_overview_source'] = 'machine_translation'

    fa_tagline = (fa.get('tagline') or '').strip()
    if fa_tagline and contains_persian(fa_tagline):
        details['tagline'] = fa_tagline
    elif (details.get('tagline') or '').strip() and not contains_persian(details.get('tagline') or ''):
        translated_tagline = translate_to_persian(details['tagline'])
        if translated_tagline:
            details['tagline'] = translated_tagline

    return details
