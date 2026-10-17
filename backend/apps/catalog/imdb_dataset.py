"""The real IMDb ratings, straight from IMDb's own daily dataset.

Why this module exists
----------------------
Until now every ``imdb_rating`` on the site was a *TMDB* ``vote_average``
wearing an IMDb label, because the accurate path (OMDb) needs an API key that
has never been set. Measured against IMDb's own numbers on 2026-09-24, only
9% of the catalog's 20,168 rated titles were actually right: 8,433 were off by
at least half a point, 3,898 by a full point or more, the worst by 7.9.

IMDb publishes the ground truth itself, for free and without a key:
``https://datasets.imdbws.com/title.ratings.tsv.gz`` — 8 MB gzipped, ~1.71 M
titles, refreshed every day, three columns (``tconst``, ``averageRating``,
``numVotes``). Every title we hold an ``imdb_id`` for is in it (96.8% coverage;
the remainder are titles IMDb itself has not rated yet).

How it is used
--------------
The file is **sorted by tconst**, which makes it an index, not just a dump. So
there are two access paths and they share one cached copy:

* :func:`lookup` binary-searches the decompressed file through ``mmap`` — a
  handful of page reads, no parsing of the other 1.7 M rows, no dict in RAM.
  That is what the importer calls, so a title gets its exact score at the
  moment it is imported rather than whenever the next sweep happens to run.
* :func:`sync_catalog_ratings` scans the file once, keeping only the ~21 K
  rows whose tconst we actually hold, and bulk-updates the catalog.

The cache lives in a tmpfs directory by default. It is worth almost nothing to
lose — a cold start costs one 8 MB download — so it deliberately does not claim
a named volume or the chown dance that comes with one.
"""

from __future__ import annotations

import gzip
import logging
import mmap
import os
import shutil
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

DATASET_URL = 'https://datasets.imdbws.com/title.ratings.tsv.gz'

#: IMDb regenerates the file once a day. Twenty hours keeps us on the newest
#: copy without re-downloading it because a task happened to fire twice.
DEFAULT_MAX_AGE_HOURS = 20

#: Ratings written from this file are exact, so they outrank every other source.
SOURCE_IMDB = 'imdb'

#: Ordered least- to most-trustworthy. A sync never downgrades a rating that a
#: human set by hand, and never leaves a TMDB guess in place of a real score.
SOURCE_RANK = {'': 0, 'tmdb': 1, 'omdb': 2, 'imdb': 3, 'manual': 4}


@dataclass(frozen=True)
class ImdbRating:
    """One row of the dataset."""

    rating: float
    votes: int


def cache_dir() -> Path:
    configured = getattr(settings, 'IMDB_DATASET_CACHE_DIR', '') or os.environ.get(
        'IMDB_DATASET_CACHE_DIR', ''
    )
    return Path(configured.strip() or (Path(tempfile.gettempdir()) / 'revayato-imdb'))


def dataset_path() -> Path:
    """The decompressed, tconst-sorted TSV the lookups read."""
    return cache_dir() / 'title.ratings.tsv'


def dataset_age_seconds() -> float | None:
    """Seconds since the cached copy was written, or ``None`` when absent."""
    try:
        return max(0.0, time.time() - dataset_path().stat().st_mtime)
    except OSError:
        return None


def ensure_dataset(*, max_age_hours: float = DEFAULT_MAX_AGE_HOURS, force: bool = False,
                   timeout: int = 180) -> Path:
    """Download and decompress the dataset unless a fresh copy is already here.

    The download lands on a temporary name and is moved into place only once it
    is complete, so a killed container can never leave a half-written file that
    a binary search would happily return garbage from.
    """
    target = dataset_path()
    if not force:
        age = dataset_age_seconds()
        if age is not None and age < max_age_hours * 3600:
            return target

    target.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    tmp_gz = target.with_suffix('.tsv.gz.part')
    tmp_tsv = target.with_suffix('.tsv.part')
    request = urllib.request.Request(
        DATASET_URL,
        headers={'User-Agent': getattr(settings, 'IMDB_DATASET_USER_AGENT', 'RevayatoCatalog/1.0')},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, open(tmp_gz, 'wb') as fh:
            shutil.copyfileobj(response, fh, length=1 << 20)
        with gzip.open(tmp_gz, 'rb') as src, open(tmp_tsv, 'wb') as dst:
            shutil.copyfileobj(src, dst, length=1 << 20)
        os.replace(tmp_tsv, target)
    finally:
        for leftover in (tmp_gz, tmp_tsv):
            try:
                leftover.unlink(missing_ok=True)
            except OSError:
                pass
    logger.info(
        'imdb_dataset.refreshed bytes=%s seconds=%.1f',
        target.stat().st_size,
        time.monotonic() - started,
    )
    return target


def _parse(line: bytes) -> ImdbRating | None:
    parts = line.split(b'\t')
    if len(parts) < 3:
        return None
    try:
        rating = float(parts[1])
        votes = int(parts[2])
    except (TypeError, ValueError):
        return None
    if rating <= 0:
        return None
    return ImdbRating(rating=rating, votes=votes)


def lookup(imdb_id: str, *, max_age_hours: float = DEFAULT_MAX_AGE_HOURS) -> ImdbRating | None:
    """Exact rating for one ``tt…`` id, or ``None`` when IMDb has not rated it.

    Binary search over the sorted file. The comparison is plain byte ordering,
    which is the order the file is actually in — IMDb ids are not fixed width
    (``tt9916880`` vs ``tt10000001``) and sorting them numerically would put the
    file in a different order than the one it ships in.
    """
    key = (imdb_id or '').strip().encode('ascii', 'ignore')
    if not key.startswith(b'tt'):
        return None
    try:
        path = ensure_dataset(max_age_hours=max_age_hours)
        handle = open(path, 'rb')
    except Exception as exc:  # noqa: BLE001 - a rating is never worth failing an import over
        logger.warning('imdb_dataset.lookup_unavailable id=%s error=%s', imdb_id, exc)
        return None
    try:
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            lo, hi = 0, mm.size()
            while lo < hi:
                mid = (lo + hi) // 2
                newline = mm.rfind(b'\n', lo, mid)
                start = lo if newline == -1 else newline + 1
                end = mm.find(b'\n', start)
                if end == -1:
                    end = mm.size()
                line = mm[start:end]
                tconst = line.split(b'\t', 1)[0]
                if tconst == key:
                    return _parse(line)
                if tconst < key:
                    lo = end + 1
                else:
                    hi = start
    except (OSError, ValueError) as exc:
        logger.warning('imdb_dataset.lookup_failed id=%s error=%s', imdb_id, exc)
    finally:
        handle.close()
    return None


def index_for(imdb_ids, *, max_age_hours: float = DEFAULT_MAX_AGE_HOURS) -> dict[str, ImdbRating]:
    """Ratings for a set of ids, read with a single sequential pass.

    For a bulk sweep this beats thousands of binary searches and — more to the
    point — never holds the whole 1.7 M-row file in memory: only the rows whose
    tconst we asked for survive the scan.
    """
    wanted = {i.strip().encode() for i in imdb_ids if i and i.strip().startswith('tt')}
    if not wanted:
        return {}
    path = ensure_dataset(max_age_hours=max_age_hours)
    found: dict[str, ImdbRating] = {}
    with open(path, 'rb') as fh:
        fh.readline()  # header
        for line in fh:
            tconst = line.split(b'\t', 1)[0]
            if tconst not in wanted:
                continue
            parsed = _parse(line.rstrip(b'\n'))
            if parsed is not None:
                found[tconst.decode()] = parsed
            wanted.discard(tconst)
            if not wanted:
                break
    return found


def _may_overwrite(obj, current_source: str) -> bool:
    """Whether the dataset is allowed to replace what is already on the row.

    A score a human typed in the admin outranks even IMDb: that override exists
    precisely because someone judged the automatic number wrong.
    """
    if 'imdb_rating' in (getattr(obj, 'manual_override_fields', None) or []):
        return False
    return SOURCE_RANK.get(current_source or '', 0) <= SOURCE_RANK[SOURCE_IMDB]


def sync_catalog_ratings(*, movies: bool = True, series: bool = True, limit: int = 0,
                         only_missing: bool = False, dry_run: bool = False,
                         batch_size: int = 500,
                         max_age_hours: float = DEFAULT_MAX_AGE_HOURS) -> dict:
    """Replace approximated ratings with IMDb's own, in bulk.

    Returns a summary rather than logging one, so both the management command
    and the Celery task can report the same numbers.
    """
    from django.db.models import Q

    from .models import Movie, Series

    targets = []
    if movies:
        targets.append(('movies', Movie))
    if series:
        targets.append(('series', Series))

    summary = {
        'checked': 0, 'updated': 0, 'filled': 0, 'corrected': 0,
        'unrated_by_imdb': 0, 'skipped_manual': 0, 'dry_run': dry_run,
        'movies': 0, 'series': 0,
    }

    for label, model in targets:
        queryset = model.objects.exclude(imdb_id='').exclude(imdb_id=None)
        if only_missing:
            queryset = queryset.filter(Q(imdb_rating__isnull=True) | Q(imdb_rating__lte=0))
        # Newest first: a title someone is likely to open today gets its real
        # score before the 2009 back-catalogue does when `--limit` cuts the run.
        queryset = queryset.order_by('-id')
        if limit:
            queryset = queryset[:limit]

        rows = list(queryset.only(
            'id', 'imdb_id', 'imdb_rating', 'imdb_votes', 'imdb_rating_source',
            *(('manual_override_fields',) if hasattr(model, 'manual_override_fields') else ()),
        ))
        if not rows:
            continue
        ratings = index_for([r.imdb_id for r in rows], max_age_hours=max_age_hours)
        now = timezone.now()
        pending = []
        for row in rows:
            summary['checked'] += 1
            exact = ratings.get((row.imdb_id or '').strip())
            if exact is None:
                summary['unrated_by_imdb'] += 1
                continue
            if not _may_overwrite(row, row.imdb_rating_source):
                summary['skipped_manual'] += 1
                continue
            previous = float(row.imdb_rating) if row.imdb_rating is not None else None
            unchanged = (
                previous is not None
                and abs(previous - exact.rating) < 0.05
                and row.imdb_rating_source == SOURCE_IMDB
                and row.imdb_votes == exact.votes
            )
            if unchanged:
                continue
            if previous is None or previous <= 0:
                summary['filled'] += 1
            elif abs(previous - exact.rating) >= 0.05:
                summary['corrected'] += 1
            row.imdb_rating = round(exact.rating, 1)
            row.imdb_votes = exact.votes
            row.imdb_rating_source = SOURCE_IMDB
            row.imdb_rating_synced_at = now
            pending.append(row)

        summary['updated'] += len(pending)
        summary[label] = len(pending)
        if pending and not dry_run:
            for start in range(0, len(pending), batch_size):
                model.objects.bulk_update(
                    pending[start:start + batch_size],
                    ['imdb_rating', 'imdb_votes', 'imdb_rating_source', 'imdb_rating_synced_at'],
                )
    return summary


def sync_title_rating(obj) -> str:
    """IMDb's own score for one title — the per-title half of :func:`sync_catalog_ratings`.

    Returns what happened: ``updated``, ``unchanged``, ``unrated_by_imdb``,
    ``manual`` (a human's score stands) or ``no_imdb_id``.
    """
    imdb_id = (getattr(obj, 'imdb_id', '') or '').strip()
    if not imdb_id.startswith('tt'):
        return 'no_imdb_id'
    if not _may_overwrite(obj, obj.imdb_rating_source):
        return 'manual'
    exact = lookup(imdb_id)
    if exact is None:
        return 'unrated_by_imdb'
    previous = float(obj.imdb_rating) if obj.imdb_rating is not None else None
    if (
        previous is not None and abs(previous - exact.rating) < 0.05
        and obj.imdb_rating_source == SOURCE_IMDB and obj.imdb_votes == exact.votes
    ):
        return 'unchanged'
    obj.imdb_rating = round(exact.rating, 1)
    obj.imdb_votes = exact.votes
    obj.imdb_rating_source = SOURCE_IMDB
    obj.imdb_rating_synced_at = timezone.now()
    obj.save(update_fields=['imdb_rating', 'imdb_votes', 'imdb_rating_source', 'imdb_rating_synced_at'])
    return 'updated'
