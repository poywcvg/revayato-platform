#!/usr/bin/env python3
"""Repair Film2Media series links whose filename uses Show.01.1080p notation.

Dry-run is the default. Pass --apply to persist corrected season/episode fields
and materialize the corresponding Episode rows for online playback.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if not (_APP_ROOT / 'config').is_dir():
    _APP_ROOT = Path('/app')
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


def _positive_int(value) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--sample-limit', type=int, default=20)
    args = parser.parse_args()

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from apps.catalog.cache import bump_catalog_cache_version
    from apps.catalog.models import Series
    from apps.catalog.provider_import.providers.cdn_link_parse import (
        _episode_from_url,
        stamp_season_episode,
    )
    from apps.catalog.subtitle_extract import ensure_episodes_from_download_links

    stats = {
        'series_scanned': 0,
        'myf2m_rows_scanned': 0,
        'rows_repaired': 0,
        'series_repaired': 0,
        'episodes_materialized_for_series': 0,
        'materialize_errors': 0,
    }
    samples = []

    queryset = (
        Series.objects.exclude(download_links=[])
        .exclude(download_links__isnull=True)
        .only('id', 'title', 'download_links')
        .order_by('pk')
    )
    for series in queryset.iterator(chunk_size=100):
        stats['series_scanned'] += 1
        links = list(series.download_links or [])
        changed = False
        for index, item in enumerate(links):
            if not isinstance(item, dict):
                continue
            if str(item.get('source') or '').strip().lower() != 'myf2m':
                continue
            stats['myf2m_rows_scanned'] += 1
            url = str(item.get('url') or item.get('key') or '').strip()
            season_hint = _positive_int(item.get('season_number'))
            if not url or season_hint is None:
                continue

            inferred_season, inferred_episode = _episode_from_url(
                url,
                surrounding='',
                season_hint=season_hint,
            )
            inferred_season = _positive_int(inferred_season)
            inferred_episode = _positive_int(inferred_episode)
            if inferred_season is None or inferred_episode is None:
                continue
            before = (
                _positive_int(item.get('season_number')),
                _positive_int(item.get('episode_number')),
            )
            after = (inferred_season, inferred_episode)
            if before == after:
                continue

            links[index] = stamp_season_episode(
                item,
                season_number=inferred_season,
                episode_number=inferred_episode,
                quality=str(item.get('quality') or ''),
            )
            changed = True
            stats['rows_repaired'] += 1
            if len(samples) < max(0, int(args.sample_limit)):
                samples.append({
                    'series_id': series.pk,
                    'title': series.title,
                    'before': before,
                    'after': after,
                    'url_tail': url.rsplit('/', 1)[-1][:180],
                })

        if not changed:
            continue
        stats['series_repaired'] += 1
        if not args.apply:
            continue

        series.download_links = links
        series.save(update_fields=['download_links', 'updated_at'])
        try:
            ensure_episodes_from_download_links(series)
            stats['episodes_materialized_for_series'] += 1
        except Exception as exc:
            stats['materialize_errors'] += 1
            print(
                f'materialize error series={series.pk}: {type(exc).__name__}: {exc}',
                flush=True,
            )

    if args.apply and stats['series_repaired']:
        bump_catalog_cache_version()

    print('REPAIR_MYF2M_EPISODE_NUMBERS', 'APPLY' if args.apply else 'DRY_RUN', stats, flush=True)
    for sample in samples:
        print('sample', sample, flush=True)
    return 1 if args.apply and stats['materialize_errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
