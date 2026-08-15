#!/usr/bin/env python3
"""Attach player-synced WebVTT for newly imported movies (SubtitleStar by default)."""

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
    from django.utils import timezone
    from datetime import timedelta

    from apps.catalog.models import Movie
    from apps.catalog.subtitle_extract import (
        attach_extracted_subtitle,
        download_links_imply_softsub,
    )
    from apps.catalog.cache import bump_catalog_cache_version

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ids-file', default='')
    parser.add_argument('--hours', type=float, default=12.0, help='Select published movies created in last N hours')
    parser.add_argument('--pause-seconds', type=float, default=20.0)
    parser.add_argument('--ffmpeg-timeout', type=int, default=55)
    parser.add_argument('--ss-timeout', type=int, default=55)
    parser.add_argument(
        '--allow-ffmpeg',
        action='store_true',
        default=False,
        help='Optional SoftSub demux fallback after SubtitleStar miss',
    )
    parser.add_argument('--no-ffmpeg', action='store_false', dest='allow_ffmpeg')
    args = parser.parse_args()

    ids: list[int] = []
    if args.ids_file and Path(args.ids_file).exists():
        for line in Path(args.ids_file).read_text().splitlines():
            line = line.strip()
            if line.isdigit():
                ids.append(int(line))
    else:
        cutoff = timezone.now() - timedelta(hours=max(1.0, float(args.hours)))
        ids = list(
            Movie.objects.filter(is_published=True, created_at__gte=cutoff)
            .order_by('id')
            .values_list('id', flat=True)
        )

    movies = list(Movie.objects.filter(pk__in=ids, is_published=True).order_by('-popularity', 'id'))
    pending = [m for m in movies if not m.subtitle_tracks]
    # Prefer titles SubtitleStar is most likely to have (IMDb + older/popular).
    pending.sort(
        key=lambda m: (
            0 if (m.imdb_id or '').strip() else 1,
            -(float(m.popularity or 0)),
            -(int(getattr(m, 'release_year', None) or 0)),
            m.pk,
        )
    )
    print(
        f'target={len(movies)} pending={len(pending)} '
        f'ffmpeg={args.allow_ffmpeg} pause={args.pause_seconds}',
        flush=True,
    )

    stats = {
        'tried': 0,
        'ss_or_ffmpeg': 0,
        'empty': 0,
        'blocked': 0,
        'already': len(movies) - len(pending),
    }

    for index, movie in enumerate(pending, start=1):
        while cache.get('catalog:subtitlestar:circuit-open'):
            print('waiting SubtitleStar circuit...', flush=True)
            time.sleep(45)

        stats['tried'] += 1
        soft = download_links_imply_softsub(movie.download_links or [])
        print(
            f'[{index}/{len(pending)}] movie={movie.pk} soft={soft} imdb={movie.imdb_id} {movie.title}',
            flush=True,
        )
        # Pass 1: SubtitleStar only (fast path).
        changed = attach_extracted_subtitle(
            movie,
            force=False,
            timeout_seconds=max(20, int(args.ss_timeout)),
            allow_ffmpeg=False,
        )
        movie.refresh_from_db(fields=['subtitle_tracks', 'has_subtitle'])

        # Pass 2: Soft ffmpeg when Soft encodes exist and SS missed.
        if not movie.subtitle_tracks and args.allow_ffmpeg and soft:
            if cache.get('catalog:subtitlestar:circuit-open'):
                stats['blocked'] += 1
                print('  -> circuit open before ffmpeg; defer', flush=True)
                time.sleep(60)
                continue
            print('  -> SS miss; trying Soft ffmpeg extract', flush=True)
            changed = attach_extracted_subtitle(
                movie,
                force=False,
                timeout_seconds=max(30, int(args.ffmpeg_timeout)),
                allow_ffmpeg=True,
            )
            movie.refresh_from_db(fields=['subtitle_tracks', 'has_subtitle'])

        if movie.subtitle_tracks:
            stats['ss_or_ffmpeg'] += 1
            print(f'  -> attached tracks={len(movie.subtitle_tracks)} changed={changed}', flush=True)
        else:
            stats['empty'] += 1
            print('  -> still no WebVTT', flush=True)

        if cache.get('catalog:subtitlestar:circuit-open'):
            stats['blocked'] += 1
            print('circuit opened — cooling down 90s', flush=True)
            time.sleep(90)
            continue
        time.sleep(max(0.0, float(args.pause_seconds)))

    try:
        bump_catalog_cache_version()
    except Exception:
        pass

    remaining = Movie.objects.filter(pk__in=ids, is_published=True)
    still = sum(1 for m in remaining if not m.subtitle_tracks)
    with_tracks = sum(1 for m in remaining if m.subtitle_tracks)
    stats['with_tracks_final'] = with_tracks
    stats['still_missing'] = still
    print('NEW_MOVIES_PLAYER_SOFTSUB_DONE', stats, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
