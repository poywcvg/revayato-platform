#!/usr/bin/env python
"""Import/enrich all 2026 movies+series from myf2m+dornatv without duplicates.

Phases:
  1) Dornatv missing-import for year 2026 (TMDB/IMDb dedupe; create+publish only new)
  2) Enrich existing 2026 titles missing playback / dub / softsub via multi-provider crawl
  3) Publish unpublished 2026 rows that gained playable links
  4) Queue SoftSub / SubtitleStar where needed

Safe to re-run; skips titles that already have solid coverage.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if not (_APP_ROOT / 'config').is_dir():
    _APP_ROOT = Path('/app')
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from django.db.models import Q

from apps.catalog.models import Movie, Series
from apps.catalog.provider_import.dornatv_import import run_dornatv_missing_import
from apps.catalog.provider_import.multi_provider_crawl import (
    crawl_catalog_downloads_for_movie,
    crawl_catalog_downloads_for_series,
)
from apps.catalog.subtitle_extract import (
    download_links_imply_dub,
    download_links_imply_softsub,
    download_links_imply_subtitle,
)
from apps.catalog.tasks import enqueue_movie_softsub, enqueue_series_softsub
from apps.catalog.top_catalog import _has_download_links, _publish_movie, _publish_series

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger('import_2026')


def _coverage(obj) -> dict:
    links = getattr(obj, 'download_links', None) or []
    has_links = _has_download_links(obj)
    has_dub = download_links_imply_dub(links)
    has_soft = download_links_imply_softsub(links)
    has_sub = has_soft or download_links_imply_subtitle(links) or bool(getattr(obj, 'subtitle_tracks', None))
    has_play = has_links or bool(str(getattr(obj, 'video_url', '') or '').strip())
    return {
        'has_links': has_links,
        'has_play': has_play,
        'has_dub': has_dub,
        'has_sub': has_sub,
        'complete': has_play and has_dub and has_sub,
    }


def phase_dornatv_missing(*, movies_limit: int, series_limit: int, rounds: int, delay: float) -> dict:
    """Pull remaining 2026 titles from Dornatv until a quiet round."""
    totals = {
        'movies_created': 0,
        'series_created': 0,
        'skipped_existing': 0,
        'rounds': 0,
    }
    for round_no in range(1, rounds + 1):
        logger.info('dornatv missing round %s/%s movies=%s series=%s', round_no, rounds, movies_limit, series_limit)
        result = run_dornatv_missing_import(
            movies_limit=movies_limit,
            series_limit=series_limit,
            year_start=2026,
            year_end=2026,
            delay=delay,
            dry_run=False,
            queue_softsub=True,
            checkpoint_path='/app/media/dornatv_import_checkpoint_2026.json',
        )
        totals['rounds'] += 1
        created_m = int(result.get('movies_created') or result.get('movies_kept') or 0)
        created_s = int(result.get('series_created') or result.get('series_kept') or 0)
        totals['movies_created'] += created_m
        totals['series_created'] += created_s
        totals['skipped_existing'] += int(result.get('skipped_existing') or 0)
        logger.info('dornatv round result: %s', {k: result.get(k) for k in (
            'status', 'movies_kept', 'series_kept', 'movies_created', 'series_created',
            'skipped_existing', 'skipped_tmdb_miss', 'no_links', 'errors', 'softsub_queued',
            'movie_page', 'series_page', 'movie_year', 'series_year',
        )})
        if created_m == 0 and created_s == 0:
            logger.info('dornatv quiet round — stopping missing-import phase')
            break
        time.sleep(1)
    return totals


def _needs_enrich(obj) -> bool:
    cov = _coverage(obj)
    if not cov['has_play']:
        return True
    # Prefer filling missing dub OR missing sub when at least one encode family is absent.
    if not cov['has_dub'] or not cov['has_sub']:
        return True
    return False


def phase_enrich(*, limit: int | None, delay: float, movies: bool, series: bool) -> dict:
    stats = {
        'movies_considered': 0,
        'movies_crawled_ok': 0,
        'movies_failed': 0,
        'movies_published': 0,
        'series_considered': 0,
        'series_crawled_ok': 0,
        'series_failed': 0,
        'series_published': 0,
        'skipped_complete': 0,
    }

    if movies:
        qs = (
            Movie.objects.filter(release_year=2026)
            .order_by('-is_published', '-popularity', 'id')
        )
        for obj in qs.iterator(chunk_size=50):
            if limit is not None and stats['movies_considered'] >= limit:
                break
            if not _needs_enrich(obj):
                stats['skipped_complete'] += 1
                continue
            stats['movies_considered'] += 1
            was_published = bool(obj.is_published)
            try:
                crawl_catalog_downloads_for_movie(
                    movie=obj,
                    replace=False,
                    queue_softsub_extract=True,
                )
                obj.refresh_from_db()
                stats['movies_crawled_ok'] += 1
            except Exception as exc:
                stats['movies_failed'] += 1
                logger.info('movie crawl fail id=%s %s: %s', obj.pk, obj.title, exc)
                continue
            if _has_download_links(obj) and not was_published:
                try:
                    _publish_movie(obj)
                    stats['movies_published'] += 1
                except Exception as exc:
                    logger.info('movie publish fail id=%s: %s', obj.pk, exc)
            if delay:
                time.sleep(delay)
            if stats['movies_considered'] % 25 == 0:
                logger.info('movie enrich progress %s ok=%s fail=%s pub+=%s',
                            stats['movies_considered'], stats['movies_crawled_ok'],
                            stats['movies_failed'], stats['movies_published'])

    if series:
        qs = (
            Series.objects.filter(start_year=2026)
            .order_by('-is_published', '-popularity', 'id')
        )
        for obj in qs.iterator(chunk_size=25):
            if limit is not None and stats['series_considered'] >= limit:
                break
            if not _needs_enrich(obj):
                stats['skipped_complete'] += 1
                continue
            stats['series_considered'] += 1
            was_published = bool(obj.is_published)
            try:
                crawl_catalog_downloads_for_series(
                    series=obj,
                    replace=False,
                    queue_softsub_extract=True,
                )
                obj.refresh_from_db()
                stats['series_crawled_ok'] += 1
            except Exception as exc:
                stats['series_failed'] += 1
                logger.info('series crawl fail id=%s %s: %s', obj.pk, obj.title, exc)
                continue
            if _has_download_links(obj) and not was_published:
                try:
                    _publish_series(obj)
                    stats['series_published'] += 1
                except Exception as exc:
                    logger.info('series publish fail id=%s: %s', obj.pk, exc)
            if delay:
                time.sleep(delay)
            if stats['series_considered'] % 10 == 0:
                logger.info('series enrich progress %s ok=%s fail=%s pub+=%s',
                            stats['series_considered'], stats['series_crawled_ok'],
                            stats['series_failed'], stats['series_published'])

    return stats


def phase_softsub_queue(*, limit_movies: int, limit_series: int) -> dict:
    stats = {'movies_queued': 0, 'series_queued': 0}
    movies = (
        Movie.objects.filter(release_year=2026, is_published=True)
        .filter(Q(subtitle_tracks=[]) | Q(subtitle_tracks__isnull=True))
        .order_by('-popularity', 'id')[:limit_movies]
    )
    for obj in movies:
        links = obj.download_links or []
        if not (download_links_imply_softsub(links) or obj.imdb_id):
            continue
        try:
            if enqueue_movie_softsub(obj.pk, force=False):
                stats['movies_queued'] += 1
        except Exception as exc:
            logger.info('softsub movie queue fail %s: %s', obj.pk, exc)

    series = (
        Series.objects.filter(start_year=2026, is_published=True)
        .order_by('-popularity', 'id')[:limit_series]
    )
    for obj in series:
        links = obj.download_links or []
        if not (download_links_imply_softsub(links) or obj.imdb_id):
            continue
        try:
            if enqueue_series_softsub(obj.pk, force=False, episode_limit=40):
                stats['series_queued'] += 1
        except Exception as exc:
            logger.info('softsub series queue fail %s: %s', obj.pk, exc)
    return stats


def report() -> dict:
    from apps.catalog.models import Episode

    movies = Movie.objects.filter(release_year=2026)
    series = Series.objects.filter(start_year=2026)
    mp = movies.filter(is_published=True)
    sp = series.filter(is_published=True)

    def count_cov(qs):
        dub = sub = play = both = 0
        only_fields = ['download_links']
        if any(field.name == 'subtitle_tracks' for field in qs.model._meta.get_fields()):
            only_fields.append('subtitle_tracks')
        for obj in qs.only(*only_fields).iterator():
            cov = _coverage(obj)
            dub += int(cov['has_dub'])
            sub += int(cov['has_sub'])
            play += int(cov['has_play'])
            both += int(cov['has_dub'] and cov['has_sub'])
        return {'dub': dub, 'sub': sub, 'play': play, 'both': both}

    out = {
        'movies_total': movies.count(),
        'movies_published': mp.count(),
        'series_total': series.count(),
        'series_published': sp.count(),
        'episodes_published': Episode.objects.filter(
            season__series__start_year=2026, is_published=True,
        ).count(),
        'movies_cov': count_cov(mp),
        'series_cov': count_cov(sp),
    }
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-dornatv', action='store_true')
    parser.add_argument('--skip-enrich', action='store_true')
    parser.add_argument('--skip-softsub', action='store_true')
    parser.add_argument('--movies-only', action='store_true')
    parser.add_argument('--series-only', action='store_true')
    parser.add_argument('--enrich-limit', type=int, default=0, help='0 = no limit')
    parser.add_argument('--dornatv-rounds', type=int, default=8)
    parser.add_argument('--dornatv-movies', type=int, default=40)
    parser.add_argument('--dornatv-series', type=int, default=20)
    parser.add_argument('--delay', type=float, default=0.25)
    args = parser.parse_args()

    do_movies = not args.series_only
    do_series = not args.movies_only
    enrich_limit = args.enrich_limit or None

    logger.info('=== 2026 catalog bootstrap start ===')
    logger.info('before: %s', report())

    if not args.skip_dornatv:
        dornatv_stats = phase_dornatv_missing(
            movies_limit=args.dornatv_movies if do_movies else 0,
            series_limit=args.dornatv_series if do_series else 0,
            rounds=args.dornatv_rounds,
            delay=args.delay,
        )
        logger.info('dornatv phase: %s', dornatv_stats)

    if not args.skip_enrich:
        enrich_stats = phase_enrich(
            limit=enrich_limit,
            delay=args.delay,
            movies=do_movies,
            series=do_series,
        )
        logger.info('enrich phase: %s', enrich_stats)

    if not args.skip_softsub:
        soft_stats = phase_softsub_queue(limit_movies=800, limit_series=400)
        logger.info('softsub phase: %s', soft_stats)

    final = report()
    logger.info('=== 2026 catalog bootstrap done ===')
    logger.info('after: %s', final)
    print('FINAL_REPORT', final)


if __name__ == '__main__':
    main()
