"""Bring a catalog row's Persian ``title`` and English ``original_title`` up to truth.

Every movie and series must carry both. Sources, most trustworthy first:

Persian  — TMDB's ``fa`` translation → Persian Wikipedia / Wikidata (matched by
           IMDb/TMDB id) → the row's own Persian title → machine translation.
English  — TMDB's ``en`` translation → a Latin ``original_title`` the row has →
           a Latin ``title``.

The source that won is written to ``source_metadata['title_source']`` so a
machine translation is never mistaken for a curated name, and a later pass can
upgrade it once a curated one appears. Hand edits (``manual_override_fields``)
are never touched.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .localization import (
    _translation_data,
    contains_disallowed_catalog_script,
    contains_persian,
    is_latin_text,
    translate_to_persian,
    wikidata_persian_title,
)

# Curated names; a title from one of these is final.
CURATED_SOURCES = {'tmdb_translation', 'wikidata', 'manual'}
# Titles a curated name should replace when one exists.
WEAK_SOURCES = {'machine_translation', 'english_fallback'}
STAMP_KEY = 'title_repair_at'


def is_english_title(value: str) -> bool:
    value = (value or '').strip()
    return bool(value) and is_latin_text(value) and not contains_disallowed_catalog_script(value)


def title_problem(obj) -> str:
    """Why this row's titles are wrong right now (``''`` when both are fine)."""
    if not contains_persian(obj.title or ''):
        return 'missing_persian_title'
    if not is_english_title(obj.original_title or ''):
        return 'missing_english_title'
    source = ((obj.source_metadata or {}).get('title_source') or '').strip()
    if source in WEAK_SOURCES:
        return 'machine_title'
    return ''


def broken_titles_q() -> Q:
    """Rows with no Persian in ``title`` or no usable ``original_title`` (DB-side approximation).

    The Arabic-script block is what :func:`contains_persian` tests; the Python
    check in :func:`title_problem` is the final word.
    """
    return (
        ~Q(title__regex=r'[؀-ۿ]')
        | Q(original_title='')
        | Q(original_title__regex=r'[؀-ۿ]')
    )


def weak_titles_q() -> Q:
    return Q(source_metadata__title_source__in=sorted(WEAK_SOURCES))


def _recently_checked(obj, *, hours: float) -> bool:
    stamp = parse_datetime(str((obj.source_metadata or {}).get(STAMP_KEY) or ''))
    return bool(stamp) and timezone.now() - stamp < timedelta(hours=hours)


def _tmdb_translations(client, obj, *, content_type: str) -> dict:
    if not client or not getattr(obj, 'tmdb_id', None):
        return {}
    kind = 'tv' if content_type == 'tv' else 'movie'
    try:
        return client._request(f'{kind}/{int(obj.tmdb_id)}/translations', {}) or {}
    except Exception:  # TMDB down: the other sources still apply
        return {}


def resolve_titles(obj, *, client=None, translate: bool = True) -> dict:
    """Best (persian, persian_source, english, english_source) for ``obj``; no writes."""
    content_type = 'tv' if obj.__class__.__name__ == 'Series' else 'movie'
    translations = _tmdb_translations(client, obj, content_type=content_type)
    payload = {'translations': translations} if translations else {}
    fa = _translation_data(payload, 'fa')
    en = _translation_data(payload, 'en')
    current_title = (obj.title or '').strip()
    current_original = (obj.original_title or '').strip()
    current_source = ((obj.source_metadata or {}).get('title_source') or '').strip()

    english, english_source = '', ''
    for candidate, source in (
        ((en.get('title') or en.get('name') or '').strip(), 'tmdb_translation'),
        (current_original, 'existing'),
        (current_title, 'existing'),
    ):
        if is_english_title(candidate):
            english, english_source = candidate[:255], source
            break

    persian, persian_source = '', ''
    fa_title = (fa.get('title') or fa.get('name') or '').strip()
    if contains_persian(fa_title):
        persian, persian_source = fa_title[:255], 'tmdb_translation'
    if not persian:
        wiki = wikidata_persian_title(
            imdb_id=getattr(obj, 'imdb_id', '') or '',
            tmdb_id=getattr(obj, 'tmdb_id', None),
            content_type=content_type,
        )
        if wiki:
            persian, persian_source = wiki, 'wikidata'
    if not persian and contains_persian(current_title):
        persian = current_title
        persian_source = current_source if current_source and current_source != 'english_fallback' else 'existing'
    if not persian and contains_persian(current_original):
        # Old English-primary rows stored the two titles the wrong way round.
        persian, persian_source = current_original[:255], 'existing'
    if not persian and translate and english:
        translated = translate_to_persian(english)
        if contains_persian(translated):
            persian, persian_source = translated[:255], 'machine_translation'
    return {
        'persian': persian, 'persian_source': persian_source,
        'english': english, 'english_source': english_source,
    }


def repair_titles(obj, *, client=None, translate: bool = True, dry_run: bool = False) -> dict:
    """Fix ``obj``'s titles in place; returns what changed (``changed`` empty = nothing)."""
    manual = set(getattr(obj, 'manual_override_fields', None) or [])
    resolved = resolve_titles(obj, client=client, translate=translate)
    current_title = (obj.title or '').strip()
    current_original = (obj.original_title or '').strip()
    current_source = ((obj.source_metadata or {}).get('title_source') or '').strip()
    changes: dict[str, tuple[str, str]] = {}

    persian = resolved['persian']
    if persian and persian != current_title and 'title' not in manual:
        replace = (
            not contains_persian(current_title)
            # A curated name beats a machine translation; nothing else is
            # second-guessed, so a hand-picked or provider name stays.
            or (current_source in WEAK_SOURCES and resolved['persian_source'] in CURATED_SOURCES)
        )
        if replace:
            changes['title'] = (current_title, persian)

    english = resolved['english']
    if english and english != current_original and 'original_title' not in manual:
        if not is_english_title(current_original) or resolved['english_source'] == 'tmdb_translation':
            changes['original_title'] = (current_original, english)

    meta = dict(obj.source_metadata or {})
    meta[STAMP_KEY] = timezone.now().isoformat()
    if 'title' in changes or (
        contains_persian(current_title) and current_source in {'', 'english_fallback'}
        and resolved['persian'] == current_title
    ):
        meta['title_source'] = resolved['persian_source']
        meta['persian_title_source'] = resolved['persian_source']
    if 'original_title' in changes:
        meta['original_title_source'] = resolved['english_source']

    result = {
        'changed': changes,
        'persian_source': resolved['persian_source'],
        'english_source': resolved['english_source'],
        'unresolved': [
            name for name, ok in (
                ('persian', contains_persian(changes.get('title', ('', current_title))[1])),
                ('english', is_english_title(changes.get('original_title', ('', current_original))[1])),
            ) if not ok
        ],
    }
    if dry_run:
        return result

    fields = ['source_metadata']
    if 'title' in changes:
        obj.title = changes['title'][1]
        fields.append('title')
        if hasattr(obj, 'meta_title') and (not (obj.meta_title or '').strip() or obj.meta_title == current_title):
            obj.meta_title = obj.title[:255]
            fields.append('meta_title')
    if 'original_title' in changes:
        obj.original_title = changes['original_title'][1]
        fields.append('original_title')
    obj.source_metadata = meta
    if hasattr(obj, 'updated_at') and changes:
        obj.updated_at = timezone.now()
        fields.append('updated_at')
    obj.save(update_fields=fields)
    return result
