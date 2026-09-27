"""Complete missing catalog metadata and artwork (poster/backdrop) from TMDB.

Picks movies/series that are incomplete — missing a key metadata field
(description, release date/year, genres, cast, crew, countries, artwork) or
whose titles do not follow the site's structure (no Latin original title) —
and fills the gaps from TMDB, reusing the existing upsert/artwork machinery.

Scope: only incomplete rows are processed. Existing manual/curated fields and
posters are protected (upsert runs with ``overwrite_manual=False``). If a title
still has no backdrop after TMDB, the poster is copied so hero/detail pages are
never blank.
"""

from __future__ import annotations

import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count, F, Q
from django.utils import timezone

from apps.catalog.ingestion import (
    attach_tmdb_artwork,
    ensure_local_backdrop_from_poster,
    upsert_tmdb_movie,
    upsert_tmdb_series,
)
from apps.catalog.localization import (
    contains_disallowed_catalog_script,
    prefer_original_artwork,
)
from apps.catalog.models import Movie, Series
from apps.catalog.tmdb import TMDBError, configured_tmdb_client


def _missing_art_q(field):
    return (Q(**{f'{field}': ''}) | Q(**{f'{field}__isnull': True}) | Q(**{f'{field}__exact': None}))


# Relation-count annotations. Emptiness is tested on these aggregates instead of
# ``~Q(relation__isnull=False)`` because Django mis-joins several negated m2m Q
# objects inside one big OR — that silently drops most incomplete rows from the
# result (e.g. it returned fewer titles than ``age_rating=''`` alone). Filtering on
# Count() annotations evaluates in HAVING and composes correctly under OR.
_MOVIE_REL_ANNOTATIONS = {
    '_ngenres': Count('genres', distinct=True),
    '_nactors': Count('movie_actors', distinct=True),
    '_ndirectors': Count('directors', distinct=True),
    '_ncountries': Count('countries', distinct=True),
}
_SERIES_REL_ANNOTATIONS = {
    '_ngenres': Count('genres', distinct=True),
    '_nactors': Count('series_actors', distinct=True),
    '_ndirectors': Count('directors', distinct=True),
    '_ncountries': Count('countries', distinct=True),
}


def _movie_incomplete_q():
    # A trailer is missing only when neither the hosted key nor the external URL is set.
    trailer_empty = Q(trailer_external_url='') & Q(trailer_url='')
    return (
        Q(description='')
        | Q(release_date__isnull=True)
        | _missing_art_q('poster')
        | _missing_art_q('backdrop')
        | _missing_art_q('poster_external_url')
        | _missing_art_q('backdrop_external_url')
        | _missing_art_q('poster_path')
        | Q(_ngenres=0)
        | Q(_nactors=0)
        | Q(_ndirectors=0)
        | Q(_ncountries=0)
        | Q(original_title='')
        | Q(age_rating='')
        | trailer_empty
        | Q(writers=[])
    )


def _series_incomplete_q():
    trailer_empty = Q(trailer_external_url='') & Q(trailer_url='')
    return (
        Q(description='')
        | Q(start_year__isnull=True)
        | _missing_art_q('poster')
        | _missing_art_q('backdrop')
        | _missing_art_q('poster_external_url')
        | _missing_art_q('backdrop_external_url')
        | Q(_ngenres=0)
        | Q(_nactors=0)
        | Q(_ndirectors=0)
        | Q(_ncountries=0)
        | Q(original_title='')
        | Q(age_rating='')
        | trailer_empty
    )


def _needs_title_fix(title: str) -> bool:
    return bool(contains_disallowed_catalog_script(title))


class Command(BaseCommand):
    help = (
        'Complete missing metadata (description, release date/year, genres, '
        'cast, crew, countries) and artwork (poster/backdrop) for incomplete '
        'catalog titles, using TMDB. Optionally scoped to a single release year.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0, help='Max titles to process (0 = all).')
        parser.add_argument('--sleep', type=float, default=0.15, help='Pause between TMDB calls.')
        parser.add_argument('--year', type=int, default=0, help='Only titles released in this year (0 = all).')
        parser.add_argument('--movies-only', action='store_true')
        parser.add_argument('--series-only', action='store_true')
        parser.add_argument('--include-unpublished', action='store_true')
        parser.add_argument(
            '--include-sourced-drafts', action='store_true',
            help=(
                'Also fill unpublished titles that already have download links. '
                'They are one metadata pass away from the publish gate; a '
                'published-only pass never reached them.'
            ),
        )
        parser.add_argument('--dry-run', action='store_true', help='Report only; write nothing.')
        parser.add_argument('--no-poster-fallback', action='store_true')
        parser.add_argument(
            '--stale-days', type=int, default=0,
            help=(
                'Only re-sync titles last synced more than N days ago (or never). '
                'Rotates coverage and avoids re-hitting titles TMDB cannot fill '
                '(0 = disabled, uses popularity order).'
            ),
        )

    def handle(self, *args, **options):
        client = configured_tmdb_client()
        limit = max(0, int(options['limit'] or 0))
        sleep = max(0.0, float(options['sleep'] or 0))
        year = max(0, int(options['year'] or 0))
        do_movies = not options['series_only']
        do_series = not options['movies_only']
        published_only = not bool(options['include_unpublished'])
        sourced_drafts = bool(options['include_sourced_drafts'])
        dry_run = bool(options['dry_run'])
        allow_poster_fallback = not bool(options['no_poster_fallback'])
        stale_days = max(0, int(options['stale_days'] or 0))
        stale_cutoff = timezone.now() - timedelta(days=stale_days) if stale_days else None

        stats = {
            'movies_fixed': 0,
            'series_fixed': 0,
            'resolved_search': 0,
            'poster_fallback': 0,
            'skipped_no_match': 0,
            'tmdb_repointed': 0,
            'tmdb_gone': 0,
            'errors': 0,
        }
        processed = 0

        def budget_ok() -> bool:
            return not limit or processed < limit

        def resolve_tmdb_id(content_type: str, obj) -> int | None:
            """Return a TMDB id from the row, its IMDb id, or a title search."""
            if getattr(obj, 'tmdb_id', None):
                return int(obj.tmdb_id)
            imdb_id = str(getattr(obj, 'imdb_id', None) or '').strip()
            if imdb_id:
                summary = client.resolve_imdb_to_tmdb(imdb_id, content_type=content_type)
                if summary and summary.get('id'):
                    stats['resolved_search'] += 1
                    return int(summary['id'])
            query = (obj.original_title or obj.title or '').strip()
            if not query:
                return None
            if content_type == 'series':
                payload = client.search_tv(query, first_air_year=getattr(obj, 'start_year', None))
                results = payload.get('results') or []
            else:
                payload = client.search_movies(query, year=getattr(obj, 'release_year', None))
                results = payload.get('results') or []
            year = getattr(obj, 'release_year', None) or getattr(obj, 'start_year', None)
            if year:
                for row in results:
                    date = str(row.get('release_date') or row.get('first_air_date') or '')
                    if date.startswith(str(year)):
                        stats['resolved_search'] += 1
                        return int(row['id'])
            if results:
                stats['resolved_search'] += 1
                return int(results[0]['id'])
            return None

        def recover_deleted_tmdb(content_type: str, obj, exc: TMDBError) -> bool:
            """TMDB deleted this id (404). Repoint via IMDb, or rest the row.

            A deleted/merged TMDB id failed the same way every round — 13 movies
            and 3 series of each 80/40 budget, forever — because a failure
            never stamped the row and the stale order put it first again.
            IMDb ids are stable, so TMDB's own IMDb lookup usually names the
            surviving record; repoint only when no other row already owns it
            (that row *is* the title, and merging is a human decision).
            Otherwise stamp ``last_tmdb_sync_at`` so ``--stale-days`` rotates
            the row out instead of retrying it next round. Returns True when
            the row was repointed and is worth one more try.
            """
            if getattr(exc, 'status_code', None) != 404 or dry_run or not getattr(obj, 'tmdb_id', None):
                return False
            model = type(obj)
            imdb_id = str(getattr(obj, 'imdb_id', None) or '').strip()
            new_id = None
            if imdb_id:
                try:
                    summary = client.resolve_imdb_to_tmdb(imdb_id, content_type=content_type)
                except TMDBError:
                    summary = None
                if summary and summary.get('id'):
                    new_id = int(summary['id'])
            if (new_id and new_id != int(obj.tmdb_id)
                    and not model.objects.filter(tmdb_id=new_id).exclude(pk=obj.pk).exists()):
                self.stdout.write(f'{content_type}#{obj.pk} tmdb {obj.tmdb_id} deleted upstream → {new_id} via {imdb_id}')
                obj.tmdb_id = new_id
                obj.save(update_fields=['tmdb_id', 'updated_at'])
                stats['tmdb_repointed'] += 1
                return True
            obj.last_tmdb_sync_at = timezone.now()
            obj.save(update_fields=['last_tmdb_sync_at'])
            stats['tmdb_gone'] += 1
            return False

        def fill_movie(movie: Movie, *, retried: bool = False) -> bool:
            nonlocal processed
            processed += 1
            try:
                tmdb_id = resolve_tmdb_id('movie', movie)
                if not tmdb_id:
                    stats['skipped_no_match'] += 1
                    self.stdout.write(f'movie#{movie.pk} no TMDB match for {(movie.original_title or movie.title)[:50]!r}')
                    return False
                details = client.movie_details(tmdb_id)
                prefer_original_artwork(details)
                if dry_run:
                    stats['movies_fixed'] += 1
                    self.stdout.write(
                        f'[dry-run] movie#{movie.pk} {(movie.original_title or movie.title)[:50]} '
                        f'→ tmdb={tmdb_id} (would upsert + artwork)'
                    )
                    return True
                upsert_tmdb_movie(details, overwrite_manual=False)
                movie.refresh_from_db()
                if allow_poster_fallback and not movie.backdrop and not movie.backdrop_external_url:
                    if ensure_local_backdrop_from_poster(movie):
                        stats['poster_fallback'] += 1
                        movie.save(update_fields=['backdrop', 'backdrop_external_url', 'updated_at'])
                movie.updated_at = timezone.now()
                movie.save(update_fields=['updated_at'])
                stats['movies_fixed'] += 1
                self.stdout.write(
                    f"movie#{movie.pk} {(movie.original_title or movie.title)[:50]} tmdb={tmdb_id} → completed"
                )
                return True
            except TMDBError as exc:
                stale_id = getattr(movie, 'tmdb_id', None)
                if not retried and recover_deleted_tmdb('movie', movie, exc):
                    processed -= 1  # the retry is the same title, not a new one
                    return fill_movie(movie, retried=True)
                stats['errors'] += 1
                self.stderr.write(f'movie#{movie.pk} tmdb={stale_id}: {exc}')
                return False
            except Exception as exc:  # noqa: BLE001 - defensive, keep going
                stats['errors'] += 1
                self.stderr.write(f'movie#{movie.pk}: {type(exc).__name__}: {exc}')
                return False

        def fill_series(series: Series, *, retried: bool = False) -> bool:
            nonlocal processed
            processed += 1
            try:
                tmdb_id = resolve_tmdb_id('series', series)
                if not tmdb_id:
                    stats['skipped_no_match'] += 1
                    self.stdout.write(f'series#{series.pk} no TMDB match for {(series.original_title or series.title)[:50]!r}')
                    return False
                details = client.tv_details(tmdb_id)
                prefer_original_artwork(details)
                if dry_run:
                    stats['series_fixed'] += 1
                    self.stdout.write(
                        f'[dry-run] series#{series.pk} {(series.original_title or series.title)[:50]} '
                        f'→ tmdb={tmdb_id} (would upsert + artwork)'
                    )
                    return True
                upsert_tmdb_series(details)
                series.refresh_from_db()
                if allow_poster_fallback and not series.backdrop and not series.backdrop_external_url:
                    if ensure_local_backdrop_from_poster(series):
                        stats['poster_fallback'] += 1
                        series.save(update_fields=['backdrop', 'backdrop_external_url', 'updated_at'])
                series.updated_at = timezone.now()
                series.save(update_fields=['updated_at'])
                stats['series_fixed'] += 1
                self.stdout.write(
                    f"series#{series.pk} {(series.original_title or series.title)[:50]} tmdb={tmdb_id} → completed"
                )
                return True
            except TMDBError as exc:
                stale_id = getattr(series, 'tmdb_id', None)
                if not retried and recover_deleted_tmdb('series', series, exc):
                    processed -= 1
                    return fill_series(series, retried=True)
                stats['errors'] += 1
                self.stderr.write(f'series#{series.pk} tmdb={stale_id}: {exc}')
                return False
            except Exception as exc:  # noqa: BLE001
                stats['errors'] += 1
                self.stderr.write(f'series#{series.pk}: {type(exc).__name__}: {exc}')
                return False

        if do_movies:
            qs = Movie.objects.annotate(**_MOVIE_REL_ANNOTATIONS).filter(_movie_incomplete_q())
            if year:
                qs = qs.filter(release_year=year)
            if stale_cutoff is not None:
                qs = qs.filter(Q(last_tmdb_sync_at__isnull=True) | Q(last_tmdb_sync_at__lt=stale_cutoff))
                qs = qs.order_by(F('last_tmdb_sync_at').asc(nulls_first=True), '-popularity', 'id').distinct()
            else:
                qs = qs.order_by('-popularity', 'id').distinct()
            if published_only:
                visible = Q(is_published=True)
                if sourced_drafts:
                    visible |= Q(is_published=False) & (
                        ~Q(download_links=[]) & Q(download_links__isnull=False)
                        | ~Q(video_url='') & Q(video_url__isnull=False)
                    )
                    visible &= ~Q(publication_status=Movie.PublicationStatus.ARCHIVED)
                qs = qs.filter(visible)
            for movie in qs.iterator(chunk_size=50):
                if not budget_ok():
                    break
                fill_movie(movie)
                if sleep:
                    time.sleep(sleep)

        if do_series:
            qs = Series.objects.annotate(**_SERIES_REL_ANNOTATIONS).filter(_series_incomplete_q())
            if year:
                qs = qs.filter(start_year=year)
            if stale_cutoff is not None:
                qs = qs.filter(Q(last_tmdb_sync_at__isnull=True) | Q(last_tmdb_sync_at__lt=stale_cutoff))
                qs = qs.order_by(F('last_tmdb_sync_at').asc(nulls_first=True), '-popularity', 'id').distinct()
            else:
                qs = qs.order_by('-popularity', 'id').distinct()
            if published_only:
                visible = Q(is_published=True)
                if sourced_drafts:
                    visible |= Q(is_published=False) & ~Q(download_links=[]) & Q(download_links__isnull=False)
                qs = qs.filter(visible)
            for series in qs.iterator(chunk_size=50):
                if not budget_ok():
                    break
                fill_series(series)
                if sleep:
                    time.sleep(sleep)

        self.stdout.write(self.style.SUCCESS(
            'complete_catalog_metadata done: '
            f'movies_fixed={stats["movies_fixed"]} series_fixed={stats["series_fixed"]} '
            f'resolved_search={stats["resolved_search"]} poster_fallback={stats["poster_fallback"]} '
            f'skipped_no_match={stats["skipped_no_match"]} tmdb_repointed={stats["tmdb_repointed"]} '
            f'tmdb_gone={stats["tmdb_gone"]} errors={stats["errors"]}'
        ))
