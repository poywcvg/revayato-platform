#!/usr/bin/env python3
"""Crawl or delete unpublished movies that still lack download/playback links."""

from __future__ import annotations

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

    from apps.catalog.cache import bump_catalog_cache_version
    from apps.catalog.models import Movie
    from apps.catalog.provider_import.registry import get_connector
    from apps.catalog.top_catalog import (
        _crawl_movie_links,
        _has_download_links,
        _publish_movie,
        _suppress_provider_publish_signals,
    )

    delay = 0.55
    missing = [
        m for m in Movie.objects.filter(is_published=False).order_by('-id')[:400]
        if not _has_download_links(m) and not (m.video_url or '').strip()
    ]
    print(f'draft_missing={len(missing)}', flush=True)
    connector = get_connector('myf2m')
    connector.authenticate()
    stats = {'ok': 0, 'published': 0, 'deleted': 0, 'failed': 0}
    missing_codes = {
        'myf2m_page_required', 'myf2m_links_empty',
        'myf2m_page_required', 'myf2m_links_empty',
    }

    try:
        with _suppress_provider_publish_signals():
            for i, movie in enumerate(missing, 1):
                label = movie.original_title or movie.title
                print(f'[{i}/{len(missing)}] {movie.id} {label} ({movie.release_year})', flush=True)
                result = _crawl_movie_links(movie, connector, replace=True)
                movie.refresh_from_db()
                status = result.get('status')
                imported = int(result.get('imported_count') or 0)
                code = result.get('code') or ''
                if status == 'ok' and imported > 0 and _has_download_links(movie):
                    stats['ok'] += 1
                    if _publish_movie(movie):
                        stats['published'] += 1
                        print(f'  -> ok+published ({imported})', flush=True)
                    else:
                        print(f'  -> ok links, publish blocked ({imported})', flush=True)
                else:
                    is_miss = (
                        status == 'page_not_found'
                        or code in missing_codes
                        or (status == 'ok' and not _has_download_links(movie))
                    )
                    if is_miss:
                        movie.delete()
                        stats['deleted'] += 1
                        print(f'  -> deleted ({status} {code})', flush=True)
                    else:
                        stats['failed'] += 1
                        detail = result.get('detail') or ''
                        print(f'  -> failed {status} {code} {detail}', flush=True)
                if delay:
                    time.sleep(delay)
    finally:
        close = getattr(connector, 'close', None)
        if callable(close):
            close()

    print('DONE', stats, 'cache', bump_catalog_cache_version(), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
