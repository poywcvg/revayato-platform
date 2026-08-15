#!/usr/bin/env python3
"""Import Disenchantment (طلسم شدگان) with all seasons, dub + SoftSub WebVTT.

Pipeline:
  TMDB upsert → Persian title → publish → myf2m crawl → episode stubs → SoftSub queue

Run inside the backend container:

  python /app/scripts/import_disenchantment.py
  python /app/scripts/import_disenchantment.py --dry-run
  python /app/scripts/import_disenchantment.py --skip-crawl
  python /app/scripts/import_disenchantment.py --force-softsub
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

DISENCHANTMENT_TMDB_ID = 73021
PERSIAN_TITLE = 'طلسم شدگان'
ORIGINAL_TITLE = 'Disenchantment'


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
    from apps.catalog.ingestion import upsert_tmdb_series
    from apps.catalog.importer_config import get_importer_settings
    from apps.catalog.models import Episode, Season, Series, Tag
    from apps.catalog.provider_import.registry import get_connector
    from apps.catalog.subtitle_extract import (
        download_links_imply_dub,
        download_links_imply_softsub,
        download_links_imply_subtitle,
        ensure_episodes_from_download_links,
    )
    from apps.catalog.tasks import enqueue_series_softsub
    from apps.catalog.tmdb import TMDBError, configured_tmdb_client
    from apps.catalog.top_catalog import (
        _crawl_series_links,
        _has_download_links,
        _publish_series,
        _version_coverage,
    )

    print(
        f'Disenchantment import tmdb={DISENCHANTMENT_TMDB_ID} dry_run={args.dry_run}',
        flush=True,
    )

    existing = Series.objects.filter(tmdb_id=DISENCHANTMENT_TMDB_ID).first()
    if args.dry_run:
        if not existing:
            print('  series exists=False')
            return 0
        eps = Episode.objects.filter(season__series=existing)
        print(
            f'  pk={existing.pk} title={existing.title!r} pub={existing.is_published} '
            f'links={len(existing.download_links or [])} '
            f'seasons={Season.objects.filter(series=existing).count()} '
            f'eps={eps.count()} tracks={eps.exclude(subtitle_tracks=[]).exclude(subtitle_tracks__isnull=True).count()} '
            f'dub={existing.is_dubbed} sub={existing.has_subtitle} slug={existing.slug}',
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

    tag_anim, _ = Tag.objects.get_or_create(
        slug='animation',
        defaults={'name': 'انیمیشن', 'is_featured': True},
    )
    if tag_anim.name != 'انیمیشن' or not tag_anim.is_featured:
        tag_anim.name = 'انیمیشن'
        tag_anim.is_featured = True
        tag_anim.save(update_fields=['name', 'is_featured'])

    try:
        details = client.tv_details(DISENCHANTMENT_TMDB_ID)
    except TMDBError as exc:
        print(f'ERROR: TMDB {exc}', file=sys.stderr)
        return 1

    title = details.get('name') or details.get('original_name') or ORIGINAL_TITLE
    print(f'  tmdb_title={title!r}', flush=True)

    series, created = upsert_tmdb_series(details, importer=importer)
    print(f'  upsert pk={series.pk} created={created}', flush=True)

    # Prefer the well-known Persian marketing title used on Iranian platforms.
    fields: list[str] = []
    if (series.title or '').strip() != PERSIAN_TITLE:
        series.title = PERSIAN_TITLE
        fields.append('title')
    if not (series.original_title or '').strip():
        series.original_title = ORIGINAL_TITLE
        fields.append('original_title')
    elif (series.original_title or '').strip().lower() != ORIGINAL_TITLE.lower():
        # Keep TMDB original when present; only fill if blank above.
        pass
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

    series.tags.add(tag_anim)

    crawl: dict = {'status': 'skipped'}
    if connector is not None:
        crawl = _crawl_series_links(series, connector, replace=True, resolve_english=True)
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
        print('ERROR: no download links after crawl — cannot wire playback', file=sys.stderr)
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

    # Cover all seasons (Film2Media lists 5×10; TMDB packs them as 3 parts / 50 eps).
    # Clear a stale queue lock so a just-imported title is not skipped.
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
        print(f'  cache bump warn: {exc}', flush=True)

    series.refresh_from_db()
    print(
        f'DONE pk={series.pk} slug={series.slug} title={series.title!r} '
        f'dub={series.is_dubbed} has_sub={series.has_subtitle} '
        f'url=/series/{series.slug}',
        flush=True,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
