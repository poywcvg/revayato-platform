"""Delete draft catalog titles that still have no poster OR backdrop artwork.

Designed to be run AFTER an artwork enrichment pass (e.g.
``complete_catalog_metadata --include-unpublished``). Any draft movie/series left
without usable artwork (local ImageField, external URL, or, for movies, TMDB
path) and with no playable media is treated as an unusable catalog shell and
removed.

Rules:
* Only DRAFT (unpublished, no playable media) titles are deleted.
* Published titles are ALWAYS kept, even if they lack artwork — they carry real
  playback/download content and were explicitly out of scope.
* Drafts that DO have a playable video/download are also kept (content loss would
  be real, even if unpublished).
* Deletion uses ``queryset.delete()`` so Django fires ``post_delete`` cache
  invalidation signals and cascades dependents (MovieActor/SeriesActor, seasons,
  episodes, archive assets) the same way other bulk removals in this codebase do
  (see ``purge_iranian_catalog`` in myf2m_reconcile.py).
* Without ``--confirm`` the command only reports; run --confirm to actually
  delete.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.catalog.models import Movie, Series


def _missing_art_q(field: str) -> Q:
    """Q matching "field is empty/unset" for a Char/Image/URL field."""
    return Q(**{field: ''}) | Q(**{field + '__isnull': True})


def _movie_has_no_poster() -> Q:
    return (
        _missing_art_q('poster')
        & _missing_art_q('poster_external_url')
        & _missing_art_q('poster_path')
    )


def _movie_has_no_backdrop() -> Q:
    return (
        _missing_art_q('backdrop')
        & _missing_art_q('backdrop_external_url')
        & _missing_art_q('backdrop_path')
    )


def _series_has_no_poster() -> Q:
    return _missing_art_q('poster') & _missing_art_q('poster_external_url')


def _series_has_no_backdrop() -> Q:
    return _missing_art_q('backdrop') & _missing_art_q('backdrop_external_url')


class Command(BaseCommand):
    help = (
        'Delete DRAFT movies/series still lacking poster & backdrop artwork after an '
        'enrichment pass. Published titles and any title with playable media are kept. '
        'Use --confirm to actually delete; otherwise it only reports.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true', help='Actually delete (without this only a report is shown).')
        parser.add_argument('--limit', type=int, default=0, help='Max candidates per model to act on (0 = all).')
        parser.add_argument('--movies-only', action='store_true')
        parser.add_argument('--series-only', action='store_true')

    def handle(self, *args, **options):
        confirm = bool(options['confirm'])
        limit = max(0, int(options['limit'] or 0))
        do_movies = not options['series_only']
        do_series = not options['movies_only']

        deleted_movies = 0
        deleted_series = 0
        kept_with_playback_m = 0
        kept_with_playback_s = 0

        if not confirm:
            self.stdout.write(self.style.WARNING(
                'REPORT ONLY — nothing will be deleted. Pass --confirm to actually delete.'
            ))

        if do_movies:
            m_qs = Movie.objects.filter(
                is_published=False,
                publication_status='draft',
            ).filter(_movie_has_no_poster() | _movie_has_no_backdrop())
            if limit:
                m_qs = m_qs[:limit]
            m_rows = list(m_qs.values_list('pk', 'tmdb_id', 'title', 'download_key', 'video_url'))
            self.stdout.write(
                f'candidate draft movies (missing poster and/or backdrop): {len(m_rows)}'
            )
            to_delete = []
            for pk, _tmdb_id, _title, dk, vod in m_rows:
                has_media = bool((dk or '').strip() or (vod or '').strip())
                if has_media:
                    kept_with_playback_m += 1
                    continue
                to_delete.append(pk)
            self.stdout.write(
                f'  would delete movies: {len(to_delete)} / keep-with-playback: {kept_with_playback_m}'
            )
            if confirm and to_delete:
                before = timezone.now()
                deleted_movies = Movie.objects.filter(id__in=to_delete).delete()[0]
                self.stdout.write(f'  deleted movies: {deleted_movies} '
                                  f'(took {(timezone.now() - before).total_seconds():.1f}s)')

        if do_series:
            s_qs = Series.objects.filter(
                is_published=False,
            ).filter(_series_has_no_poster() | _series_has_no_backdrop())
            if limit:
                s_qs = s_qs[:limit]
            s_rows = list(s_qs.values_list('pk', 'tmdb_id', 'title', 'download_links'))
            self.stdout.write(
                f'candidate draft series (missing poster and/or backdrop): {len(s_rows)}'
            )
            to_delete = []
            for pk, _tmdb_id, _title, dls in s_rows:
                if bool(dls):
                    kept_with_playback_s += 1
                    continue
                to_delete.append(pk)
            self.stdout.write(
                f'  would delete series: {len(to_delete)} / keep-with-playback: {kept_with_playback_s}'
            )
            if confirm and to_delete:
                before = timezone.now()
                deleted_series = Series.objects.filter(id__in=to_delete).delete()[0]
                self.stdout.write(f'  deleted series: {deleted_series} '
                                  f'(took {(timezone.now() - before).total_seconds():.1f}s)')

        self.stdout.write(self.style.SUCCESS(
            'summary: '
            f'movies_deleted={deleted_movies} series_deleted={deleted_series} '
            f'kept_with_playback_movies={kept_with_playback_m} '
            f'kept_with_playback_series={kept_with_playback_s}'
        ))