#!/usr/bin/env python3
"""Mirror series download_links into Episode.video_url for player/list sync.

Usage (inside backend container):
  python /app/scripts/sync_episode_streams.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


def main() -> int:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from apps.catalog.models import Episode, Series
    from apps.catalog.subtitle_extract import ensure_episodes_from_download_links
    from apps.catalog.top_catalog import _has_download_links

    qs = Series.objects.all()
    synced = 0
    created = 0
    before_video = Episode.objects.exclude(video_url='').exclude(video_url__isnull=True).count()
    for series in qs.iterator(chunk_size=100):
        if not _has_download_links(series):
            continue
        synced += 1
        created += ensure_episodes_from_download_links(series)
    after_video = Episode.objects.exclude(video_url='').exclude(video_url__isnull=True).count()
    print(
        f'SYNC_EPISODES_DONE series={synced} episodes_created={created} '
        f'episode_video_before={before_video} after={after_video}',
        flush=True,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
