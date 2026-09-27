"""IMDb-facing rating enrichment for catalog imports.

Ratings are sourced in order of accuracy:

1. A value already on the payload (provider/manual) — kept, labeled ``manual``.
2. IMDb's own published number for the title's ``tt…`` id, read out of the
   daily dataset — labeled ``imdb``. Exact, free, and needs no API key, so this
   is the path that actually runs. See :mod:`apps.catalog.imdb_dataset`.
3. The real IMDb score from OMDb when ``OMDB_API_KEY`` is set — labeled
   ``omdb``. Equivalent in accuracy to (2); kept for titles the dataset lags on.
4. TMDB ``vote_average`` as a last-resort approximation — labeled ``tmdb`` — so a
   public card is never shipped without an IMDb-facing score.

Order matters more than it looks. (2) was added on 2026-09-24 after measuring
the catalog against IMDb's own file: with only (3) unavailable and (4) doing all
the work, just 9% of 20,168 rated titles carried the right number and 3,898 were
off by a full point or more. Anything landing on (4) today is explicitly a
placeholder — it is labeled ``tmdb`` so the six-hourly sync can come back and
replace it the moment IMDb publishes a score.

Making the score mandatory is enforced separately in ``completeness.py``
(``missing_imdb_rating`` is a publish blocker); this module only fills it.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def configured_imdb_client():
    """Compatibility stub — ratings are sourced from OMDb/TMDB, not a client."""
    return None


def _imdb_id_from_details(details) -> str:
    external_ids = details.get('external_ids') or {}
    return (external_ids.get('imdb_id') or details.get('imdb_id') or '').strip()


def _enrich_from_dataset(details) -> bool:
    """Attach IMDb's own score for this title. Returns True when it set one."""
    imdb_id = _imdb_id_from_details(details)
    if not imdb_id.startswith('tt'):
        return False
    try:
        from .imdb_dataset import lookup
    except Exception:  # pragma: no cover - defensive import guard
        return False
    exact = lookup(imdb_id)
    if exact is None:
        return False
    details['imdb_rating'] = round(exact.rating, 1)
    details['imdb_votes'] = exact.votes
    details['imdb_rating_source'] = 'imdb'
    return True


def _enrich_from_omdb(details) -> bool:
    """Attach the real IMDb score from OMDb. Returns True when it set one."""
    imdb_id = _imdb_id_from_details(details)
    if not imdb_id.startswith('tt'):
        return False
    try:
        from .ratings import _as_float, _as_int, _fetch_omdb_by_imdb_id, _omdb_configured
    except Exception:  # pragma: no cover - defensive import guard
        return False
    if not _omdb_configured():
        return False
    payload = _fetch_omdb_by_imdb_id(imdb_id)
    if not payload:
        return False
    score = _as_float(payload.get('imdbRating'))
    if score is None or score <= 0:
        return False
    details['imdb_rating'] = round(score, 1)
    details['imdb_votes'] = _as_int(str(payload.get('imdbVotes') or '').replace(',', '').strip())
    details['imdb_rating_source'] = 'omdb'
    return True


def enrich_imdb_rating(details, *, client=None, enabled=True):
    """Fill ``imdb_rating`` from OMDb (accurate) or TMDB ``vote_average``."""
    del client
    # A rating already on the payload wins; only tag its provenance.
    if details.get('imdb_rating') not in (None, ''):
        if not details.get('imdb_rating_source'):
            details['imdb_rating_source'] = 'manual'
        return details
    if not enabled:
        return details

    # IMDb's own published number first — exact, and available without a key.
    if _enrich_from_dataset(details):
        return details

    # Then OMDb, which reports the same score through an account-gated API.
    if _enrich_from_omdb(details):
        return details

    # Fall back to TMDB vote_average so the card always has a score to show.
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
