"""Every movie and series carries a real Persian title and an English title.

Covers the title source order (TMDB fa → Wikidata → stored → machine
translation), the no-downgrade guarantee on re-sync, ``repair_titles`` /
``repair_catalog_titles``, age bands and the metadata gap fillers.
"""

from copy import deepcopy
from io import StringIO
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings

from .age_ratings import age_rating_bucket, raw_ratings_in_band
from .ingestion import (
    _certification_from_details,
    _episode_directors,
    _series_content_rating,
    upsert_tmdb_movie,
    upsert_tmdb_series,
)
from .localization import clean_wikipedia_title, wikidata_persian_title
from .models import Movie, Series
from .tests_import_structure import MOVIE_PAYLOAD, SERIES_PAYLOAD, _offline_artwork
from .title_repair import repair_titles, title_problem


def _without_fa(payload):
    payload = deepcopy(payload)
    payload['translations'] = {'translations': []}
    return payload


def _no_mt():
    return mock.patch('apps.catalog.localization.translate_to_persian', return_value='')


class ResyncNeverDowngradesTests(TestCase):
    def test_movie_resync_without_fa_keeps_persian_title_and_overview(self):
        with _offline_artwork():
            movie = upsert_tmdb_movie(deepcopy(MOVIE_PAYLOAD))[0]
        title, description = movie.title, movie.description
        with _offline_artwork(), _no_mt():
            movie, created, _published, _skipped = upsert_tmdb_movie(_without_fa(MOVIE_PAYLOAD))
        self.assertFalse(created)
        movie.refresh_from_db()
        self.assertEqual(movie.title, title)
        self.assertEqual(movie.description, description)
        self.assertEqual(movie.original_title, MOVIE_PAYLOAD['original_title'])

    def test_series_resync_without_fa_keeps_persian_title_and_overview(self):
        with _offline_artwork():
            series, _ = upsert_tmdb_series(deepcopy(SERIES_PAYLOAD))
        title, description = series.title, series.description
        with _offline_artwork(), _no_mt():
            series, created = upsert_tmdb_series(_without_fa(SERIES_PAYLOAD))
        self.assertFalse(created)
        series.refresh_from_db()
        self.assertEqual(series.title, title)
        self.assertEqual(series.description, description)


class TitleSourceOrderTests(TestCase):
    def test_wikidata_beats_machine_translation(self):
        with _offline_artwork(), \
                mock.patch('apps.catalog.localization.wikidata_persian_title', return_value='نام ویکی') as wiki, \
                mock.patch('apps.catalog.localization.translate_to_persian', return_value='ترجمه ماشینی'):
            movie = upsert_tmdb_movie(_without_fa(MOVIE_PAYLOAD))[0]
        self.assertEqual(movie.title, 'نام ویکی')
        self.assertEqual(movie.source_metadata.get('title_source'), 'wikidata')
        # Memoized on the payload: one lookup even though localization runs twice.
        self.assertEqual(wiki.call_count, 1)

    def test_tmdb_fa_beats_wikidata(self):
        with _offline_artwork(), \
                mock.patch('apps.catalog.localization.wikidata_persian_title', return_value='نام ویکی'):
            movie = upsert_tmdb_movie(deepcopy(MOVIE_PAYLOAD))[0]
        self.assertNotEqual(movie.title, 'نام ویکی')
        self.assertEqual(movie.source_metadata.get('title_source'), 'tmdb_translation')

    def test_machine_translation_is_last_resort_and_labelled(self):
        with _offline_artwork(), \
                mock.patch('apps.catalog.localization.wikidata_persian_title', return_value=''), \
                mock.patch('apps.catalog.localization.translate_to_persian', return_value='ترجمه ماشینی'):
            movie = upsert_tmdb_movie(_without_fa(MOVIE_PAYLOAD))[0]
        self.assertEqual(movie.title, 'ترجمه ماشینی')
        self.assertEqual(movie.source_metadata.get('title_source'), 'machine_translation')


@override_settings(CATALOG_WIKIDATA_TITLES_ENABLED=True)
class WikidataLookupTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_clean_wikipedia_title_strips_qualifiers(self):
        self.assertEqual(clean_wikipedia_title('تلقین (فیلم)'), 'تلقین')
        self.assertEqual(clean_wikipedia_title('دوستان (مجموعه تلویزیونی) (۱۹۹۴)'), 'دوستان')
        self.assertEqual(clean_wikipedia_title('(فیلم)'), '(فیلم)')

    def test_single_hit_returns_fawiki_title(self):
        responses = [
            {'query': {'search': [{'title': 'Q25188'}]}},
            {'entities': {'Q25188': {
                'sitelinks': {'fawiki': {'title': 'تلقین (فیلم)'}},
                'labels': {'fa': {'value': 'سرآغاز'}},
            }}},
        ]
        with mock.patch('apps.catalog.localization._wikidata_get', side_effect=responses):
            self.assertEqual(wikidata_persian_title(imdb_id='tt1375666', tmdb_id=27205), 'تلقین')
        # Cached: no second network round-trip.
        with mock.patch('apps.catalog.localization._wikidata_get') as get:
            self.assertEqual(wikidata_persian_title(imdb_id='tt1375666', tmdb_id=27205), 'تلقین')
            get.assert_not_called()

    def test_ambiguous_id_trusts_nothing(self):
        with mock.patch(
            'apps.catalog.localization._wikidata_get',
            return_value={'query': {'search': [{'title': 'Q1'}, {'title': 'Q2'}]}},
        ):
            self.assertEqual(wikidata_persian_title(imdb_id='tt0000001'), '')

    def test_latin_label_is_not_a_persian_title(self):
        responses = [
            {'query': {'search': [{'title': 'Q9'}]}},
            {'entities': {'Q9': {'labels': {'fa': {'value': 'Inception'}}}}},
        ]
        with mock.patch('apps.catalog.localization._wikidata_get', side_effect=responses):
            self.assertEqual(wikidata_persian_title(imdb_id='tt0000009'), '')

    def test_outage_trips_breaker(self):
        with mock.patch('apps.catalog.localization._wikidata_get', side_effect=TimeoutError()):
            self.assertEqual(wikidata_persian_title(imdb_id='tt0000002'), '')
        with mock.patch('apps.catalog.localization._wikidata_get') as get:
            self.assertEqual(wikidata_persian_title(imdb_id='tt0000003'), '')
            get.assert_not_called()


class FakeTmdb:
    def __init__(self, translations):
        self.translations = translations

    def _request(self, path, params):
        return {'translations': [
            {'iso_639_1': lang, 'data': data} for lang, data in self.translations.items()
        ]}


class RepairTitlesTests(TestCase):
    def setUp(self):
        self.wiki = mock.patch('apps.catalog.title_repair.wikidata_persian_title', return_value='')
        self.wiki.start()
        self.addCleanup(self.wiki.stop)

    def test_english_only_row_gets_tmdb_persian_title(self):
        movie = Movie.objects.create(title='The Lost Girls', original_title='The Lost Girls', slug='lost-girls', tmdb_id=501)
        self.assertEqual(title_problem(movie), 'missing_persian_title')
        result = repair_titles(movie, client=FakeTmdb({'fa': {'title': 'دختران گمشده'}}))
        movie.refresh_from_db()
        self.assertEqual(movie.title, 'دختران گمشده')
        self.assertEqual(movie.source_metadata['title_source'], 'tmdb_translation')
        self.assertEqual(result['unresolved'], [])
        self.assertEqual(title_problem(movie), '')

    def test_machine_title_upgraded_to_wikidata(self):
        movie = Movie.objects.create(
            title='ترجمه ماشینی', original_title='Inception', slug='inception', imdb_id='tt1375666',
            source_metadata={'title_source': 'machine_translation'},
        )
        self.assertEqual(title_problem(movie), 'machine_title')
        with mock.patch('apps.catalog.title_repair.wikidata_persian_title', return_value='تلقین'):
            repair_titles(movie, client=None)
        movie.refresh_from_db()
        self.assertEqual(movie.title, 'تلقین')
        self.assertEqual(movie.source_metadata['title_source'], 'wikidata')

    def test_curated_title_is_not_replaced_by_machine_translation(self):
        movie = Movie.objects.create(
            title='نام انتخابی', original_title='Chosen', slug='chosen',
            source_metadata={'title_source': 'provider'},
        )
        with mock.patch('apps.catalog.title_repair.translate_to_persian', return_value='ترجمه'):
            result = repair_titles(movie, client=None)
        self.assertNotIn('title', result['changed'])
        movie.refresh_from_db()
        self.assertEqual(movie.title, 'نام انتخابی')

    def test_manual_override_is_never_touched(self):
        movie = Movie.objects.create(title='English Only', original_title='English Only', slug='english-only', tmdb_id=502)
        if not hasattr(movie, 'manual_override_fields'):
            self.skipTest('model has no manual overrides')
        movie.manual_override_fields = ['title']
        movie.save(update_fields=['manual_override_fields'])
        repair_titles(movie, client=FakeTmdb({'fa': {'title': 'فقط انگلیسی'}}))
        movie.refresh_from_db()
        self.assertEqual(movie.title, 'English Only')

    def test_non_english_original_replaced_by_tmdb_english(self):
        series = Series.objects.create(title='خانه کاغذی', original_title='La casa de papel', slug='money-heist', tmdb_id=71446)
        repair_titles(series, client=FakeTmdb({'en': {'name': 'Money Heist'}}))
        series.refresh_from_db()
        self.assertEqual(series.original_title, 'Money Heist')
        self.assertEqual(series.title, 'خانه کاغذی')

    def test_swapped_titles_are_restored(self):
        movie = Movie.objects.create(title='Parasite', original_title='انگل', slug='parasite')
        repair_titles(movie, client=None, translate=False)
        movie.refresh_from_db()
        self.assertEqual(movie.title, 'انگل')
        self.assertEqual(movie.original_title, 'Parasite')

    def test_dry_run_writes_nothing(self):
        movie = Movie.objects.create(title='Dry', original_title='Dry', slug='dry', tmdb_id=503)
        result = repair_titles(movie, client=FakeTmdb({'fa': {'title': 'خشک'}}), dry_run=True)
        self.assertIn('title', result['changed'])
        movie.refresh_from_db()
        self.assertEqual(movie.title, 'Dry')


class RepairCommandTests(TestCase):
    def test_report_counts_problems(self):
        Movie.objects.create(title='English Only', original_title='English Only', slug='eo', is_published=True)
        Movie.objects.create(title='درست', original_title='Fine', slug='fine', is_published=True,
                             source_metadata={'title_source': 'tmdb_translation'})
        out = StringIO()
        call_command('repair_catalog_titles', '--report', '--movies-only', stdout=out)
        text = out.getvalue()
        self.assertIn('published_missing_persian_title=1', text)
        self.assertIn('published_total=2', text)

    def test_repair_run_fixes_broken_rows(self):
        movie = Movie.objects.create(title='Parasite', original_title='انگل', slug='parasite2', is_published=True)
        out = StringIO()
        with mock.patch('apps.catalog.tmdb.configured_tmdb_client', side_effect=RuntimeError('no key')), \
                mock.patch('apps.catalog.title_repair.wikidata_persian_title', return_value=''):
            call_command('repair_catalog_titles', '--no-translate', '--sleep', '0', stdout=out, stderr=StringIO())
        movie.refresh_from_db()
        self.assertEqual((movie.title, movie.original_title), ('انگل', 'Parasite'))
        self.assertIn('changed=1', out.getvalue())


class AgeBandTests(TestCase):
    def test_bucket(self):
        cases = {
            'PG-13': '12+', 'G': '12+', 'TV-PG': '12+', 'TV-14': '15+', 'R': '18+', 'NC-17': '18+',
            'TV-MA': '18+', '15': '15+', '16': '15+', '18': '18+', 'R15+': '15+', '12A': '12+',
            'FSK 18': '18+', 'NR': '', 'Unrated': '', '': '',
        }
        for raw, band in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(age_rating_bucket(raw), band)

    def test_raw_ratings_in_band(self):
        self.assertEqual(raw_ratings_in_band(['R', 'TV-MA', 'PG', '18', ''], '18+'), ['18', 'R', 'TV-MA'])

    def test_api_band_filter_matches_raw_certification(self):
        Movie.objects.create(title='بزرگسال', original_title='Adult', slug='adult', age_rating='R', is_published=True)
        Movie.objects.create(title='خانوادگی', original_title='Family', slug='family', age_rating='PG', is_published=True)
        response = self.client.get('/api/movies/', {'age_rating': '18+'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        rows = body.get('results', body) if isinstance(body, dict) else body
        self.assertEqual([row['slug'] for row in rows], ['adult'])


class MetadataGapFillerTests(TestCase):
    def test_certification_falls_back_to_origin_country(self):
        details = {
            'origin_country': ['KR'],
            'release_dates': {'results': [
                {'iso_3166_1': 'KR', 'release_dates': [{'certification': '15'}]},
                {'iso_3166_1': 'FR', 'release_dates': [{'certification': 'U'}]},
            ]},
        }
        self.assertEqual(_certification_from_details(details), '15')

    def test_certification_prefers_us_over_origin(self):
        details = {
            'production_countries': [{'iso_3166_1': 'KR'}],
            'release_dates': {'results': [
                {'iso_3166_1': 'KR', 'release_dates': [{'certification': '15'}]},
                {'iso_3166_1': 'US', 'release_dates': [{'certification': 'R'}]},
            ]},
        }
        self.assertEqual(_certification_from_details(details), 'R')

    def test_series_rating_falls_back_to_origin_country(self):
        details = {'origin_country': ['JP'], 'content_ratings': {'results': [{'iso_3166_1': 'JP', 'rating': 'R15+'}]}}
        self.assertEqual(_series_content_rating(details), 'R15+')

    def test_episode_directors_ranked_by_episode_count(self):
        details = {'aggregate_credits': {'crew': [
            {'id': 1, 'name': 'Few', 'jobs': [{'job': 'Director', 'episode_count': 1}]},
            {'id': 2, 'name': 'Many', 'jobs': [{'job': 'Director', 'episode_count': 6}]},
            {'id': 3, 'name': 'Writer', 'jobs': [{'job': 'Writer', 'episode_count': 10}]},
        ]}}
        self.assertEqual([item['name'] for item in _episode_directors(details)], ['Many', 'Few'])

    def test_series_without_director_crew_uses_episode_directors(self):
        payload = deepcopy(SERIES_PAYLOAD)
        payload['credits']['crew'] = []
        payload['aggregate_credits'] = {'crew': [
            {'id': 77, 'name': 'Episode Director', 'jobs': [{'job': 'Director', 'episode_count': 4}]},
        ]}
        with _offline_artwork():
            series, _ = upsert_tmdb_series(payload)
        self.assertEqual(list(series.directors.values_list('name', flat=True)), ['Episode Director'])
