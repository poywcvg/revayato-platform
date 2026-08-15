#!/usr/bin/env python3
"""Remove trailer/sample assets from download qualities and repair playback URLs.

Dry-run is the default.  ``--apply`` updates Movie/Series JSON rows in batches,
selects a real feature/episode encode as the playback fallback, and unpublishes
only records that no longer have any real playable media.
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


def main() -> int:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from django.db import transaction
    from django.utils import timezone

    from apps.catalog.models import Episode, Movie, Season, Series
    from apps.catalog.provider_import.catalog_lookup import _prefer_streamable_download
    from apps.catalog.provider_import.media_links import is_trailer_download_link, is_trailer_media_url
    from apps.catalog.subtitle_extract import (
        _links_for_episode,
        _prefer_episode_stream_url,
        apply_availability_flags,
        ensure_episodes_from_download_links,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--batch-size', type=int, default=200)
    parser.add_argument('--sample-limit', type=int, default=30)
    args = parser.parse_args()
    batch_size = max(20, int(args.batch_size or 200))

    stats = {
        'movie_rows_removed': 0,
        'movies_changed': 0,
        'movie_video_repaired': 0,
        'movies_unpublished': 0,
        'series_rows_removed': 0,
        'series_changed': 0,
        'series_unpublished': 0,
        'episode_video_repaired': 0,
        'episodes_unpublished': 0,
    }
    samples: list[tuple[str, int, str]] = []

    def split_links(obj, label: str):
        kept = []
        removed = []
        for item in obj.download_links or []:
            if not isinstance(item, dict):
                continue
            if is_trailer_download_link(item):
                removed.append(item)
                if len(samples) < max(0, int(args.sample_limit)):
                    samples.append((label, obj.pk, str(item.get('url') or item.get('key') or '')))
            else:
                kept.append(item)
        return kept, removed

    movie_fields = [
        'download_links', 'video_url', 'is_dubbed', 'has_subtitle', 'is_published', 'updated_at',
    ]
    series_fields = [
        'download_links', 'is_dubbed', 'has_subtitle', 'is_published', 'updated_at',
    ]
    movie_updates = []

    def flush_movies() -> None:
        if not args.apply or not movie_updates:
            return
        with transaction.atomic():
            Movie.objects.bulk_update(movie_updates, movie_fields, batch_size=batch_size)
        movie_updates.clear()

    for movie in Movie.objects.only(
        'id', 'download_links', 'video_url', 'is_published', 'is_dubbed', 'has_subtitle',
    ).iterator(chunk_size=batch_size):
        kept, removed = split_links(movie, 'movie')
        if not removed and not is_trailer_media_url(movie.video_url or ''):
            continue
        removed_urls = {
            str(item.get('url') or item.get('key') or '').strip() for item in removed
        }
        movie.download_links = kept
        stats['movie_rows_removed'] += len(removed)
        stats['movies_changed'] += 1
        current_video = str(movie.video_url or '').strip()
        if is_trailer_media_url(current_video) or current_video in removed_urls:
            replacement = _prefer_streamable_download(kept)
            if replacement != current_video:
                movie.video_url = replacement
                stats['movie_video_repaired'] += 1
        apply_availability_flags(movie, kept)
        if movie.is_published and not str(movie.video_url or '').strip() and not _prefer_streamable_download(kept):
            movie.is_published = False
            stats['movies_unpublished'] += 1
        movie.updated_at = timezone.now()
        if args.apply:
            movie_updates.append(movie)
            if len(movie_updates) >= batch_size:
                flush_movies()
    flush_movies()

    series_updates = []
    affected_series_ids: set[int] = set()
    for series in Series.objects.only(
        'id', 'download_links', 'is_published', 'is_dubbed', 'has_subtitle',
    ).iterator(chunk_size=batch_size):
        kept, removed = split_links(series, 'series')
        if not removed:
            continue
        series.download_links = kept
        stats['series_rows_removed'] += len(removed)
        stats['series_changed'] += 1
        affected_series_ids.add(series.pk)
        apply_availability_flags(series, kept)
        if series.is_published and not kept:
            series.is_published = False
            stats['series_unpublished'] += 1
        series.updated_at = timezone.now()
        if args.apply:
            series_updates.append(series)
            if len(series_updates) >= batch_size:
                with transaction.atomic():
                    Series.objects.bulk_update(series_updates, series_fields, batch_size=batch_size)
                series_updates.clear()

    if args.apply and series_updates:
        with transaction.atomic():
            Series.objects.bulk_update(series_updates, series_fields, batch_size=batch_size)
        series_updates.clear()

    print('DRY_RUN' if not args.apply else 'APPLY', stats, flush=True)
    for sample in samples:
        print('REMOVE', sample, flush=True)
    if not args.apply:
        return 0

    # Repair any Episode.video_url that directly points at a removed preview.
    series_link_cache: dict[int, list[dict]] = {}
    episode_updates = []
    touched_season_ids: set[int] = set()
    episode_qs = Episode.objects.exclude(video_url='').select_related('season').only(
        'id', 'video_url', 'is_published', 'season_id', 'episode_number',
        'season__series_id', 'season__season_number',
    )
    for episode in episode_qs.iterator(chunk_size=batch_size):
        if not is_trailer_media_url(episode.video_url or ''):
            continue
        series_id = episode.season.series_id
        links = series_link_cache.get(series_id)
        if links is None:
            links = list(
                Series.objects.filter(pk=series_id).values_list('download_links', flat=True).first() or []
            )
            series_link_cache[series_id] = links
        scoped = _links_for_episode(
            links,
            int(episode.season.season_number or 1),
            int(episode.episode_number or 0),
        )
        replacement = _prefer_episode_stream_url(scoped)
        if replacement:
            episode.video_url = replacement
            episode.is_published = True
            stats['episode_video_repaired'] += 1
        else:
            episode.video_url = ''
            episode.is_published = False
            stats['episodes_unpublished'] += 1
        episode.updated_at = timezone.now()
        episode_updates.append(episode)
        touched_season_ids.add(episode.season_id)

    Episode.objects.bulk_update(
        episode_updates,
        ['video_url', 'is_published', 'updated_at'],
        batch_size=batch_size,
    )

    # Do not re-walk every episode of every affected series. Most trailer rows
    # are unrelated extras and the episode table is already complete. Only
    # materialize a series when it has no playable episode at all.
    playable_series_ids = set(
        Episode.objects.filter(
            season__series_id__in=affected_series_ids,
            is_published=True,
        ).exclude(video_url='').values_list('season__series_id', flat=True).distinct()
    )
    missing_episode_series_ids = affected_series_ids - playable_series_ids
    for series in Series.objects.filter(pk__in=missing_episode_series_ids).iterator(chunk_size=100):
        ensure_episodes_from_download_links(series)

    # Episode URLs were only touched when they themselves were trailers.
    for season in Season.objects.filter(pk__in=touched_season_ids).iterator(chunk_size=200):
        count = season.episodes.filter(is_published=True).exclude(video_url='').count()
        published = count > 0
        fields = []
        if season.episode_count != count:
            season.episode_count = count
            fields.append('episode_count')
        if season.is_published != published:
            season.is_published = published
            fields.append('is_published')
        if fields:
            season.save(update_fields=[*fields, 'updated_at'])

    try:
        from apps.catalog.cache import bump_catalog_cache_version
        bump_catalog_cache_version()
    except Exception:
        pass
    print('REPAIR_TRAILER_LINKS_DONE', stats, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
