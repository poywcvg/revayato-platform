"""Structural completeness rules for catalog imports.

Every imported movie/series must carry the full presentation structure:

- ``title``            — Persian primary title
- ``original_title``   — English/Latin secondary title
- ``description``      — Persian plot summary
- ``short_description``— Persian short summary
- cast (actors), genres, artwork, year and rating facts

``metadata_gaps`` reports every missing piece; ``publish_blockers`` returns the
subset that must block auto/publication until repaired.
"""

from __future__ import annotations

from .localization import contains_persian, is_latin_text

#: Gaps that must be repaired before a title may go live.
PUBLISH_BLOCKING_GAPS = frozenset({
    'missing_title',
    'missing_persian_title',
    'missing_english_title',
    'non_latin_english_title',
    'missing_description',
    'missing_persian_description',
    'missing_cast',
    'missing_genres',
})

_CAST_RELATIONS = ('movie_actors', 'series_actors')


def _cast_exists(item) -> bool:
    for relation in _CAST_RELATIONS:
        manager = getattr(item, relation, None)
        if manager is not None:
            return manager.exists()
    return False


def _has_poster(item) -> bool:
    poster = getattr(item, 'poster', None)
    if poster is not None and getattr(poster, 'name', None):
        return True
    if (getattr(item, 'poster_external_url', '') or '').strip():
        return True
    return bool((getattr(item, 'poster_path', '') or '').strip())


def metadata_gaps(item) -> list[str]:
    """Return ordered structural gap codes for a Movie/Series instance."""
    gaps: list[str] = []

    title = (getattr(item, 'title', '') or '').strip()
    original_title = (getattr(item, 'original_title', '') or '').strip()
    description = (getattr(item, 'description', '') or '').strip()
    short_description = (getattr(item, 'short_description', '') or '').strip()

    if not title:
        gaps.append('missing_title')
    elif not contains_persian(title):
        gaps.append('missing_persian_title')

    if not original_title:
        gaps.append('missing_english_title')
    elif not is_latin_text(original_title):
        gaps.append('non_latin_english_title')

    if not description:
        gaps.append('missing_description')
    elif not contains_persian(description):
        gaps.append('missing_persian_description')
    if not short_description:
        gaps.append('missing_short_description')

    if not _cast_exists(item):
        gaps.append('missing_cast')

    directors = getattr(item, 'directors', None)
    if directors is not None and not directors.exists():
        gaps.append('missing_directors')

    genres = getattr(item, 'genres', None)
    if genres is not None and not genres.exists():
        gaps.append('missing_genres')

    year = getattr(item, 'release_year', None) or getattr(item, 'start_year', None)
    if not year:
        gaps.append('missing_release_year')

    if getattr(item, 'imdb_rating', None) is None and getattr(item, 'rating_average', None) is None:
        gaps.append('missing_rating')

    if not _has_poster(item):
        gaps.append('missing_poster')

    return gaps


def publish_blockers(item) -> list[str]:
    """Structural gap codes that block publication for this item."""
    return [gap for gap in metadata_gaps(item) if gap in PUBLISH_BLOCKING_GAPS]
