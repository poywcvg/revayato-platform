"""Hot titles: what people are watching this week, made watchable first.

Every other lane in the importer is driven by what a *provider* lists (the
Film2Media/Dornatv/Kargadan walks) or by a TMDB ``popularity`` number frozen on
the row the day it was imported. Neither says what is hot *now*: a title that was
a hit three years ago still outranks this week's release in every "popular" queue,
and a trending film that the providers list on page 30 waits for the deep walk.

This module is the missing signal, in three parts:

* :func:`refresh_hot_chart` builds a ranked chart per kind from TMDB's live
  feeds (trending today, trending this week, now playing, releases of the last
  weeks), fused by reciprocal rank with a small bonus for recency, and stores it
  in the shared cache. No model, no migration: the chart is disposable and
  rebuilt every couple of hours, and a TMDB outage keeps the previous one.
* :func:`complete_hot_titles` walks the chart hottest first and does whatever
  each title is missing — the same import → multi-provider crawl → publish-gate
  path the IMDb Top 250 lane uses. Bounded per call, claimed before work, never
  deletes a row.
* :func:`hot_order` / :func:`hot_first` put the same chart in front of every
  other queue (draft source hunt, playback-source crawl, subtitle extraction,
  link refresh), so the whole pipeline agrees on what comes first: hot titles by
  chart rank, then the newest releases, then stored popularity.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

KINDS = ('movie', 'series')

CHART_CACHE_KEY = 'catalog:hot:chart:v1'
#: Kept far longer than the refresh interval so a TMDB outage never empties it.
CHART_CACHE_TTL = 3 * 24 * 60 * 60
ATTEMPT_KEY = 'catalog:hot:attempt:{kind}:{tmdb_id}'

#: Sort value for a title that is not on the chart.
MISS_RANK = 1_000_000
#: Reciprocal-rank-fusion constant. 60 is the usual choice: position 1 and 10 of
#: one feed differ, but appearing in several feeds matters more.
RRF_K = 60
#: At most this much is added for a release that came out today, fading to 0.
RECENCY_WEIGHT = 0.35
RECENCY_HORIZON_DAYS = 365

#: TMDB TV genres no provider carries: News, Reality, Talk. Trending TV is full
#: of them, and every one would cost a three-provider crawl that cannot succeed.
SKIP_TV_GENRES = frozenset({10763, 10764, 10767})

GAP_TMDB_MISS = 'tmdb_miss'
GAP_IRANIAN = 'iranian'
GAP_NO_SOURCE = 'no_source'
GAP_NOT_PUBLISHED = 'not_published'
GAP_IMPORT_FAILED = 'import_failed'


def _models():
    from apps.catalog.models import Movie, Series

    return Movie, Series


def _setting(name: str, default):
    from django.conf import settings

    value = getattr(settings, name, default)
    return default if value in (None, '') else value


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

def _released_on(item: dict, kind: str) -> date | None:
    raw = str(item.get('release_date' if kind == 'movie' else 'first_air_date') or '')[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _recency_bonus(released: date | None, today: date) -> float:
    if released is None:
        return 0.0
    age = (today - released).days
    if age < 0:
        return 0.0
    return RECENCY_WEIGHT * max(0.0, 1.0 - age / RECENCY_HORIZON_DAYS)


def _admit(item: dict, kind: str, today: date, *, exclude_iranian: bool) -> dict | None:
    """A chart row for ``item``, or ``None`` when it can never become watchable here."""
    from apps.catalog.iranian import is_iranian_tmdb_details

    try:
        tmdb_id = int(item.get('id') or 0)
    except (TypeError, ValueError):
        return None
    if tmdb_id <= 0 or item.get('adult'):
        return None
    if exclude_iranian and is_iranian_tmdb_details(item):
        return None
    released = _released_on(item, kind)
    # Not out yet: there is nothing any provider could have. It joins the chart
    # on its release day, when it is also at its hottest.
    if released is None or released > today:
        return None
    if kind == 'series' and SKIP_TV_GENRES.intersection(item.get('genre_ids') or ()):
        return None
    title_key, original_key = ('title', 'original_title') if kind == 'movie' else ('name', 'original_name')
    return {
        'tmdb_id': tmdb_id,
        'title': str(item.get(title_key) or '')[:200],
        'original_title': str(item.get(original_key) or '')[:200],
        'released': released.isoformat(),
        'score': 0.0,
        'signals': [],
    }


def _feeds(client, kind: str, today: date, *, pages: int):
    """(label, weight, fetch) per TMDB feed. Today's trend weighs most."""
    if kind == 'movie':
        return (
            ('trending_day', 1.0, lambda: client.trending_movies(window='day', max_pages=1)),
            ('trending_week', 0.8, lambda: client.trending_movies(window='week', max_pages=pages)),
            ('now_playing', 0.6, lambda: client.now_playing_movies(max_pages=pages)),
            ('new_releases', 0.5, lambda: client.discover_movies(
                released_from=today - timedelta(days=60), released_until=today, max_pages=1,
            )),
        )
    return (
        ('trending_day', 1.0, lambda: client.trending_tv(window='day', max_pages=1)),
        ('trending_week', 0.8, lambda: client.trending_tv(window='week', max_pages=pages)),
        ('new_releases', 0.5, lambda: client.discover_tv(
            aired_from=today - timedelta(days=90), aired_until=today, max_pages=1,
        )),
    )


def build_hot_chart(client=None, *, size: int | None = None, pages: int | None = None,
                    today: date | None = None) -> dict:
    """Rank this week's titles per kind from TMDB's live feeds. Stores nothing.

    A feed that fails is recorded under ``feeds`` and skipped; the others still
    rank. Positions inside a feed count before any filtering, so a title keeps
    the rank TMDB gave it even when rows above it are skipped.
    """
    from apps.catalog.tmdb import configured_tmdb_client

    client = client or configured_tmdb_client()
    today = today or timezone.localdate()
    size = max(1, int(size or _setting('CATALOG_HOT_CHART_SIZE', 80)))
    pages = max(1, int(pages or _setting('CATALOG_HOT_TMDB_PAGES', 2)))
    exclude_iranian = bool(_setting('CATALOG_EXCLUDE_IRANIAN', True))

    chart = {'built_at': timezone.now().isoformat(), 'feeds': {}}
    for kind in KINDS:
        scored: dict[int, dict] = {}
        for label, weight, fetch in _feeds(client, kind, today, pages=pages):
            try:
                rows = list(fetch())
            except Exception as exc:  # one dead feed must not empty the chart
                logger.warning('hot chart feed %s:%s failed: %s', kind, label, str(exc)[:160])
                chart['feeds'][f'{kind}:{label}'] = 'error'
                continue
            chart['feeds'][f'{kind}:{label}'] = len(rows)
            for position, item in enumerate(rows, start=1):
                row = _admit(item, kind, today, exclude_iranian=exclude_iranian)
                if row is None:
                    continue
                slot = scored.setdefault(row['tmdb_id'], row)
                slot['score'] += weight * RRF_K / (RRF_K + position)
                if label not in slot['signals']:
                    slot['signals'].append(label)
        for slot in scored.values():
            bonus = _recency_bonus(date.fromisoformat(slot['released']), today)
            slot['score'] = round(slot['score'] + bonus, 4)
        ranked = sorted(scored.values(), key=lambda row: (-row['score'], row['tmdb_id']))[:size]
        for rank, row in enumerate(ranked, start=1):
            row['rank'] = rank
        chart[kind] = ranked
    return chart


def get_hot_chart() -> dict | None:
    from django.core.cache import cache

    try:
        chart = cache.get(CHART_CACHE_KEY)
    except Exception:  # cache down: every queue falls back to recency order
        logger.warning('hot chart cache read failed', exc_info=True)
        return None
    return chart if isinstance(chart, dict) else None


def chart_age_hours(chart: dict | None = None) -> float | None:
    from django.utils.dateparse import parse_datetime

    chart = chart if chart is not None else get_hot_chart()
    built = parse_datetime(str((chart or {}).get('built_at') or ''))
    if built is None:
        return None
    return (timezone.now() - built).total_seconds() / 3600


def refresh_hot_chart(*, max_age_hours: float | None = None, force: bool = False, client=None) -> dict:
    """Rebuild the stored chart when it is older than ``max_age_hours``.

    A kind whose feeds all failed keeps its previous ranking: trends move over
    days, so an old chart is far better than none.
    """
    from django.core.cache import cache

    if max_age_hours is None:
        max_age_hours = float(_setting('CATALOG_HOT_CHART_MAX_AGE_HOURS', 2))
    current = get_hot_chart()
    age = chart_age_hours(current)
    if not force and age is not None and age < max_age_hours:
        return {'status': 'fresh', 'age_hours': round(age, 2)}

    chart = build_hot_chart(client)
    if not any(chart.get(kind) for kind in KINDS):
        # Nothing new at all: leave the stored chart (and its age) alone, so the
        # next tick tries again instead of treating a re-stamped copy as fresh.
        return {'status': 'empty', 'feeds': chart['feeds']}
    for kind in KINDS:
        if not chart.get(kind) and current and current.get(kind):
            chart[kind] = current[kind]
            chart['feeds'][f'{kind}:kept_previous'] = len(current[kind])
    cache.set(CHART_CACHE_KEY, chart, timeout=CHART_CACHE_TTL)
    return {
        'status': 'refreshed',
        'movie': len(chart.get('movie') or []),
        'series': len(chart.get('series') or []),
        'feeds': chart['feeds'],
    }


def hot_rank_map(kind: str, chart: dict | None = None) -> dict[int, int]:
    """``{tmdb_id: rank}`` for ``kind`` ('movie' or 'series'); empty without a chart."""
    chart = chart if chart is not None else get_hot_chart()
    out = {}
    for row in (chart or {}).get(kind) or []:
        try:
            out[int(row['tmdb_id'])] = int(row['rank'])
        except (KeyError, TypeError, ValueError):
            continue
    return out


# ---------------------------------------------------------------------------
# Ordering shared by every queue
# ---------------------------------------------------------------------------

def _kind_of(model) -> str:
    return 'movie' if model.__name__ == 'Movie' else 'series'


def hot_order(qs, *, chart: dict | None = None):
    """Order a Movie/Series queryset hot-first.

    Chart titles by rank, then titles already out before unreleased ones, then
    newest release first, then stored popularity. Without a chart it is still
    newest-first, which is what the stale ``-popularity`` order never was.
    """
    from django.db.models import Case, F, IntegerField, Value, When
    from django.db.models.functions import Greatest

    kind = _kind_of(qs.model)
    ranks = hot_rank_map(kind, chart)
    if ranks:
        rank = Case(
            *[When(tmdb_id=tmdb_id, then=Value(position)) for tmdb_id, position in ranks.items()],
            default=Value(MISS_RANK),
            output_field=IntegerField(),
        )
    else:
        rank = Value(MISS_RANK, output_field=IntegerField())
    today = timezone.localdate()
    if kind == 'movie':
        future = Case(When(release_date__gt=today, then=Value(1)), default=Value(0), output_field=IntegerField())
        recency = F('release_date').desc(nulls_last=True)
    else:
        future = Case(When(start_year__gt=today.year, then=Value(1)), default=Value(0), output_field=IntegerField())
        # GREATEST ignores NULL on PostgreSQL: an airing show (no end_year) sorts
        # by its start, a returning one by its latest season year.
        recency = Greatest('start_year', 'end_year').desc(nulls_last=True)
    return qs.annotate(hot_rank_order=rank, hot_future_order=future).order_by(
        'hot_rank_order', 'hot_future_order', recency, '-popularity', '-id',
    )


def hot_priority_pks(qs, limit: int, *, recent_days: int = 120) -> list[tuple[int, int]]:
    """``(pk, chart_rank)`` of rows in ``qs`` that are hot or recent, hottest first.

    ``chart_rank`` is :data:`MISS_RANK` for a recent release that is not on the
    chart. For queues that keep their own rotation and only need a head.
    """
    from django.db.models import Q

    kind = _kind_of(qs.model)
    since = timezone.localdate() - timedelta(days=recent_days)
    if kind == 'movie':
        recent = Q(release_date__gte=since, release_date__lte=timezone.localdate())
    else:
        recent = Q(start_year__gte=since.year) | Q(end_year__gte=since.year)
    ordered = hot_order(qs).filter(Q(hot_rank_order__lt=MISS_RANK) | recent)
    return list(ordered.values_list('pk', 'hot_rank_order')[: max(1, int(limit))])


REFRESH_REST_KEY = 'catalog:hot:refresh-rest:{kind}:{pk}'


def hot_head(rows, kind: str, *, limit: int, share: float = 0.5, rest_hours: float = 6,
             recent_days: int = 120, chart: dict | None = None) -> list:
    """Put hot and recently released rows at the front of a refresh slice.

    At most ``limit * share`` rows go to the front, hottest first, and each one
    then rests for ``rest_hours`` — a new quality or episode lands within hours,
    and re-reading the same hot pages every round would only spend the provider
    budget. Everything else keeps the order it came in (the scripts' stale-first
    rotation), so the long tail is still reached every few rounds.
    """
    from django.core.cache import cache

    ranks = hot_rank_map(kind, chart)
    today = timezone.localdate()
    cap = max(1, int(limit * share)) if limit else len(rows)
    candidates = []
    for index, obj in enumerate(rows):
        rank = ranks.get(int(getattr(obj, 'tmdb_id', 0) or 0), MISS_RANK)
        if rank < MISS_RANK or _is_recent(obj, kind, today, recent_days):
            candidates.append((rank, index, obj))
    candidates.sort(key=lambda item: (item[0], item[1]))
    head = []
    for _, _, obj in candidates:
        if len(head) >= cap:
            break
        try:
            due = cache.add(REFRESH_REST_KEY.format(kind=kind, pk=obj.pk), '1',
                            timeout=max(60, int(rest_hours * 3600)))
        except Exception:
            due = True
        if due:
            head.append(obj)
    chosen = {id(obj) for obj in head}
    return head + [obj for obj in rows if id(obj) not in chosen]


def _is_recent(obj, kind: str, today: date, days: int) -> bool:
    if kind == 'movie':
        released = getattr(obj, 'release_date', None)
        return bool(released and today - timedelta(days=days) <= released <= today)
    latest = max(int(getattr(obj, 'start_year', 0) or 0), int(getattr(obj, 'end_year', 0) or 0))
    return (today - timedelta(days=days)).year <= latest <= today.year


def hot_first(rows, kind: str, *, recent_days: int = 120, chart: dict | None = None) -> list:
    """Stable re-order of an already-selected list: chart titles by rank, then
    recent releases, then everything else in the order it came in.

    For the refresh scripts, whose own order (stale-first rotation) must survive
    for the tail so every title is still reached.
    """
    ranks = hot_rank_map(kind, chart)
    today = timezone.localdate()

    def key(obj):
        rank = ranks.get(int(getattr(obj, 'tmdb_id', 0) or 0), MISS_RANK)
        return rank, 0 if _is_recent(obj, kind, today, recent_days) else 1

    return sorted(rows, key=key)


# ---------------------------------------------------------------------------
# Completion lane
# ---------------------------------------------------------------------------

def _is_watchable(obj) -> bool:
    from apps.catalog.top_catalog import _has_download_links

    return bool(obj and obj.is_published and _has_download_links(obj))


def _claim(kind: str, tmdb_id: int, retry_hours: float) -> bool:
    """Claim a title before any work, so a killed crawl never pins the queue head."""
    from django.core.cache import cache

    try:
        return bool(cache.add(
            ATTEMPT_KEY.format(kind=kind, tmdb_id=tmdb_id), '1',
            timeout=max(60, int(retry_hours * 3600)),
        ))
    except Exception:  # without a cache, fail toward importing
        return True


def _import_from_tmdb(kind: str, tmdb_id: int, client):
    """Create the catalog row for a hot title we do not hold. Never deletes."""
    from apps.catalog.ingestion import upsert_tmdb_movie, upsert_tmdb_series
    from apps.catalog.iranian import is_iranian_tmdb_details

    details = client.movie_details(tmdb_id) if kind == 'movie' else client.tv_details(tmdb_id)
    if not details or not details.get('id'):
        return None, GAP_TMDB_MISS
    if _setting('CATALOG_EXCLUDE_IRANIAN', True) and is_iranian_tmdb_details(details):
        return None, GAP_IRANIAN
    with transaction.atomic():
        if kind == 'movie':
            obj, *_ = upsert_tmdb_movie(details, auto_publish=False)
        else:
            obj, *_ = upsert_tmdb_series(details)
    return obj, ''


def coverage(chart: dict | None = None) -> dict:
    """Per kind: titles on the chart, held in the catalog, and actually watchable."""
    Movie, Series = _models()
    chart = chart if chart is not None else get_hot_chart()
    out = {}
    for kind, model in (('movie', Movie), ('series', Series)):
        ids = [int(row['tmdb_id']) for row in (chart or {}).get(kind) or []]
        held = list(model.objects.filter(tmdb_id__in=ids).only('id', 'tmdb_id', 'is_published', 'download_links'))
        out[kind] = {
            'total': len(ids),
            'in_catalog': len(held),
            'watchable': sum(1 for obj in held if _is_watchable(obj)),
        }
    return out


def complete_hot_titles(
    *,
    limit: int = 30,
    retry_hours: float = 6,
    delay: float = 1.0,
    budget_seconds: float | None = None,
    kinds: tuple[str, ...] = KINDS,
    chart: dict | None = None,
) -> dict:
    """Make up to ``limit`` more hot titles watchable, hottest first across kinds.

    Same bar as every other lane: a title is published only through the publish
    gate (Persian + English title, real IMDb score, live media probe). A title no
    provider carries yet stays a draft, where the next pass and the draft-source
    hunter (which also runs hot-first) retry it.
    """
    from celery.exceptions import SoftTimeLimitExceeded

    from apps.catalog.completeness import publish_blockers
    from apps.catalog.iranian import is_iranian_catalog_item
    from apps.catalog.tmdb import configured_tmdb_client
    from apps.catalog.top250 import _refresh_from_tmdb
    from apps.catalog.top_catalog import (
        _crawl_movie_links,
        _crawl_series_links,
        _has_download_links,
        _publish_movie,
        _publish_series,
        _suppress_provider_publish_signals,
    )

    Movie, Series = _models()
    chart = chart if chart is not None else (get_hot_chart() or {})
    stats = {
        'status': 'ok', 'considered': 0, 'watchable': 0, 'resting': 0, 'attempted': 0,
        'imported': 0, 'crawled': 0, 'published': 0, 'gaps': {},
    }
    queue = sorted(
        ((kind, row) for kind in kinds for row in chart.get(kind) or []),
        key=lambda pair: (-float(pair[1].get('score') or 0), int(pair[1].get('rank') or MISS_RANK)),
    )
    exclude_iranian = bool(_setting('CATALOG_EXCLUDE_IRANIAN', True))
    started = time.monotonic()
    client = None

    with _suppress_provider_publish_signals():
        for kind, row in queue:
            if stats['attempted'] >= limit:
                break
            if budget_seconds and time.monotonic() - started >= budget_seconds:
                stats['status'] = 'budget'
                break
            stats['considered'] += 1
            model = Movie if kind == 'movie' else Series
            tmdb_id = int(row['tmdb_id'])
            obj = model.objects.filter(tmdb_id=tmdb_id).first()
            if obj is not None and _is_watchable(obj):
                stats['watchable'] += 1
                continue
            if obj is not None and exclude_iranian and is_iranian_catalog_item(obj):
                continue
            if not _claim(kind, tmdb_id, retry_hours):
                stats['resting'] += 1
                continue
            stats['attempted'] += 1
            gap = ''
            try:
                if obj is None:
                    client = client or configured_tmdb_client()
                    obj, gap = _import_from_tmdb(kind, tmdb_id, client)
                    if obj is not None:
                        stats['imported'] += 1
                if obj is not None:
                    if not _has_download_links(obj):
                        crawl = _crawl_movie_links if kind == 'movie' else _crawl_series_links
                        crawl(obj, replace=False, resolve_english=True)
                        stats['crawled'] += 1
                        obj.refresh_from_db()
                    if not _has_download_links(obj):
                        gap = GAP_NO_SOURCE
                    else:
                        blockers = publish_blockers(obj)
                        if blockers and obj.tmdb_id:
                            client = client or configured_tmdb_client()
                            _refresh_from_tmdb(obj, client)
                            obj.refresh_from_db()
                            blockers = publish_blockers(obj)
                        if blockers:
                            gap = ('metadata:' + ','.join(blockers))[:64]
                        elif not obj.is_published:
                            (_publish_movie if kind == 'movie' else _publish_series)(obj)
                            obj.refresh_from_db()
                            if obj.is_published:
                                stats['published'] += 1
                            else:
                                gap = GAP_NOT_PUBLISHED  # refused by the live media probe
            except SoftTimeLimitExceeded:
                raise  # out of time: end the task, never ride into the hard limit
            except Exception as exc:  # one bad title must not end the lane
                logger.exception('hot title completion failed for %s tmdb=%s', kind, tmdb_id)
                gap = GAP_IMPORT_FAILED
                stats.setdefault('errors', []).append(f'{kind}:{tmdb_id}: {str(exc)[:160]}')
            if gap:
                stats['gaps'][gap] = stats['gaps'].get(gap, 0) + 1
            if delay:
                time.sleep(delay)

    stats['coverage'] = coverage(chart)
    return stats
