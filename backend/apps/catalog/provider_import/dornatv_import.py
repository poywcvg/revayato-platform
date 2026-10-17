"""Continuous Dornatv missing-title importer.

Walks WP REST listings on dornatv.com, crawls detail pages for FA+EN titles and
public CDN download/stream links, resolves TMDB metadata, and creates only
titles that are not already in the Revayato catalog.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)


def _coverage_ok(links) -> tuple[bool, dict]:
    from apps.catalog.subtitle_extract import (
        canonicalize_download_links,
        download_links_imply_dub,
        download_links_imply_hardsub,
        download_links_imply_softsub,
        download_links_imply_subtitle,
    )

    normalized, _ = canonicalize_download_links(links)
    has_links = False
    for item in normalized or []:
        if not isinstance(item, dict):
            continue
        if str(item.get('url') or '').strip() or str(item.get('key') or '').strip():
            has_links = True
            break
    has_dub = download_links_imply_dub(normalized)
    has_soft = download_links_imply_softsub(normalized)
    has_hard = download_links_imply_hardsub(normalized)
    has_sub = download_links_imply_subtitle(normalized)
    cov = {
        'has_links': has_links,
        'has_dub': has_dub,
        'has_softsub': has_soft,
        'has_hardsub': has_hard,
        'has_sub': has_sub,
        'has_both': has_dub and has_sub,
        'link_count': sum(
            1 for item in (normalized or [])
            if isinstance(item, dict) and (str(item.get('url') or '').strip() or str(item.get('key') or '').strip())
        ),
    }
    return bool(has_links), cov


def _stamp_page_path(links, page_path: str) -> list[dict]:
    stamped = []
    for item in links or []:
        if isinstance(item, dict):
            row = dict(item)
            row.setdefault('page_path', page_path)
            row.setdefault('source', 'dornatv')
            stamped.append(row)
    return stamped


class _DonePaths(dict):
    """Detail pages already handled, oldest first.

    The checkpoint used to keep ``sorted(paths)[-5000:]``: the 5,000
    alphabetically *last* paths, not the most recent. Once the movie set passed
    5,000 every tick dropped a different alphabetical slice, and the dropped
    pages were crawled again the next time the walk met them, then dropped
    again: an endless re-crawl that spent the provider's rate budget on titles
    already handled. Insertion order keeps the cap about age instead.
    """

    def add(self, path: str) -> None:
        self[path] = None

    def recent(self, cap: int) -> list[str]:
        return list(self)[-cap:] if cap > 0 else list(self)


def _load_checkpoint(path: Path) -> dict:
    defaults = {
        'done_movie_paths': [],
        'done_series_paths': [],
        'movie_page': 1,
        'series_page': 1,
        'current_year': None,
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


def _save_checkpoint(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def _year_window(*, year_start: int | None, year_end: int | None) -> tuple[int, int]:
    """Inclusive year window walked newest → oldest (start >= end).

    The upper bound follows the clock when unset, so the walk keeps covering the
    newest releases next January without a code change.
    """
    from django.utils import timezone

    configured_hi = int(getattr(settings, 'DORNATV_IMPORT_YEAR_START', 0) or 0)
    start = int(year_start if year_start is not None else (configured_hi or timezone.now().year + 1))
    end = int(year_end if year_end is not None else getattr(settings, 'DORNATV_IMPORT_YEAR_END', 1970))
    if start < end:
        start, end = end, start
    return start, end


def _resolve_tmdb(client, *, content_type: str, title_en: str, year, imdb_id: str = ''):
    if imdb_id:
        try:
            hit = client.resolve_imdb_to_tmdb(imdb_id, content_type=content_type)
            if hit and hit.get('id'):
                return hit
        except Exception as exc:
            logger.info('dornatv tmdb imdb resolve failed %s: %s', imdb_id, exc)
    query = (title_en or '').strip()
    if not query:
        return None
    try:
        if content_type == 'series':
            payload = client.search_tv(query, first_air_year=year)
            key_year = 'first_air_date'
        else:
            payload = client.search_movies(query, year=year)
            key_year = 'release_date'
    except Exception as exc:
        logger.info('dornatv tmdb search failed %r: %s', query, exc)
        return None
    results = payload.get('results') or []
    if not results:
        return None
    if year:
        for row in results:
            date = str(row.get(key_year) or '')
            if date.startswith(str(year)):
                return row
            # year field sometimes present
            if str(row.get('year') or '') == str(year):
                return row
    return results[0]


def run_dornatv_missing_import(
    *,
    movies_limit: int | None = None,
    series_limit: int | None = None,
    checkpoint_path: str | None = None,
    budget_seconds: float | None = None,
    delay: float = 0.2,
    dry_run: bool = False,
    queue_softsub: bool = True,
    year_start: int | None = None,
    year_end: int | None = None,
    strict_year_window: bool = False,
    should_cancel=lambda: False,
) -> dict:
    """Import a batch of missing Dornatv titles. Designed for Celery beat ticks.

    Walks release years from ``year_start`` (default: next calendar year) down to
    ``year_end``, creating only titles not already in the catalog (TMDB/IMDb
    dedupe) with streamable download links + TMDB metadata.
    """
    from apps.catalog.ingestion import upsert_tmdb_movie, upsert_tmdb_series
    from apps.catalog.iranian import is_iranian_catalog_item, is_iranian_tmdb_details
    from apps.catalog.models import Movie, Series
    from apps.catalog.provider_import.dornatv_sync import ensure_dornatv_provider
    from apps.catalog.provider_import.exceptions import ProviderImportError, ProviderRateLimited
    from apps.catalog.provider_import.providers.dornatv_parser import (
        MOVIE_CATEGORY_IDS,
        SERIES_CATEGORY_IDS,
        parse_wp_rest_item,
    )
    from apps.catalog.provider_import.registry import get_connector
    from apps.catalog.subtitle_extract import (
        apply_availability_flags,
        coalesce_download_links,
        ensure_episodes_from_download_links,
    )
    from apps.catalog.tasks import enqueue_movie_softsub, enqueue_series_softsub
    from apps.catalog.top_catalog import (
        _has_download_links,
        _publish_movie,
        _publish_series,
        _suppress_provider_publish_signals,
        _version_coverage,
    )
    from apps.catalog.tmdb import configured_tmdb_client
    from config.public_urls import normalize_download_links

    ensure_dornatv_provider()
    movies_limit = int(movies_limit if movies_limit is not None else getattr(settings, 'DORNATV_IMPORT_MOVIES_PER_TICK', 12))
    series_limit = int(series_limit if series_limit is not None else getattr(settings, 'DORNATV_IMPORT_SERIES_PER_TICK', 6))
    year_hi, year_lo = _year_window(year_start=year_start, year_end=year_end)
    checkpoint = Path(checkpoint_path or getattr(settings, 'DORNATV_IMPORT_CHECKPOINT', '/app/media/dornatv_import_checkpoint.json'))
    state = _load_checkpoint(checkpoint)
    done_movie_paths = _DonePaths.fromkeys(state.get('done_movie_paths') or [])
    done_series_paths = _DonePaths.fromkeys(state.get('done_series_paths') or [])
    done_cap = int(getattr(settings, 'DORNATV_IMPORT_DONE_PATHS_CAP', 50000))
    movie_page = max(1, int(state.get('movie_page') or 1))
    series_page = max(1, int(state.get('series_page') or 1))

    # A tick must end on its own terms, before Celery's soft time limit ends it for
    # us. Without this every run walked until it was killed at 12 min, so it never
    # returned a result, never logged its stats, and reported failure to anything
    # watching — while the work it had done was real and already checkpointed. The
    # walk is resumable by design, so stopping early costs nothing: the next tick
    # picks up at the same page. Under the soft limit by a wide margin, because the
    # budget is only checked between items and one item can take tens of seconds.
    tick_budget = float(
        budget_seconds if budget_seconds is not None
        else getattr(settings, 'DORNATV_IMPORT_BUDGET_SECONDS', 9 * 60)
    )
    started_at = time.monotonic()

    def out_of_time() -> bool:
        return tick_budget > 0 and (time.monotonic() - started_at) >= tick_budget

    def _clamp_year(raw, fallback: int) -> int:
        try:
            value = int(raw if raw is not None else fallback)
        except (TypeError, ValueError):
            value = fallback
        if value > year_hi or value < year_lo:
            return year_hi
        return value

    # Separate year cursors so movies finishing the newest year do not skip series
    # still working through it.
    legacy_year = state.get('current_year')
    movie_year = _clamp_year(state.get('movie_year', legacy_year), year_hi)
    series_year = _clamp_year(state.get('series_year', legacy_year), year_hi)
    if state.get('movie_year') is None and legacy_year is None:
        movie_page = 1
    if state.get('series_year') is None and legacy_year is None:
        series_page = 1

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
    connector = get_connector('dornatv')
    auth = connector.validate_credentials()
    if not auth.ok:
        return {'status': 'unreachable', 'message': auth.message}

    stats = {
        'movies_kept': 0,
        'series_kept': 0,
        'movies_created': 0,
        'series_created': 0,
        'skipped_existing': 0,
        'skipped_no_titles': 0,
        'skipped_tmdb_miss': 0,
        'skipped_wrong_year': 0,
        'no_links': 0,
        'iranian': 0,
        'errors': 0,
        'softsub_queued': 0,
        'merged_existing': 0,
        'movie_page': movie_page,
        'series_page': series_page,
        'movie_year': movie_year,
        'series_year': series_year,
        'year_start': year_hi,
        'year_end': year_lo,
    }

    def persist():
        _save_checkpoint(checkpoint, {
            'done_movie_paths': done_movie_paths.recent(done_cap),
            'done_series_paths': done_series_paths.recent(done_cap),
            'movie_page': movie_page,
            'series_page': series_page,
            'movie_year': movie_year,
            'series_year': series_year,
            'modified_page': modified_page,
            'modified_cursor': modified_cursor,
            'newest_modified': newest_modified,
            # Keep legacy key for older readers / ops dashboards.
            'current_year': min(movie_year, series_year),
            'year_start': year_hi,
            'year_end': year_lo,
            'stats': stats,
            'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        })

    merge_budget = int(getattr(settings, 'DORNATV_IMPORT_MERGE_PER_TICK', 8))

    def _existing_obj(content_type: str, *, imdb_id: str = '', tmdb_id=None):
        model = Movie if content_type == 'movie' else Series
        if imdb_id:
            return model.objects.filter(imdb_id=imdb_id).first()
        if tmdb_id:
            return model.objects.filter(tmdb_id=tmdb_id).first()
        return None

    def _lacks_dornatv(obj) -> bool:
        from apps.catalog.provider_import.source_fill import providers_present

        return obj is not None and 'dornatv' not in providers_present(obj.download_links)

    def merge_into_existing(obj, crawled: dict, available, page_path: str) -> bool:
        """Add this page's links to a title the catalog already has from elsewhere.

        The walk used to crawl the page, see that the title existed, and throw the
        links away, so a title first imported from Film2Media never gained its
        Dornatv qualities. Merge only (existing links are kept), through the same
        identity check and guarded apply path the per-title crawl uses.
        """
        if dry_run or merge_budget <= stats['merged_existing'] or not _lacks_dornatv(obj):
            return False
        from apps.catalog.provider_import.dornatv_sync import _validate_dornatv_identity
        from apps.catalog.provider_import.link_apply import apply_provider_download_links

        try:
            _validate_dornatv_identity(obj, crawled)
            apply_provider_download_links(
                obj,
                _stamp_page_path(available, crawled.get('page_path') or page_path),
                replace=False,
                queue_softsub_extract=False,
                empty_code='dornatv_links_empty',
                empty_message='No usable Dornatv download links after normalization.',
            )
        except ProviderImportError as exc:
            logger.info('dornatv merge into existing %s skipped: %s', obj.pk, exc)
            return False
        except Exception:
            logger.exception('dornatv merge into existing %s failed', obj.pk)
            return False
        stats['merged_existing'] += 1
        return True

    # Detail pages fetched so far. The per-item politeness delay belongs to a
    # request, not to a listing row: most rows hit the done-set or the catalog
    # without touching the network, and sleeping after each of those turned a
    # 50-row page of already-handled titles into ~18 s of idling per page.
    fetches = 0

    def import_one(*, content_type: str, item: dict, expected_year: int, enforce_year: bool = True) -> str:
        nonlocal stats, fetches
        if should_cancel():
            return 'cancelled'
        parsed = parse_wp_rest_item(item, content_type=content_type)
        page_path = parsed['provider_item_id']
        done = done_movie_paths if content_type == 'movie' else done_series_paths
        existing_imdb = existing_movie_imdb if content_type == 'movie' else existing_series_imdb
        existing_tmdb = existing_movie_tmdb if content_type == 'movie' else existing_series_tmdb
        if page_path in done:
            return 'checkpoint'
        list_imdb = (parsed.get('imdb_id') or '').strip().lower()
        if list_imdb and list_imdb in existing_imdb:
            # Crawl it anyway when the catalog title has no Dornatv links yet, so
            # they can be merged below; otherwise there is nothing to do here.
            if dry_run or not _lacks_dornatv(_existing_obj(content_type, imdb_id=list_imdb)):
                stats['skipped_existing'] += 1
                done.add(page_path)
                return 'existing'
            if stats['merged_existing'] >= merge_budget:
                # Not checkpointed: the next pass that meets it can still merge.
                stats['skipped_existing'] += 1
                return 'existing'

        # A strict one-year run can reject taxonomy/modified-list rows before
        # downloading their much larger detail pages. TMDB is still verified
        # later for rows that claim the requested year.
        parsed_year = parsed.get('year')
        try:
            parsed_year_i = int(parsed_year) if parsed_year else None
        except (TypeError, ValueError):
            parsed_year_i = None
        if strict_year_window and parsed_year_i and not (year_lo <= parsed_year_i <= year_hi):
            stats['skipped_wrong_year'] += 1
            done.add(page_path)
            return 'wrong_year'

        fetches += 1
        try:
            crawled = connector.crawl_download_links(page_path, content_type=content_type)
        except ProviderRateLimited:
            stats['errors'] += 1
            time.sleep(15)
            return 'rate_limited'
        except ProviderImportError:
            stats['no_links'] += 1
            done.add(page_path)
            return 'no_links'
        except Exception:
            stats['errors'] += 1
            logger.exception('dornatv crawl failed for %s', page_path)
            return 'error'

        title_fa = str(crawled.get('title_fa') or parsed.get('title_fa') or '').strip()
        title_en = str(crawled.get('title_en') or parsed.get('title_en') or '').strip()
        if not (title_fa and title_en):
            stats['skipped_no_titles'] += 1
            done.add(page_path)
            return 'no_titles'

        available = crawled.get('available_links') or []
        ok, _cov = _coverage_ok(available)
        if not ok:
            stats['no_links'] += 1
            done.add(page_path)
            return 'no_links'

        imdb_id = (crawled.get('imdb_id') or list_imdb or '').strip().lower()
        if imdb_id and imdb_id in existing_imdb:
            stats['skipped_existing'] += 1
            merge_into_existing(_existing_obj(content_type, imdb_id=imdb_id), crawled, available, page_path)
            done.add(page_path)
            return 'existing'

        year = crawled.get('year') or parsed.get('year')
        try:
            year_i = int(year) if year else None
        except (TypeError, ValueError):
            year_i = None
        # When walking a release-year taxonomy, skip titles that clearly belong
        # elsewhere — but do NOT checkpoint them, so the real year can import later.
        # The modified-sweep normally accepts any year; it discovers
        # new/updated titles without walking release taxonomies.
        if (enforce_year or strict_year_window) and year_i and not (year_lo <= year_i <= year_hi):
            stats['skipped_wrong_year'] += 1
            return 'wrong_year'

        tmdb_summary = _resolve_tmdb(
            client,
            content_type=content_type,
            title_en=title_en,
            year=year_i or expected_year,
            imdb_id=imdb_id,
        )
        if not tmdb_summary or not tmdb_summary.get('id'):
            stats['skipped_tmdb_miss'] += 1
            done.add(page_path)
            return 'tmdb_miss'

        tmdb_id = int(tmdb_summary['id'])
        if tmdb_id in existing_tmdb:
            stats['skipped_existing'] += 1
            merge_into_existing(_existing_obj(content_type, tmdb_id=tmdb_id), crawled, available, page_path)
            done.add(page_path)
            return 'existing'

        if dry_run:
            if content_type == 'movie':
                stats['movies_kept'] += 1
            else:
                stats['series_kept'] += 1
            done.add(page_path)
            return 'dry_keep'

        try:
            if content_type == 'movie':
                details = client.movie_details(tmdb_id)
                if is_iranian_tmdb_details(details):
                    stats['iranian'] += 1
                    done.add(page_path)
                    return 'iranian'
                with transaction.atomic():
                    obj, created, _pub, _skip = upsert_tmdb_movie(details, auto_publish=False)
            else:
                details = client.tv_details(tmdb_id)
                if is_iranian_tmdb_details(details):
                    stats['iranian'] += 1
                    done.add(page_path)
                    return 'iranian'
                with transaction.atomic():
                    obj, created = upsert_tmdb_series(details)
        except Exception:
            stats['errors'] += 1
            logger.exception('dornatv upsert failed tmdb=%s', tmdb_id)
            return 'error'

        # Provider years can be missing or inaccurate. For a bounded one-year
        # import, verify the authoritative TMDB detail year before retaining the
        # newly-created row. This check intentionally leaves the normal rolling
        # importer unchanged unless strict_year_window=True.
        actual_year = getattr(obj, 'release_year', None) if content_type == 'movie' else getattr(obj, 'start_year', None)
        if strict_year_window and actual_year not in range(year_lo, year_hi + 1):
            if created:
                obj.delete()
            stats['skipped_wrong_year'] += 1
            done.add(page_path)
            return 'wrong_year'

        if not created:
            stats['skipped_existing'] += 1
            existing_tmdb.add(tmdb_id)
            merge_into_existing(obj, crawled, available, page_path)
            done.add(page_path)
            return 'existing'

        from apps.catalog.provider_import.dornatv_sync import _apply_dornatv_page_metadata
        _apply_dornatv_page_metadata(obj, crawled)

        normalized = normalize_download_links(available)
        # The discovery crawler used to store whatever the page listed. Run the
        # same guards the shared storage path uses — links that belong to another
        # title are rejected, links the CDN has deleted are dropped — before any
        # of this reaches a viewer.
        from apps.catalog.provider_import.link_apply import guard_provider_links

        normalized, _bad, _dead = guard_provider_links(obj, normalized)
        if not normalized:
            obj.delete()
            stats['no_links'] += 1
            done.add(page_path)
            return 'no_links'
        obj.download_links = _stamp_page_path(
            coalesce_download_links([], normalized, replace=True),
            crawled.get('page_path') or page_path,
        )
        if imdb_id and not obj.imdb_id:
            obj.imdb_id = imdb_id
        flag_fields = apply_availability_flags(obj, obj.download_links)
        update_fields = ['download_links', 'updated_at', *flag_fields]
        # Online playback gets a source that passed the tests, not the best
        # looking file name. See playback_gate.
        if hasattr(obj, 'video_url'):
            from apps.catalog import playback_gate

            _choice, gate_fields = playback_gate.gate_links(obj, obj.download_links or [])
            update_fields.extend(gate_fields)
        if imdb_id:
            update_fields.append('imdb_id')
        if content_type == 'movie' and not getattr(obj, 'quality', None):
            for item_link in obj.download_links or []:
                q = str(item_link.get('quality') or '').strip()
                if q:
                    obj.quality = q[:40]
                    update_fields.append('quality')
                    break
        obj.save(update_fields=list(dict.fromkeys(update_fields)))
        if content_type == 'series':
            ensure_episodes_from_download_links(obj)

        iranian = is_iranian_catalog_item(obj)
        if iranian or not _has_download_links(obj):
            obj.delete()
            stats['iranian' if iranian else 'no_links'] += 1
            done.add(page_path)
            return 'dropped'

        if content_type == 'movie':
            _publish_movie(obj)
            stats['movies_kept'] += 1
            stats['movies_created'] += 1
            existing_movie_tmdb.add(tmdb_id)
            if imdb_id:
                existing_movie_imdb.add(imdb_id)
        else:
            _publish_series(obj)
            stats['series_kept'] += 1
            stats['series_created'] += 1
            existing_series_tmdb.add(tmdb_id)
            if imdb_id:
                existing_series_imdb.add(imdb_id)

        # Enrich Film2Media qualities first, then queue SoftSub against the merged set.
        try:
            from apps.catalog.provider_import.multi_provider_crawl import enrich_with_other_providers
            enrich_with_other_providers(obj, already_used='dornatv', queue_softsub_extract=False)
            obj.refresh_from_db()
        except Exception as exc:
            logger.info('dornatv myf2m enrich skip for %s: %s', obj.pk, exc)

        if queue_softsub:
            try:
                if content_type == 'movie':
                    if enqueue_movie_softsub(obj.pk):
                        stats['softsub_queued'] += 1
                else:
                    if enqueue_series_softsub(obj.pk):
                        stats['softsub_queued'] += 1
            except Exception:
                pass

        done.add(page_path)
        cov = _version_coverage(obj)
        logger.info(
            'dornatv kept %s id=%s %s / %s tmdb=%s links=%s dub=%s soft=%s hard=%s tracks=%s both=%s',
            content_type, obj.pk, title_fa, title_en, tmdb_id,
            len(obj.download_links or []),
            cov.get('has_dub'), cov.get('has_softsub'), cov.get('has_hardsub'),
            cov.get('has_tracks'), cov.get('has_both'),
        )
        return 'kept'

    def scan_content(*, content_type: str, category_ids, kept_key: str, limit: int, max_pages: int):
        nonlocal movie_page, series_page, movie_year, series_year
        pages_scanned = 0
        while stats[kept_key] < limit and pages_scanned < max_pages:
            if should_cancel():
                return 'cancelled'
            if out_of_time():
                persist()
                return 'budget'
            if content_type == 'movie':
                year = movie_year
                page = movie_page
            else:
                year = series_year
                page = series_page
            if year < year_lo:
                break
            release_id = connector.resolve_release_term_id(year)
            if not release_id:
                logger.info('dornatv release term missing for %s; skipping year', year)
                if content_type == 'movie':
                    movie_year = year - 1
                    movie_page = 1
                    stats['movie_year'] = movie_year
                else:
                    series_year = year - 1
                    series_page = 1
                    stats['series_year'] = series_year
                continue
            rows, meta = connector._rest_list_by_category(
                category_ids=category_ids,
                page=page,
                embed=True,
                release_id=release_id,
                orderby='date',
            )
            if not rows:
                if content_type == 'movie':
                    movie_year = year - 1
                    movie_page = 1
                    stats['movie_year'] = movie_year
                else:
                    series_year = year - 1
                    series_page = 1
                    stats['series_year'] = series_year
                persist()
                continue
            for item in rows:
                if should_cancel():
                    persist()
                    return 'cancelled'
                if out_of_time():
                    persist()
                    return 'budget'
                if stats[kept_key] >= limit:
                    break
                fetched_before = fetches
                result = import_one(content_type=content_type, item=item, expected_year=year)
                if result == 'rate_limited':
                    persist()
                    return 'rate_limited'
                if delay and fetches != fetched_before:
                    time.sleep(delay)
            pages_scanned += 1
            total_pages = int(meta.get('total_pages') or 0)
            if total_pages and page >= total_pages:
                if content_type == 'movie':
                    movie_year = year - 1
                    movie_page = 1
                    stats['movie_year'] = movie_year
                else:
                    series_year = year - 1
                    series_page = 1
                    stats['series_year'] = series_year
            else:
                if content_type == 'movie':
                    movie_page = page + 1
                else:
                    series_page = page + 1
            persist()
        return 'ok'

    modified_pages = max(1, int(getattr(settings, 'DORNATV_MODIFIED_PAGES_PER_TICK', 3)))
    modified_page = max(1, int(state.get('modified_page') or 1))
    modified_cursor = state.get('modified_cursor') or ''  # oldest mod ever processed (informational)
    newest_modified = state.get('newest_modified') or ''  # newest mod seen at the front of the listing

    def scan_recent_modified() -> str:
        """Incremental 'recently modified' sweep, newest → oldest.

        Runs before the year-walk so newly added/dubbed/updated titles are
        discovered on every tick without walking the release-year taxonomy.

        Front-reset + resume-page design:
        * Every tick peeks at listing page 1. If a row at the front is newer than
          the last ``newest_modified`` we ever saw, a title was added/edited, so
          we reset ``modified_page`` to 1 to sweep from the top again.
        * Otherwise we *resume* at the persisted ``modified_page`` (monotonic),
          processing :data:`DORNATV_MODIFIED_PAGES_PER_TICK` pages. Already-
          handled rows hit the done-set fast path in import_one (no HTTP), so
          reprocessing is cheap. The page pointer guarantees full coverage of the
          whole listing over many ticks; ``modified_cursor`` is informational.
        """
        nonlocal modified_page, modified_cursor, newest_modified
        all_categories = sorted(set(MOVIE_CATEGORY_IDS) | set(SERIES_CATEGORY_IDS))

        # 1) Front-check: any activity newer than we've seen → restart from page 1.
        front_rows, _ = connector._rest_list_by_category(
            category_ids=all_categories, page=1, embed=True, orderby='modified',
        )
        if front_rows:
            front_mod = str(front_rows[0].get('modified') or '')
            if front_mod and (not newest_modified or front_mod > newest_modified):
                modified_page = 1
                newest_modified = front_mod

        pages = 0
        while pages < modified_pages:
            if should_cancel():
                persist()
                return 'cancelled'
            if out_of_time():
                persist()
                return 'budget'
            rows, meta = connector._rest_list_by_category(
                category_ids=all_categories, page=modified_page, embed=True,
                orderby='modified',
            )
            if not rows:
                break  # window exhausted; keep page pointer where it is
            total_pages = int(meta.get('total_pages') or 0)
            page_oldest_mod = ''  # smallest (oldest) modified in this page
            for item in rows:
                if should_cancel():
                    persist()
                    return 'cancelled'
                if out_of_time():
                    persist()
                    return 'budget'
                mod = str(item.get('modified') or '')
                if mod and (not page_oldest_mod or mod < page_oldest_mod):
                    page_oldest_mod = mod
                ctype = parse_wp_rest_item(item).get('content_type', '')
                fetched_before = fetches
                if ctype == 'movie':
                    result = import_one(
                        content_type='movie', item=item,
                        expected_year=_mod_year(item), enforce_year=False,
                    )
                elif ctype == 'series':
                    result = import_one(
                        content_type='series', item=item,
                        expected_year=_mod_year(item), enforce_year=False,
                    )
                else:
                    result = 'unknown'
                if result == 'rate_limited':
                    persist()
                    return 'rate_limited'
                if delay and fetches != fetched_before:
                    time.sleep(delay)
            # Informational high-water mark: oldest row we've actually processed.
            if page_oldest_mod and (not modified_cursor or page_oldest_mod < modified_cursor):
                modified_cursor = page_oldest_mod
            if total_pages and modified_page >= total_pages:
                break
            modified_page += 1
            pages += 1
        return 'ok'

    def _mod_year(item: dict) -> int:
        # A missing/garbled ``modified`` stamp is treated as the newest year in the
        # window, so the row is not silently pushed outside it.
        try:
            return int(str((item.get('modified') or '')[:4]) or year_hi)
        except (TypeError, ValueError):
            return year_hi

    def refresh_stale_links() -> int:
        """Re-crawl published dornatv-sourced rows whose signed CDN links expired.

        Signed dlyar.top URLs self-expire in ~13 h; without a re-crawl the stored
        links quietly become 403/410. Picks a small bounded set per tick to keep
        the beat cheap, refreshing via crawl_dornatv_downloads_for_movie/series
        (which re-validates identity with the detail page).
        """
        from apps.catalog.provider_import.dornatv_sync import crawl_dornatv_downloads_for_movie, crawl_dornatv_downloads_for_series
        from django.utils import timezone as _tz
        from datetime import timedelta as _timedelta

        # A --dry-run must never modify existing catalog rows (the crawl helpers
        # re-write download_links / metadata with replace=True).
        if dry_run:
            return 0
        budget = int(getattr(settings, 'DORNATV_REFRESH_PER_TICK', 4))
        if budget <= 0:
            return 0
        max_age = int(getattr(settings, 'DORNATV_REFRESH_LINK_MAX_AGE_SECONDS', 6 * 60 * 60))
        cutoff = _tz.now() - _timedelta(seconds=max_age)
        done = 0

        # Pick the stalest published rows that are actually sourced from dornatv
        # (a row carries source='dornatv' and the detail page_path). Sorted by
        # updated_at so the most-expired links refresh first.
        #
        # A row whose refresh fails keeps its old ``updated_at``, so it stays the
        # stalest candidate forever. Eight such rows (pages Dornatv removed) used
        # to take every slot of every tick and nothing else was ever refreshed.
        # A failed row now sits out a cooldown, and the window is wide enough to
        # reach past any cluster of them.
        from django.core.cache import cache as _cache

        cooldown = int(getattr(settings, 'DORNATV_REFRESH_FAIL_COOLDOWN_SECONDS', 24 * 60 * 60))
        window = int(getattr(settings, 'DORNATV_REFRESH_SCAN_WINDOW', 1000))

        def _cooling_key(model, pk) -> str:
            return f'dornatv:refresh:fail:{model._meta.model_name}:{pk}'

        def _refresh(model, crawl, kwarg: str) -> None:
            nonlocal done
            rows = (
                model.objects.filter(is_published=True, updated_at__lt=cutoff)
                .order_by('updated_at').values_list('pk', 'download_links')[:window]
            )
            pks = [pk for pk, links in rows if _has_dornatv_row(SimpleNamespace(download_links=links))]
            cooling = _cache.get_many([_cooling_key(model, pk) for pk in pks])
            attempts = 0
            for pk in pks:
                if done >= budget or attempts >= budget * 2 or out_of_time():
                    return
                if _cooling_key(model, pk) in cooling:
                    continue
                obj = model.objects.filter(pk=pk).first()
                if obj is None:
                    continue
                attempts += 1
                try:
                    # crawl_dornatv_downloads_for_* manage their own connector (and
                    # page cache) — no need to open one here.
                    result = crawl(
                        **{kwarg: obj},
                        provider_item_id=_dornatv_path_for(obj),
                        replace=True,
                        queue_softsub_extract=False,
                    )
                    if result.get('code') in ('ok', 'dornatv_links_empty'):
                        done += 1
                        stats['refreshed'] = stats.get('refreshed', 0) + 1
                except Exception as exc:
                    stats['errors'] += 1
                    stats['refresh_cooled'] = stats.get('refresh_cooled', 0) + 1
                    _cache.set(_cooling_key(model, pk), 1, cooldown)
                    logger.info('dornatv refresh %s %s failed: %s', kwarg, pk, exc)

        # Each kind gets its own share of the budget: series links expire on the
        # same clock, and used to be refreshed only when movies left slots over.
        _refresh(Movie, crawl_dornatv_downloads_for_movie, 'movie')
        total = done
        done = 0
        _refresh(Series, crawl_dornatv_downloads_for_series, 'series')
        return total + done

    def _has_dornatv_row(obj) -> bool:
        for item in (getattr(obj, 'download_links', None) or []):
            if isinstance(item, dict):
                src = str(item.get('source') or '').strip().lower()
                page = str(item.get('page_path') or '').strip()
                if src == 'dornatv' or (page and page.startswith('/') and 'dlyar' in str(item.get('url') or '')):
                    return True
        return False

    def _dornatv_path_for(obj) -> str:
        for item in (getattr(obj, 'download_links', None) or []):
            if isinstance(item, dict):
                page = str(item.get('page_path') or '').strip()
                if page:
                    return page
        return ''

    try:
        with _suppress_provider_publish_signals():
            # 1) Incremental recent-changes sweep first — cheap, catches new titles.
            if modified_pages > 0:
                status = scan_recent_modified()
                if status in ('rate_limited', 'budget'):
                    return {'status': status, **stats}
            # 2) Refresh signed-link staleness on published titles (small budget).
            if out_of_time():
                return {'status': 'budget', **stats}
            refresh_stale_links()
            if movies_limit > 0:
                status = scan_content(
                    content_type='movie',
                    category_ids=MOVIE_CATEGORY_IDS,
                    kept_key='movies_kept',
                    limit=movies_limit,
                    max_pages=40,
                )
                if status in ('rate_limited', 'budget'):
                    return {'status': status, **stats}
            if series_limit > 0:
                status = scan_content(
                    content_type='series',
                    category_ids=SERIES_CATEGORY_IDS,
                    kept_key='series_kept',
                    limit=series_limit,
                    max_pages=30,
                )
                if status in ('rate_limited', 'budget'):
                    return {'status': status, **stats}
    finally:
        close = getattr(connector, 'close', None)
        if callable(close):
            close()
        stats['movie_page'] = movie_page
        stats['series_page'] = series_page
        stats['movie_year'] = movie_year
        stats['series_year'] = series_year
        stats['modified_cursor'] = modified_cursor
        stats['modified_page'] = modified_page
        stats['newest_modified'] = newest_modified
        persist()

    return {'status': 'ok', **stats}
