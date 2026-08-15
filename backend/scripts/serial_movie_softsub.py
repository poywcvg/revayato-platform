#!/usr/bin/env python3
"""Attach SubtitleStar/SoftSub WebVTT for published movies missing online tracks."""

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
        download_links_imply_softsub,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pause-seconds', type=float, default=20.0)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--wait-circuit', action='store_true', default=True)
    parser.add_argument('--no-wait-circuit', action='store_false', dest='wait_circuit')
    parser.add_argument(
        '--allow-ffmpeg',
        action='store_true',
        default=False,
        help='Optional SoftSub demux fallback. Default is SubtitleStar-only for the online player.',
    )
    args = parser.parse_args()

    if args.wait_circuit:
        while cache.get('catalog:subtitlestar:circuit-open'):
            print('waiting for SubtitleStar circuit...', flush=True)
            time.sleep(30)

    movies = []
    for movie in (
        Movie.objects.filter(is_published=True)
        # Existing subtitle flags and older releases are far likelier to expose a
        # real embedded Persian stream than newly announced/future titles.
        .order_by('-has_subtitle', 'release_year', '-popularity', '-updated_at', '-id')
        .iterator(chunk_size=100)
    ):
        if movie.subtitle_tracks:
            continue
        links = movie.download_links or []
        eligible = bool(
            (getattr(settings, 'SUBTITLESTAR_ENABLED', True) and movie.imdb_id and _ranked_movie_stream_urls(links))
            or download_links_imply_softsub(links)
        )
        if eligible:
            movies.append(movie)
    if args.limit:
        movies = movies[: max(1, args.limit)]

    stats = {'tried': 0, 'attached': 0, 'empty': 0, 'blocked': 0}
    print(
        f'serial_movie_softsub movies={len(movies)} ffmpeg={args.allow_ffmpeg}',
        flush=True,
    )

    for index, movie in enumerate(movies, start=1):
        if cache.get('catalog:subtitlestar:circuit-open'):
            stats['blocked'] = 1
            if args.allow_ffmpeg:
                print('SubtitleStar circuit open — continuing with ffmpeg fallback', flush=True)
            else:
                print('waiting for SubtitleStar circuit...', flush=True)
                while cache.get('catalog:subtitlestar:circuit-open'):
                    time.sleep(30)
        stats['tried'] += 1
        print(f'[{index}/{len(movies)}] movie={movie.pk} {movie.title}', flush=True)
        # Online player SoftSub comes from SubtitleStar by default.
        changed = attach_extracted_subtitle(
            movie,
            timeout_seconds=90,
            allow_ffmpeg=bool(args.allow_ffmpeg),
        )
        movie.refresh_from_db(fields=['subtitle_tracks', 'has_subtitle'])
        if movie.subtitle_tracks:
            stats['attached'] += 1
            print(f'  -> attached tracks={len(movie.subtitle_tracks)} changed={changed}', flush=True)
        else:
            stats['empty'] += 1
            print('  -> no tracks', flush=True)
        time.sleep(max(0.0, float(args.pause_seconds)))

    remaining = Movie.objects.filter(is_published=True).filter(
        subtitle_tracks__isnull=True,
    ).count()
    # empty list also counts as missing in JSON
    empty_list = 0
    for tracks in Movie.objects.filter(is_published=True).values_list('subtitle_tracks', flat=True).iterator(chunk_size=200):
        if not tracks:
            empty_list += 1
    stats['missing_after'] = empty_list
    print('SERIAL_MOVIE_SOFTSUB_DONE', stats, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
