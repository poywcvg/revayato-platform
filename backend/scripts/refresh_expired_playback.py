#!/usr/bin/env python3
"""Refresh published titles whose download/playback links have expired.

Dornatv CDN signatures self-expire (~13 h). Titles whose every download link is
an expired signed URL (or a known-dead host) stop playing in the online player.
This script re-crawls those titles (myf2m + dornatv) to refresh the signatures,
and deletes titles that no provider carries anymore.

The logic lives in ``apps.catalog.playback_refresh`` and is shared with the
periodic Celery beat task ``refresh_expired_playback_task``.

Usage (backend/crawler container):
  python /app/scripts/refresh_expired_playback.py --limit 100 --delay 1.0
  python /app/scripts/refresh_expired_playback.py --no-delete --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if not (_APP_ROOT / 'config').is_dir():
    _APP_ROOT = Path('/app')
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


def main() -> int:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from apps.catalog.playback_refresh import refresh_broken_playback

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delay', type=float, default=1.0)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--movies-only', action='store_true')
    parser.add_argument('--series-only', action='store_true')
    parser.add_argument('--no-delete', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    print(
        f'work=collecting delete={not args.no_delete} dry_run={args.dry_run}',
        flush=True,
    )

    def report(index, total, outcome, content_type, pk, label, before, after, codes):
        if outcome == 'dry_run':
            print(f'[{index}/{total}] DRY {content_type} {pk} {label}', flush=True)
        elif outcome == 'refreshed':
            print(f'[{index}/{total}] REFRESHED {content_type} {pk} {label} links {before}->{after}', flush=True)
        elif outcome == 'deleted':
            print(f'[{index}/{total}] DELETED {content_type} {pk} {label} codes={codes}', flush=True)
        elif outcome == 'keep_no_playable':
            print(f'[{index}/{total}] KEEP (no playable) {content_type} {pk} {label} codes={codes}', flush=True)
        elif outcome == 'keep_transient':
            print(f'[{index}/{total}] KEEP (transient) {content_type} {pk} {label} codes={codes}', flush=True)

    stats = refresh_broken_playback(
        max_batch=args.limit,
        delete=not args.no_delete,
        delay=args.delay,
        movies_only=args.movies_only,
        series_only=args.series_only,
        dry_run=args.dry_run,
        on_progress=report,
    )
    print('REFRESH_EXPIRED_DONE', stats, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
