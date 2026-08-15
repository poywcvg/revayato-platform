#!/usr/bin/env python3
"""Backfill size_label (حجم) for myf2m CDN download links via HEAD Content-Length.

Runs a cheap HEAD (fallback GET Range: bytes=0-0) against every external download
URL that still lacks a size, then stores a human size like "2.5 GB" / "850 MB" in
download_links[].size_label so the public download box shows the file size.

Usage (inside backend container):
  python /app/scripts/backfill_download_sizes.py --workers 12
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

_APP_ROOT = Path(__file__).resolve().parents[1]
if not (_APP_ROOT / 'config').is_dir():
    _APP_ROOT = Path('/app')
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

SIZE_LABEL_RE = re.compile(r'(?P<size>\d+(?:\.\d+)?)\s*(?P<unit>GIB?|MIB?|KIB?)\b', re.I)


def human_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return ''
    if size_bytes >= 1024 ** 3:
        return f'{size_bytes / 1024 ** 3:.1f} GB'
    if size_bytes >= 1024 ** 2:
        return f'{size_bytes / 1024 ** 2:.0f} MB'
    if size_bytes >= 1024:
        return f'{size_bytes // 1024} KB'
    return ''


def probe_size(url: str, timeout: int) -> int | None:
    """Return Content-Length via HEAD, falling back to a ranged GET."""
    headers = {'User-Agent': 'RevayatoCatalogCrawler/1.0 (+https://revayato.ir)'}
    try:
        request = Request(url, headers=headers, method='HEAD')
        with urlopen(request, timeout=timeout) as response:
            value = response.headers.get('Content-Length')
            if value:
                return int(value)
    except Exception:
        pass
    try:
        range_headers = dict(headers, Range='bytes=0-0')
        request = Request(url, headers=range_headers, method='GET')
        with urlopen(request, timeout=timeout) as response:
            total = response.headers.get('Content-Range')
            if total:
                match = re.search(r'/(\d+)\s*$', total)
                if match:
                    return int(match.group(1))
    except Exception:
        pass
    return None


def _link_rows(links, *, source: str = '') -> list[tuple[int, dict]]:
    rows = []
    for index, item in enumerate(links or []):
        if not isinstance(item, dict):
            continue
        if source and str(item.get('source') or '').strip().lower() != source:
            continue
        if str(item.get('size_label') or '').strip():
            continue
        url = str(item.get('url') or '').strip()
        if not url:
            continue
        parsed = urlsplit(url)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            continue
        rows.append((index, item, url))
    return rows


def main() -> int:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from django.db import transaction
    from django.utils import timezone

    from apps.catalog.models import Movie, Series

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=12)
    parser.add_argument('--timeout', type=int, default=25)
    parser.add_argument('--limit', type=int, default=0, help='0 = process every link')
    parser.add_argument(
        '--probe-batch-size',
        type=int,
        default=600,
        help='Maximum unresolved link rows kept in memory per network batch',
    )
    parser.add_argument('--movies-only', action='store_true')
    parser.add_argument('--series-only', action='store_true')
    parser.add_argument(
        '--source',
        default='',
        help='Only probe links from this provider (for example: myf2m)',
    )
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    workers = max(1, int(args.workers))
    timeout = max(5, int(args.timeout))
    limit = max(0, int(args.limit))
    probe_batch_size = max(workers, int(args.probe_batch_size))
    source = str(args.source or '').strip().lower()

    do_movies = not args.series_only
    do_series = not args.movies_only
    querysets = []
    if do_movies:
        querysets.append(('movie', Movie.objects.exclude(download_links=[]).exclude(
            download_links__isnull=True,
        ).only('id', 'download_links')))
    if do_series:
        querysets.append(('series', Series.objects.exclude(download_links=[]).exclude(
            download_links__isnull=True,
        ).only('id', 'download_links')))

    stats = {
        'link_rows_seen': 0,
        'probed_urls': 0,
        'ok': 0,
        'empty': 0,
        'failed': 0,
        'rows_patched': 0,
        'objects_saved': 0,
    }
    pending: list[tuple[str, object, int, dict, str]] = []

    def save_batch(pool: ThreadPoolExecutor) -> None:
        if not pending:
            return
        by_url: dict[str, list[tuple[str, object, int, dict, str]]] = {}
        for entry in pending:
            by_url.setdefault(entry[4], []).append(entry)
        if args.dry_run:
            stats['probed_urls'] += len(by_url)
            pending.clear()
            return

        futures = {pool.submit(probe_size, url, timeout): url for url in by_url}
        sizes: dict[str, int | None] = {}
        for future in as_completed(futures):
            url = futures[future]
            try:
                size = future.result()
            except Exception:
                size = None
            sizes[url] = size
            stats['probed_urls'] += 1
            if size:
                stats['ok'] += 1
            else:
                stats['failed'] += 1

        updated: dict[tuple[str, int], object] = {}
        for url, entries in by_url.items():
            label = human_size(sizes.get(url) or 0)
            if not label:
                stats['empty'] += 1
                continue
            for kind, obj, _index, item, _entry_url in entries:
                item['size_label'] = label
                updated[(kind, obj.pk)] = obj
                stats['rows_patched'] += 1

        now = timezone.now()
        movie_updates = []
        series_updates = []
        for (kind, _pk), obj in updated.items():
            obj.updated_at = now
            (movie_updates if kind == 'movie' else series_updates).append(obj)
        with transaction.atomic():
            if movie_updates:
                Movie.objects.bulk_update(movie_updates, ['download_links', 'updated_at'], batch_size=100)
            if series_updates:
                Series.objects.bulk_update(series_updates, ['download_links', 'updated_at'], batch_size=100)
        stats['objects_saved'] += len(updated)
        print(
            f'progress rows={stats["link_rows_seen"]} urls={stats["probed_urls"]} '
            f'ok={stats["ok"]} failed={stats["failed"]} saved={stats["objects_saved"]}',
            flush=True,
        )
        pending.clear()

    stop = False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for kind, qs in querysets:
            for obj in qs.iterator(chunk_size=100):
                for index, item, url in _link_rows(obj.download_links, source=source):
                    if limit and stats['link_rows_seen'] >= limit:
                        stop = True
                        break
                    pending.append((kind, obj, index, item, url))
                    stats['link_rows_seen'] += 1
                if len(pending) >= probe_batch_size:
                    save_batch(pool)
                if stop:
                    break
            if stop:
                break
        save_batch(pool)

    if args.dry_run:
        print(
            f'dry-run: would probe {stats["link_rows_seen"]} rows / '
            f'{stats["probed_urls"]} batch-local unique URLs',
            flush=True,
        )
        return 0

    try:
        from apps.catalog.cache import bump_catalog_cache_version
        bump_catalog_cache_version()
    except Exception:
        pass

    print(
        'SIZE_BACKFILL_DONE',
        {
            'link_rows_seen': stats['link_rows_seen'],
            'probed_urls': stats['probed_urls'],
            'ok': stats['ok'],
            'failed': stats['failed'],
            'rows_patched': stats['rows_patched'],
            'objects_saved': stats['objects_saved'],
        },
        flush=True,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
