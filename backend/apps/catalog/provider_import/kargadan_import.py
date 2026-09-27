"""Always-on Kargadan discovery: import titles the catalog is missing, refresh the rest.

Kargadan's ``wp-sitemap`` is the discovery source. It is public, lists every movie
and series page with a ``lastmod``, and every page URL *is* the IMDb id — so a
tick knows exactly which titles are new, which changed since it last looked, and
which have not moved, without walking a single listing page.

One tick:

1. Read the sitemap (≈10 requests) and store it as the inventory that lets every
   other Kargadan crawl skip titles the site does not carry.
2. Stop early, without touching a detail page, when there is no signed-in session
   (download links are shown only to a signed-in account; see
   :mod:`.providers.kargadan`). The tick still *completes*, so the watchdog does not
   restart a lane that is waiting on an operator, not broken.
3. Newest ``lastmod`` first: create titles the catalog lacks (same TMDB, Iranian,
   link-guard and publish path as the Film2Media walk), then merge Kargadan links
   into catalog titles whose page changed since the last visit.

The checkpoint remembers each page's ``lastmod`` once its outcome is final, so a
page is fetched again only when Kargadan edits it — new links, a new episode.
Outcomes that may change without an edit (VIP-locked, transient errors) are parked
for ``KARGADAN_IMPORT_RETRY_HOURS`` instead.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path

from django.conf import settings
from django.db import transaction

from .dornatv_import import _save_checkpoint

logger = logging.getLogger(__name__)

DEFAULT_CHECKPOINT = '/app/media/kargadan_import_checkpoint.json'

# Codes that mean "the session cannot read links" — every later page would say the
# same, so the tick stops instead of spending the budget re-learning it.
SESSION_CODES = {'kargadan_login_required', 'kargadan_session_missing'}
# Final for this ``lastmod``: only an edit on Kargadan can change the answer.
FINAL_CODES = {'kargadan_page_missing', 'kargadan_links_empty', 'kargadan_identity_mismatch'}


def _load_checkpoint(path: Path) -> dict:
    defaults = {'seen': {}, 'deferred': {}, 'stats': {}}
    if not path.exists():
        return dict(defaults)
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return dict(defaults)
    if not isinstance(payload, dict):
        return dict(defaults)
    merged = {**defaults, **payload}
    for key in ('seen', 'deferred'):
        if not isinstance(merged.get(key), dict):
            merged[key] = {}
    return merged


def _entry_key(entry: dict) -> str:
    return f"{entry['content_type']}:{entry['imdb_id']}"


def _now() -> datetime:
    return datetime.now(dt_timezone.utc)


def _deferred_active(deferred: dict, key: str, *, retry_hours: float) -> bool:
    raw = deferred.get(key)
    if not raw:
        return False
    try:
        parked = datetime.fromisoformat(str(raw))
    except ValueError:
        return False
    if parked.tzinfo is None:
        parked = parked.replace(tzinfo=dt_timezone.utc)
    return _now() - parked < timedelta(hours=retry_hours)


def pending_entries(entries: list[dict], *, seen: dict, deferred: dict, retry_hours: float) -> list[dict]:
    """Sitemap rows whose page changed since the last final visit, newest first."""
    out = []
    for entry in entries:
        key = _entry_key(entry)
        if key in seen and seen[key] == (entry.get('lastmod') or ''):
            continue
        if _deferred_active(deferred, key, retry_hours=retry_hours):
            continue
        out.append(entry)
    out.sort(key=lambda e: e.get('lastmod') or '', reverse=True)
    return out


def run_kargadan_missing_import(
    *,
    movies_limit: int | None = None,
    series_limit: int | None = None,
    refresh_limit: int | None = None,
    checkpoint_path: str | None = None,
    budget_seconds: float | None = None,
    delay: float = 0.3,
    dry_run: bool = False,
    queue_softsub: bool = True,
    should_cancel=lambda: False,
    connector=None,
    tmdb_client=None,
) -> dict:
    """Run one Kargadan discovery tick. Always returns a stats dict."""
    from apps.catalog.ingestion import upsert_tmdb_movie, upsert_tmdb_series
    from apps.catalog.iranian import is_iranian_catalog_item, is_iranian_tmdb_details
    from apps.catalog.models import Movie, Series
    from apps.catalog.subtitle_extract import (
        apply_availability_flags,
        coalesce_download_links,
        ensure_episodes_from_download_links,
    )
    from apps.catalog.tasks import enqueue_movie_softsub, enqueue_series_softsub
    from apps.catalog.tmdb import configured_tmdb_client
    from apps.catalog.top_catalog import (
        _has_download_links,
        _publish_movie,
        _publish_series,
        _suppress_provider_publish_signals,
    )
    from config.public_urls import normalize_download_links

    from .exceptions import ProviderImportError, ProviderRateLimited
    from .kargadan_sync import (
        crawl_kargadan_downloads_for_movie,
        crawl_kargadan_downloads_for_series,
        ensure_kargadan_provider,
    )
    from .link_apply import apply_provider_download_links, guard_provider_links
    from .providers.kargadan import record_inventory, session_blocker
    from .registry import get_connector

    def setting_int(name: str, default: int) -> int:
        return max(0, int(getattr(settings, name, default) or 0))

    movies_limit = max(0, int(movies_limit if movies_limit is not None
                              else setting_int('KARGADAN_IMPORT_MOVIES_PER_TICK', 8)))
    series_limit = max(0, int(series_limit if series_limit is not None
                              else setting_int('KARGADAN_IMPORT_SERIES_PER_TICK', 4)))
    refresh_limit = max(0, int(refresh_limit if refresh_limit is not None
                               else setting_int('KARGADAN_IMPORT_REFRESH_PER_TICK', 12)))
    retry_hours = float(getattr(settings, 'KARGADAN_IMPORT_RETRY_HOURS', 24) or 24)
    tick_budget = float(budget_seconds if budget_seconds is not None
                        else getattr(settings, 'KARGADAN_IMPORT_BUDGET_SECONDS', 9 * 60))
    started_at = time.monotonic()

    def out_of_time() -> bool:
        return tick_budget > 0 and (time.monotonic() - started_at) >= tick_budget

    checkpoint = Path(checkpoint_path or getattr(settings, 'KARGADAN_IMPORT_CHECKPOINT', DEFAULT_CHECKPOINT))
    state = _load_checkpoint(checkpoint)
    seen: dict = dict(state['seen'])
    deferred: dict = dict(state['deferred'])

    stats = {
        'status': 'ok',
        'sitemap_movies': 0,
        'sitemap_series': 0,
        'pending': 0,
        'tried': 0,
        'movies_created': 0,
        'series_created': 0,
        'refreshed': 0,
        'merged_existing': 0,
        'skipped_tmdb_miss': 0,
        'no_links': 0,
        'page_missing': 0,
        'vip_required': 0,
        'iranian': 0,
        'errors': 0,
        'softsub_queued': 0,
        'episodes_created': 0,
        'budget_exhausted': False,
        'dry_run': bool(dry_run),
    }

    def persist() -> None:
        _save_checkpoint(checkpoint, {
            'seen': seen,
            'deferred': {k: v for k, v in deferred.items()
                         if _deferred_active(deferred, k, retry_hours=retry_hours)},
            'stats': stats,
            'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        })

    def settle(entry: dict) -> None:
        key = _entry_key(entry)
        seen[key] = entry.get('lastmod') or ''
        deferred.pop(key, None)

    def park(entry: dict) -> None:
        deferred[_entry_key(entry)] = _now().isoformat()

    owns_connector = connector is None
    if connector is None:
        ensure_kargadan_provider()
        connector = get_connector('kargadan')
    try:
        auth = connector.validate_credentials()
        if not auth.ok:
            stats.update(status='unreachable', message=auth.message)
            return stats
        try:
            entries = connector.sitemap_entries()
        except ProviderImportError as exc:
            stats.update(status='sitemap_failed', code=getattr(exc, 'code', ''), message=str(exc)[:200])
            logger.warning('provider_import.kargadan_sitemap_failed %s', exc)
            return stats
        record_inventory(entries)
        stats['sitemap_movies'] = sum(1 for e in entries if e['content_type'] == 'movie')
        stats['sitemap_series'] = sum(1 for e in entries if e['content_type'] == 'series')

        blocker = session_blocker()
        if blocker:
            stats.update(status='session_required', code=blocker)
            logger.warning(
                'provider_import.kargadan_session_missing code=%s — sign in to kargadanmovie.com in a '
                'browser and set KARGADAN_SESSION_COOKIE; discovery keeps the inventory fresh meanwhile',
                blocker,
            )
            return stats

        existing = {
            'movie': {
                str(v).strip().lower(): pk
                for pk, v in Movie.objects.exclude(imdb_id__isnull=True).exclude(imdb_id='')
                .values_list('pk', 'imdb_id')
            },
            'series': {
                str(v).strip().lower(): pk
                for pk, v in Series.objects.exclude(imdb_id__isnull=True).exclude(imdb_id='')
                .values_list('pk', 'imdb_id')
            },
        }
        pending = pending_entries(entries, seen=seen, deferred=deferred, retry_hours=retry_hours)
        stats['pending'] = len(pending)
        client = tmdb_client or configured_tmdb_client()

        def stop_for_session(code: str) -> None:
            stats.update(status='session_expired', code=code)
            logger.warning(
                'provider_import.kargadan_session_expired code=%s — the configured browser session no '
                'longer reads links; sign in again and replace KARGADAN_SESSION_COOKIE', code,
            )

        def create_one(entry: dict) -> str:
            is_series = entry['content_type'] == 'series'
            imdb_id = entry['imdb_id']
            crawled = connector.crawl_download_links(imdb_id, content_type=entry['content_type'])
            if crawled.get('imdb_id') and crawled['imdb_id'] != imdb_id:
                raise ProviderImportError('Kargadan page identity mismatch.', code='kargadan_identity_mismatch')
            available = crawled.get('available_links') or []
            if not available:
                raise ProviderImportError(crawled.get('message') or 'no links',
                                          code=crawled.get('code') or 'kargadan_links_empty')

            summary = None
            try:
                summary = client.resolve_imdb_to_tmdb(imdb_id, content_type=entry['content_type'])
            except Exception as exc:
                logger.info('kargadan tmdb lookup failed imdb=%s: %s', imdb_id, exc)
            if not summary or not summary.get('id'):
                stats['skipped_tmdb_miss'] += 1
                return 'tmdb_miss'
            tmdb_id = int(summary['id'])
            model = Series if is_series else Movie

            rows = []
            for item in normalize_download_links(available):
                if isinstance(item, dict):
                    row = dict(item)
                    row.setdefault('page_path', crawled.get('page_path') or '')
                    row.setdefault('source', 'kargadan')
                    rows.append(row)

            twin = model.objects.filter(tmdb_id=tmdb_id).first()
            if twin is not None:
                # Same title (TMDB resolved it from the IMDb id) stored without an
                # IMDb id. Merge the links rather than creating a duplicate.
                if not dry_run:
                    apply_provider_download_links(
                        twin, rows, replace=False, queue_softsub_extract=queue_softsub,
                        empty_code='kargadan_links_empty',
                        empty_message='No usable Kargadan download links after normalization.',
                    )
                stats['merged_existing'] += 1
                return 'merged'
            if dry_run:
                stats['series_created' if is_series else 'movies_created'] += 1
                return 'dry_run'

            details = client.tv_details(tmdb_id) if is_series else client.movie_details(tmdb_id)
            if is_iranian_tmdb_details(details):
                stats['iranian'] += 1
                return 'iranian'
            with transaction.atomic():
                if is_series:
                    obj, created = upsert_tmdb_series(details)
                else:
                    obj, created, _published, _skipped = upsert_tmdb_movie(details, auto_publish=False)
            if not created:
                stats['merged_existing'] += 1
                return 'raced'

            rows, _bad, _dead = guard_provider_links(obj, rows)
            obj.download_links = coalesce_download_links([], rows, replace=True)
            update_fields = ['download_links', 'updated_at']
            if not (obj.imdb_id or '').strip():
                obj.imdb_id = imdb_id
                update_fields.append('imdb_id')
            if not is_series:
                from apps.catalog import playback_gate

                _choice, gate_fields = playback_gate.gate_links(obj, obj.download_links or [])
                update_fields.extend(gate_fields)
            update_fields.extend(apply_availability_flags(obj, obj.download_links))
            obj.save(update_fields=list(dict.fromkeys(update_fields)))

            obj.refresh_from_db()
            if is_iranian_catalog_item(obj) or not _has_download_links(obj):
                reason = 'iranian' if is_iranian_catalog_item(obj) else 'no_links'
                obj.delete()
                stats[reason] += 1
                return reason
            if is_series:
                try:
                    stats['episodes_created'] += int(ensure_episodes_from_download_links(obj) or 0)
                except Exception as exc:
                    logger.info('kargadan episode materialisation failed series=%s: %s', obj.pk, exc)
            (_publish_series if is_series else _publish_movie)(obj)
            existing[entry['content_type']][imdb_id] = obj.pk
            stats['series_created' if is_series else 'movies_created'] += 1
            if queue_softsub:
                try:
                    queued = (enqueue_series_softsub(obj.pk, force=False, episode_limit=80) if is_series
                              else enqueue_movie_softsub(obj.pk, force=False))
                except Exception as exc:
                    logger.info('kargadan softsub enqueue failed id=%s: %s', obj.pk, exc)
                    queued = False
                if queued:
                    stats['softsub_queued'] += 1
            logger.info('kargadan import kept type=%s id=%s tmdb=%s imdb=%s links=%s',
                        entry['content_type'], obj.pk, tmdb_id, imdb_id, len(obj.download_links or []))
            return 'kept'

        def refresh_one(entry: dict, pk: int) -> str:
            if dry_run:
                stats['refreshed'] += 1
                return 'dry_run'
            if entry['content_type'] == 'series':
                series = Series.objects.filter(pk=pk).first()
                if series is None:
                    return 'gone'
                crawl_kargadan_downloads_for_series(series=series, replace=False,
                                                    queue_softsub_extract=queue_softsub)
            else:
                movie = Movie.objects.filter(pk=pk).first()
                if movie is None:
                    return 'gone'
                crawl_kargadan_downloads_for_movie(movie=movie, replace=False,
                                                   queue_softsub_extract=queue_softsub)
            stats['refreshed'] += 1
            return 'refreshed'

        remaining = {'movie': movies_limit, 'series': series_limit, 'refresh': refresh_limit}
        with _suppress_provider_publish_signals():
            for entry in pending:
                if should_cancel():
                    stats['status'] = 'cancelled'
                    break
                if out_of_time():
                    stats['budget_exhausted'] = True
                    break
                if not any(remaining.values()):
                    break
                pk = existing[entry['content_type']].get(entry['imdb_id'])
                bucket = 'refresh' if pk else entry['content_type']
                if remaining[bucket] <= 0:
                    continue
                remaining[bucket] -= 1
                stats['tried'] += 1
                try:
                    outcome = refresh_one(entry, pk) if pk else create_one(entry)
                except ProviderRateLimited as exc:
                    logger.warning('kargadan rate-limited on %s: %s', entry['imdb_id'], exc)
                    stats['status'] = 'rate_limited'
                    break
                except ProviderImportError as exc:
                    code = getattr(exc, 'code', '') or ''
                    if code in SESSION_CODES:
                        stop_for_session(code)
                        break
                    if code == 'kargadan_unreachable':
                        stats.update(status='unreachable', message=str(exc)[:200])
                        break
                    if code in FINAL_CODES:
                        stats['page_missing' if code == 'kargadan_page_missing' else 'no_links'] += 1
                        settle(entry)
                    else:
                        # VIP-locked or a failed crawl: may change without a page edit.
                        stats['vip_required' if code == 'kargadan_vip_required' else 'errors'] += 1
                        park(entry)
                    logger.info('kargadan skip %s %s: %s (%s)', entry['content_type'], entry['imdb_id'], exc, code)
                except Exception as exc:
                    stats['errors'] += 1
                    park(entry)
                    logger.exception('kargadan import crashed on %s: %s', entry['imdb_id'], exc)
                else:
                    if outcome != 'raced':
                        settle(entry)
                if stats['tried'] % 5 == 0:
                    persist()
                if delay:
                    time.sleep(delay)
    finally:
        if owns_connector:
            close = getattr(connector, 'close', None)
            if callable(close):
                close()
        persist()

    if stats['movies_created'] or stats['series_created'] or stats['refreshed'] or stats['merged_existing']:
        try:
            from apps.catalog.cache import bump_catalog_cache_version
            bump_catalog_cache_version()
        except Exception:
            logger.debug('catalog cache bump failed after kargadan import', exc_info=True)
    logger.info('kargadan discovery tick done: %s', stats)
    return stats
