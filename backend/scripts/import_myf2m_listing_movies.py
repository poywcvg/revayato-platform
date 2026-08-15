#!/usr/bin/env python3
"""Import NEW movies from Film2Media listings (never touch existing catalog rows).

Walks myf2m /movies/ pages, resolves each title via IMDb→TMDB, skips any TMDB id
already in the DB, then publishes download/stream links and queues SoftSub VTT.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

LISTING_ITEM_RE = re.compile(
    r'href="(?:https?://(?:www\.)?myf2m\.info)?/(?P<id>\d+)/(?P<slug>[^"/]+)/"',
    re.I,
)
IMDB_RE = re.compile(r'(tt\d{7,8})')
H1_RE = re.compile(r'<h1[^>]*>(?P<title>.*?)</h1>', re.I | re.S)


def _clean_html(value: str) -> str:
    return re.sub(r'<[^>]+>', '', value or '').strip()


def main() -> int:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from django.db import transaction

    from apps.catalog.ingestion import upsert_tmdb_movie
    from apps.catalog.iranian import is_iranian_catalog_item, is_iranian_tmdb_details
    from apps.catalog.models import Movie
    from apps.catalog.provider_import.exceptions import ProviderImportError, ProviderRateLimited
    from apps.catalog.provider_import.registry import get_connector
    from apps.catalog.subtitle_extract import (
        apply_availability_flags,
        coalesce_download_links,
    )
    from apps.catalog.tasks import enqueue_movie_softsub
    from apps.catalog.top_catalog import (
        _has_download_links,
        _publish_movie,
        _suppress_provider_publish_signals,
        _version_coverage,
    )
    from apps.catalog.tmdb import configured_tmdb_client
    from config.public_urls import normalize_download_links

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=int, default=200)
    parser.add_argument('--max-pages', type=int, default=120)
    parser.add_argument('--delay', type=float, default=0.55)
    parser.add_argument('--queue-softsub', action='store_true', default=True)
    parser.add_argument('--no-queue-softsub', action='store_false', dest='queue_softsub')
    args = parser.parse_args()

    target = max(1, int(args.target))
    delay = max(0.0, float(args.delay))
    max_pages = max(1, int(args.max_pages))

    existing_tmdb = set(
        Movie.objects.exclude(tmdb_id__isnull=True).values_list('tmdb_id', flat=True)
    )
    existing_imdb = {
        str(v).strip().lower()
        for v in Movie.objects.exclude(imdb_id__isnull=True).exclude(imdb_id='').values_list('imdb_id', flat=True)
    }
    # Paths already referenced by current catalog download boxes.
    existing_paths: set[str] = set()
    for links in Movie.objects.exclude(download_links=[]).exclude(download_links__isnull=True).values_list('download_links', flat=True).iterator(chunk_size=200):
        for item in links or []:
            if isinstance(item, dict):
                path = str(item.get('page_path') or '').strip()
                if path:
                    existing_paths.add('/' + path.strip('/') + '/')

    print(
        f'existing_tmdb={len(existing_tmdb)} existing_imdb={len(existing_imdb)} '
        f'existing_paths={len(existing_paths)} target={target}',
        flush=True,
    )

    client = configured_tmdb_client()
    connector = get_connector('myf2m')
    connector.authenticate()

    stats = {
        'listing_urls': 0,
        'tried': 0,
        'kept': 0,
        'skipped_existing': 0,
        'skipped_no_imdb': 0,
        'skipped_tmdb_miss': 0,
        'no_links': 0,
        'iranian': 0,
        'errors': 0,
        'softsub_queued': 0,
        'with_dub': 0,
        'with_sub': 0,
        'with_both': 0,
        'kept_ids': [],
    }

    def iter_listing_paths():
        seen: set[str] = set()
        for page in range(1, max_pages + 1):
            path = '/movies/' if page == 1 else f'/movies/page/{page}/'
            try:
                response = connector._request('GET', path)
            except Exception as exc:
                print(f'listing fail page={page}: {exc}', flush=True)
                break
            if response.status_code >= 400:
                print(f'listing http={response.status_code} page={page}', flush=True)
                break
            html = response.text or ''
            found = 0
            for match in LISTING_ITEM_RE.finditer(html):
                item_path = f'/{match.group("id")}/{match.group("slug")}/'
                if item_path in seen:
                    continue
                seen.add(item_path)
                found += 1
                yield item_path, match.group('slug')
            print(f'listing page={page} items={found} unique_total={len(seen)}', flush=True)
            if found == 0:
                break
            if delay:
                time.sleep(delay)

    try:
        with _suppress_provider_publish_signals():
            for page_path, slug in iter_listing_paths():
                if stats['kept'] >= target:
                    break
                stats['listing_urls'] += 1
                if page_path in existing_paths:
                    stats['skipped_existing'] += 1
                    continue

                stats['tried'] += 1
                print(f'[{stats["kept"]}/{target}] try={stats["tried"]} {page_path}', flush=True)
                try:
                    crawled = connector.crawl_download_links(page_path, content_type='movie')
                except ProviderRateLimited as exc:
                    stats['errors'] += 1
                    print(f'  -> rate limited: {exc}; sleep 25s', flush=True)
                    time.sleep(25)
                    continue
                except ProviderImportError as exc:
                    stats['no_links'] += 1
                    print(f'  -> crawl skip {getattr(exc, "code", "")}: {exc}', flush=True)
                    if delay:
                        time.sleep(delay)
                    continue
                except Exception as exc:
                    stats['errors'] += 1
                    print(f'  -> crawl error {type(exc).__name__}: {exc}', flush=True)
                    if delay:
                        time.sleep(delay)
                    continue

                available = crawled.get('available_links') or []
                if not available:
                    stats['no_links'] += 1
                    print('  -> empty links', flush=True)
                    if delay:
                        time.sleep(delay)
                    continue

                # Re-fetch HTML is expensive; crawl already did. Use page_url body via another GET only for imdb/title.
                try:
                    detail = connector._request('GET', page_path)
                    html = detail.text or ''
                except Exception:
                    html = ''
                imdb_ids = IMDB_RE.findall(html)
                imdb_id = (imdb_ids[0] if imdb_ids else '').lower()
                h1 = H1_RE.search(html)
                page_title = _clean_html(h1.group('title')) if h1 else slug.replace('-', ' ')
                year_match = re.search(r'\b((?:19|20)\d{2})\b', page_title) or re.search(r'\b((?:19|20)\d{2})\b', slug)
                year = int(year_match.group(1)) if year_match else None

                if imdb_id and imdb_id in existing_imdb:
                    stats['skipped_existing'] += 1
                    print(f'  -> skip existing imdb={imdb_id}', flush=True)
                    existing_paths.add(page_path)
                    if delay:
                        time.sleep(delay)
                    continue

                tmdb_summary = None
                if imdb_id:
                    tmdb_summary = client.resolve_imdb_to_tmdb(imdb_id, content_type='movie')
                if tmdb_summary is None:
                    query = re.sub(r'\b(19|20)\d{2}\b', '', page_title).strip(' -_')
                    try:
                        payload = client.search_movies(query, page=1) or {}
                    except Exception:
                        payload = {}
                    results = payload.get('results') if isinstance(payload, dict) else (payload or [])
                    results = list(results or [])
                    for row in results[:8]:
                        if year and str(row.get('release_date') or '')[:4] not in {'', str(year), str(year - 1), str(year + 1)}:
                            continue
                        tmdb_summary = row
                        break
                    if tmdb_summary is None and results:
                        tmdb_summary = results[0]

                if not tmdb_summary or not tmdb_summary.get('id'):
                    stats['skipped_tmdb_miss'] += 1
                    print(f'  -> tmdb miss title={page_title!r} imdb={imdb_id}', flush=True)
                    if delay:
                        time.sleep(delay)
                    continue

                tmdb_id = int(tmdb_summary['id'])
                if tmdb_id in existing_tmdb or Movie.objects.filter(tmdb_id=tmdb_id).exists():
                    stats['skipped_existing'] += 1
                    existing_tmdb.add(tmdb_id)
                    existing_paths.add(page_path)
                    print(f'  -> skip existing tmdb={tmdb_id}', flush=True)
                    if delay:
                        time.sleep(delay)
                    continue

                try:
                    details = client.movie_details(tmdb_id)
                    if is_iranian_tmdb_details(details):
                        stats['iranian'] += 1
                        print('  -> skip iranian', flush=True)
                        continue
                    with transaction.atomic():
                        movie, created, _pub, _skip = upsert_tmdb_movie(details, auto_publish=False)
                    if not created:
                        stats['skipped_existing'] += 1
                        existing_tmdb.add(tmdb_id)
                        print(f'  -> skip raced existing id={movie.pk}', flush=True)
                        continue
                except Exception as exc:
                    stats['errors'] += 1
                    print(f'  -> import error {type(exc).__name__}: {exc}', flush=True)
                    continue

                normalized = normalize_download_links(available)
                movie.download_links = coalesce_download_links([], normalized, replace=True)
                # Ensure page_path stamped on links for future skips.
                stamped = []
                for item in movie.download_links or []:
                    if isinstance(item, dict):
                        row = dict(item)
                        row.setdefault('page_path', crawled.get('page_path') or page_path)
                        stamped.append(row)
                movie.download_links = stamped
                if imdb_id and not movie.imdb_id:
                    movie.imdb_id = imdb_id
                flag_fields = apply_availability_flags(movie, movie.download_links)
                # Prefer first http video as video_url if empty.
                if not (movie.video_url or '').strip():
                    for item in movie.download_links:
                        url = str(item.get('url') or '')
                        if url.startswith('http') and not url.lower().endswith(('.vtt', '.srt', '.ass')):
                            movie.video_url = url
                            break
                update_fields = ['download_links', 'updated_at', *flag_fields]
                if movie.imdb_id:
                    update_fields.append('imdb_id')
                if movie.video_url:
                    update_fields.append('video_url')
                movie.save(update_fields=list(dict.fromkeys(update_fields)))

                if is_iranian_catalog_item(movie) or not _has_download_links(movie):
                    movie.delete()
                    stats['no_links' if not _has_download_links(movie) else 'iranian'] += 1
                    print('  -> deleted (iranian/no links)', flush=True)
                    continue

                _publish_movie(movie)
                cov = _version_coverage(movie)
                stats['kept'] += 1
                stats['kept_ids'].append(movie.pk)
                existing_tmdb.add(tmdb_id)
                existing_paths.add(page_path)
                if imdb_id:
                    existing_imdb.add(imdb_id)
                if cov['has_dub']:
                    stats['with_dub'] += 1
                if cov['has_sub']:
                    stats['with_sub'] += 1
                if cov['has_both']:
                    stats['with_both'] += 1
                print(
                    f'  -> KEPT id={movie.pk} {movie.title} tmdb={tmdb_id} '
                    f'links={len(movie.download_links or [])} dub={cov["has_dub"]} sub={cov["has_sub"]}',
                    flush=True,
                )
                if args.queue_softsub:
                    if enqueue_movie_softsub(movie.pk):
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

    print('IMPORT_MYF2M_LISTING_DONE', {k: v for k, v in stats.items() if k != 'kept_ids'}, flush=True)
    print('kept_ids_sample', stats['kept_ids'][:40], flush=True)
    return 0 if stats['kept'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
