"""Why the importer ran all day and grew the catalog by almost nothing (2026-09-26).

Every lane was running; each was spending its budget on work that could not
succeed, round after round:

* the listing walk skipped every title that had *any* row — including ~7,000
  crawler-made drafts with no link at all, so the page that carried their links
  was read, recognised and thrown away (deep rounds: ~1,230 tried, 0 kept);
* the movie refresh slice was 200 titles the provider had taken down, re-tried
  every round because a failure changes nothing on the row (200/200 failed);
* a TMDB id deleted upstream failed the metadata lane the same way, forever.

These tests pin the three rotations that let the budget move on.
"""

import importlib.util
from io import StringIO
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase

from apps.catalog import refresh_rotation
from apps.catalog.models import Movie, MovieSyncAudit, Series
from apps.catalog.provider_import.exceptions import ProviderImportError, ProviderRateLimited
from apps.catalog.tmdb import TMDBError

MP4 = {'url': 'https://cdn/x/movie.720p.x264.mp4', 'quality': '720p'}


def _load_import_batch():
    path = settings.BASE_DIR / 'scripts' / 'import_missing_myf2m_batch.py'
    spec = importlib.util.spec_from_file_location('import_missing_myf2m_batch', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RefreshRotationTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_a_refused_title_rests_and_a_success_brings_it_back(self):
        refresh_rotation.remember_failure('movie', 7)
        self.assertEqual(refresh_rotation.recently_failed('movie', [7, 8]), {7})
        # Kinds never collide: a movie id is not a series id.
        self.assertEqual(refresh_rotation.recently_failed('series', [7]), set())
        refresh_rotation.forget_failure('movie', 7)
        self.assertEqual(refresh_rotation.recently_failed('movie', [7]), set())

    def test_a_rate_limit_is_the_providers_state_not_the_titles(self):
        self.assertTrue(refresh_rotation.is_rotating_failure(
            ProviderImportError('gone', code='myf2m_page_required')))
        self.assertFalse(refresh_rotation.is_rotating_failure(ProviderRateLimited('slow down')))
        self.assertFalse(refresh_rotation.is_rotating_failure(RuntimeError('boom')))

    def test_ttl_zero_turns_the_rotation_off(self):
        with patch.dict('os.environ', {'MYF2M_REFRESH_FAIL_TTL_SECONDS': '0'}):
            refresh_rotation.remember_failure('movie', 9)
        self.assertEqual(refresh_rotation.recently_failed('movie', [9]), set())

    def test_a_cache_outage_never_stops_the_lane(self):
        with patch.object(refresh_rotation.cache, 'get_many', side_effect=ConnectionError):
            self.assertEqual(refresh_rotation.recently_failed('movie', [1]), set())


class RevivableDraftTests(TestCase):
    """Which existing rows the listing walk may fill instead of skipping."""

    def setUp(self):
        self.batch = _load_import_batch()

    def _movie(self, slug, **extra):
        extra.setdefault('title', 'فیلم')
        extra.setdefault('is_published', False)
        extra.setdefault('metadata_source', 'tmdb')
        extra.setdefault('download_links', [])
        return Movie.objects.create(slug=slug, **extra)

    def test_only_linkless_crawler_drafts_are_revivable(self):
        self._movie('empty', tmdb_id=1, imdb_id='TT0000001')
        self._movie('linked', tmdb_id=2, imdb_id='tt0000002', download_links=[MP4])
        self._movie('live', tmdb_id=3, is_published=True)
        self._movie('hand', tmdb_id=4, metadata_source='manual')
        self._movie('archived', tmdb_id=5, publication_status=Movie.PublicationStatus.ARCHIVED)
        self._movie('hls', tmdb_id=6, video_url='hls/x/master.m3u8')

        tmdb_ids, imdb_ids = self.batch._sourceless_draft_ids(Movie)
        self.assertEqual(tmdb_ids, {1})
        self.assertEqual(imdb_ids, {'tt0000001'})

    def test_an_admin_archived_series_is_not_revived(self):
        kept = Series.objects.create(title='الف', slug='a', tmdb_id=11, is_published=False,
                                     metadata_source='tmdb')
        gone = Series.objects.create(title='ب', slug='b', tmdb_id=12, is_published=False,
                                     metadata_source='tmdb')
        MovieSyncAudit.objects.create(action=MovieSyncAudit.Action.ARCHIVE,
                                      details={'kind': 'series', 'object_id': gone.pk})
        tmdb_ids, _ = self.batch._sourceless_draft_ids(Series)
        self.assertEqual(tmdb_ids, {kept.tmdb_id})

    def test_the_new_only_skips_let_revivable_ids_through(self):
        # Structural: all four "already have it" checks must consult the revival set.
        source = (settings.BASE_DIR / 'scripts' / 'import_missing_myf2m_batch.py').read_text()
        for kind in ('movie', 'series'):
            self.assertIn(f'imdb_id not in revivable_{kind}_imdb', source)
            self.assertIn(f'tmdb_id not in revivable_{kind}_tmdb', source)


class DeletedTmdbIdTests(TestCase):
    """complete_catalog_metadata on an id TMDB no longer has."""

    def setUp(self):
        # The incompleteness query joins four m2m tables; on the freshly created
        # (never ANALYZEd) test tables the planner's estimate is astronomical,
        # so Postgres JIT-compiles it for ~5 s and hits the 5 s statement
        # timeout on a one-row table. Real tables carry statistics.
        with connection.cursor() as cursor:
            cursor.execute('SET jit = off')

    def _movie(self, **extra):
        return Movie.objects.create(title='فیلم', original_title='Film', slug='film',
                                    tmdb_id=100, imdb_id='tt1234567', is_published=True,
                                    description='', **extra)

    CMD = 'apps.catalog.management.commands.complete_catalog_metadata'

    def _run(self, client):
        with patch(f'{self.CMD}.configured_tmdb_client', return_value=client), \
                patch(f'{self.CMD}.prefer_original_artwork'), \
                patch(f'{self.CMD}.ensure_local_backdrop_from_poster', return_value=False), \
                patch(f'{self.CMD}.upsert_tmdb_movie') as upsert:
            call_command('complete_catalog_metadata', '--movies-only', '--sleep', '0', stdout=StringIO(),
                         stderr=StringIO())
        return upsert

    def test_a_deleted_id_is_repointed_through_imdb_and_filled(self):
        movie = self._movie()
        client = MagicMock()
        client.movie_details.side_effect = [TMDBError('gone', status_code=404), {'id': 200}]
        client.resolve_imdb_to_tmdb.return_value = {'id': 200}
        upsert = self._run(client)
        movie.refresh_from_db()
        self.assertEqual(movie.tmdb_id, 200)
        upsert.assert_called_once()

    def test_never_steals_an_id_another_row_owns(self):
        movie = self._movie()
        Movie.objects.create(title='دیگر', slug='other', tmdb_id=200)
        client = MagicMock()
        client.movie_details.side_effect = TMDBError('gone', status_code=404)
        client.resolve_imdb_to_tmdb.return_value = {'id': 200}
        self._run(client)
        movie.refresh_from_db()
        self.assertEqual(movie.tmdb_id, 100)
        # Stamped, so --stale-days rotates it out instead of retrying next round.
        self.assertIsNotNone(movie.last_tmdb_sync_at)

    def test_other_tmdb_errors_leave_the_row_alone(self):
        movie = self._movie()
        client = MagicMock()
        client.movie_details.side_effect = TMDBError('busy', status_code=503)
        self._run(client)
        movie.refresh_from_db()
        self.assertEqual(movie.tmdb_id, 100)
        self.assertIsNone(movie.last_tmdb_sync_at)
        client.resolve_imdb_to_tmdb.assert_not_called()

    def test_a_sourced_draft_is_in_scope_only_when_asked(self):
        draft = Movie.objects.create(title='پیش', original_title='Draft', slug='draft', tmdb_id=300,
                                     is_published=False, description='', download_links=[MP4])
        client = MagicMock()
        client.movie_details.return_value = {'id': 300}
        with patch(f'{self.CMD}.configured_tmdb_client', return_value=client), \
                patch(f'{self.CMD}.prefer_original_artwork'), \
                patch(f'{self.CMD}.ensure_local_backdrop_from_poster', return_value=False), \
                patch(f'{self.CMD}.upsert_tmdb_movie'):
            call_command('complete_catalog_metadata', '--movies-only', '--sleep', '0',
                         stdout=StringIO(), stderr=StringIO())
            self.assertFalse(client.movie_details.called)
            call_command('complete_catalog_metadata', '--movies-only', '--sleep', '0',
                         '--include-sourced-drafts', stdout=StringIO(), stderr=StringIO())
        client.movie_details.assert_called_once_with(draft.tmdb_id)
