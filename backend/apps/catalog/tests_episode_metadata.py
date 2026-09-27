"""Tests for the TMDB season/episode metadata completion pass."""

from datetime import date

from django.test import TestCase
from django.utils import timezone

from apps.catalog.episode_metadata import (
    _is_stub_title,
    _STUB_EPISODE_TITLE,
    complete_missing_episode_metadata,
    complete_series_episode_metadata,
    series_needing_episode_metadata,
)
from apps.catalog.models import Episode, Season, Series


class _FakeTMDB:
    """Minimal stand-in for ``TMDBClient.tv_season_details``."""

    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def tv_season_details(self, series_id, season_number, *, language=None):
        self.calls.append((series_id, season_number))
        try:
            return self.payloads[season_number]
        except KeyError as exc:
            from apps.catalog.tmdb import TMDBError
            raise TMDBError('season not found') from exc


def _season_payload(season_number, episodes):
    return {
        'id': 9000 + season_number,
        'name': f'The Real Season {season_number}',
        'overview': 'season overview',
        'air_date': '2024-03-01',
        'poster_path': '/season.jpg',
        'episodes': episodes,
    }


class EpisodeMetadataTests(TestCase):
    def setUp(self):
        self.series = Series.objects.create(
            title='سریال آزمایشی', slug='test-series', tmdb_id=555,
            is_published=True, start_year=2024,
        )
        self.season = Season.objects.create(
            series=self.series, season_number=1, title='فصل 1', is_published=True,
        )
        # The stub titles the link materializer writes carry a bidi mark.
        self.ep1 = Episode.objects.create(
            season=self.season, episode_number=1, title='‫قسمت 1', is_published=True,
        )
        self.ep2 = Episode.objects.create(
            season=self.season, episode_number=2, title='‫قسمت 2', is_published=True,
        )

    def test_stub_title_detection_ignores_bidi_marks(self):
        self.assertTrue(_is_stub_title('‫قسمت 1', _STUB_EPISODE_TITLE))
        self.assertTrue(_is_stub_title('Episode 07', _STUB_EPISODE_TITLE))
        self.assertFalse(_is_stub_title('پایان راه', _STUB_EPISODE_TITLE))

    def test_fills_titles_descriptions_air_dates_and_runtime(self):
        client = _FakeTMDB({1: _season_payload(1, [
            {'episode_number': 1, 'name': 'آغاز', 'overview': 'شرح یک',
             'air_date': '2024-03-01', 'runtime': 42},
            {'episode_number': 2, 'name': 'ادامه', 'overview': 'شرح دو',
             'air_date': '2024-03-08', 'runtime': 45},
        ])})

        result = complete_series_episode_metadata(self.series, client=client)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['episodes_updated'], 2)
        self.assertEqual(result['episodes_missing'], 0)
        self.ep1.refresh_from_db()
        self.assertEqual(self.ep1.title, 'آغاز')
        self.assertEqual(self.ep1.description, 'شرح یک')
        self.assertEqual(self.ep1.air_date, date(2024, 3, 1))
        self.assertEqual(self.ep1.duration_minutes, 42)

        self.season.refresh_from_db()
        self.assertEqual(self.season.title, 'The Real Season 1')
        self.assertEqual(self.season.description, 'season overview')
        self.assertEqual(self.season.release_year, 2024)
        # ``episode_count`` tracks the rows the site actually carries.
        self.assertEqual(self.season.episode_count, 2)
        self.assertTrue(self.season.poster_external_url.endswith('/season.jpg'))

    def test_generic_tmdb_name_does_not_replace_persian_stub(self):
        client = _FakeTMDB({1: _season_payload(1, [
            {'episode_number': 1, 'name': 'Episode 1', 'overview': 'x', 'runtime': 30},
        ])})

        complete_series_episode_metadata(self.series, client=client)

        self.ep1.refresh_from_db()
        self.assertEqual(self.ep1.title, '‫قسمت 1')
        self.assertEqual(self.ep1.description, 'x')

    def test_real_titles_are_never_overwritten(self):
        self.ep1.title = 'یک عنوان واقعی'
        self.ep1.description = 'توضیح دستی'
        self.ep1.save(update_fields=['title', 'description'])
        client = _FakeTMDB({1: _season_payload(1, [
            {'episode_number': 1, 'name': 'TMDB Name', 'overview': 'tmdb overview', 'runtime': 30},
        ])})

        complete_series_episode_metadata(self.series, client=client)

        self.ep1.refresh_from_db()
        self.assertEqual(self.ep1.title, 'یک عنوان واقعی')
        self.assertEqual(self.ep1.description, 'توضیح دستی')

    def test_missing_season_on_tmdb_is_counted_not_raised(self):
        Season.objects.create(series=self.series, season_number=7, title='فصل 7')
        client = _FakeTMDB({1: _season_payload(1, [
            {'episode_number': 1, 'name': 'آغاز', 'overview': 'شرح', 'runtime': 40},
        ])})

        result = complete_series_episode_metadata(self.series, client=client)

        self.assertEqual(result['errors'], 1)
        self.assertEqual(result['seasons_seen'], 2)
        self.assertEqual(result['episodes_updated'], 1)

    def test_english_name_fills_in_for_a_persian_stub(self):
        """TMDB's fa localisation is often «قسمت N»; en is a real improvement."""
        class _Bilingual(_FakeTMDB):
            language = 'fa-IR'
            fallback_language = 'en-US'

            def tv_season_details(self, series_id, season_number, *, language=None):
                self.calls.append((series_id, season_number, language))
                if language == 'en-US':
                    return _season_payload(1, [
                        {'episode_number': 1, 'name': 'Chapter One', 'overview': 'en overview'},
                        {'episode_number': 2, 'name': 'Episode 2', 'overview': 'en two'},
                    ])
                return _season_payload(1, [
                    {'episode_number': 1, 'name': '‫قسمت 1', 'overview': 'شرح یک', 'runtime': 40},
                    {'episode_number': 2, 'name': '‫قسمت 2', 'overview': 'شرح دو', 'runtime': 41},
                ])

        client = _Bilingual({})
        complete_series_episode_metadata(self.series, client=client)

        self.ep1.refresh_from_db()
        self.ep2.refresh_from_db()
        self.assertEqual(self.ep1.title, 'Chapter One')
        # A numbered English name is no better than the Persian stub it replaces.
        self.assertEqual(self.ep2.title, '‫قسمت 2')
        # Persian overviews are still preferred over the English ones.
        self.assertEqual(self.ep1.description, 'شرح یک')

    def test_series_without_tmdb_id_is_skipped(self):
        self.series.tmdb_id = None
        self.series.save(update_fields=['tmdb_id'])

        result = complete_series_episode_metadata(self.series, client=_FakeTMDB({}))

        self.assertEqual(result['status'], 'no_tmdb_id')

    def test_selector_finds_incomplete_series_and_honours_the_stamp(self):
        self.assertIn(self.series, list(series_needing_episode_metadata()))

        self.series.source_metadata = {'episode_metadata': {'at': timezone.now().isoformat()}}
        self.series.save(update_fields=['source_metadata'])
        # A fresh stamp suppresses the series ...
        self.assertNotIn(self.series, list(series_needing_episode_metadata()))
        # ... but a series that has never been stamped must never be dropped by
        # the JSON exclude, and ``force`` bypasses the stamp entirely.
        self.assertIn(self.series, list(series_needing_episode_metadata(force=True)))

    def test_selector_ignores_unpublished_series(self):
        self.series.is_published = False
        self.series.save(update_fields=['is_published'])
        self.assertNotIn(self.series, list(series_needing_episode_metadata()))

    def test_pass_stamps_series_even_when_nothing_changed(self):
        from unittest.mock import patch

        client = _FakeTMDB({1: _season_payload(1, [])})
        with patch('apps.catalog.episode_metadata.configured_tmdb_client', return_value=client):
            stats = complete_missing_episode_metadata(series_limit=5, stills=False, delay=0)

        self.assertEqual(stats['series_considered'], 1)
        self.assertEqual(stats['episodes_missing'], 2)
        self.series.refresh_from_db()
        self.assertIn('episode_metadata', self.series.source_metadata)
        # The stamp is what stops an unfillable series from being retried hourly.
        self.assertNotIn(self.series, list(series_needing_episode_metadata()))

    def test_cancellation_stops_the_pass(self):
        from unittest.mock import patch

        client = _FakeTMDB({1: _season_payload(1, [])})
        with patch('apps.catalog.episode_metadata.configured_tmdb_client', return_value=client):
            stats = complete_missing_episode_metadata(
                series_limit=5, stills=False, delay=0, should_cancel=lambda: True,
            )

        self.assertTrue(stats['cancelled'])
        self.assertEqual(stats['series_considered'], 0)
        self.assertEqual(client.calls, [])
