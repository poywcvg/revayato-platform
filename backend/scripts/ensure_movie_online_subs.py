#!/usr/bin/env python3
"""Ensure published movies can show Persian text in the online player.

Priority:
  1) SoftSub encode without WebVTT (player would show no cues)
  2) Dub-only without WebVTT (no burned-in Persian)
  3) Hard/Soft mix without WebVTT (burned-in ok; still attach Soft cues)

SubtitleStar first; ffmpeg SoftSub demux for priority-1 Soft encodes.
See docs/SUBTITLES.md.
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

    from django.conf import settings
    from django.core.cache import cache

    from apps.catalog.models import Movie
    from apps.catalog.subtitle_extract import (
        _ranked_movie_stream_urls,
        attach_extracted_subtitle,
        download_links_imply_dub,
        download_links_imply_softsub,
        looks_like_hardsub_link,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pause-seconds', type=float, default=6.0)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--prio-max', type=int, default=3, choices=(1, 2, 3))
    args = parser.parse_args()

    def priority_for(movie: Movie) -> int | None:
        if movie.subtitle_tracks:
            return None
        links = [i for i in (movie.download_links or []) if isinstance(i, dict)]
        if not _ranked_movie_stream_urls(links):
            return None
        has_soft = download_links_imply_softsub(links)
        has_hard = any(looks_like_hardsub_link(i) for i in links)
        has_dub = download_links_imply_dub(links)
        if has_soft and not has_hard:
            return 1
        if has_dub and not has_soft and not has_hard:
            return 2
        if has_soft or has_hard or has_dub:
            return 3
        return None

    buckets: dict[int, list] = {1: [], 2: [], 3: []}
    for movie in (
        Movie.objects.filter(is_published=True)
        .order_by('-updated_at', '-id')
        .iterator(chunk_size=150)
    ):
        prio = priority_for(movie)
        if prio is None or prio > args.prio_max:
            continue
        if not movie.imdb_id and prio != 1:
            continue
        buckets[prio].append(movie)

    ordered = buckets[1] + buckets[2] + buckets[3]
    if args.limit:
        ordered = ordered[: max(1, int(args.limit))]

    pause = max(0.0, float(args.pause_seconds))
    print(
        f'ensure_online_subs soft={len(buckets[1])} dub={len(buckets[2])} '
        f'other={len(buckets[3])} run={len(ordered)} pause={pause}',
        flush=True,
    )

    stats = {'tried': 0, 'attached': 0, 'empty': 0, 'by_prio': {1: 0, 2: 0, 3: 0}}
    for index, movie in enumerate(ordered, start=1):
        while cache.get('catalog:subtitlestar:circuit-open'):
            print('circuit open — waiting', flush=True)
            time.sleep(30)

        movie.refresh_from_db(fields=['subtitle_tracks', 'download_links', 'imdb_id', 'has_subtitle'])
        if movie.subtitle_tracks:
            continue

        prio = priority_for(movie) or 3
        allow_ffmpeg = prio == 1  # Soft-only: allow demux when SubtitleStar misses

        stats['tried'] += 1
        print(
            f'[{index}/{len(ordered)}] prio={prio} id={movie.pk} imdb={movie.imdb_id} {movie.title}',
            flush=True,
        )
        try:
            attach_extracted_subtitle(
                movie,
                timeout_seconds=100,
                allow_ffmpeg=allow_ffmpeg,
            )
        except Exception as exc:
            print(f'  -> error {type(exc).__name__}: {exc}', flush=True)
            stats['empty'] += 1
            time.sleep(pause)
            continue

        movie.refresh_from_db(fields=['subtitle_tracks', 'has_subtitle'])
        if movie.subtitle_tracks:
            stats['attached'] += 1
            stats['by_prio'][prio] = stats['by_prio'].get(prio, 0) + 1
            print(f'  -> attached tracks={len(movie.subtitle_tracks)}', flush=True)
        else:
            stats['empty'] += 1
            links = movie.download_links or []
            if any(looks_like_hardsub_link(i) for i in links if isinstance(i, dict)):
                print('  -> no VTT (HardSub burned-in still visible)', flush=True)
            else:
                print('  -> no tracks', flush=True)
        time.sleep(pause)

    print('ENSURE_MOVIE_ONLINE_SUBS_DONE', stats, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
