#!/usr/bin/env python3
"""Find dead download/playback URLs and re-crawl fresh provider links into the DB.

Checks representative HTTPS URLs (video_url + a few download_links) with HEAD/Range.
When none are reachable, re-crawls via the configured catalog link provider (default myf2m)
with replace=True so the site stores working download/stream URLs again.

Usage (backend container):
  PYTHONPATH=/app python /app/scripts/fix_broken_playback_links.py --delay 0.55
  PYTHONPATH=/app python /app/scripts/fix_broken_playback_links.py --dry-run --limit 40
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


def _is_http(url: str) -> bool:
    return url.startswith('http://') or url.startswith('https://')


def _prefer_streamable(url: str) -> int:
    lower = url.lower()
    if '.mp4' in lower:
        return 0
    if '.m3u8' in lower:
        return 1
    if '.mkv' in lower:
        return 2
    return 3


def candidate_urls(obj, *, max_n: int = 3) -> list[str]:
    """Pick a small set of URLs that represent playback + downloads."""
    from apps.catalog.provider_import.media_links import (
        is_playable_video_link,
        is_playable_video_url,
    )

    found: list[str] = []
    video = (getattr(obj, 'video_url', None) or '').strip()
    if _is_http(video) and is_playable_video_url(video):
        found.append(video)

    download_urls: list[str] = []
    for item in getattr(obj, 'download_links', None) or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get('url') or '').strip()
        if _is_http(url) and is_playable_video_link(item):
            download_urls.append(url)
    download_urls.sort(key=_prefer_streamable)
    for url in download_urls:
        if url not in found:
            found.append(url)
        if len(found) >= max_n:
            break
    return found[:max_n]


def static_playback_issues(obj) -> list[str]:
    """Return deterministic DB issues which must never count as healthy."""
    from apps.catalog.provider_import.media_links import (
        has_malformed_video_suffix,
        is_dead_playback_host,
        is_playable_video_url,
        is_trailer_download_link,
    )

    issues: list[str] = []
    video = str(getattr(obj, 'video_url', None) or '').strip()
    if _is_http(video) and not is_playable_video_url(video):
        issues.append('invalid_primary_video')

    for item in getattr(obj, 'download_links', None) or []:
        if not isinstance(item, dict):
            issues.append('invalid_download_row')
            continue
        url = str(item.get('url') or item.get('key') or '').strip()
        if not url:
            issues.append('empty_download_row')
        elif is_dead_playback_host(url):
            issues.append('dead_host')
        elif has_malformed_video_suffix(url):
            issues.append('malformed_media_suffix')
        elif is_trailer_download_link(item):
            issues.append('trailer_in_downloads')
    return list(dict.fromkeys(issues))


def any_url_reachable(urls: list[str], *, timeout_seconds: int, workers: int) -> bool:
    if not urls:
        return False
    from apps.catalog.subtitle_extract import _http_url_reachable

    if len(urls) == 1:
        return _http_url_reachable(urls[0], timeout_seconds=timeout_seconds)

    with ThreadPoolExecutor(max_workers=min(workers, len(urls))) as pool:
        futures = {
            pool.submit(_http_url_reachable, url, timeout_seconds=timeout_seconds): url
            for url in urls
        }
        for future in as_completed(futures):
            try:
                if future.result():
                    for pending in futures:
                        pending.cancel()
                    return True
            except Exception:  # noqa: BLE001
                continue
    return False


def main() -> int:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from apps.catalog.models import Movie, Series
    from apps.catalog.provider_import.registry import get_connector
    from apps.catalog.subtitle_extract import ensure_episodes_from_download_links
    from apps.catalog.top_catalog import (
        _crawl_movie_links,
        _crawl_series_links,
        _has_download_links,
        _link_provider_slug,
        _suppress_provider_publish_signals,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delay', type=float, default=0.55)
    parser.add_argument('--limit', type=int, default=0, help='0 = all published titles')
    parser.add_argument('--movies-only', action='store_true')
    parser.add_argument('--series-only', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='Only report broken titles')
    parser.add_argument('--check-timeout', type=int, default=6)
    parser.add_argument('--check-workers', type=int, default=4)
    parser.add_argument('--urls-per-title', type=int, default=3)
    parser.add_argument('--force-all', action='store_true', help='Re-crawl every title (skip reachability)')
    args = parser.parse_args()

    do_movies = not args.series_only
    do_series = not args.movies_only
    delay = max(0.0, float(args.delay or 0))
    limit = max(0, int(args.limit or 0))

    stats = {
        'movies_checked': 0,
        'movies_broken': 0,
        'movies_fixed': 0,
        'movies_failed': 0,
        'movies_skipped_ok': 0,
        'series_checked': 0,
        'series_broken': 0,
        'series_fixed': 0,
        'series_failed': 0,
        'series_skipped_ok': 0,
        'episodes_synced': 0,
    }

    def needs_fix(obj) -> bool:
        if args.force_all:
            return True
        issues = static_playback_issues(obj)
        if issues:
            print(f'  static_issues={",".join(issues)}', flush=True)
            return True
        urls = candidate_urls(obj, max_n=max(1, int(args.urls_per_title)))
        if not urls:
            # No external URLs — either missing links or own-site keys only.
            return not _has_download_links(obj) and not (getattr(obj, 'video_url', None) or '').strip()
        return not any_url_reachable(
            urls,
            timeout_seconds=max(3, int(args.check_timeout)),
            workers=max(1, int(args.check_workers)),
        )

    connector = get_connector(_link_provider_slug())
    connector.authenticate()
    print(f'provider={_link_provider_slug()} dry_run={args.dry_run}', flush=True)

    try:
        with _suppress_provider_publish_signals():
            if do_movies:
                qs = Movie.objects.filter(is_published=True).order_by('-popularity', '-id')
                if limit:
                    qs = qs[:limit]
                for movie in qs.iterator(chunk_size=50):
                    stats['movies_checked'] += 1
                    broken = needs_fix(movie)
                    if not broken:
                        stats['movies_skipped_ok'] += 1
                        if stats['movies_checked'] % 25 == 0:
                            print(
                                f"[progress movies] checked={stats['movies_checked']} "
                                f"broken={stats['movies_broken']} fixed={stats['movies_fixed']}",
                                flush=True,
                            )
                        continue

                    stats['movies_broken'] += 1
                    print(f'[movie broken] {movie.pk} {movie.title}', flush=True)
                    if args.dry_run:
                        continue

                    result = _crawl_movie_links(movie, connector, replace=True)
                    movie.refresh_from_db()
                    status = result.get('status')
                    imported = int(result.get('imported_count') or 0)
                    repaired_urls = candidate_urls(movie, max_n=max(1, int(args.urls_per_title)))
                    repaired_static_issues = static_playback_issues(movie)
                    if status == 'ok' and imported > 0 and repaired_urls and not repaired_static_issues:
                        stats['movies_fixed'] += 1
                        print(f'  -> fixed ({imported} links)', flush=True)
                    else:
                        stats['movies_failed'] += 1
                        detail = result.get('detail') or ','.join(repaired_static_issues)
                        print(f'  -> {status} {detail}', flush=True)
                    if delay:
                        time.sleep(delay)

            if do_series:
                qs = Series.objects.filter(is_published=True).order_by('-popularity', '-id')
                if limit:
                    qs = qs[:limit]
                for series in qs.iterator(chunk_size=25):
                    stats['series_checked'] += 1
                    broken = needs_fix(series)
                    if not broken:
                        stats['series_skipped_ok'] += 1
                        if stats['series_checked'] % 15 == 0:
                            print(
                                f"[progress series] checked={stats['series_checked']} "
                                f"broken={stats['series_broken']} fixed={stats['series_fixed']}",
                                flush=True,
                            )
                        continue

                    stats['series_broken'] += 1
                    print(f'[series broken] {series.pk} {series.title}', flush=True)
                    if args.dry_run:
                        continue

                    result = _crawl_series_links(series, connector, replace=True)
                    series.refresh_from_db()
                    status = result.get('status')
                    imported = int(result.get('imported_count') or 0)
                    repaired_urls = candidate_urls(series, max_n=max(1, int(args.urls_per_title)))
                    repaired_static_issues = static_playback_issues(series)
                    if status == 'ok' and imported > 0 and repaired_urls and not repaired_static_issues:
                        synced = ensure_episodes_from_download_links(series)
                        stats['episodes_synced'] += int(synced or 0)
                        stats['series_fixed'] += 1
                        print(f'  -> fixed ({imported} links, episodes+={synced})', flush=True)
                    else:
                        stats['series_failed'] += 1
                        print(f'  -> {status} {result.get("detail") or ""}', flush=True)
                    if delay:
                        time.sleep(delay)
    finally:
        close = getattr(connector, 'close', None)
        if callable(close):
            close()

    print('DONE', stats, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
