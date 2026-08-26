"""Structured import guarantees.

Every imported movie/series must carry: a Persian title, an English/Latin
original title, a Persian plot summary, cast, genres and core facts — no
matter which caller feeds the upsert pipeline.
"""

from unittest import mock
from copy import deepcopy

from urllib.error import URLError

from django.test import TestCase

from .completeness import metadata_gaps, publish_blockers
from .ingestion import upsert_tmdb_movie, upsert_tmdb_series
from .localization import contains_persian, is_latin_text
from .models import Episode, Movie, Season, Series


def _offline_artwork():
    """Never reach the TMDB image CDN from tests; external URLs still persist."""
    return mock.patch(
        'apps.catalog.ingestion.urllib.request.urlopen',
        side_effect=URLError('offline'),
    )


MOVIE_PAYLOAD = {
    'id': 9101,
    'title': 'Structured Import',
    'original_title': 'Structured Import',
    'overview': 'An English overview that must be replaced by Persian text.',
    'translations': {
        'translations': [
            {
                'iso_639_1': 'fa',
                'data': {
                    'title': 'درون‌ریزی ساختاریافته',
                    'overview': 'خلاصه داستان فارسی برای آزمون ساختار درون‌ریزی.',
                    'tagline': '',
                },
            },
        ],
    },
    'release_date': '2026-05-01',
    'runtime': 101,
    'original_language': 'en',
    'vote_average': 7.2,
    'vote_count': 880,
    'popularity': 18.4,
    'genres': [{'id': 28, 'name': 'Action'}],
    'production_countries': [{'iso_3166_1': 'US', 'name': 'United States'}],
    'external_ids': {'imdb_id': 'tt91019101'},
    'credits': {
        'cast': [
            {'id': 31, 'name': 'Lead Actor', 'character': 'Hero', 'popularity': 5.1},
            {'id': 32, 'name': 'Support Actor', 'character': 'Sidekick', 'popularity': 2.3},
        ],
        'crew': [{'id': 33, 'name': 'Movie Director', 'job': 'Director', 'popularity': 3.0}],
    },
    'status': 'Released',
    'poster_path': '/structured-poster.jpg',
    'backdrop_path': '/structured-backdrop.jpg',
}

SERIES_PAYLOAD = {
    'id': 9201,
    'name': 'Structured Series',
    'original_name': 'Structured Series',
    'overview': 'English series overview awaiting Persian replacement.',
    'translations': {
        'translations': [
            {
                'iso_639_1': 'fa',
                'data': {
                    'title': 'سریال ساختاریافته',
                    'overview': 'خلاصه داستان فارسی سریال برای آزمون ساختار درون‌ریزی.',
                    'tagline': '',
                },
            },
        ],
    },
    'first_air_date': '2026-01-10',
    'last_air_date': '2026-03-20',
    'status': 'Ended',
    'original_language': 'en',
    'vote_average': 8.1,
    'vote_count': 1520,
    'popularity': 31.2,
    'genres': [{'id': 18, 'name': 'Drama'}],
    'origin_country': ['US'],
    'external_ids': {'imdb_id': 'tt92019201'},
    'credits': {
        'cast': [{'id': 41, 'name': 'Series Actor', 'character': 'Main', 'popularity': 6.0}],
        'crew': [{'id': 42, 'name': 'Series Director', 'job': 'Director', 'popularity': 2.5}],
    },
    'created_by': [],
    'number_of_seasons': 1,
    'number_of_episodes': 8,
    'poster_path': '/series-poster.jpg',
    'backdrop_path': '/series-backdrop.jpg',
}


class StructuredMovieImportTests(TestCase):
    @staticmethod
    def _movie_payload():
        # ensure_persian_metadata mutates payloads; always hand it a fresh copy.
        return deepcopy(MOVIE_PAYLOAD)

    def test_movie_import_produces_full_structure(self):
        with _offline_artwork():
            movie, created, _published, _skipped = upsert_tmdb_movie(self._movie_payload())

        self.assertTrue(created)
        self.assertTrue(contains_persian(movie.title))
        self.assertEqual(movie.original_title, 'Structured Import')
        self.assertTrue(is_latin_text(movie.original_title))
        self.assertTrue(contains_persian(movie.description))
        self.assertTrue(contains_persian(movie.short_description))
        self.assertTrue(movie.movie_actors.exists())
        self.assertEqual(movie.movie_actors.count(), 2)
        self.assertTrue(movie.directors.exists())
        self.assertTrue(movie.genres.exists())
        self.assertEqual(movie.metadata_structure_gaps, [])
        self.assertNotIn('missing_cast', publish_blockers(movie))

    def test_untranslatable_payload_is_blocked_from_publishing(self):
        payload = self._movie_payload()
        payload.pop('translations', None)
        manifest = {
            str(payload['id']): {
                'hls_key': f"movies/{payload['id']}/hls/master.m3u8",
                'rights_verified': True,
                'auto_publish': True,
            },
        }
        with mock.patch(
            'apps.catalog.localization.translate_to_persian',
            return_value='',
        ), _offline_artwork():
            movie, created, published, _skipped = upsert_tmdb_movie(
                payload,
                media_entry=manifest[str(payload['id'])],
                auto_publish=True,
            )

        self.assertTrue(created)
        self.assertFalse(published)
        self.assertFalse(movie.is_published)
        self.assertIn('missing_persian_title', movie.auto_publish_blockers)
        self.assertIn('missing_description', movie.auto_publish_blockers)
        self.assertTrue(metadata_gaps(movie))

    def test_localized_payload_is_not_relocalized_on_resync(self):
        with _offline_artwork():
            upsert_tmdb_movie(self._movie_payload())
            movie, created, _published, _skipped = upsert_tmdb_movie(self._movie_payload())

        self.assertFalse(created)
        self.assertTrue(contains_persian(movie.title))
        self.assertEqual(movie.original_title, 'Structured Import')
        self.assertEqual(movie.metadata_structure_gaps, [])

    def test_title_source_marker_does_not_bypass_overview_localization(self):
        payload = self._movie_payload()
        payload['_title_source'] = 'provider'
        payload['overview'] = 'This English plot must not bypass localization.'

        with _offline_artwork():
            movie, _created, _published, _skipped = upsert_tmdb_movie(payload)

        self.assertEqual(
            movie.description,
            'خلاصه داستان فارسی برای آزمون ساختار درون‌ریزی.',
        )


class StructuredSeriesImportTests(TestCase):
    @staticmethod
    def _series_payload():
        return deepcopy(SERIES_PAYLOAD)

    def test_series_import_produces_full_structure(self):
        with _offline_artwork():
            series, created = upsert_tmdb_series(self._series_payload())

        self.assertTrue(created)
        self.assertTrue(contains_persian(series.title))
        self.assertEqual(series.original_title, 'Structured Series')
        self.assertTrue(is_latin_text(series.original_title))
        self.assertTrue(contains_persian(series.description))
        self.assertTrue(series.series_actors.exists())
        self.assertTrue(series.directors.exists())
        self.assertTrue(series.genres.exists())
        self.assertTrue(series.countries.exists())
        # No episodes yet → playback is the only blocker; structure is complete.
        self.assertEqual(series.metadata_structure_gaps, [])
        self.assertIn('missing_playback_links', series.auto_publish_blockers)

    def test_series_playback_blocker_clears_once_episodes_exist(self):
        with _offline_artwork():
            series, _created = upsert_tmdb_series(self._series_payload())

        season = Season.objects.create(series=series, season_number=1, title='فصل اول')
        Episode.objects.create(season=season, episode_number=1, title='قسمت اول')

        series = Series.objects.get(pk=series.pk)
        self.assertNotIn('missing_playback_links', series.auto_publish_blockers)

    def test_incomplete_series_reports_structural_gaps(self):
        series = Series.objects.create(
            title='Only English',
            original_title='Only English',
            slug='only-english',
            start_year=2026,
        )
        gaps = series.metadata_structure_gaps
        self.assertIn('missing_persian_title', gaps)
        self.assertIn('missing_description', gaps)
        self.assertIn('missing_cast', gaps)
        self.assertIn('missing_genres', gaps)
        for gap in ('missing_persian_title', 'missing_cast', 'missing_genres'):
            self.assertIn(gap, series.auto_publish_blockers)
