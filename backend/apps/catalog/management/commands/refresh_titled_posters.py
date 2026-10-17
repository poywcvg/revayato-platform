"""Swap textless TMDB key art for the titled release poster on existing titles.

Every title imported before the titled-poster rule got TMDB's null-language
(textless) poster when one existed. This walks published titles hot-first,
asks TMDB for the poster list and stores the titled one. A title is marked
``source_metadata.poster_source = 'titled'`` once checked, so a rerun resumes
where the last one stopped. Posters an admin set by hand are never touched,
and the old image file is left on disk.
"""

from __future__ import annotations

import shutil
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.catalog.ingestion import _download_tmdb_image, _tmdb_image_url
from apps.catalog.localization import pick_titled_poster
from apps.catalog.models import Movie, Series
from apps.catalog.tmdb import TMDBError, configured_tmdb_client

TITLED = 'titled'


def media_disk_free_gb() -> float:
    return shutil.disk_usage(settings.MEDIA_ROOT).free / 1024 ** 3


class Command(BaseCommand):
    help = 'Replace textless posters with the titled TMDB release poster (resumable, hot-first).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0, help='Max titles to check (0 = all).')
        parser.add_argument('--sleep', type=float, default=0.3, help='Pause between TMDB calls.')
        parser.add_argument('--movies-only', action='store_true')
        parser.add_argument('--series-only', action='store_true')
        parser.add_argument('--include-unpublished', action='store_true')
        parser.add_argument('--dry-run', action='store_true', help='Report what would change, write nothing.')
        parser.add_argument(
            '--min-free-gb', type=float, default=2.5,
            help='Stop before the media disk drops below this much free space (old files are kept).',
        )

    def handle(self, *args, **options):
        client = configured_tmdb_client()
        limit = max(0, int(options['limit'] or 0))
        sleep = max(0.0, float(options['sleep'] or 0))
        dry_run = bool(options['dry_run'])
        kinds = []
        if not options['series_only']:
            kinds.append((Movie, 'movie', 'movie'))
        if not options['movies_only']:
            kinds.append((Series, 'tv', 'series'))

        stats = {'checked': 0, 'replaced': 0, 'already_titled': 0, 'manual': 0, 'errors': 0}
        for model, tmdb_kind, prefix in kinds:
            qs = model.objects.exclude(tmdb_id__isnull=True).exclude(
                source_metadata__poster_source=TITLED,
            )
            if not options['include_unpublished']:
                qs = qs.filter(is_published=True)
            for pk in qs.order_by('-popularity', '-pk').values_list('pk', flat=True).iterator():
                if limit and stats['checked'] >= limit:
                    break
                if not dry_run and media_disk_free_gb() < options['min_free_gb']:
                    self.stderr.write(f'stopping: media disk under {options["min_free_gb"]} GB free')
                    stats['stopped_low_disk'] = 1
                    break
                item = model.objects.filter(pk=pk).first()
                if item is None:
                    continue
                stats['checked'] += 1
                self._refresh(item, client, tmdb_kind, prefix, stats, dry_run)
                if sleep:
                    time.sleep(sleep)

        self.stdout.write(self.style.SUCCESS(' '.join(f'{key}={value}' for key, value in stats.items())))

    def _refresh(self, item, client, tmdb_kind, prefix, stats, dry_run):
        label = f'{prefix}#{item.pk} {(item.original_title or item.title)[:50]}'
        meta = dict(item.source_metadata or {})
        if 'poster' in (getattr(item, 'manual_override_fields', None) or []):
            stats['manual'] += 1
            self._mark(item, meta, dry_run)
            return
        try:
            images = client.title_images(tmdb_kind, item.tmdb_id)
        except TMDBError as exc:
            stats['errors'] += 1
            self.stderr.write(f'{label}: {exc}')
            return

        current = (getattr(item, 'poster_path', '') or meta.get('poster_path') or '').strip()
        best = pick_titled_poster(images.get('posters') or [], current, item.original_language)
        if not best or best == current:
            stats['already_titled'] += 1
            self._mark(item, meta, dry_run)
            return
        if dry_run:
            stats['replaced'] += 1
            self.stdout.write(f'{label}: {current or "—"} → {best} (dry run)')
            return

        content = _download_tmdb_image(best, size='w500', basename=f'tmdb-{item.tmdb_id}-{prefix}-poster')
        if content is None:
            # Leave it unmarked so the next run retries the download.
            stats['errors'] += 1
            self.stderr.write(f'{label}: download failed for {best}')
            return
        item.poster.save(content.name, content, save=False)
        fields = ['poster', 'poster_external_url', 'source_metadata', 'updated_at']
        if hasattr(item, 'poster_path'):
            item.poster_path = best[:255]
            fields.append('poster_path')
        item.poster_external_url = _tmdb_image_url(best, 'w500')
        meta['poster_path'] = best
        meta['poster_source'] = TITLED
        item.source_metadata = meta
        item.updated_at = timezone.now()
        item.save(update_fields=fields)
        stats['replaced'] += 1
        self.stdout.write(f'{label}: {current or "—"} → {best}')

    @staticmethod
    def _mark(item, meta, dry_run):
        if dry_run:
            return
        meta['poster_source'] = TITLED
        type(item).objects.filter(pk=item.pk).update(source_metadata=meta)
