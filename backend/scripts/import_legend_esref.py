#!/usr/bin/env python3
"""Import Legend (2015) and Eşref Rüya / اشرف رویا with full metadata + playback.

Pipeline:
  Movie: TMDB upsert → Persian title → publish → feature → myf2m+dornatv crawl
         → SoftSub queue (+ synchronous attach fallback)
  Series: TMDB upsert → Persian title → publish → feature → myf2m+dornatv crawl
          → Season/Episode stubs from links → SoftSub queue

Run inside the backend container:

  python /app/scripts/import_legend_esref.py
  python /app/scripts/import_legend_esref.py --dry-run
  python /app/scripts/import_legend_esref.py --skip-crawl
  python /app/scripts/import_legend_esref.py --force-softsub
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

for _candidate in (Path('/app'), Path(__file__).resolve().parents[1]):
    if (_candidate / 'config' / 'settings.py').exists():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        break

LEGEND_TMDB_ID = 276907
LEGEND_PERSIAN_TITLE = 'لجند'
LEGEND_ORIGINAL_TITLE = 'Legend'

ESREF_TMDB_ID = 283123
ESREF_PERSIAN_TITLE = 'اشرف رویا'
ESREF_ORIGINAL_TITLE = 'Eşref Rüya'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--skip-crawl', action='store_true')
    parser.add_argument('--force-softsub', action='store_true')
    parser.add_argument('--episode-limit', type=int, default=80)
    parser.add_argument('--delay', type=float, default=0.5)
    args = parser.parse_args()

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from apps.catalog.cache import bump_catalog_cache_version
    from apps.catalog.importer_config import get_importer_settings
    from apps.catalog.ingestion import upsert_tmdb_movie, upsert_tmdb_series
    from apps.catalog.models import Episode, Movie, Season, Series
    from apps.catalog.subtitle_extract import (
        download_links_imply_dub,
        download_links_imply_softsub,
        download_links_imply_subtitle,
        ensure_episodes_from_download_links,
    )
    from apps.catalog.tasks import enqueue_movie_softsub, enqueue_series_softsub
    from apps.catalog.tmdb import TMDBError, configured_tmdb_client
    from apps.catalog.top_catalog import (
        _crawl_movie_links,
        _crawl_series_links,
        _has_download_links,
        _publish_movie,
        _publish_series,
        _version_coverage,
    )

    print(
        f'Legend + Eşref Rüya import movie_tmdb={LEGEND_TMDB_ID} '
        f'series_tmdb={ESREF_TMDB_ID} dry_run={args.dry_run}',
        flush=True,
    )

    if args.dry_run:
        movie = Movie.objects.filter(tmdb_id=LEGEND_TMDB_ID).first()
        if movie:
            print(
                f'  MOVIE pk={movie.pk} title={movie.title!r} pub={movie.is_published} '
                f'links={len(movie.download_links or [])} tracks={len(movie.subtitle_tracks or [])} '
                f'dub={movie.is_dubbed} sub={movie.has_subtitle} slug={movie.slug}',
                flush=True,
            )
        else:
            print('  MOVIE exists=False', flush=True)
        series = Series.objects.filter(tmdb_id=ESREF_TMDB_ID).first()
        if series:
            eps = Episode.objects.filter(season__series=series)
            print(
                f'  SERIES pk={series.pk} title={series.title!r} pub={series.is_published} '
                f'links={len(series.download_links or [])} '
                f'seasons={Season.objects.filter(series=series).count()} eps={eps.count()} '
                f'dub={series.is_dubbed} sub={series.has_subtitle} slug={series.slug}',
                flush=True,
            )
        else:
            print('  SERIES exists=False', flush=True)
        return 0

    client = configured_tmdb_client()
    importer = get_importer_settings()

    # ------------------------------------------------------------------ movie
    print('\n=== MOVIE: Legend (2015) ===', flush=True)
    try:
        details = client.movie_details(LEGEND_TMDB_ID)
    except TMDBError as exc:
        print(f'ERROR: TMDB movie {exc}', file=sys.stderr)
        return 1

    title = details.get('title') or details.get('original_title') or LEGEND_ORIGINAL_TITLE
    print(f'  tmdb_title={title!r}', flush=True)

    movie, created, _, _ = upsert_tmdb_movie(details, importer=importer)
    print(f'  upsert pk={movie.pk} created={created}', flush=True)

    fields: list[str] = []
    if (movie.title or '').strip() != LEGEND_PERSIAN_TITLE:
        movie.title = LEGEND_PERSIAN_TITLE
        fields.append('title')
    if not (movie.original_title or '').strip():
        movie.original_title = LEGEND_ORIGINAL_TITLE
        fields.append('original_title')
    if not movie.is_featured:
        movie.is_featured = True
        fields.append('is_featured')
    if not movie.is_recommended:
        movie.is_recommended = True
        fields.append('is_recommended')
    if fields:
        movie.save(update_fields=[*fields, 'updated_at'])
        print(f'  localized fields={fields}', flush=True)

    if _publish_movie(movie):
        print('  published=True', flush=True)
    else:
        print('  published=already', flush=True)

    if not args.skip_crawl:
        crawl = _crawl_movie_links(movie, replace=True, resolve_english=True)
        movie.refresh_from_db(
            fields=['download_links', 'is_dubbed', 'has_subtitle', 'updated_at'],
        )
        if args.delay > 0:
            time.sleep(args.delay)
        cov = _version_coverage(movie)
        links = movie.download_links or []
        print(
            f'  crawl={crawl.get("status")} imported={crawl.get("imported_count")} '
            f'links={len(links)} dub={cov.get("has_dub")} sub={cov.get("has_sub")} '
            f'imply_dub={download_links_imply_dub(links)} '
            f'imply_sub={download_links_imply_subtitle(links)} '
            f'imply_soft={download_links_imply_softsub(links)}',
            flush=True,
        )
        if not _has_download_links(movie):
            print('ERROR: no movie download links after crawl', file=sys.stderr)
            return 1

        # SoftSub WebVTT for the online player (async + sync fallback).
        try:
            from apps.catalog.subtitle_extract import attach_extracted_subtitle

            has_tracks = bool(movie.subtitle_tracks)
            if not has_tracks or args.force_softsub:
                queued = enqueue_movie_softsub(movie.pk, force=bool(args.force_softsub or not has_tracks))
                print(f'  softsub_queued={queued}', flush=True)
                movie.refresh_from_db(fields=['subtitle_tracks'])
                if not movie.subtitle_tracks:
                    if attach_extracted_subtitle(
                        movie,
                        force=bool(args.force_softsub or not movie.subtitle_tracks),
                        timeout_seconds=240,
                        allow_ffmpeg=True,
                    ):
                        print('  softsub attached synchronously', flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f'  softsub warn: {exc}', flush=True)

    # ----------------------------------------------------------------- series
    print('\n=== SERIES: Eşref Rüya / اشرف رویا ===', flush=True)
    try:
        details = client.tv_details(ESREF_TMDB_ID)
    except TMDBError as exc:
        print(f'ERROR: TMDB series {exc}', file=sys.stderr)
        return 1

    title = details.get('name') or details.get('original_name') or ESREF_ORIGINAL_TITLE
    print(f'  tmdb_title={title!r}', flush=True)

    series, created = upsert_tmdb_series(details, importer=importer)
    print(f'  upsert pk={series.pk} created={created}', flush=True)

    fields = []
    if (series.title or '').strip() != ESREF_PERSIAN_TITLE:
        series.title = ESREF_PERSIAN_TITLE
        fields.append('title')
    if not (series.original_title or '').strip():
        series.original_title = ESREF_ORIGINAL_TITLE
        fields.append('original_title')
    if not series.is_featured:
        series.is_featured = True
        fields.append('is_featured')
    if fields:
        series.save(update_fields=[*fields, 'updated_at'])
        print(f'  localized fields={fields}', flush=True)

    if _publish_series(series):
        print('  published=True', flush=True)
    else:
        print('  published=already', flush=True)

    if not args.skip_crawl:
        crawl = _crawl_series_links(series, replace=True, resolve_english=True)
        series.refresh_from_db(
            fields=['download_links', 'is_dubbed', 'has_subtitle', 'updated_at'],
        )
        if args.delay > 0:
            time.sleep(args.delay)
        cov = _version_coverage(series)
        links = series.download_links or []
        print(
            f'  crawl={crawl.get("status")} imported={crawl.get("imported_count")} '
            f'links={len(links)} dub={cov.get("has_dub")} sub={cov.get("has_sub")} '
            f'imply_dub={download_links_imply_dub(links)} '
            f'imply_sub={download_links_imply_subtitle(links)} '
            f'imply_soft={download_links_imply_softsub(links)}',
            flush=True,
        )

        if not _has_download_links(series):
            print('ERROR: no series download links after crawl', file=sys.stderr)
            return 1

        created_eps = ensure_episodes_from_download_links(series) or 0
        seasons = Season.objects.filter(series=series).count()
        eps = Episode.objects.filter(season__series=series)
        with_video = eps.exclude(video_url='').exclude(video_url__isnull=True).count()
        with_tracks = eps.exclude(subtitle_tracks=[]).exclude(subtitle_tracks__isnull=True).count()
        print(
            f'  episodes_created={created_eps} seasons={seasons} '
            f'eps={eps.count()} with_video={with_video} with_tracks={with_tracks}',
            flush=True,
        )

        if args.force_softsub:
            try:
                from django.core.cache import cache
                from apps.catalog.tasks import _softsub_queue_lock
                cache.delete(_softsub_queue_lock('series', series.pk))
            except Exception as exc:  # noqa: BLE001
                print(f'  softsub lock clear warn: {exc}', flush=True)

        queued = enqueue_series_softsub(
            series.pk,
            force=bool(args.force_softsub),
            episode_limit=max(50, int(args.episode_limit)),
        )
        print(f'  softsub_queued={queued} episode_limit={args.episode_limit}', flush=True)

    try:
        bump_catalog_cache_version()
    except Exception as exc:  # noqa: BLE001
        print(f'cache bump warn: {exc}', flush=True)

    movie.refresh_from_db()
    series.refresh_from_db()
    print(
        f'\nDONE movie pk={movie.pk} slug={movie.slug} title={movie.title!r} '
        f'dub={movie.is_dubbed} has_sub={movie.has_subtitle} url=/movies/{movie.slug}',
        flush=True,
    )
    print(
        f'DONE series pk={series.pk} slug={series.slug} title={series.title!r} '
        f'dub={series.is_dubbed} has_sub={series.has_subtitle} url=/series/{series.slug}',
        flush=True,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
