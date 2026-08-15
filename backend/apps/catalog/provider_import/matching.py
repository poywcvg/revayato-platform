"""Catalog ↔ provider title matching with explicit confidence rules."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from apps.catalog.models import Movie, Series


def normalize_title(value: str) -> str:
    value = unicodedata.normalize('NFKC', str(value or ''))
    # Persian/Arabic yeh/kaf variants
    value = value.replace('\u064a', '\u06cc').replace('\u0643', '\u06a9').replace('\u200c', ' ')
    value = value.casefold()
    return re.sub(r'[\W_]+', '', value, flags=re.UNICODE)


@dataclass
class MatchResult:
    score: float
    reason: str
    reasons: list = field(default_factory=list)
    requires_manual_approval: bool = True
    movie: Movie | None = None
    series: Series | None = None


_PROVIDER_MIN_AUTO_MATCH_SCORE = 0.95
_PROVIDER_REQUIRE_MANUAL_APPROVAL = False


def score_provider_candidate_against_movie(candidate, movie: Movie) -> MatchResult:
    reasons = []
    score = 0.0
    c_tmdb = getattr(candidate, 'tmdb_id', None)
    c_imdb = (getattr(candidate, 'imdb_id', None) or '').strip()
    c_title = getattr(candidate, 'title', '') or getattr(candidate, 'original_title', '')
    c_year = getattr(candidate, 'year', None)

    if movie.tmdb_id and c_tmdb and int(movie.tmdb_id) == int(c_tmdb):
        require_manual = _PROVIDER_REQUIRE_MANUAL_APPROVAL
        return MatchResult(1.0, 'tmdb_id', ['tmdb_id'], require_manual, movie=movie)
    if movie.tmdb_id and c_tmdb and int(movie.tmdb_id) != int(c_tmdb):
        return MatchResult(0.0, 'tmdb_conflict', ['tmdb_conflict'], True, movie=movie)

    if movie.imdb_id and c_imdb and movie.imdb_id.lower() == c_imdb.lower():
        require_manual = _PROVIDER_REQUIRE_MANUAL_APPROVAL
        return MatchResult(0.99, 'imdb_id', ['imdb_id'], require_manual, movie=movie)
    if movie.imdb_id and c_imdb and movie.imdb_id.lower() != c_imdb.lower():
        return MatchResult(0.0, 'imdb_conflict', ['imdb_conflict'], True, movie=movie)

    nt = normalize_title(c_title)
    movie_titles = {normalize_title(movie.title), normalize_title(movie.original_title)}
    movie_titles.discard('')
    year_ok = bool(c_year and movie.release_year and int(c_year) == int(movie.release_year))
    year_close = bool(
        c_year and movie.release_year and abs(int(c_year) - int(movie.release_year)) <= 1
    )

    if nt and nt in movie_titles and year_ok:
        require_manual = _PROVIDER_REQUIRE_MANUAL_APPROVAL
        return MatchResult(0.96, 'title_year', ['title_year'], require_manual, movie=movie)

    if nt and nt in movie_titles and year_close:
        reasons = ['title_close_year']
        score = 0.85
    elif nt and nt in movie_titles:
        reasons = ['title_only']
        score = 0.7
    elif nt and any(_similar(nt, other) for other in movie_titles):
        reasons = ['fuzzy_title']
        score = 0.55
    else:
        reasons = ['no_match']
        score = 0.0

    min_auto = _PROVIDER_MIN_AUTO_MATCH_SCORE
    require_manual = _PROVIDER_REQUIRE_MANUAL_APPROVAL
    needs_approval = require_manual or score < min_auto or 'fuzzy' in (reasons[0] if reasons else '')
    return MatchResult(score, reasons[0], reasons, needs_approval, movie=movie)


def score_provider_candidate_against_series(candidate, series: Series) -> MatchResult:
    reasons = []
    c_tmdb = getattr(candidate, 'tmdb_id', None)
    c_imdb = (getattr(candidate, 'imdb_id', None) or '').strip()
    c_title = getattr(candidate, 'title', '') or getattr(candidate, 'original_title', '')
    c_year = getattr(candidate, 'year', None)
    series_year = series.start_year or getattr(series, 'release_year', None)

    if series.tmdb_id and c_tmdb and int(series.tmdb_id) == int(c_tmdb):
        require_manual = _PROVIDER_REQUIRE_MANUAL_APPROVAL
        return MatchResult(1.0, 'tmdb_id', ['tmdb_id'], require_manual, series=series)
    if series.tmdb_id and c_tmdb and int(series.tmdb_id) != int(c_tmdb):
        return MatchResult(0.0, 'tmdb_conflict', ['tmdb_conflict'], True, series=series)

    if series.imdb_id and c_imdb and series.imdb_id.lower() == c_imdb.lower():
        require_manual = _PROVIDER_REQUIRE_MANUAL_APPROVAL
        return MatchResult(0.99, 'imdb_id', ['imdb_id'], require_manual, series=series)
    if series.imdb_id and c_imdb and series.imdb_id.lower() != c_imdb.lower():
        return MatchResult(0.0, 'imdb_conflict', ['imdb_conflict'], True, series=series)

    nt = normalize_title(c_title)
    titles = {normalize_title(series.title), normalize_title(series.original_title)}
    titles.discard('')
    year_ok = bool(c_year and series_year and int(c_year) == int(series_year))

    if nt and nt in titles and year_ok:
        require_manual = _PROVIDER_REQUIRE_MANUAL_APPROVAL
        return MatchResult(0.96, 'title_year', ['title_year'], require_manual, series=series)
    if nt and nt in titles:
        score, reasons = 0.7, ['title_only']
    elif nt and any(_similar(nt, other) for other in titles):
        score, reasons = 0.55, ['fuzzy_title']
    else:
        score, reasons = 0.0, ['no_match']

    min_auto = _PROVIDER_MIN_AUTO_MATCH_SCORE
    require_manual = _PROVIDER_REQUIRE_MANUAL_APPROVAL
    needs_approval = require_manual or score < min_auto or 'fuzzy' in reasons[0]
    return MatchResult(score, reasons[0], reasons, needs_approval, series=series)


def _similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    if a in b or b in a:
        return abs(len(a) - len(b)) <= max(4, len(a) // 5)
    return False


# Backwards-compatible helpers used by Avasarami path.
def match_movie(*, tmdb_id=None, imdb_id=None, title='', year=None):
    class _C:
        pass

    c = _C()
    c.tmdb_id = tmdb_id
    c.imdb_id = imdb_id or ''
    c.title = title
    c.original_title = title
    c.year = year
    qs = Movie.objects.all()
    if tmdb_id:
        movie = qs.filter(tmdb_id=tmdb_id).first()
        if movie:
            return movie, 'tmdb_id'
    if imdb_id:
        movie = qs.filter(imdb_id__iexact=imdb_id).first()
        if movie:
            return movie, 'imdb_id'
    if title and year:
        for movie in qs.filter(release_year=year).only('id', 'title', 'original_title', 'release_year'):
            result = score_provider_candidate_against_movie(c, movie)
            if result.score >= 0.96:
                return movie, 'title_year'
    return None, ''


def match_series(*, tmdb_id=None, imdb_id=None, title='', year=None):
    class _C:
        pass

    c = _C()
    c.tmdb_id = tmdb_id
    c.imdb_id = imdb_id or ''
    c.title = title
    c.original_title = title
    c.year = year
    qs = Series.objects.all()
    if tmdb_id:
        series = qs.filter(tmdb_id=tmdb_id).first()
        if series:
            return series, 'tmdb_id'
    if imdb_id:
        series = qs.filter(imdb_id__iexact=imdb_id).first()
        if series:
            return series, 'imdb_id'
    if title and year:
        for series in qs.filter(start_year=year).only('id', 'title', 'original_title', 'start_year'):
            result = score_provider_candidate_against_series(c, series)
            if result.score >= 0.96:
                return series, 'title_year'
    return None, ''


def movie_has_available_archive(movie: Movie) -> bool:
    return movie.archive_assets.filter(status='available').exists()
