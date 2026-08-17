"""Fill missing backdrop artwork for published (or all) catalog titles."""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.catalog.ingestion import (
    attach_tmdb_artwork,
    ensure_local_backdrop_from_poster,
)
from apps.catalog.localization import prefer_original_artwork
from apps.catalog.models import Movie, Series
from apps.catalog.tmdb import TMDBError, configured_tmdb_client


def _missing_backdrop_q():
    return (
        Q(backdrop='') | Q(backdrop__isnull=True)
    ) & (
        Q(backdrop_external_url='') | Q(backdrop_external_url__isnull=True)
    )


class Command(BaseCommand):
    help = (
        'Download TMDB backdrops for titles that have none. '
        'When TMDB has no wide still, falls back to the poster so hero/detail pages are never blank.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0, help='Max titles to process (0 = all).')
        parser.add_argument('--sleep', type=float, default=0.12)
        parser.add_argument('--movies-only', action='store_true')
        parser.add_argument('--series-only', action='store_true')
        parser.add_argument(
            '--include-unpublished',
            action='store_true',
            help='Also fill draft titles (default: published only).',
        )
        parser.add_argument(
            '--no-poster-fallback',
            action='store_true',
            help='Do not use the poster when TMDB has no backdrop.',
        )

    def handle(self, *args, **options):
        client = configured_tmdb_client()
        limit = max(0, int(options['limit'] or 0))
        sleep = max(0.0, float(options['sleep'] or 0))
        do_movies = not options['series_only']
        do_series = not options['movies_only']
        published_only = not bool(options['include_unpublished'])
        allow_poster_fallback = not bool(options['no_poster_fallback'])

        stats = {
            'movies_filled': 0,
            'series_filled': 0,
            'skipped': 0,
            'errors': 0,
            'poster_fallback': 0,
        }
        processed = 0

        def budget_ok() -> bool:
            return not limit or processed < limit

        def fill_movie(movie: Movie) -> bool:
            nonlocal processed
            processed += 1
            changed: list[str] = []
            try:
                if movie.tmdb_id:
                    details = client.movie_details(movie.tmdb_id)
                    prefer_original_artwork(details)
                    changed = attach_tmdb_artwork(
                        movie,
                        details,
                        force=False,
                        prefix='movie',
                        allow_poster_backdrop=allow_poster_fallback,
                    )
                    if 'backdrop' in changed and not details.get('backdrop_path'):
                        stats['poster_fallback'] += 1
                if 'backdrop' not in changed and allow_poster_fallback:
                    changed = list(dict.fromkeys([*changed, *ensure_local_backdrop_from_poster(movie)]))
                    if 'backdrop' in changed:
                        stats['poster_fallback'] += 1
            except TMDBError as exc:
                self.stderr.write(f'movie#{movie.pk} tmdb={movie.tmdb_id}: {exc}')
                stats['errors'] += 1
                if allow_poster_fallback:
                    changed = ensure_local_backdrop_from_poster(movie)
                    if 'backdrop' in changed:
                        stats['poster_fallback'] += 1
                else:
                    return False
            except Exception as exc:  # pragma: no cover - defensive
                self.stderr.write(f'movie#{movie.pk}: {type(exc).__name__}: {exc}')
                stats['errors'] += 1
                return False

            filled = 'backdrop' in changed or 'backdrop_external_url' in changed
            if not filled:
                stats['skipped'] += 1
                return False
            movie.updated_at = timezone.now()
            movie.save(update_fields=list(dict.fromkeys([*changed, 'updated_at'])))
            stats['movies_filled'] += 1
            self.stdout.write(
                f"movie#{movie.pk} {(movie.original_title or movie.title)[:60]} → {movie.backdrop.name if movie.backdrop and movie.backdrop.name else movie.backdrop_external_url[:80]}"
            )
            return True

        def fill_series(series: Series) -> bool:
            nonlocal processed
            processed += 1
            changed: list[str] = []
            try:
                if series.tmdb_id:
                    details = client.tv_details(series.tmdb_id)
                    prefer_original_artwork(details)
                    changed = attach_tmdb_artwork(
                        series,
                        details,
                        force=False,
                        prefix='series',
                        allow_poster_backdrop=allow_poster_fallback,
                    )
                    if 'backdrop' in changed and not details.get('backdrop_path'):
                        stats['poster_fallback'] += 1
                if 'backdrop' not in changed and allow_poster_fallback:
                    changed = list(dict.fromkeys([*changed, *ensure_local_backdrop_from_poster(series)]))
                    if 'backdrop' in changed:
                        stats['poster_fallback'] += 1
            except TMDBError as exc:
                self.stderr.write(f'series#{series.pk} tmdb={series.tmdb_id}: {exc}')
                stats['errors'] += 1
                if allow_poster_fallback:
                    changed = ensure_local_backdrop_from_poster(series)
                    if 'backdrop' in changed:
                        stats['poster_fallback'] += 1
                else:
                    return False
            except Exception as exc:  # pragma: no cover
                self.stderr.write(f'series#{series.pk}: {type(exc).__name__}: {exc}')
                stats['errors'] += 1
                return False

            filled = 'backdrop' in changed or 'backdrop_external_url' in changed
            if not filled:
                stats['skipped'] += 1
                return False
            series.updated_at = timezone.now()
            series.save(update_fields=list(dict.fromkeys([*changed, 'updated_at'])))
            stats['series_filled'] += 1
            self.stdout.write(
                f"series#{series.pk} {(series.original_title or series.title)[:60]} → {series.backdrop.name if series.backdrop and series.backdrop.name else series.backdrop_external_url[:80]}"
            )
            return True

        if do_movies:
            qs = Movie.objects.filter(_missing_backdrop_q()).order_by('-popularity', 'id')
            if published_only:
                qs = qs.filter(is_published=True)
            for movie in qs.iterator(chunk_size=50):
                if not budget_ok():
                    break
                fill_movie(movie)
                if sleep:
                    time.sleep(sleep)

        if do_series:
            qs = Series.objects.filter(_missing_backdrop_q()).order_by('-popularity', 'id')
            if published_only:
                qs = qs.filter(is_published=True)
            for series in qs.iterator(chunk_size=50):
                if not budget_ok():
                    break
                fill_series(series)
                if sleep:
                    time.sleep(sleep)

        self.stdout.write(self.style.SUCCESS(str(stats)))
