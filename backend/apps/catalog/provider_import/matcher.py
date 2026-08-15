"""Compatibility re-exports for earlier Avasarami matcher imports."""

from .matching import match_movie, match_series, movie_has_available_archive, normalize_title

__all__ = [
    'normalize_title',
    'match_movie',
    'match_series',
    'movie_has_available_archive',
]
