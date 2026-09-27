"""Build the IMDb Top-250 movie/TV charts from IMDb's own public datasets.

IMDb's chart HTML is bot-gated; the TSV dumps at ``datasets.imdbws.com`` are the
stable source. We apply the Bayesian weighted rating IMDb documents for the Top
250 (``WR = (v/(v+m))*R + (m/(v+m))*C``) so the ranking stays close to the chart.

Two files are involved and they are very different sizes: ``title.ratings`` is
~8 MB gzipped, ``title.basics`` is a couple of hundred. Both are therefore read
as *streams* — decompressed row by row straight off the socket — and the ratings
map is filtered down to the vote floor while it is being built. That keeps the
whole build inside a few tens of MB, which matters because the container that
runs it (``catalog-crawler``) has a 768 MB ceiling shared with everything else it
does; buffering the raw downloads and keeping all 1.7 M rated titles in a dict
put it within sight of that ceiling for no benefit — nothing under 25 000 votes
can ever reach a Top-250 position.

The built chart is written to :class:`~apps.catalog.models.ImdbChartEntry`, and
every reader (the API, the apps, the completion lane) goes to that table. Nothing
user-facing ever waits on this download.
"""

from __future__ import annotations

import csv
import gzip
import io
import logging
import time
import urllib.request
from dataclasses import dataclass
from functools import lru_cache

logger = logging.getLogger(__name__)

IMDB_RATINGS_URL = 'https://datasets.imdbws.com/title.ratings.tsv.gz'
IMDB_BASICS_URL = 'https://datasets.imdbws.com/title.basics.tsv.gz'
DEFAULT_USER_AGENT = 'RevayatoCatalog/1.0 (+https://revayato.com)'

# IMDb Top 250 historically requires a high vote floor; 25k matches their docs.
MOVIE_MIN_VOTES = 25_000
TV_MIN_VOTES = 25_000
MOVIE_TYPES = frozenset({'movie'})
TV_TYPES = frozenset({'tvSeries'})

#: Nothing below this can reach either chart, so it never enters the ratings map.
CHART_MIN_VOTES = min(MOVIE_MIN_VOTES, TV_MIN_VOTES)

#: How many chart positions each kind holds. The name of the feature, basically.
TOP_LIMIT = 250


@dataclass(frozen=True)
class ImdbChartTitle:
    imdb_id: str
    title_type: str
    primary_title: str
    original_title: str
    start_year: int | None
    average_rating: float
    num_votes: int
    weighted_rating: float
    rank: int


def _stream_tsv_gz(url: str, *, timeout: int = 180):
    """Yield decoded rows of a gzipped TSV without ever holding the file in RAM."""
    request = urllib.request.Request(
        url,
        headers={
            'User-Agent': DEFAULT_USER_AGENT,
            'Accept': 'application/gzip,application/octet-stream,*/*',
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        # GzipFile only needs ``read`` from the underlying object, so the HTTP
        # response works directly as the source and nothing is buffered whole.
        with gzip.GzipFile(fileobj=response) as decompressed:
            text = io.TextIOWrapper(decompressed, encoding='utf-8', errors='replace')
            yield from csv.DictReader(text, delimiter='\t')


def _safe_int(value) -> int | None:
    text = str(value or '').strip()
    if not text or text == '\\N':
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _safe_float(value) -> float | None:
    text = str(value or '').strip()
    if not text or text == '\\N':
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _weighted_rating(rating: float, votes: int, *, mean: float, min_votes: int) -> float:
    """IMDb-style Bayesian estimate used by the public Top 250 explanation."""
    m = max(1, int(min_votes))
    v = max(0, int(votes))
    return (v / (v + m)) * rating + (m / (v + m)) * mean


def _rank_chart(
    candidates: list[dict],
    *,
    limit: int,
    min_votes: int,
) -> list[ImdbChartTitle]:
    if not candidates:
        return []
    mean = sum(row['average_rating'] for row in candidates) / len(candidates)
    scored: list[ImdbChartTitle] = []
    for row in candidates:
        wr = _weighted_rating(
            row['average_rating'],
            row['num_votes'],
            mean=mean,
            min_votes=min_votes,
        )
        scored.append(
            ImdbChartTitle(
                imdb_id=row['imdb_id'],
                title_type=row['title_type'],
                primary_title=row['primary_title'],
                original_title=row['original_title'],
                start_year=row['start_year'],
                average_rating=row['average_rating'],
                num_votes=row['num_votes'],
                weighted_rating=wr,
                rank=0,
            )
        )
    scored.sort(key=lambda item: (-item.weighted_rating, -item.num_votes, item.imdb_id))
    out: list[ImdbChartTitle] = []
    for index, item in enumerate(scored[: max(1, int(limit))], start=1):
        out.append(
            ImdbChartTitle(
                imdb_id=item.imdb_id,
                title_type=item.title_type,
                primary_title=item.primary_title,
                original_title=item.original_title,
                start_year=item.start_year,
                average_rating=item.average_rating,
                num_votes=item.num_votes,
                weighted_rating=item.weighted_rating,
                rank=index,
            )
        )
    return out


@lru_cache(maxsize=4)
def _load_chart_payload(*, limit: int) -> tuple[ImdbChartTitle, ...]:
    """Download IMDb datasets once and rank both movie + TV Top charts."""
    started = time.monotonic()

    ratings: dict[str, tuple[float, int]] = {}
    for row in _stream_tsv_gz(IMDB_RATINGS_URL):
        votes = _safe_int(row.get('numVotes')) or 0
        # The vote floor is applied here, not later, so the map holds ~15 K rows
        # instead of 1.7 M. Everything discarded is by definition unrankable.
        if votes < CHART_MIN_VOTES:
            continue
        imdb_id = str(row.get('tconst') or '').strip()
        rating = _safe_float(row.get('averageRating'))
        if not imdb_id or rating is None:
            continue
        ratings[imdb_id] = (rating, votes)

    movie_candidates: list[dict] = []
    series_candidates: list[dict] = []
    wanted_types = MOVIE_TYPES | TV_TYPES

    for row in _stream_tsv_gz(IMDB_BASICS_URL):
        title_type = str(row.get('titleType') or '').strip()
        if title_type not in wanted_types:
            continue
        if str(row.get('isAdult') or '0').strip() not in {'0', 'False', 'false'}:
            continue
        imdb_id = str(row.get('tconst') or '').strip()
        rated = ratings.get(imdb_id)
        if not rated:
            continue
        average_rating, num_votes = rated
        min_votes = MOVIE_MIN_VOTES if title_type in MOVIE_TYPES else TV_MIN_VOTES
        if num_votes < min_votes:
            continue
        payload = {
            'imdb_id': imdb_id,
            'title_type': title_type,
            'primary_title': str(row.get('primaryTitle') or '').strip(),
            'original_title': str(row.get('originalTitle') or row.get('primaryTitle') or '').strip(),
            'start_year': _safe_int(row.get('startYear')),
            'average_rating': average_rating,
            'num_votes': num_votes,
        }
        if title_type in MOVIE_TYPES:
            movie_candidates.append(payload)
        else:
            series_candidates.append(payload)

    ranked: list[ImdbChartTitle] = []
    ranked.extend(_rank_chart(movie_candidates, limit=limit, min_votes=MOVIE_MIN_VOTES))
    ranked.extend(_rank_chart(series_candidates, limit=limit, min_votes=TV_MIN_VOTES))

    logger.info(
        'imdb_chart loaded movies=%s series=%s rows=%s rated_pool=%s elapsed=%.1fs',
        sum(1 for item in ranked if item.title_type in MOVIE_TYPES),
        sum(1 for item in ranked if item.title_type in TV_TYPES),
        len(ranked),
        len(ratings),
        time.monotonic() - started,
    )
    return tuple(ranked)


def imdb_top_movies(*, limit: int = TOP_LIMIT) -> list[ImdbChartTitle]:
    return [
        item
        for item in _load_chart_payload(limit=max(1, int(limit)))
        if item.title_type in MOVIE_TYPES
    ]


def imdb_top_series(*, limit: int = TOP_LIMIT) -> list[ImdbChartTitle]:
    return [
        item
        for item in _load_chart_payload(limit=max(1, int(limit)))
        if item.title_type in TV_TYPES
    ]


def clear_imdb_chart_cache() -> None:
    _load_chart_payload.cache_clear()


def sync_imdb_top_ranks(*, limit: int = TOP_LIMIT) -> dict:
    """Stamp ``imdb_rank`` / ``imdb_rating`` on catalog rows that match the charts.

    Titles that fall off the chart get ``imdb_rank`` cleared so badges stay
    accurate. Kept as the thin, dependency-free entry point; the snapshot table is
    written by :func:`refresh_imdb_chart_snapshot`, which calls this.
    """
    from decimal import Decimal

    from apps.catalog.models import Movie, Series

    limit = max(1, min(TOP_LIMIT, int(limit)))
    clear_imdb_chart_cache()
    movies = imdb_top_movies(limit=limit)
    series = imdb_top_series(limit=limit)

    movie_by_id = {row.imdb_id.lower(): row for row in movies}
    series_by_id = {row.imdb_id.lower(): row for row in series}

    stats = {
        'movies_chart': len(movies),
        'series_chart': len(series),
        'movies_ranked': 0,
        'series_ranked': 0,
        'movies_cleared': 0,
        'series_cleared': 0,
        'movies_missing': [],
        'series_missing': [],
    }

    # Clear stale ranks first, then apply the current chart.
    stats['movies_cleared'] = Movie.objects.exclude(imdb_rank__isnull=True).update(imdb_rank=None)
    stats['series_cleared'] = Series.objects.exclude(imdb_rank__isnull=True).update(imdb_rank=None)

    for model, chart_map, ranked_key, missing_key, kind in (
        (Movie, movie_by_id, 'movies_ranked', 'movies_missing', 'movie'),
        (Series, series_by_id, 'series_ranked', 'series_missing', 'series'),
    ):
        for imdb_id, chart in chart_map.items():
            updated = model.objects.filter(imdb_id__iexact=imdb_id).update(
                imdb_rank=chart.rank,
                imdb_rating=Decimal(str(round(chart.average_rating, 1))),
            )
            if updated:
                stats[ranked_key] += updated
            else:
                stats[missing_key].append({
                    'rank': chart.rank,
                    'imdb_id': chart.imdb_id,
                    'title': chart.primary_title,
                    'kind': kind,
                })

    return stats
