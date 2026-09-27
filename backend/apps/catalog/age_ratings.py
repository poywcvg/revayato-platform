"""Map a stored certification (``R``, ``PG-13``, ``TV-MA``, ``15``, ``R15+``…) to the site's age band.

The catalog keeps the certification exactly as the rating board issued it; the
site shows one of three bands. ``frontend/app/data/catalogAdapter.ts``
(``normalizeAgeRating``) mirrors these rules — change both together.

A rating nobody can read (``NR``, ``Unrated``, blank) maps to ``''``: no badge
is better than a made-up one.
"""

from __future__ import annotations

import re

BANDS = ('12+', '15+', '18+')

# Letter-only certifications from the US (MPA, TV Parental Guidelines) and
# boards that use words rather than ages.
_LETTER_BANDS = {
    'g': '12+', 'pg': '12+', 'pg-13': '12+', 'u': '12+', 'uc': '12+', 'all': '12+', 'al': '12+',
    'tv-y': '12+', 'tv-y7': '12+', 'tv-y7-fv': '12+', 'tv-g': '12+', 'tv-pg': '12+', 'tv-14': '15+',
    'm': '15+', 'ma': '18+', 'r': '18+', 'nc-17': '18+', 'x': '18+', 'tv-ma': '18+', 'r18': '18+',
}
_DIGITS_RE = re.compile(r'\d+')


def age_rating_bucket(value: str | None) -> str:
    raw = (value or '').strip().lower()
    if not raw:
        return ''
    if raw in _LETTER_BANDS:
        return _LETTER_BANDS[raw]
    digits = _DIGITS_RE.findall(raw)
    if digits:
        age = int(digits[-1])
        if age >= 18:
            return '18+'
        if age >= 14:
            return '15+'
        return '12+'
    return ''


def raw_ratings_in_band(raw_values, band: str) -> list[str]:
    """The stored certifications that display as ``band`` (for DB filtering)."""
    return sorted({value for value in raw_values if value and age_rating_bucket(value) == band})
