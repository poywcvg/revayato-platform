"""Metadata-aware verification for subtitle matching.

Provider search only matches on *title* (plus a year hint). That is enough for a
unique title, but it silently picks the wrong release for remakes, common-word
titles (``Dreams``, ``It``, ``1917``) and same-year namesakes. This module adds
the rest of the catalog identity — release year, genres, cast and directors — as
verification signals so the correct subtitle page is chosen.

Two tiers of signal, deliberately kept separate:

* **Hard gates** (``reject``): IMDb id conflict, or a year that disagrees by more
  than a year with no IMDb confirmation. These are authoritative — a page that
  fails them is a different title and is dropped.
* **Soft confidence** (``score`` / ``confirmed``): cast, director, genre and an
  exact year match. Absence never rejects (a provider page may simply omit the
  cast), but presence raises confidence, and callers try the most-confirmed page
  first instead of blindly following the raw search rank.

The module is provider-agnostic: it takes a catalog ``Movie``/``Series`` instance
plus already-resolved ``title``/``year``/``imdb_id`` and, separately, the fetched
HTML of a candidate page. It never performs I/O.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_YEAR_IN_TEXT = re.compile(r'(?:19|20)\d{2}')
# Latin word of >=4 chars (surnames); apostrophes/hyphens kept (O'Brien, Day-Lewis).
_LATIN_WORD = re.compile(r"[a-z][a-z'’\-]{3,}")
# Persian/Arabic run of >=3 chars (actor display names, genre words).
_PERSIAN_RUN = re.compile(r"[؀-ۿ][؀-ۿ‌\s]{2,}")

# Latin surnames/genre words too generic to confirm anything on their own.
_STOP_TERMS = frozenset({
    'the', 'and', 'for', 'with', 'from', 'this', 'that', 'film', 'movie',
    'series', 'season', 'part', 'story', 'love', 'man', 'men', 'girl', 'boy',
    'day', 'night', 'life', 'world', 'war', 'new', 'old', 'jr', 'sr', 'van',
    'von', 'del', 'della', 'lee', 'kim', 'wang', 'li', 'ali', 'khan',
    'action', 'drama', 'comedy', 'family', 'music', 'crime', 'war', 'sport',
    # Persian generic genre/label words (never disambiguate a specific title).
    'درام', 'کمدی', 'اکشن',
    'خانوادگی', 'فیلم',
    'سریال', 'زیرنویس',
    'فارسی', 'دانلود',
})


@dataclass(frozen=True)
class TitleIdentity:
    """Everything known about a catalog title that a provider page can confirm."""

    title: str
    year: int | None
    imdb_id: str
    cast_terms: tuple[str, ...]      # Latin surnames, casefolded
    cast_fa: tuple[str, ...]         # Persian display names, normalized
    director_terms: tuple[str, ...]  # Latin surnames, casefolded
    director_fa: tuple[str, ...]     # Persian display names, normalized
    genre_terms: tuple[str, ...]     # genre labels (Latin token or Persian run)

    @property
    def has_people(self) -> bool:
        return bool(self.cast_terms or self.cast_fa or self.director_terms or self.director_fa)


@dataclass(frozen=True)
class MetadataVerdict:
    """Outcome of checking one candidate page against a :class:`TitleIdentity`."""

    reject: bool
    score: int
    confirmed: bool           # at least one strong signal (imdb / year / a person)
    reasons: tuple[str, ...]


def _normalize(text: str) -> str:
    """Casefold + strip diacritics + collapse Persian variants for matching."""
    if not text:
        return ''
    text = unicodedata.normalize('NFKC', str(text))
    text = text.replace('ي', 'ی').replace('ك', 'ک')  # Arabic ya/kaf -> Persian
    text = text.replace('‌', ' ')  # ZWNJ -> space
    return text.casefold()


def _latin_surname(name: str) -> str:
    """Longest Latin token of a person's name — the most identifying part."""
    tokens = [t for t in _LATIN_WORD.findall(_normalize(name)) if t not in _STOP_TERMS]
    return max(tokens, key=len) if tokens else ''


def _persian_name(name: str) -> str:
    norm = _normalize(name)
    return norm if _PERSIAN_RUN.search(norm) else ''


def _dedupe(values) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = (value or '').strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return tuple(out)


def build_title_identity(
    obj,
    *,
    title: str,
    year: int | None,
    imdb_id: str,
    people_limit: int = 8,
) -> TitleIdentity:
    """Build a :class:`TitleIdentity` from a catalog ``Movie``/``Series`` instance.

    Reads cast/director/genre via the ORM. Any DB hiccup degrades gracefully to a
    title+year+imdb identity (still fully usable) rather than raising into the
    subtitle worker.
    """
    cast_terms: list[str] = []
    cast_fa: list[str] = []
    director_terms: list[str] = []
    director_fa: list[str] = []
    genre_terms: list[str] = []

    try:
        actor_rel = getattr(obj, 'movie_actors', None) or getattr(obj, 'series_actors', None)
        if actor_rel is not None and getattr(obj, 'pk', None):
            rows = (
                actor_rel.select_related('actor')
                .order_by('order')
                .values_list('actor__original_name', 'actor__name')[:people_limit]
            )
            for original_name, display_name in rows:
                surname = _latin_surname(original_name) or _latin_surname(display_name)
                if surname:
                    cast_terms.append(surname)
                fa = _persian_name(display_name) or _persian_name(original_name)
                if fa:
                    cast_fa.append(fa)
    except Exception:  # pragma: no cover - defensive ORM guard
        pass

    try:
        if getattr(obj, 'pk', None) and hasattr(obj, 'directors'):
            for original_name, display_name in obj.directors.values_list('original_name', 'name')[:4]:
                surname = _latin_surname(original_name) or _latin_surname(display_name)
                if surname:
                    director_terms.append(surname)
                fa = _persian_name(display_name) or _persian_name(original_name)
                if fa:
                    director_fa.append(fa)
    except Exception:  # pragma: no cover - defensive ORM guard
        pass

    try:
        if getattr(obj, 'pk', None) and hasattr(obj, 'genres'):
            for label in obj.genres.values_list('title', flat=True)[:8]:
                norm = _normalize(label)
                token = norm.strip()
                if not token or token in _STOP_TERMS:
                    continue
                # Keep the whole label for Persian; a single token for Latin.
                if _PERSIAN_RUN.search(token):
                    genre_terms.append(token)
                else:
                    latin = [t for t in _LATIN_WORD.findall(token) if t not in _STOP_TERMS]
                    genre_terms.extend(latin)
    except Exception:  # pragma: no cover - defensive ORM guard
        pass

    return TitleIdentity(
        title=str(title or ''),
        year=int(year) if year else None,
        imdb_id=str(imdb_id or ''),
        cast_terms=_dedupe(cast_terms),
        cast_fa=_dedupe(cast_fa),
        director_terms=_dedupe(director_terms),
        director_fa=_dedupe(director_fa),
        genre_terms=_dedupe(genre_terms),
    )


def _word_in_text(term: str, text: str) -> bool:
    """Whole-word Latin match; substring match for Persian runs (no word breaks)."""
    if not term:
        return False
    if _PERSIAN_RUN.search(term):
        return term in text
    return re.search(rf'(?<![a-z]){re.escape(term)}(?![a-z])', text) is not None


def evaluate_subtitle_page(
    identity: TitleIdentity,
    html: str,
    *,
    page_imdb: str = '',
    page_year: int | None = None,
) -> MetadataVerdict:
    """Score one candidate provider page against the catalog identity.

    ``page_imdb`` / ``page_year`` are the values the caller already parsed from the
    page (Subzone exposes both); when absent they are re-derived from ``html`` so
    the year gate still applies. Cast/director/genre are matched against the page
    text as positive confidence only.
    """
    text = _normalize(html)
    reasons: list[str] = []
    score = 0
    confirmed = False

    imdb_confirms = False
    want_imdb = (identity.imdb_id or '').lower()
    page_imdb = (page_imdb or '').lower()
    if want_imdb and page_imdb:
        if want_imdb == page_imdb:
            imdb_confirms = True
            confirmed = True
            score += 120
            reasons.append('imdb')
        else:
            return MetadataVerdict(reject=True, score=0, confirmed=False, reasons=('imdb-conflict',))

    # Year gate (skipped when IMDb already confirms the exact title).
    if identity.year and not imdb_confirms:
        year = page_year
        if year is None:
            found = {int(m) for m in _YEAR_IN_TEXT.findall(text)}
            # Only treat as a conflict when the page commits to a single year.
            if len(found) == 1:
                year = next(iter(found))
        if year is not None:
            if abs(int(year) - identity.year) > 1:
                return MetadataVerdict(reject=True, score=0, confirmed=False, reasons=('year-conflict',))
            confirmed = True
            score += 30
            reasons.append('year')
    elif identity.year and imdb_confirms:
        pass

    # Cast — the strongest soft signal (surnames are highly identifying).
    cast_hits = sum(1 for term in identity.cast_terms if _word_in_text(term, text))
    cast_hits += sum(1 for term in identity.cast_fa if _word_in_text(term, text))
    if cast_hits:
        confirmed = True
        score += min(3, cast_hits) * 18
        reasons.append(f'cast:{cast_hits}')

    director_hits = sum(1 for term in identity.director_terms if _word_in_text(term, text))
    director_hits += sum(1 for term in identity.director_fa if _word_in_text(term, text))
    if director_hits:
        confirmed = True
        score += min(2, director_hits) * 16
        reasons.append(f'director:{director_hits}')

    genre_hits = sum(1 for term in identity.genre_terms if _word_in_text(term, text))
    if genre_hits:
        score += min(3, genre_hits) * 6
        reasons.append(f'genre:{genre_hits}')

    return MetadataVerdict(reject=False, score=score, confirmed=confirmed, reasons=tuple(reasons))
