"""IMDb-facing rating enrichment from TMDB vote averages.

TMDB does not expose the official IMDb score. Staff-enabled rating import stores
TMDB ``vote_average`` in ``imdb_rating`` so public cards always have an IMDb-
labeled score without requiring OMDb.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def configured_imdb_client():
    """Compatibility stub — ratings are sourced from TMDB when OMDb is unset."""
    return None


def enrich_imdb_rating(details, *, client=None, enabled=True):
    """Attach a display rating from TMDB ``vote_average`` when IMDb is missing."""
    del client
    if not enabled or details.get('imdb_rating') not in (None, ''):
        if details.get('imdb_rating') not in (None, '') and not details.get('imdb_rating_source'):
            details['imdb_rating_source'] = 'manual'
        return details

    vote = details.get('vote_average')
    if vote in (None, ''):
        return details
    try:
        score = float(vote)
    except (TypeError, ValueError):
        return details
    if score <= 0:
        return details

    details['imdb_rating'] = round(score, 1)
    details['imdb_votes'] = details.get('vote_count')
    details['imdb_rating_source'] = 'tmdb'
    return details
