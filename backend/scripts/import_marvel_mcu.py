#!/usr/bin/env python3
"""Import the Marvel Cinematic Universe catalog with dub/softsub when available.

Pipeline per title:
  TMDB upsert → publish → myf2m download crawl → SoftSub VTT queue → tag marvel/mcu

Run inside the backend container:

  python /app/scripts/import_marvel_mcu.py
  python /app/scripts/import_marvel_mcu.py --dry-run
  python /app/scripts/import_marvel_mcu.py --skip-crawl
  python /app/scripts/import_marvel_mcu.py --movies-only
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Prefer the Django app root inside the container (/app), then fall back to repo layout.
for _candidate in (Path('/app'), Path(__file__).resolve().parents[1]):
    if (_candidate / 'config' / 'settings.py').exists():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        break


# Curated MCU theatrical + Sony Spider-Man (MCU) + Deadpool (MCU-adjacent).
MCU_MOVIE_TMDB_IDS: tuple[int, ...] = (
    # Phase One
    1726,    # Iron Man
    1724,    # The Incredible Hulk
    10138,   # Iron Man 2
    10195,   # Thor
    1771,    # Captain America: The First Avenger
    24428,   # The Avengers
    # Phase Two
    68721,   # Iron Man 3
    76338,   # Thor: The Dark World
    100402,  # Captain America: The Winter Soldier
    118340,  # Guardians of the Galaxy
    99861,   # Avengers: Age of Ultron
    102899,  # Ant-Man
    # Phase Three
    271110,  # Captain America: Civil War
    284052,  # Doctor Strange
    283995,  # Guardians of the Galaxy Vol. 2
    315635,  # Spider-Man: Homecoming
    284053,  # Thor: Ragnarok
    284054,  # Black Panther
    299536,  # Avengers: Infinity War
    363088,  # Ant-Man and the Wasp
    299537,  # Captain Marvel
    299534,  # Avengers: Endgame
    429617,  # Spider-Man: Far From Home
    # Phase Four
    497698,  # Black Widow
    566525,  # Shang-Chi and the Legend of the Ten Rings
    524434,  # Eternals
    634649,  # Spider-Man: No Way Home
    453395,  # Doctor Strange in the Multiverse of Madness
    616037,  # Thor: Love and Thunder
    505642,  # Black Panther: Wakanda Forever
    # Phase Five / Six
    640146,  # Ant-Man and the Wasp: Quantumania
    447365,  # Guardians of the Galaxy Vol. 3
    609681,  # The Marvels
    533535,  # Deadpool & Wolverine
    822119,  # Captain America: Brave New World
    986056,  # Thunderbolts*
    617126,  # The Fantastic Four: First Steps
    # MCU-adjacent Deadpool / Spider-Verse (commonly expected on a Marvel shelf)
    293660,  # Deadpool
    383498,  # Deadpool 2
    324857,  # Spider-Man: Into the Spider-Verse
    569094,  # Spider-Man: Across the Spider-Verse
)

# Lean MCU Disney+ / Marvel Television core (skip talk/award noise).
MCU_SERIES_TMDB_IDS: tuple[int, ...] = (
    85271,   # WandaVision
    88396,   # The Falcon and the Winter Soldier
    84958,   # Loki
    91363,   # What If...?
    88329,   # Hawkeye
    92749,   # Moon Knight
    92782,   # Ms. Marvel
    92783,   # She-Hulk: Attorney at Law
    114472,  # Secret Invasion
    122226,  # Echo
    138501,  # Agatha All Along
    202555,  # Daredevil: Born Again
    114471,  # Ironheart
    61550,   # Marvel's Agent Carter
    61889,   # Daredevil (Netflix)
    38472,   # Jessica Jones
    62126,   # Luke Cage
    62127,   # Iron Fist
    62285,   # The Defenders
    67178,   # The Punisher
    1403,    # Marvel's Agents of S.H.I.E.L.D.
)


def _unique(ids: tuple[int, ...]) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for value in ids:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--skip-crawl', action='store_true')
    parser.add_argument('--movies-only', action='store_true')
    parser.add_argument('--series-only', action='store_true')
    parser.add_argument('--delay', type=float, default=0.4)
    parser.add_argument('--limit', type=int, default=0, help='Cap titles per media type (0 = all)')
    args = parser.parse_args()

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from django.utils.text import slugify

    from apps.catalog.ingestion import upsert_tmdb_movie, upsert_tmdb_series
    from apps.catalog.importer_config import get_importer_settings
    from apps.catalog.models import Movie, Series, Tag
    from apps.catalog.provider_import.registry import get_connector
    from apps.catalog.subtitle_extract import download_links_imply_softsub
    from apps.catalog.tmdb import TMDBError, configured_tmdb_client
    from apps.catalog.top_catalog import (
        _crawl_movie_links,
        _crawl_series_links,
        _has_download_links,
        _publish_movie,
        _publish_series,
        _version_coverage,
    )

    do_movies = not args.series_only
    do_series = not args.movies_only
    movie_ids = _unique(MCU_MOVIE_TMDB_IDS)
    series_ids = _unique(MCU_SERIES_TMDB_IDS)
    if args.limit > 0:
        movie_ids = movie_ids[: args.limit]
        series_ids = series_ids[: args.limit]

    print(f'MCU targets: movies={len(movie_ids)} series={len(series_ids)} dry_run={args.dry_run}', flush=True)

    tag_marvel, _ = Tag.objects.get_or_create(
        slug='marvel',
        defaults={'name': 'مارول', 'is_featured': True},
    )
    if tag_marvel.name != 'مارول':
        tag_marvel.name = 'مارول'
        tag_marvel.is_featured = True
        tag_marvel.save(update_fields=['name', 'is_featured'])
    tag_mcu, _ = Tag.objects.get_or_create(
        slug='mcu',
        defaults={'name': 'MCU', 'is_featured': True},
    )
    # Ensure Persian display name for collection page.
    if not tag_marvel.slug:
        tag_marvel.slug = slugify('marvel') or 'marvel'
        tag_marvel.save(update_fields=['slug'])

    if args.dry_run:
        for tid in movie_ids:
            exists = Movie.objects.filter(tmdb_id=tid).exists()
            print(f'  movie tmdb={tid} exists={exists}')
        for tid in series_ids:
            exists = Series.objects.filter(tmdb_id=tid).exists()
            print(f'  series tmdb={tid} exists={exists}')
        return 0

    client = configured_tmdb_client()
    importer = get_importer_settings()
    connector = None
    if not args.skip_crawl:
        try:
            connector = get_connector('myf2m')
        except Exception as exc:  # noqa: BLE001
            print(f'ERROR: myf2m connector unavailable: {exc}', file=sys.stderr)
            return 1

    stats = {
        'movies_imported': 0,
        'movies_existing': 0,
        'movies_published': 0,
        'movies_crawled': 0,
        'movies_crawl_failed': 0,
        'movies_both_versions': 0,
        'series_imported': 0,
        'series_existing': 0,
        'series_published': 0,
        'series_crawled': 0,
        'series_crawl_failed': 0,
        'series_both_versions': 0,
        'softsub_queued': 0,
        'tagged': 0,
        'errors': [],
    }

    def tag_item(obj) -> None:
        before = set(obj.tags.values_list('id', flat=True))
        obj.tags.add(tag_marvel, tag_mcu)
        after = set(obj.tags.values_list('id', flat=True))
        if after - before:
            stats['tagged'] += 1

    def crawl_movie(movie: Movie) -> dict:
        if connector is None:
            return {'status': 'skipped'}
        result = _crawl_movie_links(movie, connector, replace=True, resolve_english=True)
        movie.refresh_from_db(fields=['download_links', 'is_dubbed', 'has_subtitle', 'updated_at'])
        return {**result, 'version_coverage': _version_coverage(movie)}

    def crawl_series(series_obj: Series) -> dict:
        if connector is None:
            return {'status': 'skipped'}
        result = _crawl_series_links(series_obj, connector, replace=True, resolve_english=True)
        series_obj.refresh_from_db(fields=['download_links', 'is_dubbed', 'has_subtitle', 'updated_at'])
        return {**result, 'version_coverage': _version_coverage(series_obj)}

    def queue_movie_softsub(movie: Movie) -> None:
        try:
            from apps.catalog.tasks import enqueue_movie_softsub
            if download_links_imply_softsub(movie.download_links or []) and not movie.subtitle_tracks:
                if enqueue_movie_softsub(movie.pk, force=False):
                    stats['softsub_queued'] += 1
        except Exception as exc:  # noqa: BLE001
            print(f'  softsub queue warn: {exc}', flush=True)

    def queue_series_softsub(series_obj: Series) -> None:
        try:
            from apps.catalog.tasks import enqueue_series_softsub
            if download_links_imply_softsub(series_obj.download_links or []):
                if enqueue_series_softsub(series_obj.pk, force=False, episode_limit=40):
                    stats['softsub_queued'] += 1
        except Exception as exc:  # noqa: BLE001
            print(f'  softsub queue warn: {exc}', flush=True)

    if do_movies:
        for idx, tmdb_id in enumerate(movie_ids, start=1):
            print(f'\n[{idx}/{len(movie_ids)}] MOVIE tmdb={tmdb_id}', flush=True)
            try:
                details = client.movie_details(tmdb_id)
                title = details.get('title') or details.get('original_title') or tmdb_id
                print(f'  title={title}', flush=True)
                movie, created, _, _ = upsert_tmdb_movie(details, importer=importer)
                stats['movies_imported' if created else 'movies_existing'] += 1
                if _publish_movie(movie):
                    stats['movies_published'] += 1
                tag_item(movie)
                crawl = crawl_movie(movie)
                cov = crawl.get('version_coverage') or _version_coverage(movie)
                nlinks = len(movie.download_links or [])
                print(
                    f'  -> pk={movie.pk} created={created} links={nlinks} '
                    f"dub={cov.get('has_dub')} sub={cov.get('has_sub')} crawl={crawl.get('status')}",
                    flush=True,
                )
                if cov.get('has_dub') and cov.get('has_sub'):
                    stats['movies_both_versions'] += 1
                if crawl.get('status') == 'ok' and int(crawl.get('imported_count') or 0) > 0:
                    stats['movies_crawled'] += 1
                elif not args.skip_crawl and not _has_download_links(movie):
                    stats['movies_crawl_failed'] += 1
                    stats['errors'].append({'movie': movie.pk, 'title': str(title), **crawl})
                queue_movie_softsub(movie)
                if args.delay > 0:
                    time.sleep(args.delay)
            except TMDBError as exc:
                print(f'  !! TMDB {exc}', flush=True)
                stats['errors'].append({'movie_tmdb': tmdb_id, 'error': str(exc)[:240]})
            except Exception as exc:  # noqa: BLE001
                print(f'  !! ERROR {exc}', flush=True)
                stats['errors'].append({'movie_tmdb': tmdb_id, 'error': str(exc)[:240]})

    if do_series:
        for idx, tmdb_id in enumerate(series_ids, start=1):
            print(f'\n[{idx}/{len(series_ids)}] SERIES tmdb={tmdb_id}', flush=True)
            try:
                details = client.tv_details(tmdb_id)
                title = details.get('name') or details.get('original_name') or tmdb_id
                print(f'  title={title}', flush=True)
                series_obj, created = upsert_tmdb_series(details, importer=importer)
                stats['series_imported' if created else 'series_existing'] += 1
                if _publish_series(series_obj):
                    stats['series_published'] += 1
                tag_item(series_obj)
                crawl = crawl_series(series_obj)
                cov = crawl.get('version_coverage') or _version_coverage(series_obj)
                nlinks = len(series_obj.download_links or [])
                print(
                    f'  -> pk={series_obj.pk} created={created} links={nlinks} '
                    f"dub={cov.get('has_dub')} sub={cov.get('has_sub')} crawl={crawl.get('status')}",
                    flush=True,
                )
                if cov.get('has_dub') and cov.get('has_sub'):
                    stats['series_both_versions'] += 1
                if crawl.get('status') == 'ok' and int(crawl.get('imported_count') or 0) > 0:
                    stats['series_crawled'] += 1
                elif not args.skip_crawl and not _has_download_links(series_obj):
                    stats['series_crawl_failed'] += 1
                    stats['errors'].append({'series': series_obj.pk, 'title': str(title), **crawl})
                queue_series_softsub(series_obj)
                if args.delay > 0:
                    time.sleep(args.delay)
            except TMDBError as exc:
                print(f'  !! TMDB {exc}', flush=True)
                stats['errors'].append({'series_tmdb': tmdb_id, 'error': str(exc)[:240]})
            except Exception as exc:  # noqa: BLE001
                print(f'  !! ERROR {exc}', flush=True)
                stats['errors'].append({'series_tmdb': tmdb_id, 'error': str(exc)[:240]})

    print('\n==== SUMMARY ====', flush=True)
    for key, value in stats.items():
        if key == 'errors':
            print(f'errors={len(value)}', flush=True)
            for err in value[:40]:
                print(f'  {err}', flush=True)
        else:
            print(f'{key}={value}', flush=True)

    marvel_movies = Movie.objects.filter(is_published=True, tags=tag_marvel).count()
    marvel_series = Series.objects.filter(is_published=True, tags=tag_marvel).count()
    print(f'\nPublished Marvel shelf: movies={marvel_movies} series={marvel_series}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
