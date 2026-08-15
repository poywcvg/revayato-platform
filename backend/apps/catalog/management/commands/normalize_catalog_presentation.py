"""Backfill English catalog titles and original TMDB posters.

Forces movie/series ``title`` and ``original_title`` to English/Latin
(no Persian or other scripts). Optionally re-syncs artwork from TMDB.
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.catalog.ingestion import attach_tmdb_artwork, upsert_tmdb_movie, upsert_tmdb_series
from apps.catalog.localization import (
    contains_disallowed_catalog_script,
    contains_persian,
    is_latin_text,
)
from apps.catalog.models import Movie, Series
from apps.catalog.tmdb import TMDBError, configured_tmdb_client


class Command(BaseCommand):
    help = (
        'Normalize catalog presentation: English-only titles/original titles, '
        'and artwork that prefers the original theatrical poster.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0, help='Max titles to process (0 = all matching).')
        parser.add_argument('--sleep', type=float, default=0.15, help='Pause between TMDB calls.')
        parser.add_argument('--movies-only', action='store_true')
        parser.add_argument('--series-only', action='store_true')
        parser.add_argument(
            '--non-english-only',
            action='store_true',
            help='Only rows whose title or original_title still contain non-Latin scripts.',
        )
        parser.add_argument(
            '--cjk-only',
            action='store_true',
            help='Deprecated alias for rows with CJK in original_title/title.',
        )
        parser.add_argument(
            '--non-latin-only',
            action='store_true',
            help='Alias for --non-english-only.',
        )
        parser.add_argument(
            '--local-only',
            action='store_true',
            help='Only copy Latin original_title → title when title is non-English (no TMDB).',
        )
        parser.add_argument(
            '--force-artwork',
            action='store_true',
            default=True,
            help='Re-download posters even when a local image already exists (default: on).',
        )
        parser.add_argument('--no-force-artwork', action='store_true')

    def handle(self, *args, **options):
        limit = max(0, int(options['limit'] or 0))
        sleep = max(0.0, float(options['sleep'] or 0))
        do_movies = not options['series_only']
        do_series = not options['movies_only']
        non_english_only = bool(
            options['non_english_only'] or options['non_latin_only'] or options['cjk_only']
        )
        local_only = bool(options['local_only'])
        force_artwork = not bool(options['no_force_artwork'])

        stats = {
            'movies_updated': 0,
            'series_updated': 0,
            'local_fixed': 0,
            'skipped': 0,
            'errors': 0,
            'english_fixed': 0,
        }
        processed = 0

        def needs_fix(original: str, title: str = '') -> bool:
            if not non_english_only:
                return True
            return (
                contains_disallowed_catalog_script(original)
                or contains_disallowed_catalog_script(title)
                or contains_persian(original)
                or contains_persian(title)
            )

        def budget_ok() -> bool:
            return not limit or processed < limit

        def apply_local_english(obj) -> bool:
            """If original is Latin and title is not, promote original → title."""
            original = (obj.original_title or '').strip()
            title = (obj.title or '').strip()
            changed = []
            if is_latin_text(original) and (
                contains_disallowed_catalog_script(title) or not is_latin_text(title)
            ):
                obj.title = original
                changed.append('title')
            elif is_latin_text(title) and (
                contains_disallowed_catalog_script(original) or (original and not is_latin_text(original))
            ):
                obj.original_title = title
                changed.append('original_title')
            if not changed:
                return False
            obj.updated_at = timezone.now()
            obj.save(update_fields=[*changed, 'updated_at'])
            stats['local_fixed'] += 1
            self.stdout.write(f'{obj.__class__.__name__.lower()}#{obj.id}: local → {obj.title!r}')
            return True

        if local_only:
            if do_movies:
                qs = Movie.objects.all().order_by('-popularity', 'id')
                for movie in qs.iterator(chunk_size=100):
                    if not budget_ok():
                        break
                    if non_english_only and not needs_fix(movie.original_title or '', movie.title or ''):
                        stats['skipped'] += 1
                        continue
                    processed += 1
                    if apply_local_english(movie):
                        stats['movies_updated'] += 1
                    else:
                        stats['skipped'] += 1
            if do_series and budget_ok():
                qs = Series.objects.all().order_by('-popularity', 'id')
                for series in qs.iterator(chunk_size=100):
                    if not budget_ok():
                        break
                    if non_english_only and not needs_fix(series.original_title or '', series.title or ''):
                        stats['skipped'] += 1
                        continue
                    processed += 1
                    if apply_local_english(series):
                        stats['series_updated'] += 1
                    else:
                        stats['skipped'] += 1
            self.stdout.write(self.style.SUCCESS(
                'local english titles done: '
                f'movies={stats["movies_updated"]} series={stats["series_updated"]} '
                f'local_fixed={stats["local_fixed"]} skipped={stats["skipped"]}'
            ))
            return

        client = configured_tmdb_client()

        if do_movies:
            qs = Movie.objects.exclude(tmdb_id__isnull=True).order_by('-popularity', 'id')
            if non_english_only:
                # Broad filter; precise script checks happen in Python.
                qs = qs.filter(
                    Q(title__regex=r'[\u0600-\u06FF\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af\u0400-\u04FF]')
                    | Q(original_title__regex=r'[\u0600-\u06FF\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af\u0400-\u04FF]')
                )
            for movie in qs.iterator(chunk_size=50):
                if not budget_ok():
                    break
                if not needs_fix(movie.original_title or '', movie.title or ''):
                    stats['skipped'] += 1
                    continue
                processed += 1
                try:
                    details = client.movie_details(movie.tmdb_id)
                    before_title = movie.title
                    before_original = movie.original_title
                    upsert_tmdb_movie(details, overwrite_manual=False)
                    movie.refresh_from_db()
                    if force_artwork:
                        changed = attach_tmdb_artwork(movie, details, force=True, prefix='movie')
                        if changed:
                            movie.save(update_fields=[*changed, 'updated_at'])
                    stats['movies_updated'] += 1
                    if (
                        contains_disallowed_catalog_script(before_title)
                        or contains_disallowed_catalog_script(before_original or '')
                    ) and not contains_disallowed_catalog_script(movie.title or ''):
                        stats['english_fixed'] += 1
                        self.stdout.write(
                            f'movie#{movie.id}: {before_title!r} / {before_original!r} → {movie.title!r}'
                        )
                except TMDBError as exc:
                    stats['errors'] += 1
                    self.stderr.write(f'movie tmdb={movie.tmdb_id}: {exc}')
                    apply_local_english(movie)
                except Exception as exc:  # noqa: BLE001
                    stats['errors'] += 1
                    self.stderr.write(f'movie#{movie.id}: {exc}')
                if sleep:
                    time.sleep(sleep)

        if do_series and budget_ok():
            qs = Series.objects.exclude(tmdb_id__isnull=True).order_by('-popularity', 'id')
            if non_english_only:
                qs = qs.filter(
                    Q(title__regex=r'[\u0600-\u06FF\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af\u0400-\u04FF]')
                    | Q(original_title__regex=r'[\u0600-\u06FF\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af\u0400-\u04FF]')
                )
            for series in qs.iterator(chunk_size=50):
                if not budget_ok():
                    break
                if not needs_fix(series.original_title or '', series.title or ''):
                    stats['skipped'] += 1
                    continue
                processed += 1
                try:
                    details = client.tv_details(series.tmdb_id)
                    before_title = series.title
                    before_original = series.original_title
                    upsert_tmdb_series(details)
                    series.refresh_from_db()
                    if force_artwork:
                        changed = attach_tmdb_artwork(series, details, force=True, prefix='series')
                        if changed:
                            series.save(update_fields=[*changed, 'updated_at'])
                    stats['series_updated'] += 1
                    if (
                        contains_disallowed_catalog_script(before_title)
                        or contains_disallowed_catalog_script(before_original or '')
                    ) and not contains_disallowed_catalog_script(series.title or ''):
                        stats['english_fixed'] += 1
                        self.stdout.write(
                            f'series#{series.id}: {before_title!r} / {before_original!r} → {series.title!r}'
                        )
                except TMDBError as exc:
                    stats['errors'] += 1
                    self.stderr.write(f'series tmdb={series.tmdb_id}: {exc}')
                    apply_local_english(series)
                except Exception as exc:  # noqa: BLE001
                    stats['errors'] += 1
                    self.stderr.write(f'series#{series.id}: {exc}')
                if sleep:
                    time.sleep(sleep)

        self.stdout.write(self.style.SUCCESS(
            'normalize presentation done: '
            f'movies={stats["movies_updated"]} series={stats["series_updated"]} '
            f'english_fixed={stats["english_fixed"]} local_fixed={stats["local_fixed"]} '
            f'skipped={stats["skipped"]} errors={stats["errors"]}'
        ))
