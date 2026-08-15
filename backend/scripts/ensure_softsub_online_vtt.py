#!/usr/bin/env python3
"""Attach Persian WebVTT for SoftSub encodes so online Soft playback shows cues.

Targets published movies that have a Soft/SUB/BluSUB (etc.) encode but no
``subtitle_tracks`` yet — including Soft+Hard rows that the generic pipeline
skipped because burned-in HardSub already looked “done”.

Order:
  1) SoftSub-only (player otherwise has no Persian text)
  2) Soft+Hard (enable Soft toggle instead of Hard fallback)
  3) Optional series Soft episodes

SubtitleStar first; ``--allow-ffmpeg`` demuxes Soft mirrors when Star misses.
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

    from django.core.cache import cache
    from django.db import connection

    from apps.catalog.models import Movie, Series
    from apps.catalog.subtitle_extract import (
        _ranked_movie_stream_urls,
        attach_extracted_subtitle,
        attach_series_softsub_tracks,
        looks_like_hardsub_link,
        url_implies_softsub,
    )
    from apps.catalog.subtitle_star import normalize_imdb_id

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pause-seconds', type=float, default=2.0)
    parser.add_argument('--movie-limit', type=int, default=0)
    parser.add_argument('--series-limit', type=int, default=0)
    parser.add_argument('--episode-limit', type=int, default=80)
    parser.add_argument('--movies-only', action='store_true')
    parser.add_argument('--series-only', action='store_true')
    parser.add_argument(
        '--allow-ffmpeg',
        action='store_true',
        default=False,
        help='Demux Soft CDN embeds when SubtitleStar has no pack (slower).',
    )
    parser.add_argument(
        '--clear-miss-cache',
        action='store_true',
        default=True,
        help='Drop SubtitleStar negative cache before Soft lookups (default on).',
    )
    parser.add_argument('--keep-miss-cache', action='store_true', default=False)
    args = parser.parse_args()
    pause = max(0.0, float(args.pause_seconds))
    clear_miss = bool(args.clear_miss_cache) and not bool(args.keep_miss_cache)

    def wait_circuit():
        while cache.get('catalog:subtitlestar:circuit-open'):
            print('circuit open — waiting', flush=True)
            time.sleep(20)

    def soft_priority(movie: Movie) -> int | None:
        if movie.subtitle_tracks:
            return None
        links = [i for i in (movie.download_links or []) if isinstance(i, dict)]
        if not any(url_implies_softsub(i) for i in links):
            return None
        if not _ranked_movie_stream_urls(links):
            return None
        # Soft-only first; Soft+Hard second (Hard still visible without VTT).
        hard = any(looks_like_hardsub_link(i) for i in links)
        return 1 if not hard else 2

    if clear_miss:
        try:
            client = cache._cache.get_client()
            deleted = 0
            for pattern in ('*subtitlestar:miss:*', '*subtitlestar:series-miss:*'):
                for key in client.scan_iter(match=pattern, count=400):
                    client.delete(key)
                    deleted += 1
            print(f'cleared_miss_keys={deleted}', flush=True)
        except Exception as exc:
            print(f'clear_miss_cache_error={type(exc).__name__}:{exc}', flush=True)

    stats = {
        'movies_tried': 0,
        'movies_attached': 0,
        'movies_empty': 0,
        'series_tried': 0,
        'series_attached_eps': 0,
    }

    if not args.series_only:
        buckets: dict[int, list] = {1: [], 2: []}
        for movie in Movie.objects.filter(is_published=True).order_by('-updated_at', '-id').iterator(chunk_size=150):
            prio = soft_priority(movie)
            if prio is None:
                continue
            # Prefer IMDb rows for SubtitleStar; still queue Soft-only without IMDb for ffmpeg.
            if not normalize_imdb_id(movie.imdb_id) and not args.allow_ffmpeg and prio == 2:
                continue
            buckets[prio].append(movie)
        ordered = buckets[2] + buckets[1]
        if args.movie_limit:
            ordered = ordered[: max(1, int(args.movie_limit))]
        print(
            f'phase=softsub-movies soft_only={len(buckets[1])} soft_plus_hard={len(buckets[2])} '
            f'run={len(ordered)} ffmpeg={bool(args.allow_ffmpeg)} '
            f'order=soft+hard_then_soft-only',
            flush=True,
        )
        for index, movie in enumerate(ordered, start=1):
            wait_circuit()
            movie.refresh_from_db(fields=['subtitle_tracks', 'download_links', 'imdb_id'])
            if movie.subtitle_tracks:
                continue
            prio = soft_priority(movie) or 2
            stats['movies_tried'] += 1
            # ffmpeg only when explicitly enabled (Soft CDN demux is often minutes/title).
            use_ffmpeg = bool(args.allow_ffmpeg)
            print(
                f'[soft {index}/{len(ordered)}] prio={prio} id={movie.pk} '
                f'ffmpeg={use_ffmpeg} {movie.title}',
                flush=True,
            )
            try:
                attach_extracted_subtitle(
                    movie,
                    timeout_seconds=75 if not use_ffmpeg else 120,
                    allow_ffmpeg=use_ffmpeg,
                )
            except Exception as exc:
                print(f'  -> error {type(exc).__name__}: {exc}', flush=True)
                stats['movies_empty'] += 1
                time.sleep(pause)
                continue
            movie.refresh_from_db(fields=['subtitle_tracks'])
            if movie.subtitle_tracks:
                stats['movies_attached'] += 1
                print(f'  -> attached tracks={len(movie.subtitle_tracks)}', flush=True)
            else:
                stats['movies_empty'] += 1
                print('  -> no tracks', flush=True)
            time.sleep(pause)

    if not args.movies_only:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.id
                FROM catalog_series s
                WHERE s.is_published
                  AND COALESCE(s.imdb_id, '') <> ''
                ORDER BY s.updated_at DESC NULLS LAST, s.id DESC
                """
            )
            series_ids = [row[0] for row in cursor.fetchall()]
        if args.series_limit:
            series_ids = series_ids[: max(1, int(args.series_limit))]
        print(f'phase=softsub-series candidates={len(series_ids)}', flush=True)
        for index, series_id in enumerate(series_ids, start=1):
            wait_circuit()
            series = Series.objects.filter(pk=series_id, is_published=True).first()
            if series is None:
                continue
            links = [i for i in (series.download_links or []) if isinstance(i, dict)]
            if not any(url_implies_softsub(i) for i in links):
                continue
            stats['series_tried'] += 1
            print(f'[series {index}/{len(series_ids)}] id={series.pk} {series.title}', flush=True)
            try:
                result = attach_series_softsub_tracks(
                    series,
                    timeout_seconds=120,
                    limit=max(1, int(args.episode_limit)),
                    allow_ffmpeg=bool(args.allow_ffmpeg),
                )
            except Exception as exc:
                print(f'  -> error {type(exc).__name__}: {exc}', flush=True)
                time.sleep(pause)
                continue
            attached = int(result.get('extracted') or 0) + int(result.get('subtitlestar_attached') or 0)
            # extracted already includes subtitlestar in some paths — prefer reported extracted
            attached = int(result.get('extracted') or 0)
            if attached:
                stats['series_attached_eps'] += attached
                print(f'  -> attached episodes≈{attached}', flush=True)
            else:
                print('  -> no new episode tracks', flush=True)
            time.sleep(pause)

    print(f'DONE {stats}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
