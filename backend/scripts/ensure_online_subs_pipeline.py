#!/usr/bin/env python3
"""Backfill online-player Persian WebVTT for published movies then series.

Movies (SubtitleStar-first, no slow ffmpeg CDN demux in bulk):
  1) SoftSub-only without VTT
  2) Dub-only without VTT
  3) Remaining titles without VTT (HardSub already shows burned-in text)

Then series: SubtitleStar episode packs via attach_series_softsub_tracks.
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
    from django.db.models import Q

    from apps.catalog.models import Episode, Movie, Series
    from apps.catalog.subtitle_extract import (
        _ranked_movie_stream_urls,
        attach_extracted_subtitle,
        attach_series_softsub_tracks,
        download_links_imply_dub,
        download_links_imply_softsub,
        looks_like_hardsub_link,
        url_implies_softsub,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pause-seconds', type=float, default=5.0)
    parser.add_argument('--movie-limit', type=int, default=0)
    parser.add_argument('--series-limit', type=int, default=0)
    parser.add_argument('--episode-limit', type=int, default=120)
    parser.add_argument('--movies-only', action='store_true')
    parser.add_argument('--series-only', action='store_true')
    parser.add_argument('--allow-ffmpeg', action='store_true', default=False)
    parser.add_argument(
        '--soft-encodes-only',
        action='store_true',
        default=False,
        help='Only Soft CDN encodes (skip Dub-only backlog).',
    )
    parser.add_argument(
        '--include-hardsub-vtt',
        action='store_true',
        default=False,
        help='Also attach VTT for titles that already have burned-in HardSub (slow).',
    )
    args = parser.parse_args()
    pause = max(0.0, float(args.pause_seconds))

    def wait_circuit():
        while cache.get('catalog:subtitlestar:circuit-open'):
            print('circuit open — waiting', flush=True)
            time.sleep(25)

    def movie_priority(movie: Movie) -> int | None:
        if movie.subtitle_tracks:
            return None
        links = [i for i in (movie.download_links or []) if isinstance(i, dict)]
        if not _ranked_movie_stream_urls(links):
            return None
        true_soft = any(url_implies_softsub(i) for i in links)
        soft = download_links_imply_softsub(links)
        hard = any(looks_like_hardsub_link(i) for i in links)
        dub = download_links_imply_dub(links)
        # Soft CDN encodes need WebVTT for online Soft playback (even when Hard exists).
        if true_soft:
            return 1
        if soft and not hard:
            return 1
        if not movie.imdb_id:
            return None
        if dub and not soft and not hard:
            return 2
        if soft or hard or dub:
            return 3
        return None

    stats = {
        'movies_tried': 0,
        'movies_attached': 0,
        'movies_empty': 0,
        'series_tried': 0,
        'series_attached_eps': 0,
    }

    if not args.series_only:
        buckets: dict[int, list] = {1: [], 2: [], 3: []}
        for movie in Movie.objects.filter(is_published=True).order_by('-updated_at', '-id').iterator(chunk_size=150):
            prio = movie_priority(movie)
            if prio is None:
                continue
            # Skip Hard/Dub-only (prio 3) unless asked — Soft encodes (prio 1) always run.
            if prio == 3 and not args.include_hardsub_vtt:
                continue
            # Dub-only is optional when Soft backfill is the priority.
            if prio == 2 and getattr(args, 'soft_encodes_only', False):
                continue
            buckets[prio].append(movie)
        ordered = buckets[1] + buckets[2] + buckets[3]
        if args.movie_limit:
            ordered = ordered[: max(1, int(args.movie_limit))]
        print(
            f'phase=movies soft={len(buckets[1])} dub={len(buckets[2])} other={len(buckets[3])} '
            f'run={len(ordered)} ffmpeg={bool(args.allow_ffmpeg)}',
            flush=True,
        )
        for index, movie in enumerate(ordered, start=1):
            wait_circuit()
            movie.refresh_from_db(fields=['subtitle_tracks', 'download_links', 'imdb_id'])
            if movie.subtitle_tracks:
                continue
            prio = movie_priority(movie) or 3
            stats['movies_tried'] += 1
            print(f'[movie {index}/{len(ordered)}] prio={prio} id={movie.pk} {movie.title}', flush=True)
            try:
                # Bulk path: SubtitleStar only. Soft CDN ffmpeg often times out (~4min)
                # and stalls the whole backfill; soft-only demux stays on Celery tasks.
                attach_extracted_subtitle(
                    movie,
                    timeout_seconds=90,
                    allow_ffmpeg=False,
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
                links = movie.download_links or []
                if any(looks_like_hardsub_link(i) for i in links if isinstance(i, dict)):
                    print('  -> no VTT (HardSub still visible in player)', flush=True)
                else:
                    print('  -> no tracks', flush=True)
            time.sleep(pause)

    if not args.movies_only:
        # Prefer Soft-only series (no HardSub) — they have no burned-in fallback online.
        soft_only_ids: list[int] = []
        other_ids: list[int] = []
        missing_q = Q(subtitle_tracks__isnull=True) | Q(subtitle_tracks=[])
        for series in Series.objects.filter(is_published=True).order_by('-popularity', 'id').iterator(chunk_size=80):
            links = [item for item in (series.download_links or []) if isinstance(item, dict)]
            hard = any(looks_like_hardsub_link(item) for item in links)
            soft = any(url_implies_softsub(item) for item in links) or download_links_imply_softsub(links)
            missing = Episode.objects.filter(
                season__series_id=series.pk,
                is_published=True,
            ).filter(missing_q).exclude(video_url='').exclude(video_url__isnull=True).exists()
            if not missing:
                continue
            if soft and not hard:
                soft_only_ids.append(series.pk)
            elif series.imdb_id:
                other_ids.append(series.pk)
        series_ids = soft_only_ids + other_ids
        if args.series_limit:
            series_ids = series_ids[: max(1, int(args.series_limit))]
        print(
            f'phase=series soft_only={len(soft_only_ids)} other={len(other_ids)} '
            f'run={len(series_ids)} episode_limit={args.episode_limit}',
            flush=True,
        )
        for index, series_id in enumerate(series_ids, start=1):
            series = Series.objects.filter(pk=series_id, is_published=True).first()
            if series is None:
                continue
            links = [item for item in (series.download_links or []) if isinstance(item, dict)]
            soft_only = (
                (any(url_implies_softsub(item) for item in links) or download_links_imply_softsub(links))
                and not any(looks_like_hardsub_link(item) for item in links)
            )
            if not soft_only:
                wait_circuit()
            stats['series_tried'] += 1
            print(
                f'[series {index}/{len(series_ids)}] id={series.pk} soft_only={soft_only} {series.title}',
                flush=True,
            )
            try:
                result = attach_series_softsub_tracks(
                    series,
                    force=False,
                    timeout_seconds=120 if not soft_only else 180,
                    limit=max(1, int(args.episode_limit)),
                    # Avoid Soft CDN demux in bulk; Celery handles soft-only ffmpeg.
                    allow_ffmpeg=False,
                )
            except Exception as exc:
                print(f'  -> error {type(exc).__name__}: {exc}', flush=True)
                time.sleep(pause)
                continue
            attached = int(result.get('attached') or result.get('extracted') or result.get('subtitlestar_attached') or 0)
            stats['series_attached_eps'] += attached
            print(f'  -> result attached≈{attached} raw={ {k: result.get(k) for k in list(result)[:8]} }', flush=True)
            time.sleep(pause)

    print('ENSURE_ONLINE_SUBS_PIPELINE_DONE', stats, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
