"""IMDb Top 250 as a first-class shelf that keeps itself complete.

Three jobs, one module:

* :func:`refresh_chart` — rebuild the stored chart (:class:`ImdbChartEntry`) from
  IMDb's datasets, link every position to the catalog row it names, and stamp
  ``imdb_rank`` on those rows. Slow (two large downloads), so it only runs when
  the stored chart is older than ``max_age_hours``.
* :func:`complete_chart` — the reason this exists. Walks the positions that are
  not yet watchable, best rank first, and does whatever each one is missing:
  import the metadata from TMDB, crawl the providers for sources, publish. A
  bounded number per call, so it can run as one lane of the permanent crawler
  loop without starving the lanes around it.
* :func:`coverage` — how complete the shelf actually is, per kind. Served by the
  API and printed by the lane, so "are all 250 there?" is a number, not a hope.

Nothing here ever deletes a catalog row. The bulk importer drops a brand-new
title whose crawl came back empty; for a Top-250 position that is exactly wrong —
the draft is the thing the next pass (and the draft-source hunter) retries.
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

KINDS = ('movie', 'series')

#: Why a position is not watchable yet. Stored on the entry, shown in the admin.
GAP_NOT_IN_CATALOG = 'not_in_catalog'
GAP_TMDB_MISS = 'tmdb_miss'
GAP_NO_SOURCE = 'no_source'
GAP_NOT_PUBLISHED = 'not_published'
GAP_IMPORT_FAILED = 'import_failed'
GAP_CRAWL_TIMEOUT = 'crawl_timeout'


def _models():
    from apps.catalog.models import ImdbChartEntry, Movie, Series

    return ImdbChartEntry, Movie, Series


def chart_age_hours() -> float | None:
    ImdbChartEntry, _, _ = _models()
    newest = ImdbChartEntry.objects.order_by('-refreshed_at').values_list('refreshed_at', flat=True).first()
    if newest is None:
        return None
    return (timezone.now() - newest).total_seconds() / 3600


def link_entries() -> dict:
    """Point every chart position at the catalog row with the same ``imdb_id``.

    Cheap and idempotent, so it runs on every pass — a title imported by any
    other lane (the Film2Media walk, a manual import) joins the shelf immediately
    instead of waiting for the next chart download.
    """
    ImdbChartEntry, Movie, Series = _models()
    linked = 0
    for kind, model, field in (('movie', Movie, 'movie'), ('series', Series, 'series')):
        entries = list(ImdbChartEntry.objects.filter(kind=kind))
        by_imdb = {
            str(imdb_id).lower(): pk
            for pk, imdb_id in model.objects.filter(
                imdb_id__in=[entry.imdb_id for entry in entries],
            ).values_list('pk', 'imdb_id')
        }
        # imdb_id is stored case-sensitively but compared case-insensitively
        # elsewhere; fall back to an iexact probe for the handful that miss.
        for entry in entries:
            target = by_imdb.get(entry.imdb_id.lower())
            if target is None:
                target = model.objects.filter(imdb_id__iexact=entry.imdb_id).values_list('pk', flat=True).first()
            if getattr(entry, f'{field}_id') != target:
                setattr(entry, f'{field}_id', target)
                entry.save(update_fields=[field])
                linked += 1
            if target:
                model.objects.filter(pk=target).exclude(imdb_rank=entry.rank).update(imdb_rank=entry.rank)
    return {'relinked': linked}


def refresh_chart(*, max_age_hours: float = 20, force: bool = False) -> dict:
    """Rebuild the stored chart from IMDb's datasets when it is stale."""
    from apps.catalog.imdb_charts import TOP_LIMIT, clear_imdb_chart_cache, imdb_top_movies, imdb_top_series

    ImdbChartEntry, Movie, Series = _models()
    age = chart_age_hours()
    if not force and age is not None and age < max_age_hours:
        return {'status': 'fresh', 'age_hours': round(age, 1), **link_entries()}

    clear_imdb_chart_cache()
    charts = {
        'movie': imdb_top_movies(limit=TOP_LIMIT),
        'series': imdb_top_series(limit=TOP_LIMIT),
    }
    # A partial download would otherwise truncate a good chart to a bad one.
    for kind, rows in charts.items():
        if len(rows) < TOP_LIMIT * 0.9:
            raise RuntimeError(f'imdb chart for {kind} has only {len(rows)} rows; refusing to replace the stored chart')

    stats = {'status': 'refreshed', 'movie': 0, 'series': 0, 'dropped': 0}
    with transaction.atomic():
        for kind, rows in charts.items():
            existing = {entry.imdb_id: entry for entry in ImdbChartEntry.objects.filter(kind=kind)}
            keep = {row.imdb_id for row in rows}
            dropped = [entry.pk for imdb_id, entry in existing.items() if imdb_id not in keep]
            stats['dropped'] += len(dropped)
            ImdbChartEntry.objects.filter(pk__in=dropped).delete()
            # Park every surviving row off the chart first: ranks shuffle daily and
            # (kind, rank) is unique, so writing new ranks in place would collide.
            for offset, entry in enumerate(ImdbChartEntry.objects.filter(kind=kind).order_by('pk')):
                ImdbChartEntry.objects.filter(pk=entry.pk).update(rank=TOP_LIMIT + 1 + offset)
            for row in rows:
                entry = existing.get(row.imdb_id) or ImdbChartEntry(kind=kind, imdb_id=row.imdb_id)
                entry.rank = row.rank
                entry.primary_title = row.primary_title[:255]
                entry.original_title = row.original_title[:255]
                entry.start_year = row.start_year
                entry.average_rating = Decimal(str(round(row.average_rating, 1)))
                entry.num_votes = row.num_votes
                entry.save()
                stats[kind] += 1

        # Ranks on the catalog rows mirror the chart exactly: clear, then restamp.
        Movie.objects.exclude(imdb_rank__isnull=True).update(imdb_rank=None)
        Series.objects.exclude(imdb_rank__isnull=True).update(imdb_rank=None)
        now = timezone.now()
        for kind, model in (('movie', Movie), ('series', Series)):
            for row in charts[kind]:
                matches = model.objects.filter(imdb_id__iexact=row.imdb_id)
                matches.update(imdb_rank=row.rank)
                # The chart is computed from IMDb's own dataset, so its score is
                # exact — but a score an admin typed by hand still wins.
                exact = matches.exclude(imdb_rating_source='manual')
                if model is Movie:
                    exact = exact.exclude(manual_override_fields__contains=['imdb_rating'])
                exact.update(
                    imdb_rating=Decimal(str(round(row.average_rating, 1))),
                    imdb_votes=row.num_votes,
                    imdb_rating_source='imdb',
                    imdb_rating_synced_at=now,
                )
    stats.update(link_entries())
    return stats


def _is_watchable(obj) -> bool:
    from apps.catalog.top_catalog import _has_download_links

    return bool(obj and obj.is_published and _has_download_links(obj))


def coverage() -> dict:
    """Per kind: positions on the chart, in the catalog, and actually watchable."""
    ImdbChartEntry, _, _ = _models()
    out = {}
    for kind in KINDS:
        entries = ImdbChartEntry.objects.filter(kind=kind)
        field = 'movie' if kind == 'movie' else 'series'
        in_catalog = entries.filter(**{f'{field}__isnull': False})
        published = in_catalog.filter(**{f'{field}__is_published': True})
        out[kind] = {
            'total': entries.count(),
            'in_catalog': in_catalog.count(),
            'published': published.count(),
        }
    return out


def _incomplete_entries(kind: str, *, retry_after: timedelta):
    """Positions that are not watchable yet, best rank first, skipping recent tries."""
    ImdbChartEntry, _, _ = _models()
    field = 'movie' if kind == 'movie' else 'series'
    cutoff = timezone.now() - retry_after
    return (
        ImdbChartEntry.objects.filter(kind=kind)
        .filter(Q(**{f'{field}__isnull': True}) | Q(**{f'{field}__is_published': False}))
        .filter(Q(attempted_at__isnull=True) | Q(attempted_at__lt=cutoff))
        .select_related(field)
        .order_by('rank')
    )


def _import_from_tmdb(entry, client):
    """Create the catalog row for a chart position we do not hold. Never deletes."""
    from apps.catalog.ingestion import upsert_tmdb_movie, upsert_tmdb_series

    _, Movie, Series = _models()
    hit = client.resolve_imdb_to_tmdb(entry.imdb_id, content_type=entry.kind)
    if not hit:
        return None, GAP_TMDB_MISS
    tmdb_id = int(hit['id'])
    model = Movie if entry.kind == 'movie' else Series
    # The same title may already exist under its TMDB id with a blank imdb_id.
    existing = model.objects.filter(tmdb_id=tmdb_id).first()
    if existing is not None:
        if not existing.imdb_id:
            model.objects.filter(pk=existing.pk).update(imdb_id=entry.imdb_id)
            existing.refresh_from_db()
        return existing, ''
    with transaction.atomic():
        if entry.kind == 'movie':
            obj, *_ = upsert_tmdb_movie(client.movie_details(tmdb_id), auto_publish=False)
        else:
            obj, *_ = upsert_tmdb_series(client.tv_details(tmdb_id))
    if not obj.imdb_id:
        model.objects.filter(pk=obj.pk).update(imdb_id=entry.imdb_id)
        obj.refresh_from_db()
    return obj, ''


def _refresh_from_tmdb(obj, client) -> None:
    from apps.catalog.ingestion import upsert_tmdb_movie, upsert_tmdb_series

    try:
        with transaction.atomic():
            if obj.__class__.__name__ == 'Movie':
                upsert_tmdb_movie(client.movie_details(obj.tmdb_id), auto_publish=False)
            else:
                upsert_tmdb_series(client.tv_details(obj.tmdb_id))
    except Exception:  # the entry just keeps its metadata gap until next pass
        logger.warning('top250 metadata refresh failed for %s %s', obj.__class__.__name__, obj.pk, exc_info=True)


def complete_chart(
    *,
    limit: int = 20,
    retry_hours: float = 24,
    delay: float = 1.0,
    kinds: tuple[str, ...] = KINDS,
    budget_seconds: float | None = None,
) -> dict:
    """Make up to ``limit`` more chart positions watchable, best rank first.

    Series first when both kinds are asked for: that is where the shelf is
    furthest from complete, and a series costs more crawl time per title, so it
    should never be the half that runs out of budget.

    Each position is *claimed* (``attempted_at`` stamped) before any work starts.
    Stamping only afterwards meant a crawl killed by a time limit left its
    position untouched at the head of the queue, so every following pass picked
    the same title, was killed on the same title, and the shelf stopped moving.

    ``budget_seconds`` is a wall-clock budget checked between positions, so a
    pass run as a Celery task ends itself with ``status: 'budget'`` well before
    the task's time limit instead of being killed mid-title.
    """
    from celery.exceptions import SoftTimeLimitExceeded

    from apps.catalog.completeness import publish_blockers
    from apps.catalog.tmdb import configured_tmdb_client
    from apps.catalog.top_catalog import (
        _crawl_movie_links,
        _crawl_series_links,
        _has_download_links,
        _publish_movie,
        _publish_series,
        _suppress_provider_publish_signals,
    )

    ImdbChartEntry, _, _ = _models()
    link_entries()
    stats = {'status': 'ok', 'attempted': 0, 'imported': 0, 'crawled': 0, 'published': 0, 'gaps': {}}
    started = time.monotonic()
    client = None
    retry_after = timedelta(hours=max(0.0, retry_hours))
    ordered = sorted(kinds, key=lambda kind: 0 if kind == 'series' else 1)
    queue = [entry for kind in ordered for entry in _incomplete_entries(kind, retry_after=retry_after)[:limit]]

    with _suppress_provider_publish_signals():
        for entry in queue[:limit]:
            if budget_seconds and time.monotonic() - started >= budget_seconds:
                stats['status'] = 'budget'
                break
            stats['attempted'] += 1
            obj = entry.target
            gap = ''
            ImdbChartEntry.objects.filter(pk=entry.pk).update(
                attempted_at=timezone.now(), attempts=entry.attempts + 1,
            )
            try:
                if obj is None:
                    client = client or configured_tmdb_client()
                    obj, gap = _import_from_tmdb(entry, client)
                    if obj is not None:
                        stats['imported'] += 1
                        setattr(entry, entry.kind, obj)
                if obj is not None:
                    if not _has_download_links(obj):
                        crawl = _crawl_movie_links if entry.kind == 'movie' else _crawl_series_links
                        crawl(obj, replace=False, resolve_english=True)
                        stats['crawled'] += 1
                        obj.refresh_from_db()
                    if not _has_download_links(obj):
                        gap = GAP_NO_SOURCE
                    else:
                        blockers = publish_blockers(obj)
                        if blockers and obj.tmdb_id:
                            # Usually a Persian title/summary or artwork that TMDB
                            # has since gained. One details call, then re-judge.
                            client = client or configured_tmdb_client()
                            _refresh_from_tmdb(obj, client)
                            obj.refresh_from_db()
                            blockers = publish_blockers(obj)
                        if blockers:
                            # Same bar as every other title: never publish a card
                            # without a Persian title or a real IMDb score.
                            gap = ('metadata:' + ','.join(blockers))[:64]
                        else:
                            publish = _publish_movie if entry.kind == 'movie' else _publish_series
                            publish(obj)
                            obj.refresh_from_db()
                            if obj.is_published:
                                stats['published'] += 1
                            else:
                                # Refused by the live media probe; it logs why.
                                gap = GAP_NOT_PUBLISHED
            except SoftTimeLimitExceeded:
                # Not "one bad title": the task is out of time. Record why this
                # position stalled, then let the task end — swallowing this would
                # carry on into the hard limit and get the worker killed.
                ImdbChartEntry.objects.filter(pk=entry.pk).update(
                    gap_reason=GAP_CRAWL_TIMEOUT,
                    **({entry.kind: obj} if obj is not None else {}),
                )
                raise
            except Exception as exc:  # one bad title must not end the lane
                logger.exception('top250 completion failed for %s #%s %s', entry.kind, entry.rank, entry.imdb_id)
                gap = GAP_IMPORT_FAILED
                stats.setdefault('errors', []).append(f'{entry.kind}#{entry.rank}: {str(exc)[:160]}')
            ImdbChartEntry.objects.filter(pk=entry.pk).update(
                gap_reason=gap,
                attempted_at=timezone.now(),
                **({entry.kind: obj} if obj is not None else {}),
            )
            if gap:
                stats['gaps'][gap] = stats['gaps'].get(gap, 0) + 1
            if delay:
                time.sleep(delay)

    link_entries()
    stats['coverage'] = coverage()
    return stats
