"""Re-fetch hero backdrops at 1920 wide for existing titles, most popular first.

Titles imported before the sharp-hero rule stored TMDB's w1280 still, which a
full-width desktop hero stretches and blurs. This stores the 1920 WebP instead
and marks ``source_metadata.backdrop_hd`` so a rerun resumes. Old files are
kept, so the run stops on its own before the media disk gets too full.
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.catalog.ingestion import download_hero_backdrop
from apps.catalog.management.commands.refresh_titled_posters import media_disk_free_gb
from apps.catalog.models import Movie, Series

HD_KEY = 'backdrop_hd'


class Command(BaseCommand):
    help = 'Replace w1280 hero backdrops with 1920-wide ones (resumable, hot-first, disk-guarded).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0, help='Max titles to process (0 = all).')
        parser.add_argument('--sleep', type=float, default=0.3)
        parser.add_argument('--movies-only', action='store_true')
        parser.add_argument('--series-only', action='store_true')
        parser.add_argument('--min-free-gb', type=float, default=2.5)

    def handle(self, *args, **options):
        limit = max(0, int(options['limit'] or 0))
        sleep = max(0.0, float(options['sleep'] or 0))
        kinds = []
        if not options['series_only']:
            kinds.append((Movie, 'movie'))
        if not options['movies_only']:
            kinds.append((Series, 'series'))

        rows = []
        for model, prefix in kinds:
            qs = (
                model.objects.filter(is_published=True)
                .exclude(tmdb_id__isnull=True)
                .exclude(source_metadata__has_key=HD_KEY)
                .values_list('pk', 'popularity')
            )
            rows.extend((popularity or 0, model, prefix, pk) for pk, popularity in qs)
        # Movies and series interleaved by popularity, so the hottest heroes go first.
        rows.sort(key=lambda row: row[0], reverse=True)
        if limit:
            rows = rows[:limit]

        stats = {'done': 0, 'no_backdrop': 0, 'errors': 0}
        for _, model, prefix, pk in rows:
            if media_disk_free_gb() < options['min_free_gb']:
                self.stderr.write(f'stopping: media disk under {options["min_free_gb"]} GB free')
                stats['stopped_low_disk'] = 1
                break
            item = model.objects.filter(pk=pk).first()
            if item is None:
                continue
            meta = dict(item.source_metadata or {})
            if 'backdrop' in (getattr(item, 'manual_override_fields', None) or []):
                continue
            path = (getattr(item, 'backdrop_path', '') or meta.get('backdrop_path') or '').strip()
            if not path:
                stats['no_backdrop'] += 1
                meta[HD_KEY] = False
                model.objects.filter(pk=pk).update(source_metadata=meta)
                continue
            content = download_hero_backdrop(path, basename=f'tmdb-{item.tmdb_id}-{prefix}-backdrop')
            if content is None:
                stats['errors'] += 1
                self.stderr.write(f'{prefix}#{pk}: download failed for {path}')
                continue
            item.backdrop.save(content.name, content, save=False)
            meta[HD_KEY] = True
            item.source_metadata = meta
            item.updated_at = timezone.now()
            item.save(update_fields=['backdrop', 'source_metadata', 'updated_at'])
            stats['done'] += 1
            self.stdout.write(f'{prefix}#{pk} {(item.original_title or item.title)[:50]} → {item.backdrop.name}')
            if sleep:
                time.sleep(sleep)

        self.stdout.write(self.style.SUCCESS(' '.join(f'{key}={value}' for key, value in stats.items())))
