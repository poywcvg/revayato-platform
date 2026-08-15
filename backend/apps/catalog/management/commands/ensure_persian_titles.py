"""Backfill Persian ``title`` + English ``original_title`` for catalog rows."""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.catalog.localization import contains_persian, is_latin_text, normalize_title_pair
from apps.catalog.models import Movie, Series


class Command(BaseCommand):
    help = (
        'Ensure every movie/series has a Persian title and an English original_title. '
        'Uses local swap + machine translation (no TMDB).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0, help='Max rows to update (0 = all needing fix).')
        parser.add_argument('--sleep', type=float, default=0.05, help='Pause between translations.')
        parser.add_argument('--movies-only', action='store_true')
        parser.add_argument('--series-only', action='store_true')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        limit = max(0, int(options['limit'] or 0))
        sleep = max(0.0, float(options['sleep'] or 0))
        dry_run = bool(options['dry_run'])
        do_movies = not options['series_only']
        do_series = not options['movies_only']

        stats = {'movies': 0, 'series': 0, 'skipped': 0, 'failed': 0, 'processed': 0}

        def budget_ok() -> bool:
            return not limit or stats['processed'] < limit

        def needs_fix(title: str, original: str) -> bool:
            return (not contains_persian(title)) or (original and not is_latin_text(original) and contains_persian(original))

        def fix_obj(obj, label: str) -> bool:
            before_title = (obj.title or '').strip()
            before_original = (obj.original_title or '').strip()
            if not needs_fix(before_title, before_original) and contains_persian(before_title):
                # Still fill missing English when title is already Persian.
                if before_original and is_latin_text(before_original):
                    stats['skipped'] += 1
                    return False
                if before_original:
                    stats['skipped'] += 1
                    return False

            persian, english = normalize_title_pair(before_title, before_original, translate=True)
            if not contains_persian(persian):
                stats['failed'] += 1
                self.stderr.write(f'{label}#{obj.id}: could not resolve Persian for {before_title!r}')
                return False
            if not english:
                english = before_original if is_latin_text(before_original) else (
                    before_title if is_latin_text(before_title) else ''
                )

            if persian == before_title and english == before_original:
                stats['skipped'] += 1
                return False

            self.stdout.write(
                f'{label}#{obj.id}: {before_title!r} / {before_original!r} → {persian!r} / {english!r}'
            )
            if dry_run:
                return True

            obj.title = persian
            obj.original_title = english
            obj.updated_at = timezone.now()
            obj.save(update_fields=['title', 'original_title', 'updated_at'])
            if sleep:
                time.sleep(sleep)
            return True

        if do_movies:
            for movie in Movie.objects.all().order_by('-popularity', 'id').iterator(chunk_size=200):
                if not budget_ok():
                    break
                if not needs_fix(movie.title or '', movie.original_title or ''):
                    # Ensure English original when missing
                    title = (movie.title or '').strip()
                    original = (movie.original_title or '').strip()
                    if contains_persian(title) and (not original or not is_latin_text(original)):
                        # Try to keep any latin original from title history via source_metadata
                        meta = movie.source_metadata if isinstance(movie.source_metadata, dict) else {}
                        english = (
                            (meta.get('english_title') or meta.get('_english_title') or '').strip()
                        )
                        if english and is_latin_text(english):
                            stats['processed'] += 1
                            if not dry_run:
                                movie.original_title = english[:255]
                                movie.updated_at = timezone.now()
                                movie.save(update_fields=['original_title', 'updated_at'])
                            stats['movies'] += 1
                            continue
                    stats['skipped'] += 1
                    continue
                stats['processed'] += 1
                if fix_obj(movie, 'movie'):
                    stats['movies'] += 1

        if do_series and budget_ok():
            for series in Series.objects.all().order_by('-popularity', 'id').iterator(chunk_size=200):
                if not budget_ok():
                    break
                if not needs_fix(series.title or '', series.original_title or ''):
                    stats['skipped'] += 1
                    continue
                stats['processed'] += 1
                if fix_obj(series, 'series'):
                    stats['series'] += 1

        self.stdout.write(self.style.SUCCESS(
            f"done movies={stats['movies']} series={stats['series']} "
            f"skipped={stats['skipped']} failed={stats['failed']} "
            f"processed={stats['processed']} dry_run={dry_run}"
        ))
