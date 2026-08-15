#!/usr/bin/env python3
"""Import up to N *new* movies that exist on Film2Media (myf2m).

Never updates/deletes/re-crawls titles already present in the catalog (by TMDB id).
Each kept title is published with download links for online playback, then SoftSub
extraction is queued so the HTML5 player gets synced WebVTT.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


def main() -> int:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from django.db import transaction

    from apps.catalog.ingestion import upsert_tmdb_movie
    from apps.catalog.iranian import is_iranian_catalog_item, is_iranian_tmdb_details
    from apps.catalog.models import Movie
    from apps.catalog.provider_import.exceptions import ProviderRateLimited
    from apps.catalog.provider_import.registry import get_connector
    from apps.catalog.tasks import enqueue_movie_softsub
    from apps.catalog.top_catalog import (
        _crawl_movie_links,
        _has_download_links,
        _publish_movie,
        _suppress_provider_publish_signals,
        _version_coverage,
    )
    from apps.catalog.tmdb import configured_tmdb_client

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=int, default=200, help='How many NEW movies to keep')
    parser.add_argument('--crawl-delay', type=float, default=0.65)
    parser.add_argument('--max-candidates', type=int, default=2500)
    parser.add_argument('--queue-softsub', action='store_true', default=True)
    parser.add_argument('--no-queue-softsub', action='store_false', dest='queue_softsub')
    args = parser.parse_args()

    target = max(1, int(args.target))
    delay = max(0.0, float(args.crawl_delay))
    max_candidates = max(target, int(args.max_candidates))

    client = configured_tmdb_client()
    existing = set(
        Movie.objects.exclude(tmdb_id__isnull=True).values_list('tmdb_id', flat=True)
    )
    print(f'existing_tmdb_movies={len(existing)} target={target}', flush=True)

    seen: set[int] = set()
    candidates: list[dict] = []

    def add(item: dict) -> None:
        try:
            tid = int(item['id'])
        except (KeyError, TypeError, ValueError):
            return
        if tid in existing or tid in seen:
            return
        if item.get('adult'):
            return
        if is_iranian_tmdb_details(item):
            return
        # Skip ultra-obscure titles Film2Media almost never carries.
        if float(item.get('popularity') or 0) < 1.5 and int(item.get('vote_count') or 0) < 80:
            return
        seen.add(tid)
        candidates.append(item)

    # Broad Hollywood-heavy pools that Film2Media commonly carries.
    for item in client.popular_movies(limit=min(1000, max_candidates)):
        add(item)
    for item in client.top_rated_movies(limit=min(500, max_candidates)):
        add(item)
    for item in client.trending_movies(window='week', max_pages=10):
        add(item)
    for item in client.trending_movies(window='day', max_pages=5):
        add(item)
    for item in client.now_playing_movies(max_pages=8):
        add(item)
    for year in range(2026, 1999, -1):
        if len(candidates) >= max_candidates:
            break
        for item in client.discover_movies(
            released_from=__import__('datetime').date(year, 1, 1),
            released_until=__import__('datetime').date(year, 12, 31),
            max_pages=3,
            sort_by='popularity.desc',
            with_original_language='en',
        ):
            add(item)
            if len(candidates) >= max_candidates:
                break

    candidates = candidates[:max_candidates]
    candidates.sort(
        key=lambda item: float(item.get('popularity') or 0),
        reverse=True,
    )
    print(f'new_candidates={len(candidates)}', flush=True)
    if candidates:
        top = candidates[0]
        print(
            f'top_candidate={top.get("title") or top.get("original_title")} '
            f'pop={top.get("popularity")} tmdb={top.get("id")}',
            flush=True,
        )

    connector = get_connector('myf2m')
    connector.authenticate()

    stats = {
        'tried': 0,
        'kept': 0,
        'created': 0,
        'no_links': 0,
        'iranian': 0,
        'errors': 0,
        'softsub_queued': 0,
        'with_dub': 0,
        'with_sub': 0,
        'with_both': 0,
        'kept_ids': [],
    }

    try:
        with _suppress_provider_publish_signals():
            for summary in candidates:
                if stats['kept'] >= target:
                    break
                tmdb_id = int(summary['id'])
                label = summary.get('title') or summary.get('original_title') or str(tmdb_id)
                # Re-check — another process may have inserted meanwhile.
                if Movie.objects.filter(tmdb_id=tmdb_id).exists():
                    continue
                stats['tried'] += 1
                print(f'[{stats["kept"]}/{target}] try={stats["tried"]} {label} tmdb={tmdb_id}', flush=True)
                try:
                    details = client.movie_details(tmdb_id)
                    if is_iranian_tmdb_details(details):
                        stats['iranian'] += 1
                        print('  -> skip iranian', flush=True)
                        continue
                    with transaction.atomic():
                        movie, created, _published, _skipped = upsert_tmdb_movie(
                            details,
                            auto_publish=False,
                        )
                    if not created:
                        # Existing row somehow appeared — leave it untouched.
                        print(f'  -> skip existing id={movie.pk}', flush=True)
                        continue
                    stats['created'] += 1
                except Exception as exc:
                    stats['errors'] += 1
                    print(f'  -> import error {type(exc).__name__}: {exc}', flush=True)
                    continue

                try:
                    crawl = _crawl_movie_links(movie, connector, replace=True)
                except ProviderRateLimited as exc:
                    print(f'  -> rate limited: {exc}; sleep 30s then delete orphan', flush=True)
                    movie.delete()
                    stats['created'] = max(0, stats['created'] - 1)
                    stats['errors'] += 1
                    time.sleep(30)
                    continue
                except Exception as exc:
                    print(f'  -> crawl error {type(exc).__name__}: {exc}', flush=True)
                    movie.delete()
                    stats['created'] = max(0, stats['created'] - 1)
                    stats['no_links'] += 1
                    if delay:
                        time.sleep(delay)
                    continue

                movie.refresh_from_db()
                if is_iranian_catalog_item(movie):
                    movie.delete()
                    stats['created'] = max(0, stats['created'] - 1)
                    stats['iranian'] += 1
                    print('  -> deleted iranian after crawl', flush=True)
                    continue

                if not _has_download_links(movie) or crawl.get('status') == 'page_not_found' or crawl.get('code') in {
                    'myf2m_page_required', 'myf2m_links_empty',
                }:
                    movie.delete()
                    stats['created'] = max(0, stats['created'] - 1)
                    stats['no_links'] += 1
                    print(f'  -> not on myf2m ({crawl.get("status") or crawl.get("code")})', flush=True)
                    if delay:
                        time.sleep(delay)
                    continue

                _publish_movie(movie)
                cov = _version_coverage(movie)
                if cov['has_dub']:
                    stats['with_dub'] += 1
                if cov['has_sub']:
                    stats['with_sub'] += 1
                if cov['has_both']:
                    stats['with_both'] += 1
                stats['kept'] += 1
                stats['kept_ids'].append(movie.pk)
                print(
                    f'  -> KEPT id={movie.pk} links={len(movie.download_links or [])} '
                    f'dub={cov["has_dub"]} sub={cov["has_sub"]} video={bool(movie.video_url)}',
                    flush=True,
                )
                if args.queue_softsub:
                    if enqueue_movie_softsub(movie.pk, force=False):
                        stats['softsub_queued'] += 1
                if delay:
                    time.sleep(delay)
    finally:
        close = getattr(connector, 'close', None)
        if callable(close):
            close()

    try:
        from apps.catalog.cache import bump_catalog_cache_version
        bump_catalog_cache_version()
    except Exception:
        pass

    print('IMPORT_NEW_MYF2M_MOVIES_DONE', {k: v for k, v in stats.items() if k != 'kept_ids'}, flush=True)
    print('kept_ids', stats['kept_ids'][:50], ('...' if len(stats['kept_ids']) > 50 else ''), flush=True)
    return 0 if stats['kept'] >= min(target, 1) else 1


if __name__ == '__main__':
    raise SystemExit(main())
