"""Tests for the IMDb ratings dataset path.

The point of these is the two things that would silently corrupt the catalog:
a binary search that returns the *wrong neighbour* instead of nothing, and a
sync that overwrites a score a human set on purpose.
"""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.test import TestCase

from apps.catalog import imdb_dataset
from apps.catalog.models import Movie, Series

# Deliberately includes both 9- and 10-character ids, in the byte order the real
# file ships in — "tt1000000" sorts before "tt9916880" lexicographically, and a
# search that assumed numeric order would walk off in the wrong direction.
SAMPLE = """tconst\taverageRating\tnumVotes
tt0000001\t5.7\t2231
tt0111161\t9.3\t3005010
tt1000000\t6.1\t412
tt1375666\t8.8\t2600000
tt9916880\t7.0\t12
"""


class DatasetFileMixin:
    def setUp(self):
        super().setUp()
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        path = Path(self._dir.name) / 'title.ratings.tsv'
        path.write_text(SAMPLE, encoding='utf-8')
        patcher = mock.patch.object(imdb_dataset, 'cache_dir', return_value=Path(self._dir.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        # The file is already on disk; never reach for the network in a test.
        fresh = mock.patch.object(imdb_dataset, 'ensure_dataset', side_effect=lambda **kw: path)
        fresh.start()
        self.addCleanup(fresh.stop)


class LookupTests(DatasetFileMixin, TestCase):
    def test_finds_every_row_including_the_edges(self):
        for tconst, rating, votes in (
            ('tt0000001', 5.7, 2231),
            ('tt0111161', 9.3, 3005010),
            ('tt1000000', 6.1, 412),
            ('tt1375666', 8.8, 2600000),
            ('tt9916880', 7.0, 12),
        ):
            found = imdb_dataset.lookup(tconst)
            self.assertIsNotNone(found, tconst)
            self.assertAlmostEqual(found.rating, rating)
            self.assertEqual(found.votes, votes)

    def test_missing_id_returns_none_rather_than_a_neighbour(self):
        # Each of these lands between two real rows; a sloppy binary search
        # returns whichever line it stopped on, which is a wrong rating on a
        # real title rather than an obvious failure.
        for absent in ('tt0000002', 'tt0111160', 'tt0111162', 'tt5000000', 'tt9999999'):
            self.assertIsNone(imdb_dataset.lookup(absent), absent)

    def test_ignores_ids_that_are_not_imdb_ids(self):
        for junk in ('', None, '12345', 'nm0000001'):
            self.assertIsNone(imdb_dataset.lookup(junk))

    def test_index_for_reads_only_the_requested_rows(self):
        index = imdb_dataset.index_for(['tt0111161', 'tt9916880', 'tt0404040'])
        self.assertEqual(sorted(index), ['tt0111161', 'tt9916880'])
        self.assertEqual(index['tt0111161'].votes, 3005010)


class SyncTests(DatasetFileMixin, TestCase):
    def _movie(self, **kwargs):
        defaults = dict(title='فیلم', original_title='Film', description='x', is_published=True)
        defaults.update(kwargs)
        defaults.setdefault('slug', f"m-{defaults['imdb_id']}")
        return Movie.objects.create(**defaults)

    def test_replaces_a_tmdb_approximation_with_the_real_score(self):
        movie = self._movie(imdb_id='tt0111161', imdb_rating=Decimal('8.0'),
                            imdb_rating_source='tmdb')
        result = imdb_dataset.sync_catalog_ratings(series=False)
        movie.refresh_from_db()
        self.assertEqual(movie.imdb_rating, Decimal('9.3'))
        self.assertEqual(movie.imdb_votes, 3005010)
        self.assertEqual(movie.imdb_rating_source, 'imdb')
        self.assertIsNotNone(movie.imdb_rating_synced_at)
        self.assertEqual(result['corrected'], 1)

    def test_fills_a_title_that_had_no_rating_at_all(self):
        movie = self._movie(imdb_id='tt1375666', imdb_rating=None)
        result = imdb_dataset.sync_catalog_ratings(series=False)
        movie.refresh_from_db()
        self.assertEqual(movie.imdb_rating, Decimal('8.8'))
        self.assertEqual(result['filled'], 1)

    def test_never_overwrites_a_manually_set_score(self):
        movie = self._movie(imdb_id='tt0111161', imdb_rating=Decimal('7.1'),
                            imdb_rating_source='manual')
        pinned = self._movie(imdb_id='tt1375666', imdb_rating=Decimal('6.6'),
                             imdb_rating_source='tmdb',
                             manual_override_fields=['imdb_rating'])
        result = imdb_dataset.sync_catalog_ratings(series=False)
        movie.refresh_from_db()
        pinned.refresh_from_db()
        self.assertEqual(movie.imdb_rating, Decimal('7.1'))
        self.assertEqual(pinned.imdb_rating, Decimal('6.6'))
        self.assertEqual(result['skipped_manual'], 2)
        self.assertEqual(result['updated'], 0)

    def test_leaves_titles_imdb_has_not_rated_alone(self):
        movie = self._movie(imdb_id='tt0404040', imdb_rating=Decimal('6.2'),
                            imdb_rating_source='tmdb')
        result = imdb_dataset.sync_catalog_ratings(series=False)
        movie.refresh_from_db()
        self.assertEqual(movie.imdb_rating, Decimal('6.2'))
        self.assertEqual(result['unrated_by_imdb'], 1)
        self.assertEqual(result['updated'], 0)

    def test_second_run_writes_nothing(self):
        self._movie(imdb_id='tt0111161', imdb_rating=Decimal('8.0'),
                    imdb_rating_source='tmdb')
        imdb_dataset.sync_catalog_ratings(series=False)
        again = imdb_dataset.sync_catalog_ratings(series=False)
        self.assertEqual(again['updated'], 0)

    def test_dry_run_reports_without_writing(self):
        movie = self._movie(imdb_id='tt0111161', imdb_rating=Decimal('8.0'),
                            imdb_rating_source='tmdb')
        result = imdb_dataset.sync_catalog_ratings(series=False, dry_run=True)
        movie.refresh_from_db()
        self.assertEqual(movie.imdb_rating, Decimal('8.0'))
        self.assertEqual(result['updated'], 1)

    def test_covers_series_too(self):
        series = Series.objects.create(
            title='سریال', original_title='Show', slug='s-1', description='x',
            imdb_id='tt9916880', imdb_rating=Decimal('5.0'), imdb_rating_source='tmdb',
        )
        imdb_dataset.sync_catalog_ratings(movies=False)
        series.refresh_from_db()
        self.assertEqual(series.imdb_rating, Decimal('7.0'))
        self.assertEqual(series.imdb_rating_source, 'imdb')


class EnrichmentTests(DatasetFileMixin, TestCase):
    def test_importer_prefers_the_dataset_over_tmdb_vote_average(self):
        from apps.catalog.imdb import enrich_imdb_rating

        details = {'imdb_id': 'tt0111161', 'vote_average': 8.7, 'vote_count': 27000}
        enrich_imdb_rating(details)
        self.assertEqual(details['imdb_rating'], 9.3)
        self.assertEqual(details['imdb_votes'], 3005010)
        self.assertEqual(details['imdb_rating_source'], 'imdb')

    def test_falls_back_to_tmdb_when_imdb_has_no_score(self):
        from apps.catalog.imdb import enrich_imdb_rating

        details = {'imdb_id': 'tt0404040', 'vote_average': 7.4, 'vote_count': 31}
        enrich_imdb_rating(details)
        self.assertEqual(details['imdb_rating'], 7.4)
        self.assertEqual(details['imdb_rating_source'], 'tmdb')
