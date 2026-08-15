#!/usr/bin/env python3
"""Attach SubtitleStar WebVTT for a fixed list of newly imported movie IDs."""

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

    from django.core.cache import cache

    from apps.catalog.models import Movie
    from apps.catalog.subtitle_extract import attach_extracted_subtitle

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ids-file', required=True)
    parser.add_argument('--pause-seconds', type=float, default=25.0)
    parser.add_argument('--wait-circuit', action='store_true', default=True)
    parser.add_argument('--no-wait-circuit', action='store_false', dest='wait_circuit')
    args = parser.parse_args()

    ids = []
    for line in Path(args.ids_file).read_text().splitlines():
        line = line.strip()
        if line.isdigit():
            ids.append(int(line))
    print(f'target_movies={len(ids)}', flush=True)

    stats = {'tried': 0, 'attached': 0, 'empty': 0, 'blocked': 0, 'already': 0}
    for index, movie_id in enumerate(ids, start=1):
        if args.wait_circuit:
            while cache.get('catalog:subtitlestar:circuit-open'):
                print('waiting circuit...', flush=True)
                time.sleep(30)
        movie = Movie.objects.filter(pk=movie_id, is_published=True).first()
        if movie is None:
            continue
        if movie.subtitle_tracks:
            stats['already'] += 1
            continue
        stats['tried'] += 1
        print(f'[{index}/{len(ids)}] movie={movie_id} {movie.title}', flush=True)
        attach_extracted_subtitle(movie, timeout_seconds=90)
        movie.refresh_from_db(fields=['subtitle_tracks', 'has_subtitle'])
        if movie.subtitle_tracks:
            stats['attached'] += 1
            print(f'  -> attached {len(movie.subtitle_tracks)}', flush=True)
        else:
            stats['empty'] += 1
            print('  -> no tracks', flush=True)
        if cache.get('catalog:subtitlestar:circuit-open'):
            stats['blocked'] += 1
            print('circuit opened — pause loop', flush=True)
            time.sleep(max(60.0, float(args.pause_seconds) * 3))
            continue
        time.sleep(max(0.0, float(args.pause_seconds)))

    print('NEW_MOVIE_SOFTSUB_DONE', stats, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
