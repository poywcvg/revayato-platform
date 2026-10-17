"""Continuous Film2Media (myf2m) missing-title importer.

Walks the provider's own ``/movies/`` and ``/series/`` listings, crawls each detail
page for public CDN download/stream links, resolves the title to TMDB (IMDb id first,
then a title+year search), and creates only titles that are not already in the
Revayato catalog.

This is the listing-driven twin of :mod:`dornatv_import`: same checkpointed,
cancellable, budgeted shape, so the admin importer can run both providers inside a
single job instead of discovering from Dornatv alone.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from django.conf import settings
from django.db import transaction

from .dornatv_import import _save_checkpoint

logger = logging.getLogger(__name__)

# Movie cards are numeric permalinks (``/12345/slug/``); series live under
# ``/series/slug/``. Both listings paginate as ``/{root}/page/{n}/`` and answer
# 200 with zero cards once walked past the end.
#
# The host half is deliberately ``[^"/]+`` and not the configured domain. These
# patterns used to pin ``myf2m.info``; the provider moved to ``myf2ms.top`` and the
# listings began emitting absolute hrefs on the new host, so every tick matched zero
# cards, took the "walked past the final page" branch and reported ``status: ok``
# with ``listing_items: 0``. Nothing errored and ingestion stopped dead. Pinning the
# configured host instead would fail the same way, because the fetch follows
# redirects: the old domain still answers, and the page it returns is on the new one.
# The path shape is discriminating on its own (the only foreign links in either
# listing are social/CDN homepages, which have no ``/<id>/<slug>/`` shape), and a
# stray match costs one 404 — far cheaper than another silent outage.
MOVIE_ITEM_RE = re.compile(
    r'href="(?:https?://[^"/]+)?(?P<path>/(?P<id>\d+)/(?P<slug>[^"/]+)/)"',
    re.I,
)
SERIES_ITEM_RE = re.compile(
    r'href="(?:https?://[^"/]+)?(?P<path>/series/(?P<slug>[^"/]+)/)"',
    re.I,
)
IMDB_RE = re.compile(r'(tt\d{7,8})')
H1_RE = re.compile(r'<h1[^>]*>(?P<title>.*?)</h1>', re.I | re.S)
YEAR_RE = re.compile(r'\b((?:19|20)\d{2})\b')

DEFAULT_CHECKPOINT = '/app/media/myf2m_import_checkpoint.json'
# Paths already walked are remembered so later ticks never re-fetch them. The cap
# is generous because the two listings are finite (a few thousand pages total).
MAX_REMEMBERED_PATHS = 20000


def _strip_html(value: str) -> str:
    return re.sub(r'<[^>]+>', '', value or '').strip()


def _load_checkpoint(path: Path) -> dict:
    defaults = {
        'movie_page': 1,
        'series_page': 1,
        'done_movie_paths': [],
        'done_series_paths': [],
        'stats': {},
    }
    if not path.exists():
        return dict(defaults)
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return dict(defaults)
    if not isinstance(payload, dict):
        return dict(defaults)
    return {**defaults, **payload}


def _year_window(*, year_start: int | None, year_end: int | None) -> tuple[int, int]:
    """Inclusive year window walked newest → oldest (start >= end).

    The default upper bound follows the clock instead of a pinned year, so the
    importer keeps working next January without a code change.
    """
    from django.utils import timezone

    configured_hi = int(getattr(settings, 'MYF2M_IMPORT_YEAR_START', 0) or 0)
    start = int(year_start if year_start is not None else (configured_hi or timezone.now().year + 1))
    end = int(year_end if year_end is not None else getattr(settings, 'MYF2M_IMPORT_YEAR_END', 1970))
    if start < end:
        start, end = end, start
    return start, end


def _listing_path(root: str, page: int) -> str:
    return f'/{root}/' if page <= 1 else f'/{root}/page/{page}/'


def _page_meta(html: str, slug: str) -> dict:
    """Pull the identity signals a detail page carries: IMDb id, title, year."""
    imdb_ids = IMDB_RE.findall(html or '')
    heading = H1_RE.search(html or '')
    title = _strip_html(heading.group('title')) if heading else slug.replace('-', ' ')
    year_match = YEAR_RE.search(title) or YEAR_RE.search(slug)
    return {
        'imdb_id': (imdb_ids[0] if imdb_ids else '').lower(),
        'title': title,
        'year': int(year_match.group(1)) if year_match else None,
    }


def _resolve_tmdb_summary(client, *, content_type: str, imdb_id: str, title: str, year):
    """IMDb id is authoritative; fall back to a year-filtered title search."""
    if imdb_id:
        try:
            found = client.resolve_imdb_to_tmdb(imdb_id, content_type=content_type)
        except Exception:
            found = None
        if found and found.get('id'):
            return found
    query = YEAR_RE.sub('', title or '').strip(' -_–—')
    # Persian download-site headings prefix the Latin name ("دانلود فیلم X 2024").
    query = re.sub(r'^(?:دانلود\s+)?(?:فیلم|سریال|انیمیشن|مستند)\s+', '', query).strip()
    if not query:
        return None
    try:
        if content_type == 'series':
            payload = client.search_tv(query, page=1) or {}
        else:
            payload = client.search_movies(query, page=1) or {}
    except Exception:
        return None
    results = list((payload.get('results') if isinstance(payload, dict) else payload) or [])
    if not results:
        return None
    if year:
        date_key = 'first_air_date' if content_type == 'series' else 'release_date'
        allowed = {str(year), str(year - 1), str(year + 1)}
        for row in results[:8]:
            if str(row.get(date_key) or '')[:4] in allowed:
                return row
    return results[0]


def run_myf2m_missing_import(
    *,
    movies_limit: int | None = None,
    series_limit: int | None = None,
    checkpoint_path: str | None = None,
    budget_seconds: float | None = None,
    delay: float = 0.3,
    max_pages: int | None = None,
    dry_run: bool = False,
    queue_softsub: bool = True,
    year_start: int | None = None,
    year_end: int | None = None,
    strict_year_window: bool = False,
    should_cancel=lambda: False,
    on_progress=None,
) -> dict:
    """Import a batch of titles Film2Media carries but the catalog is missing.

    Walks the two listings from the page cursor stored in the checkpoint, so
    consecutive ticks keep moving forward instead of re-reading page 1. Titles
    already known by TMDB id or IMDb id are skipped without being touched.
    """
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
    from .providers.myf2m_parser import parse_download_links
    from .registry import get_connector

    movies_limit = max(0, int(
        movies_limit if movies_limit is not None
        else getattr(settings, 'MYF2M_IMPORT_MOVIES_PER_TICK', 8)
    ))
    series_limit = max(0, int(
        series_limit if series_limit is not None
        else getattr(settings, 'MYF2M_IMPORT_SERIES_PER_TICK', 4)
    ))
    max_pages = max(1, int(
        max_pages if max_pages is not None
        else getattr(settings, 'MYF2M_IMPORT_MAX_PAGES_PER_TICK', 12)
    ))
    delay = max(0.0, float(delay))
    # Same contract as the dornatv walk: end the tick before Celery's soft time
    # limit does, so the run returns a result instead of dying mid-page. The cursor
    # is persisted, so an early stop just means the next tick starts where this one
    # left off.
    tick_budget = float(
        budget_seconds if budget_seconds is not None
        else getattr(settings, 'MYF2M_IMPORT_BUDGET_SECONDS', 9 * 60)
    )
    started_at = time.monotonic()

    def out_of_time() -> bool:
        return tick_budget > 0 and (time.monotonic() - started_at) >= tick_budget

    year_hi, year_lo = _year_window(year_start=year_start, year_end=year_end)

    checkpoint = Path(checkpoint_path or getattr(settings, 'MYF2M_IMPORT_CHECKPOINT', DEFAULT_CHECKPOINT))
    state = _load_checkpoint(checkpoint)
    done_movie_paths = set(state.get('done_movie_paths') or [])
    done_series_paths = set(state.get('done_series_paths') or [])
    movie_page = max(1, int(state.get('movie_page') or 1))
    series_page = max(1, int(state.get('series_page') or 1))

    # Dedupe on ids only. Scanning every row's ``download_links`` JSON to collect
    # provider page paths costs hundreds of MB per tick on a catalog this size, and
    # the checkpoint already keeps visited paths out of the next walk.
    existing_movie_tmdb = set(Movie.objects.exclude(tmdb_id__isnull=True).values_list('tmdb_id', flat=True))
    existing_series_tmdb = set(Series.objects.exclude(tmdb_id__isnull=True).values_list('tmdb_id', flat=True))
    existing_movie_imdb = {
        str(v).strip().lower()
        for v in Movie.objects.exclude(imdb_id__isnull=True).exclude(imdb_id='').values_list('imdb_id', flat=True)
    }
    existing_series_imdb = {
        str(v).strip().lower()
        for v in Series.objects.exclude(imdb_id__isnull=True).exclude(imdb_id='').values_list('imdb_id', flat=True)
    }

    client = configured_tmdb_client()
    connector = get_connector('myf2m')
    auth = connector.validate_credentials()
    if not auth.ok:
        return {'status': 'unreachable', 'message': auth.message}

    stats = {
        'listing_pages': 0,
        'listing_items': 0,
        # Pages that returned real HTML but yielded no cards — see the walk.
        'unparsed_pages': 0,
        'budget_exhausted': False,
        'tried': 0,
        'movies_created': 0,
        'series_created': 0,
        'skipped_existing': 0,
        'skipped_seen': 0,
        'skipped_tmdb_miss': 0,
        'skipped_wrong_year': 0,
        'no_links': 0,
        'iranian': 0,
        'errors': 0,
        'softsub_queued': 0,
        'episodes_created': 0,
        'movie_page': movie_page,
        'series_page': series_page,
        'year_start': year_hi,
        'year_end': year_lo,
        'dry_run': bool(dry_run),
    }

    def progress(label: str) -> None:
        if on_progress is None:
            return
        try:
            on_progress(stats, label)
        except Exception:  # progress reporting must never abort an import
            logger.debug('myf2m import progress callback failed', exc_info=True)

    def persist() -> None:
        _save_checkpoint(checkpoint, {
            'movie_page': movie_page,
            'series_page': series_page,
            'done_movie_paths': sorted(done_movie_paths)[-MAX_REMEMBERED_PATHS:],
            'done_series_paths': sorted(done_series_paths)[-MAX_REMEMBERED_PATHS:],
            'year_start': year_hi,
            'year_end': year_lo,
            'stats': stats,
            'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        })

    def import_one(*, content_type: str, page_path: str, slug: str) -> str:
        """Import a single listing entry. Returns a short status for the stats."""
        is_series = content_type == 'series'
        try:
            response = connector._request('GET', page_path)
        except ProviderRateLimited:
            raise
        except Exception as exc:
            stats['errors'] += 1
            logger.info('myf2m detail fetch failed path=%s: %s', page_path, exc)
            return 'error'
        if response.status_code >= 400:
            stats['no_links'] += 1
            return 'http_error'
        html = response.text or ''

        # Links come from the page we already downloaded — never re-fetch it.
        try:
            crawled = parse_download_links(html, page_path=page_path)
        except ProviderImportError as exc:
            stats['no_links'] += 1
            logger.info('myf2m parse skip path=%s: %s', page_path, exc)
            return 'no_links'
        available = crawled.get('available_links') or []
        if not available:
            stats['no_links'] += 1
            return 'no_links'

        meta = _page_meta(html, slug)
        imdb_id = meta['imdb_id']
        known_imdb = existing_series_imdb if is_series else existing_movie_imdb
        if imdb_id and imdb_id in known_imdb:
            stats['skipped_existing'] += 1
            return 'existing'

        summary = _resolve_tmdb_summary(
            client, content_type=content_type, imdb_id=imdb_id,
            title=meta['title'], year=meta['year'],
        )
        if not summary or not summary.get('id'):
            stats['skipped_tmdb_miss'] += 1
            logger.info('myf2m tmdb miss path=%s title=%r imdb=%s', page_path, meta['title'], imdb_id)
            return 'tmdb_miss'
        tmdb_id = int(summary['id'])
        known_tmdb = existing_series_tmdb if is_series else existing_movie_tmdb
        model = Series if is_series else Movie
        if tmdb_id in known_tmdb or model.objects.filter(tmdb_id=tmdb_id).exists():
            known_tmdb.add(tmdb_id)
            stats['skipped_existing'] += 1
            return 'existing'

        date_key = 'first_air_date' if is_series else 'release_date'
        summary_year = str(summary.get(date_key) or '')[:4]
        if strict_year_window and summary_year.isdigit():
            if not (year_lo <= int(summary_year) <= year_hi):
                stats['skipped_wrong_year'] += 1
                return 'wrong_year'
        if dry_run:
            known_tmdb.add(tmdb_id)
            stats['series_created' if is_series else 'movies_created'] += 1
            return 'dry_run'

        try:
            details = client.tv_details(tmdb_id) if is_series else client.movie_details(tmdb_id)
        except Exception as exc:
            stats['errors'] += 1
            logger.info('myf2m tmdb details failed tmdb=%s: %s', tmdb_id, exc)
            return 'error'
        if is_iranian_tmdb_details(details):
            stats['iranian'] += 1
            return 'iranian'

        try:
            with transaction.atomic():
                if is_series:
                    obj, created = upsert_tmdb_series(details)
                else:
                    obj, created, _published, _skipped = upsert_tmdb_movie(details, auto_publish=False)
        except Exception as exc:
            stats['errors'] += 1
            logger.info('myf2m upsert failed tmdb=%s: %s', tmdb_id, exc)
            return 'error'
        known_tmdb.add(tmdb_id)
        if not created:
            # Raced with another importer — leave the existing row untouched.
            stats['skipped_existing'] += 1
            return 'existing'

        stamped = []
        for item in normalize_download_links(available):
            if isinstance(item, dict):
                row = dict(item)
                row.setdefault('page_path', crawled.get('page_path') or page_path)
                row.setdefault('source', 'myf2m')
                stamped.append(row)
        # The discovery crawler wrote whatever the page listed straight to the
        # row. Apply the same guards as the shared storage path: links proven to
        # belong to another title are rejected, links the CDN has deleted are
        # dropped. A title left with nothing is handled by the no_links path below.
        from apps.catalog.provider_import.link_apply import guard_provider_links

        stamped, _bad, _dead = guard_provider_links(obj, stamped)
        obj.download_links = coalesce_download_links([], stamped, replace=True)
        update_fields = ['download_links', 'updated_at']
        if imdb_id and not (obj.imdb_id or '').strip():
            obj.imdb_id = imdb_id
            update_fields.append('imdb_id')
        if not is_series:
            # Only a source that answered a probe, serves byte ranges and holds
            # a browser-decodable codec becomes the online playback link.
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
                logger.info('myf2m episode materialisation failed series=%s: %s', obj.pk, exc)

        (_publish_series if is_series else _publish_movie)(obj)
        if imdb_id:
            known_imdb.add(imdb_id)
        stats['series_created' if is_series else 'movies_created'] += 1
        if queue_softsub:
            try:
                queued = (
                    enqueue_series_softsub(obj.pk, force=False, episode_limit=80) if is_series
                    else enqueue_movie_softsub(obj.pk, force=False)
                )
            except Exception as exc:
                logger.info('myf2m softsub enqueue failed id=%s: %s', obj.pk, exc)
                queued = False
            if queued:
                stats['softsub_queued'] += 1
        logger.info(
            'myf2m import kept type=%s id=%s tmdb=%s links=%s path=%s',
            content_type, obj.pk, tmdb_id, len(obj.download_links or []), page_path,
        )
        return 'kept'

    def walk(*, content_type: str, root: str, item_re, done_paths: set, keep_limit: int,
             head_pages: int = 0) -> None:
        """Walk one listing from its stored cursor until the keep budget is spent.

        With ``head_pages`` the walk instead reads only the first N pages and leaves
        the cursor alone. New titles land on page 1, and the deep cursor needs a
        full lap of the archive (~7 ticks) to come back round to it.
        """
        nonlocal movie_page, series_page
        if keep_limit <= 0:
            return
        is_series = content_type == 'series'
        kept_key = 'series_created' if is_series else 'movies_created'
        label = 'سریال' if is_series else 'فیلم'
        start_kept = stats[kept_key]
        page = 1 if head_pages else (series_page if is_series else movie_page)
        page_cap = head_pages or max_pages
        pages_walked = 0

        def set_cursor(value: int) -> None:
            nonlocal movie_page, series_page
            if head_pages:
                return
            if is_series:
                series_page = value
            else:
                movie_page = value
            stats['series_page' if is_series else 'movie_page'] = value

        while pages_walked < page_cap and stats[kept_key] - start_kept < keep_limit:
            if should_cancel():
                return
            if out_of_time():
                stats['budget_exhausted'] = True
                persist()
                return
            listing = _listing_path(root, page)
            try:
                response = connector._request('GET', listing)
            except ProviderRateLimited as exc:
                logger.warning('myf2m listing rate-limited path=%s: %s', listing, exc)
                return
            except Exception as exc:
                logger.info('myf2m listing failed path=%s: %s', listing, exc)
                return
            if response.status_code >= 400:
                logger.info('myf2m listing http=%s path=%s', response.status_code, listing)
                return
            stats['listing_pages'] += 1
            pages_walked += 1

            entries: list[tuple[str, str]] = []
            seen_on_page: set[str] = set()
            for match in item_re.finditer(response.text or ''):
                path = match.group('path')
                if path in seen_on_page:
                    continue
                seen_on_page.add(path)
                entries.append((path, match.group('slug')))
            if not entries:
                # Walked past the final page: rewind so the next tick re-reads the
                # front of the listing, where newly published titles appear.
                #
                # This branch is also where a broken parser goes to hide. When the
                # provider moved to myf2ms.top the item patterns still pinned the old
                # host, so every page matched nothing, landed here, and the tick
                # reported ``status: ok`` with ``listing_items: 0`` — no error, no
                # alert, ingestion simply stopped for hours.
                #
                # Page 1 is the tell. Walking past the end is normal on page 40; it is
                # never legitimate on the front page of a listing that carries the
                # provider's whole catalogue. Zero items there means we can no longer
                # read the markup, not that the provider has no titles. Size is the
                # obvious alternative signal and a far worse one — this site answers a
                # past-the-end page with 48 KB of chrome against 121 KB for a real
                # one, so any byte threshold is tuned to today's template.
                if page <= 1:
                    stats['unparsed_pages'] += 1
                    logger.warning(
                        'myf2m listing parsed zero items from page 1 path=%s http=%s bytes=%s — '
                        'the item pattern no longer matches this markup; ingestion is stalled',
                        listing, response.status_code, len(response.text or ''),
                    )
                set_cursor(1)
                return
            stats['listing_items'] += len(entries)

            finished_page = True
            for path, slug in entries:
                if should_cancel() or stats[kept_key] - start_kept >= keep_limit:
                    # Leave the cursor on this page; ``done_paths`` keeps the items
                    # already handled from being fetched twice.
                    finished_page = False
                    break
                if path in done_paths:
                    stats['skipped_seen'] += 1
                    continue
                done_paths.add(path)
                stats['tried'] += 1
                progress(f'{label}: {slug}')
                try:
                    outcome = import_one(content_type=content_type, page_path=path, slug=slug)
                    if outcome == 'error':
                        # A network or TMDB hiccup is not a verdict on the title;
                        # remembering it would skip the title for good.
                        done_paths.discard(path)
                except ProviderRateLimited as exc:
                    # Retry this path on the next tick rather than burning it.
                    done_paths.discard(path)
                    logger.warning('myf2m rate-limited on %s: %s', path, exc)
                    persist()
                    return
                except Exception as exc:
                    stats['errors'] += 1
                    logger.exception('myf2m import crashed on %s: %s', path, exc)
                if delay:
                    time.sleep(delay)

            if finished_page:
                page += 1
                set_cursor(page)
            persist()
            if head_pages and not finished_page:
                return

    try:
        with _suppress_provider_publish_signals():
            head = max(0, int(getattr(settings, 'MYF2M_IMPORT_HEAD_PAGES', 2)))
            if head:
                if movie_page > head:
                    walk(content_type='movie', root='movies', item_re=MOVIE_ITEM_RE,
                         done_paths=done_movie_paths, keep_limit=movies_limit, head_pages=head)
                if series_page > head and not should_cancel():
                    walk(content_type='series', root='series', item_re=SERIES_ITEM_RE,
                         done_paths=done_series_paths, keep_limit=series_limit, head_pages=head)
            walk(content_type='movie', root='movies', item_re=MOVIE_ITEM_RE,
                 done_paths=done_movie_paths, keep_limit=movies_limit)
            if not should_cancel():
                walk(content_type='series', root='series', item_re=SERIES_ITEM_RE,
                     done_paths=done_series_paths, keep_limit=series_limit)
    finally:
        close = getattr(connector, 'close', None)
        if callable(close):
            close()
        persist()

    if stats['movies_created'] or stats['series_created']:
        try:
            from apps.catalog.cache import bump_catalog_cache_version
            bump_catalog_cache_version()
        except Exception:
            logger.debug('catalog cache bump failed after myf2m import', exc_info=True)

    stats['status'] = 'cancelled' if should_cancel() else 'ok'
    logger.info('myf2m missing-import done: %s', stats)
    return stats
