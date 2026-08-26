"""Backfill non-Persian movie and series descriptions."""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.core.exceptions import FieldDoesNotExist
from django.utils import timezone

from apps.catalog.cache import bump_catalog_cache_version
from apps.catalog.localization import contains_persian, translate_to_persian
from apps.catalog.models import Movie, Series


class Command(BaseCommand):
    help = 'Translate every non-empty, non-Persian movie/series description to Persian.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0, help='Maximum attempted rows (0 = all).')
        parser.add_argument('--sleep', type=float, default=0.05, help='Pause after each translation request.')
        parser.add_argument('--movies-only', action='store_true')
        parser.add_argument('--series-only', action='store_true')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        limit = max(0, int(options['limit'] or 0))
        pause = max(0.0, float(options['sleep'] or 0))
        dry_run = bool(options['dry_run'])
        attempted = updated = failed = 0

        def process(model, label):
            nonlocal attempted, updated, failed
            queryset = model.objects.exclude(description='').order_by('-popularity', 'id')
            for obj in queryset.iterator(chunk_size=100):
                source = (obj.description or '').strip()
                if contains_persian(source):
                    continue
                if limit and attempted >= limit:
                    return
                attempted += 1
                translated = translate_to_persian(source)
                if not translated or not contains_persian(translated):
                    failed += 1
                    self.stderr.write(f'{label}#{obj.pk}: translation failed')
                    continue

                self.stdout.write(f'{label}#{obj.pk}: translated ({len(source)} -> {len(translated)} chars)')
                updated += 1
                if not dry_run:
                    obj.description = translated
                    obj.short_description = translated[:500]
                    try:
                        obj._meta.get_field('meta_description')
                        has_meta_description = True
                    except FieldDoesNotExist:
                        has_meta_description = False
                    if has_meta_description:
                        obj.meta_description = translated[:500]
                    obj.updated_at = timezone.now()
                    fields = ['description', 'short_description', 'updated_at']
                    if has_meta_description:
                        fields.append('meta_description')
                    obj.save(update_fields=fields)
                if pause:
                    time.sleep(pause)

        if not options['series_only']:
            process(Movie, 'movie')
        if not options['movies_only'] and (not limit or attempted < limit):
            process(Series, 'series')
        if updated and not dry_run:
            bump_catalog_cache_version()
        self.stdout.write(self.style.SUCCESS(
            f'done attempted={attempted} updated={updated} failed={failed} dry_run={dry_run}'
        ))
