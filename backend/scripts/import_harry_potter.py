#!/usr/bin/env python3
"""Import the Harry Potter film franchise with dub + SoftSub WebVTT.

Covers the 8 main films plus the Fantastic Beasts trilogy.

Pipeline per title:
  TMDB upsert → publish → myf2m download crawl → SoftSub VTT queue → tag harry-potter

Run inside the backend container:

  python /app/scripts/import_harry_potter.py
  python /app/scripts/import_harry_potter.py --dry-run
  python /app/scripts/import_harry_potter.py --skip-crawl
  python /app/scripts/import_harry_potter.py --force-softsub
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


# Main saga + Fantastic Beasts (Wizarding World theatrical films).
HARRY_POTTER_MOVIE_TMDB_IDS: tuple[int, ...] = (
    671,     # Harry Potter and the Philosopher's Stone
    672,     # Harry Potter and the Chamber of Secrets
    673,     # Harry Potter and the Prisoner of Azkaban
    674,     # Harry Potter and the Goblet of Fire
    675,     # Harry Potter and the Order of the Phoenix
    767,     # Harry Potter and the Half-Blood Prince
    12444,   # Harry Potter and the Deathly Hallows: Part 1
    12445,   # Harry Potter and the Deathly Hallows: Part 2
    259316,  # Fantastic Beasts and Where to Find Them
    338952,  # Fantastic Beasts: The Crimes of Grindelwald
    338953,  # Fantastic Beasts: The Secrets of Dumbledore
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
    parser.add_argument('--force-softsub', action='store_true', help='Re-queue SoftSub even when tracks exist.')
    parser.add_argument('--delay', type=float, default=0.35)
    parser.add_argument('--limit', type=int, default=0, help='Cap titles (0 = all)')
    args = parser.parse_args()

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from apps.catalog.ingestion import upsert_tmdb_movie
    from apps.catalog.importer_config import get_importer_settings
    from apps.catalog.models import Movie, Tag
    from apps.catalog.provider_import.registry import get_connector
    from apps.catalog.subtitle_extract import download_links_imply_softsub
    from apps.catalog.tmdb import TMDBError, configured_tmdb_client
    from apps.catalog.top_catalog import (
        _crawl_movie_links,
        _has_download_links,
        _publish_movie,
        _version_coverage,
    )
    from apps.catalog.cache import bump_catalog_cache_version

    movie_ids = _unique(HARRY_POTTER_MOVIE_TMDB_IDS)
    if args.limit > 0:
        movie_ids = movie_ids[: args.limit]

    print(f'Harry Potter targets: movies={len(movie_ids)} dry_run={args.dry_run}', flush=True)

    tag_hp, _ = Tag.objects.get_or_create(
        slug='harry-potter',
        defaults={'name': 'هری پاتر', 'is_featured': True},
    )
    if tag_hp.name != 'هری پاتر' or not tag_hp.is_featured:
        tag_hp.name = 'هری پاتر'
        tag_hp.is_featured = True
        tag_hp.save(update_fields=['name', 'is_featured'])

    tag_ww, _ = Tag.objects.get_or_create(
        slug='wizarding-world',
        defaults={'name': 'دنیای جادوگری', 'is_featured': True},
    )
    if tag_ww.name != 'دنیای جادوگری' or not tag_ww.is_featured:
        tag_ww.name = 'دنیای جادوگری'
        tag_ww.is_featured = True
        tag_ww.save(update_fields=['name', 'is_featured'])

    if args.dry_run:
        for tid in movie_ids:
            movie = Movie.objects.filter(tmdb_id=tid).first()
            if not movie:
                print(f'  movie tmdb={tid} exists=False')
                continue
            tracks = len(movie.subtitle_tracks or [])
            links = len(movie.download_links or [])
            print(
                f'  movie tmdb={tid} pk={movie.pk} pub={movie.is_published} '
                f'links={links} tracks={tracks} dub={movie.is_dubbed} sub={movie.has_subtitle} '
                f'title={movie.title!r}',
            )
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
        'movies_featured': 0,
        'movies_crawled': 0,
        'movies_crawl_failed': 0,
        'movies_both_versions': 0,
        'movies_with_vtt': 0,
        'softsub_queued': 0,
        'tagged': 0,
        'errors': [],
    }

    def tag_item(obj: Movie) -> None:
        before = set(obj.tags.values_list('id', flat=True))
        obj.tags.add(tag_hp, tag_ww)
        after = set(obj.tags.values_list('id', flat=True))
        if after - before:
            stats['tagged'] += 1

    def feature_item(obj: Movie) -> None:
        fields = []
        if not obj.is_featured:
            obj.is_featured = True
            fields.append('is_featured')
        if not obj.is_recommended:
            obj.is_recommended = True
            fields.append('is_recommended')
        if fields:
            fields.append('updated_at')
            obj.save(update_fields=fields)
            stats['movies_featured'] += 1

    def crawl_movie(movie: Movie) -> dict:
        if connector is None:
            return {'status': 'skipped'}
        # Keep existing SoftSub VTT when links refresh; only replace download rows.
        result = _crawl_movie_links(movie, connector, replace=True, resolve_english=True)
        movie.refresh_from_db(fields=['download_links', 'is_dubbed', 'has_subtitle', 'updated_at'])
        return {**result, 'version_coverage': _version_coverage(movie)}

    def queue_movie_softsub(movie: Movie) -> None:
        try:
            from apps.catalog.tasks import enqueue_movie_softsub
            from apps.catalog.subtitle_extract import attach_extracted_subtitle

            movie.refresh_from_db(fields=['download_links', 'subtitle_tracks', 'has_subtitle'])
            has_tracks = bool(movie.subtitle_tracks)
            soft_links = download_links_imply_softsub(movie.download_links or [])
            if not soft_links and not args.force_softsub:
                return
            if has_tracks and not args.force_softsub:
                return
            # Prefer async queue; fall back to sync SubtitleStar/ffmpeg so new
            # titles leave this script with player-ready WebVTT when possible.
            if enqueue_movie_softsub(movie.pk, force=bool(args.force_softsub or not has_tracks)):
                stats['softsub_queued'] += 1
            movie.refresh_from_db(fields=['subtitle_tracks'])
            if movie.subtitle_tracks and not args.force_softsub:
                return
            if attach_extracted_subtitle(
                movie,
                force=bool(args.force_softsub or not movie.subtitle_tracks),
                timeout_seconds=240,
                allow_ffmpeg=True,
            ):
                stats['softsub_queued'] += 1
                print('  softsub attached synchronously', flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f'  softsub queue warn: {exc}', flush=True)

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
            feature_item(movie)
            crawl = crawl_movie(movie)
            cov = crawl.get('version_coverage') or _version_coverage(movie)
            nlinks = len(movie.download_links or [])
            ntracks = len(movie.subtitle_tracks or [])
            print(
                f'  -> pk={movie.pk} created={created} links={nlinks} tracks={ntracks} '
                f"dub={cov.get('has_dub')} sub={cov.get('has_sub')} crawl={crawl.get('status')}",
                flush=True,
            )
            if cov.get('has_dub') and cov.get('has_sub'):
                stats['movies_both_versions'] += 1
            if ntracks:
                stats['movies_with_vtt'] += 1
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

    try:
        bump_catalog_cache_version()
    except Exception as exc:  # noqa: BLE001
        print(f'cache bump warn: {exc}', flush=True)

    print('\n==== SUMMARY ====', flush=True)
    for key, value in stats.items():
        if key == 'errors':
            print(f'errors={len(value)}', flush=True)
            for err in value[:40]:
                print(f'  {err}', flush=True)
        else:
            print(f'{key}={value}', flush=True)

    shelf = Movie.objects.filter(is_published=True, tags=tag_hp).count()
    print(f'\nPublished Harry Potter shelf: movies={shelf}', flush=True)
    return 0 if not stats['errors'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
