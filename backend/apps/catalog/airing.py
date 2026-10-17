"""The airing schedule (جدول پخش): real release dates, and the crawl that follows them.

Two halves:

* **Sync** — for every series still airing (and every movie near its digital
  release) ask TMDB for the real dates: each episode's ``air_date`` from the
  season listing, and a movie's *digital* release date (``release_dates`` type
  4, the day it can actually be downloaded — not the theatrical premiere). One
  :class:`~apps.catalog.models.AiringEntry` per release, refreshed on a cadence,
  so a date TMDB moves is moved here too. Nothing is guessed: a release without
  a dated source row is not on the schedule.

* **Hunt** — from the morning a release is due (Tehran time), the providers are
  crawled for it on a widening backoff (every 2 h for two days, every 6 h for a
  week, daily for three weeks) until the episode/movie is on the site. The crawl
  is the same guarded merge every lane uses, so the new episode is materialised,
  identity-checked and published by the normal path; a draft title is published
  only through the normal publish gates.

The weekly schedule the site shows (:func:`build_weekly_schedule` in
``schedule.py``) reads these rows, so each card can say whether its release is
upcoming, aired and being fetched, or already watchable.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta
from datetime import time as dtime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date

logger = logging.getLogger(__name__)

TEHRAN = ZoneInfo('Asia/Tehran')

#: Releases this far back / ahead are kept on the schedule.
WINDOW_BACK_DAYS = 21
WINDOW_AHEAD_DAYS = 60
#: The first hunt of a release starts this many hours into its air date, Tehran
#: time. US evening broadcasts land 03:30–06:30 Tehran the next day, streaming
#: drops (Netflix, 00:00 PT) around 10:30, so the first two-hourly checks cover
#: both.
HUNT_START_HOURS = 6
#: Backoff: (release age below, wait between hunts).
HUNT_BACKOFF = (
    (timedelta(hours=48), timedelta(hours=2)),
    (timedelta(days=7), timedelta(hours=6)),
    (timedelta(days=21), timedelta(hours=24)),
)
#: How often one title's TMDB dates are re-read.
SERIES_RESYNC = timedelta(hours=12)
SERIES_RESYNC_SOON = timedelta(hours=6)   # an episode due within 3 days
MOVIE_RESYNC = timedelta(hours=24)

_DIGITAL = 4
_DIGITAL_REGIONS = ('US', 'GB', 'CA', 'AU')
_STUB_TITLE = re.compile(r'^\s*(?:قسمت|اپیزود|episode|ep\.?)\s*[\d۰-۹]+\s*$', re.I)


def _setting(name: str, default):
    return getattr(settings, name, default)


def today_tehran() -> date:
    """The schedule's "today": the viewers are in Iran, the server runs on UTC."""
    return timezone.now().astimezone(TEHRAN).date()


def first_hunt_at(air_date: date) -> datetime:
    start = datetime.combine(air_date, dtime(0, 0), TEHRAN)
    return start + timedelta(hours=int(_setting('AIRING_HUNT_START_HOURS', HUNT_START_HOURS)))


def next_hunt_after(air_date: date, now: datetime) -> datetime | None:
    """When to look again for a release that is still missing; ``None`` = give up."""
    age = now - first_hunt_at(air_date)
    for limit, wait in HUNT_BACKOFF:
        if age < limit:
            return now + wait
    return None


def _models():
    from .models import AiringEntry, Episode, Movie, Series

    return AiringEntry, Episode, Movie, Series


# --------------------------------------------------------------------------- #
# Availability — is the release on the site?
# --------------------------------------------------------------------------- #

def _movie_available(movie) -> bool:
    from .top_catalog import _has_download_links

    return bool(movie.is_published and _has_download_links(movie))


def _published_episode(series, season_number: int, episode_number: int):
    _, Episode, _, _ = _models()
    if not series.is_published:
        return None
    return (
        Episode.objects.filter(
            season__series=series, season__season_number=season_number,
            episode_number=episode_number, is_published=True, season__is_published=True,
        )
        .select_related('season')
        .first()
    )


def entry_available(entry) -> bool:
    if entry.kind == entry.Kind.MOVIE:
        return _movie_available(entry.movie)
    return _published_episode(entry.series, entry.season_number, entry.episode_number) is not None


def _mark_available(entry, now: datetime) -> None:
    entry.status = entry.Status.AVAILABLE
    entry.available_at = entry.available_at or now
    entry.next_hunt_at = None
    if entry.kind == entry.Kind.EPISODE:
        _complete_episode_row(entry)


def _complete_episode_row(entry) -> None:
    """Give the materialised episode the date and name TMDB already told us."""
    episode = _published_episode(entry.series, entry.season_number, entry.episode_number)
    if episode is None:
        return
    fields = []
    if episode.air_date != entry.air_date:
        episode.air_date = entry.air_date
        fields.append('air_date')
    name = (entry.title or '').strip()
    if name and not _STUB_TITLE.match(name) and _STUB_TITLE.match(_plain(episode.title)):
        episode.title = name[:255]
        fields.append('title')
    if fields:
        episode.save(update_fields=[*fields, 'updated_at'])


def _plain(text: str) -> str:
    return re.sub(r'[‎‏‪-‮⁦-⁩﻿]', '', str(text or ''))


def _initial_state(entry, now: datetime) -> None:
    """Status and first hunt time for a new (or re-dated) release."""
    if entry_available(entry):
        _mark_available(entry, now)
        return
    start = first_hunt_at(entry.air_date)
    if start > now:
        entry.status = entry.Status.UPCOMING
        entry.next_hunt_at = start
        return
    wait = next_hunt_after(entry.air_date, now)
    if wait is None:
        entry.status = entry.Status.MISSED
        entry.next_hunt_at = None
    else:
        entry.status = entry.Status.WAITING
        entry.next_hunt_at = now


# --------------------------------------------------------------------------- #
# Sync — real dates from TMDB
# --------------------------------------------------------------------------- #

def _window(today: date) -> tuple[date, date]:
    return (
        today - timedelta(days=int(_setting('AIRING_WINDOW_BACK_DAYS', WINDOW_BACK_DAYS))),
        today + timedelta(days=int(_setting('AIRING_WINDOW_AHEAD_DAYS', WINDOW_AHEAD_DAYS))),
    )


def _sync_key(kind: str, pk: int) -> str:
    return f'airing:synced:{kind}:{pk}'


def tracked_series(today: date):
    """Series that can still have a dated episode inside the window."""
    _, _, _, Series = _models()
    back, _ = _window(today)
    return (
        Series.objects.filter(tmdb_id__isnull=False)
        .filter(
            Q(status__in=[Series.Status.ONGOING, Series.Status.UPCOMING])
            | Q(source_metadata__last_air_date__gte=back.isoformat())
            | Q(airing_entries__air_date__gte=back)
        )
        .distinct()
        .order_by('-is_published', '-popularity', 'id')
    )


def tracked_movies(today: date):
    """Movies whose digital release can fall inside the window (theatrical ± months)."""
    _, _, Movie, _ = _models()
    back, ahead = _window(today)
    return (
        Movie.objects.filter(tmdb_id__isnull=False)
        .exclude(publication_status=Movie.PublicationStatus.ARCHIVED)
        .filter(
            Q(release_date__gte=today - timedelta(days=150), release_date__lte=ahead)
            | Q(airing_entries__air_date__gte=back)
        )
        .distinct()
        .order_by('-is_published', '-popularity', 'id')
    )


def _episode_release_type(item: dict) -> str:
    kind = str(item.get('episode_type') or '').strip().lower()
    if int(item.get('episode_number') or 0) == 1:
        return 'premiere'
    return kind if kind in {'finale', 'mid_season'} else 'standard'


def _network(details: dict) -> str:
    for item in details.get('networks') or []:
        name = str((item or {}).get('name') or '').strip()
        if name:
            return name[:80]
    return ''


def sync_series(series, client, *, today: date | None = None, now: datetime | None = None) -> dict:
    """Upsert this series' dated episodes inside the window. One TMDB call + one per live season."""
    AiringEntry, _, _, _ = _models()
    today = today or today_tehran()
    now = now or timezone.now()
    back, ahead = _window(today)
    details = client._request(f'tv/{int(series.tmdb_id)}', {})
    network = _network(details)

    seasons: set[int] = set()
    for key in ('next_episode_to_air', 'last_episode_to_air'):
        item = details.get(key) or {}
        aired = parse_date(str(item.get('air_date') or ''))
        if item.get('season_number') is not None and aired and back <= aired <= ahead:
            seasons.add(int(item['season_number']))
    for item in details.get('seasons') or []:
        aired = parse_date(str((item or {}).get('air_date') or ''))
        if aired and back <= aired <= ahead and item.get('season_number') is not None:
            seasons.add(int(item['season_number']))
    seasons.discard(0)  # specials: not what a weekly schedule means

    stats = {'seasons': len(seasons), 'created': 0, 'updated': 0, 'dropped': 0}
    for season_number in sorted(seasons):
        payload = client.tv_season_details(series.tmdb_id, season_number)
        seen: set[int] = set()
        for item in payload.get('episodes') or []:
            if not isinstance(item, dict) or item.get('episode_number') is None:
                continue
            aired = parse_date(str(item.get('air_date') or ''))
            number = int(item['episode_number'])
            if not aired:
                continue
            seen.add(number)
            if not back <= aired <= ahead:
                continue
            values = {
                'air_date': aired,
                'release_type': _episode_release_type(item),
                'title': str(item.get('name') or '').strip()[:255],
                'still_url': client.image_url(item.get('still_path'), 'w300')[:500],
                'network': network,
                'runtime_minutes': int(item['runtime']) if item.get('runtime') else None,
                'synced_at': now,
            }
            outcome = _upsert(
                AiringEntry, now,
                lookup={'kind': AiringEntry.Kind.EPISODE, 'series': series,
                        'season_number': season_number, 'episode_number': number},
                values=values,
            )
            stats[outcome] = stats.get(outcome, 0) + 1
        # An episode TMDB no longer lists (renumbered, pulled) leaves the schedule.
        stale = AiringEntry.objects.filter(
            kind=AiringEntry.Kind.EPISODE, series=series, season_number=season_number,
        ).exclude(episode_number__in=seen).exclude(status=AiringEntry.Status.AVAILABLE)
        stats['dropped'] += stale.exclude(status=AiringEntry.Status.DROPPED).update(
            status=AiringEntry.Status.DROPPED, next_hunt_at=None, updated_at=now,
        )
    cache.set(_sync_key('series', series.pk), now.timestamp(), None)
    return stats


def digital_release_date(payload: dict) -> date | None:
    """TMDB ``release_dates`` → the digital (type 4) date: US first, else the earliest."""
    by_region: dict[str, date] = {}
    for region in payload.get('results') or []:
        code = str((region or {}).get('iso_3166_1') or '')
        for item in region.get('release_dates') or []:
            if int((item or {}).get('type') or 0) != _DIGITAL:
                continue
            day = parse_date(str(item.get('release_date') or '')[:10])
            if day and (code not in by_region or day < by_region[code]):
                by_region[code] = day
    for code in _DIGITAL_REGIONS:
        if code in by_region:
            return by_region[code]
    return min(by_region.values()) if by_region else None


def sync_movie(movie, client, *, today: date | None = None, now: datetime | None = None) -> str:
    AiringEntry, _, _, _ = _models()
    today = today or today_tehran()
    now = now or timezone.now()
    back, ahead = _window(today)
    payload = client._request(f'movie/{int(movie.tmdb_id)}/release_dates', {})
    digital = digital_release_date(payload)
    cache.set(_sync_key('movie', movie.pk), now.timestamp(), None)
    existing = AiringEntry.objects.filter(kind=AiringEntry.Kind.MOVIE, movie=movie).first()
    if digital is None or not back <= digital <= ahead:
        if existing and existing.status != AiringEntry.Status.AVAILABLE and (
            digital is None or digital > ahead
        ):
            existing.status = AiringEntry.Status.DROPPED
            existing.next_hunt_at = None
            existing.save(update_fields=['status', 'next_hunt_at', 'updated_at'])
            return 'dropped'
        return 'outside'
    return _upsert(
        AiringEntry, now,
        lookup={'kind': AiringEntry.Kind.MOVIE, 'movie': movie},
        values={'air_date': digital, 'release_type': 'digital', 'synced_at': now},
    )


def _upsert(model, now: datetime, *, lookup: dict, values: dict) -> str:
    entry = model.objects.filter(**lookup).first()
    if entry is None:
        entry = model(**lookup, **values)
        _initial_state(entry, now)
        try:
            with transaction.atomic():
                entry.save()
        except IntegrityError:  # a parallel sync won the race; its row is as good
            return 'updated'
        return 'created'
    redated = entry.air_date != values['air_date']
    for field, value in values.items():
        setattr(entry, field, value)
    if entry.status == model.Status.DROPPED or (redated and entry.status != model.Status.AVAILABLE):
        entry.hunt_attempts = 0
        _initial_state(entry, now)
    entry.save()
    return 'updated'


def _due(kind: str, obj, now: datetime, today: date) -> bool:
    last = cache.get(_sync_key(kind, obj.pk))
    if last is None:
        return True
    age = now.timestamp() - float(last)
    if kind == 'movie':
        return age >= MOVIE_RESYNC.total_seconds()
    AiringEntry, _, _, _ = _models()
    soon = AiringEntry.objects.filter(
        series=obj, air_date__gte=today, air_date__lte=today + timedelta(days=3),
    ).exists()
    return age >= (SERIES_RESYNC_SOON if soon else SERIES_RESYNC).total_seconds()


def sync_schedule(*, budget_seconds: float | None = None, limit: int | None = None, client=None) -> dict:
    """One bounded pass: re-read the dates of every tracked title that is due."""
    from .iranian import is_iranian_catalog_item
    from .tmdb import TMDBError, configured_tmdb_client

    budget = float(budget_seconds if budget_seconds is not None else _setting('AIRING_SYNC_BUDGET_SECONDS', 240))
    limit = int(limit if limit is not None else _setting('AIRING_SYNC_TITLES_PER_TICK', 400))
    started = time.monotonic()
    today, now = today_tehran(), timezone.now()
    exclude_iranian = bool(_setting('CATALOG_EXCLUDE_IRANIAN', True))
    stats = {'status': 'ok', 'series': 0, 'movies': 0, 'created': 0, 'updated': 0, 'dropped': 0, 'errors': 0}
    client = client or configured_tmdb_client()

    def rows():
        for obj in tracked_series(today).only('id', 'tmdb_id', 'is_published', 'title', 'original_title', 'status'):
            yield 'series', obj
        for obj in tracked_movies(today).only('id', 'tmdb_id', 'is_published', 'title', 'original_title'):
            yield 'movie', obj

    done = 0
    for kind, obj in rows():
        if done >= limit:
            stats['status'] = 'limit'
            break
        if time.monotonic() - started >= budget:
            stats['status'] = 'budget'
            break
        if not _due(kind, obj, now, today):
            continue
        if exclude_iranian and is_iranian_catalog_item(obj):
            cache.set(_sync_key(kind, obj.pk), now.timestamp(), None)
            continue
        done += 1
        try:
            if kind == 'series':
                result = sync_series(obj, client, today=today, now=now)
                stats['series'] += 1
                for key in ('created', 'updated', 'dropped'):
                    stats[key] += result.get(key, 0)
            else:
                outcome = sync_movie(obj, client, today=today, now=now)
                stats['movies'] += 1
                if outcome in stats:
                    stats[outcome] += 1
        except TMDBError as exc:
            stats['errors'] += 1
            if getattr(exc, 'status_code', None) == 404:
                cache.set(_sync_key(kind, obj.pk), now.timestamp(), None)
            logger.info('airing sync %s %s: %s', kind, obj.pk, exc)
        except Exception:
            stats['errors'] += 1
            logger.exception('airing sync %s %s failed', kind, obj.pk)
    if stats['created'] or stats['dropped']:
        _bump_cache()
    return stats


# --------------------------------------------------------------------------- #
# Hunt — crawl for what is due
# --------------------------------------------------------------------------- #

def _bump_cache() -> None:
    try:
        from .cache import bump_catalog_cache_version

        bump_catalog_cache_version()
    except Exception:
        logger.debug('airing: cache bump failed', exc_info=True)


def _crawl(target, providers: list[str]) -> str:
    from .models import Movie
    from .provider_import.exceptions import ProviderImportError
    from .provider_import.multi_provider_crawl import (
        crawl_catalog_downloads_for_movie,
        crawl_catalog_downloads_for_series,
    )

    try:
        if isinstance(target, Movie):
            result = crawl_catalog_downloads_for_movie(
                movie=target, replace=False, queue_softsub_extract=True, providers=providers,
            )
        else:
            result = crawl_catalog_downloads_for_series(
                series=target, replace=False, queue_softsub_extract=True, providers=providers,
            )
    except ProviderImportError as exc:
        return f'not_found:{getattr(exc, "code", "") or exc}'[:200]
    return f"crawled:{result.get('imported_count', 0)}"


def _publish_if_ready(target) -> str:
    """A draft that now has the release goes live — through the normal gates only."""
    from .completeness import publish_blockers
    from .models import Movie
    from .top_catalog import _has_download_links, _publish_movie, _publish_series

    if target.is_published or not _has_download_links(target):
        return ''
    if isinstance(target, Movie) and target.publication_status == Movie.PublicationStatus.ARCHIVED:
        return 'archived'
    blockers = publish_blockers(target)
    if blockers:
        return 'blocked:' + ','.join(blockers)
    (_publish_movie if isinstance(target, Movie) else _publish_series)(target)
    target.refresh_from_db()
    return 'published' if target.is_published else 'media_unverified'


def hunt(*, budget_seconds: float | None = None, max_titles: int | None = None) -> dict:
    """Crawl for releases that are due and not on the site yet. Bounded; resumable."""
    from celery.exceptions import SoftTimeLimitExceeded

    from .provider_import.source_fill import wanted_providers
    from .top_catalog import _suppress_provider_publish_signals

    AiringEntry, _, _, _ = _models()
    budget = float(budget_seconds if budget_seconds is not None else _setting('AIRING_HUNT_BUDGET_SECONDS', 240))
    max_titles = int(max_titles if max_titles is not None else _setting('AIRING_HUNT_TITLES_PER_TICK', 6))
    started = time.monotonic()
    now = timezone.now()
    stats = {'status': 'ok', 'promoted': 0, 'already_there': 0, 'crawled': 0,
             'found': 0, 'published': 0, 'missed': 0, 'titles': 0}

    # 1. Free pass: other lanes (discovery, source fill) often land a release
    #    first. Catch those without a request, and move due upcoming rows to
    #    waiting.
    open_rows = AiringEntry.objects.filter(
        status__in=[AiringEntry.Status.UPCOMING, AiringEntry.Status.WAITING, AiringEntry.Status.MISSED],
        air_date__gte=_window(today_tehran())[0] - timedelta(days=14),
        air_date__lte=today_tehran() + timedelta(days=1),
    ).select_related('series', 'movie')
    changed = False
    for entry in open_rows:
        if entry_available(entry):
            _mark_available(entry, now)
            entry.save()
            stats['already_there'] += 1
            changed = True
        elif entry.status == AiringEntry.Status.UPCOMING and entry.next_hunt_at and entry.next_hunt_at <= now:
            entry.status = AiringEntry.Status.WAITING
            entry.save(update_fields=['status', 'updated_at'])
            stats['promoted'] += 1

    # 2. Crawl what is due, newest release first; one crawl per title covers all
    #    of its due episodes.
    due = list(
        AiringEntry.objects.filter(status=AiringEntry.Status.WAITING, next_hunt_at__lte=now)
        .select_related('series', 'movie')
        .order_by('-air_date', 'next_hunt_at')
    )
    groups: dict[tuple, list] = {}
    for entry in due:
        groups.setdefault((entry.kind, entry.series_id or entry.movie_id), []).append(entry)

    providers, _blocker = wanted_providers()
    if not providers:
        return {**stats, 'status': 'no_providers', 'due': len(due)}

    with _suppress_provider_publish_signals():
        for entries in groups.values():
            if stats['titles'] >= max_titles:
                stats['status'] = 'limit'
                break
            if time.monotonic() - started >= budget:
                stats['status'] = 'budget'
                break
            target = entries[0].target
            stats['titles'] += 1
            try:
                result = _crawl(target, providers)
                stats['crawled'] += 1
                target.refresh_from_db()
                published = _publish_if_ready(target)
                if published == 'published':
                    stats['published'] += 1
                if published:
                    result = f'{result};{published}'
            except SoftTimeLimitExceeded:
                raise
            except Exception as exc:
                logger.exception('airing hunt failed for %s', entries[0])
                result = f'error:{exc}'[:200]
            now = timezone.now()
            for entry in entries:
                # Share the refreshed title: a series published just now must
                # count for every episode in this group, not only the first.
                if entry.kind == AiringEntry.Kind.MOVIE:
                    entry.movie = target
                else:
                    entry.series = target
                entry.hunt_attempts += 1
                entry.last_hunt_at = now
                entry.last_result = result[:200]
                if entry_available(entry):
                    _mark_available(entry, now)
                    stats['found'] += 1
                    changed = True
                else:
                    wait = next_hunt_after(entry.air_date, now)
                    if wait is None:
                        entry.status = AiringEntry.Status.MISSED
                        entry.next_hunt_at = None
                        stats['missed'] += 1
                    else:
                        entry.next_hunt_at = wait
                entry.save()
    if changed or stats['published']:
        _bump_cache()
    stats['due'] = len(due)
    return stats


def status_summary() -> dict:
    """Counts for ops/admin: what the schedule holds and what the hunter is doing."""
    from django.db.models import Count

    AiringEntry, _, _, _ = _models()
    today = today_tehran()
    rows = AiringEntry.objects.filter(air_date__gte=today - timedelta(days=7), air_date__lte=today + timedelta(days=7))
    by_status = dict(rows.values_list('status').annotate(n=Count('id')))
    return {
        'today': today.isoformat(),
        'this_fortnight': by_status,
        'due_now': AiringEntry.objects.filter(
            status=AiringEntry.Status.WAITING, next_hunt_at__lte=timezone.now(),
        ).count(),
        'total': AiringEntry.objects.exclude(status=AiringEntry.Status.DROPPED).count(),
    }
