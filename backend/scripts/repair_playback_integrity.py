#!/usr/bin/env python3
"""Normalize catalog links and repair primary online-playback sources.

The command is offline with respect to providers: it never downloads media or
re-crawls a page. It removes deterministic bad rows (trailers, dead hosts,
malformed suffixes), promotes browser-friendly MP4/HLS sources, synchronizes
series episodes, and hides an episode only when no valid source remains.

Usage inside the backend container:
  python /app/scripts/repair_playback_integrity.py          # audit only
  python /app/scripts/repair_playback_integrity.py --apply  # persist repairs
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Persist repairs (default: audit only).')
    parser.add_argument('--limit', type=int, default=0, help='Maximum movies and series per type; 0 means all.')
    parser.add_argument('--start-id', type=int, default=0, help='Only process rows with id greater than or equal to this value.')
    parser.add_argument('--end-id', type=int, default=0, help='Only process rows with id less than or equal to this value.')
    parser.add_argument('--movies-only', action='store_true')
    parser.add_argument('--series-only', action='store_true')
    args = parser.parse_args()

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from django.db import connection, transaction

    from apps.catalog.models import Episode, Movie, Series
    from apps.catalog.provider_import.catalog_lookup import _prefer_streamable_download
    from apps.catalog.provider_import.media_links import (
        is_playable_video_link,
        is_playable_video_url,
    )
    from apps.catalog.subtitle_extract import (
        canonicalize_download_links,
        ensure_episodes_from_download_links,
    )
    from config.public_urls import normalize_download_links
    from apps.catalog.top_catalog import _suppress_provider_publish_signals

    # Saving repaired published rows normally triggers the auto-crawl signals.
    # Maintenance already has the complete source set and must not enqueue one
    # duplicate network crawl per cleaned title.
    signal_guard = _suppress_provider_publish_signals()
    signal_guard.__enter__()

    # The JSON rows are large. This maintenance session deliberately streams in
    # bounded chunks and must not inherit the short public-request SQL timeout.
    with connection.cursor() as cursor:
        cursor.execute('SET statement_timeout TO 0')

    stats = {
        'movies_checked': 0,
        'movies_links_cleaned': 0,
        'movies_primary_changed': 0,
        'movies_primary_cleared': 0,
        'movies_unpublished_no_source': 0,
        'series_checked': 0,
        'series_links_cleaned': 0,
        'episodes_primary_changed': 0,
        'episodes_hidden_no_source': 0,
        'series_unpublished_no_source': 0,
    }
    samples: list[str] = []

    def clean_links(value) -> list[dict]:
        normalized = normalize_download_links(value or [])
        canonical, _changed = canonicalize_download_links(normalized)
        return canonical

    if not args.series_only:
        queryset = Movie.objects.only(
            'id', 'title', 'download_links', 'video_url', 'download_key',
            'is_published', 'publication_status',
        ).order_by('id')
        if args.start_id > 0:
            queryset = queryset.filter(id__gte=args.start_id)
        if args.end_id > 0:
            queryset = queryset.filter(id__lte=args.end_id)
        if args.limit > 0:
            queryset = queryset[:args.limit]
        for movie in queryset.iterator(chunk_size=100):
            stats['movies_checked'] += 1
            old_links = movie.download_links or []
            links = clean_links(old_links)
            links_changed = links != old_links
            if links_changed:
                stats['movies_links_cleaned'] += 1

            current = str(movie.video_url or '').strip()
            old_provider_urls = {
                str(item.get('url') or '').strip()
                for item in old_links
                if isinstance(item, dict) and str(item.get('url') or '').strip()
            }
            preferred = _prefer_streamable_download(links)
            current_invalid = current.startswith(('http://', 'https://')) and not is_playable_video_url(current)
            provider_primary = current in old_provider_urls
            should_promote = bool(
                preferred
                and (
                    not current
                    or current_invalid
                    or provider_primary
                )
            )
            next_video = preferred if should_promote else current
            if current_invalid and not preferred:
                next_video = ''

            video_changed = next_video != current
            if video_changed:
                if next_video:
                    stats['movies_primary_changed'] += 1
                else:
                    stats['movies_primary_cleared'] += 1
                if len(samples) < 30:
                    samples.append(f'movie:{movie.pk}:{current[-70:]} -> {next_video[-70:]}')

            has_valid_link = any(
                is_playable_video_link(item) or (
                    isinstance(item, dict) and bool(str(item.get('key') or '').strip())
                )
                for item in links
            )
            has_valid_primary = bool(
                next_video
                and (
                    not next_video.startswith(('http://', 'https://'))
                    or is_playable_video_url(next_video)
                )
            )
            should_unpublish = bool(
                movie.is_published
                and not has_valid_link
                and not has_valid_primary
                and not str(movie.download_key or '').strip()
            )
            if should_unpublish:
                stats['movies_unpublished_no_source'] += 1
                if len(samples) < 30:
                    samples.append(f'movie:{movie.pk}:unpublished_no_source')

            if args.apply and (links_changed or video_changed or should_unpublish):
                with transaction.atomic():
                    movie.download_links = links
                    movie.video_url = next_video
                    fields = ['updated_at']
                    if links_changed:
                        fields.append('download_links')
                    if video_changed:
                        fields.append('video_url')
                    if should_unpublish:
                        movie.is_published = False
                        movie.publication_status = Movie.PublicationStatus.DRAFT
                        fields.extend(['is_published', 'publication_status'])
                    movie.save(update_fields=fields)

    if not args.movies_only:
        queryset = Series.objects.only('id', 'title', 'download_links').order_by('id')
        if args.start_id > 0:
            queryset = queryset.filter(id__gte=args.start_id)
        if args.end_id > 0:
            queryset = queryset.filter(id__lte=args.end_id)
        if args.limit > 0:
            queryset = queryset[:args.limit]
        series_ids: list[int] = []
        for series in queryset.iterator(chunk_size=50):
            stats['series_checked'] += 1
            series_ids.append(series.pk)
            old_links = series.download_links or []
            links = clean_links(old_links)
            links_changed = links != old_links
            if links_changed:
                stats['series_links_cleaned'] += 1
                if len(samples) < 30:
                    samples.append(f'series:{series.pk}:cleaned_links')
            if args.apply and links_changed:
                series.download_links = links
                series.save(update_fields=['download_links', 'updated_at'])

            if args.apply:
                before = dict(
                    Episode.objects.filter(season__series_id=series.pk)
                    .values_list('id', 'video_url')
                )
                ensure_episodes_from_download_links(series)
                after = dict(
                    Episode.objects.filter(season__series_id=series.pk)
                    .values_list('id', 'video_url')
                )
                stats['episodes_primary_changed'] += sum(
                    before.get(pk, '') != url for pk, url in after.items()
                )

        # Invalid leftovers are episodes whose bad provider row was pruned and
        # for which no alternate quality existed. Never expose those as playable.
        invalid_episodes = Episode.objects.filter(
            season__series_id__in=series_ids,
            is_published=True,
        ).exclude(video_url='').only('id', 'video_url', 'is_published')
        for episode in invalid_episodes.iterator(chunk_size=500):
            current = str(episode.video_url or '').strip()
            if not current.startswith(('http://', 'https://')) or is_playable_video_url(current):
                continue
            stats['episodes_hidden_no_source'] += 1
            if len(samples) < 30:
                samples.append(f'episode:{episode.pk}:hidden:{current[-70:]}')
            if args.apply:
                episode.video_url = ''
                episode.is_published = False
                episode.save(update_fields=['video_url', 'is_published', 'updated_at'])

        # Do not keep a public series page pointing at a player with no usable
        # episode.  The row and metadata remain intact and normal imports can
        # publish it again as soon as a healthy provider source appears.
        if args.apply and series_ids:
            published_series = Series.objects.filter(
                pk__in=series_ids,
                is_published=True,
            ).only('id', 'download_links', 'is_published')
            for series in published_series.iterator(chunk_size=200):
                has_valid_link = any(
                    is_playable_video_link(item) or (
                        isinstance(item, dict) and bool(str(item.get('key') or '').strip())
                    )
                    for item in (series.download_links or [])
                )
                has_valid_episode = Episode.objects.filter(
                    season__series_id=series.pk,
                    is_published=True,
                ).exclude(video_url='').exists()
                if has_valid_link or has_valid_episode:
                    continue
                stats['series_unpublished_no_source'] += 1
                if len(samples) < 30:
                    samples.append(f'series:{series.pk}:unpublished_no_source')
                series.is_published = False
                series.save(update_fields=['is_published', 'updated_at'])

    if args.apply:
        try:
            from apps.catalog.cache import bump_catalog_cache_version
            bump_catalog_cache_version()
        except Exception:
            pass

    signal_guard.__exit__(None, None, None)

    print(f'mode={"apply" if args.apply else "audit"}', flush=True)
    print(stats, flush=True)
    for sample in samples:
        print(f'  {sample}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
