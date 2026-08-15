from django.test import SimpleTestCase, override_settings

from apps.catalog.imdb import enrich_imdb_rating
from apps.catalog.localization import (
    contains_cjk,
    contains_disallowed_catalog_script,
    contains_persian,
    ensure_persian_metadata,
    prefer_original_artwork,
    translate_to_persian,
)


class LocalizationTests(SimpleTestCase):
    def test_contains_persian(self):
        self.assertTrue(contains_persian('مدار خاموش'))
        self.assertFalse(contains_persian('Silent Orbit'))

    def test_contains_cjk(self):
        self.assertTrue(contains_cjk('天空の城ラピュタ'))
        self.assertTrue(contains_cjk('신과함께'))
        self.assertTrue(contains_cjk('重慶森林'))
        self.assertFalse(contains_cjk('Castle in the Sky'))

    def test_contains_disallowed_catalog_script(self):
        self.assertTrue(contains_disallowed_catalog_script('天空の城ラピュタ'))
        self.assertTrue(contains_disallowed_catalog_script('Война и мир'))
        self.assertTrue(contains_disallowed_catalog_script('മാർക്കോ'))
        self.assertTrue(contains_disallowed_catalog_script('قلعه در آسمان'))
        self.assertFalse(contains_disallowed_catalog_script('Castle in the Sky'))

    def test_normalize_person_names_drops_cjk(self):
        from apps.catalog.localization import normalize_person_names
        display, original = normalize_person_names('宮崎駿', '宮崎駿', english_name='Hayao Miyazaki')
        self.assertEqual(original, 'Hayao Miyazaki')
        self.assertNotIn('宮', display)
        self.assertNotIn('宮', original)

    def test_keeps_persian_title_and_english_original(self):
        details = {
            'title': 'Silent Orbit',
            'overview': 'An English overview about space.',
            'translations': {
                'translations': [{
                    'iso_639_1': 'fa',
                    'iso_3166_1': 'IR',
                    'data': {
                        'title': 'مدار خاموش',
                        'overview': 'خلاصه فارسی رسمی تی‌ام‌دی‌بی.',
                    },
                }],
            },
        }
        ensure_persian_metadata(details, content_type='movie')
        self.assertEqual(details['title'], 'مدار خاموش')
        self.assertEqual(details['original_title'], 'Silent Orbit')
        self.assertEqual(details['_title_source'], 'tmdb_translation')
        self.assertEqual(details['_persian_overview_source'], 'tmdb_translation')

    def test_cjk_original_title_becomes_english_with_persian_title(self):
        details = {
            'title': '天気の子',
            'original_title': '天気の子',
            'overview': 'Weather story',
            'translations': {
                'translations': [{
                    'iso_639_1': 'fa',
                    'iso_3166_1': 'IR',
                    'data': {'title': 'آب و هوا با تو', 'overview': 'داستان آب و هوا.'},
                }],
            },
            'images': {'posters': [], 'backdrops': []},
        }
        ensure_persian_metadata(
            details,
            content_type='movie',
            english_details={'title': 'Weathering with You', 'original_title': '天気の子'},
        )
        self.assertEqual(details['title'], 'آب و هوا با تو')
        self.assertEqual(details['original_title'], 'Weathering with You')
        self.assertEqual(details['_native_original_title'], '天気の子')
        self.assertEqual(details['overview'], 'داستان آب و هوا.')

    def test_persian_title_kept_english_original_from_en_details(self):
        details = {
            'title': 'جدایی نادر از سیمین',
            'original_title': 'جدایی نادر از سیمین',
            'overview': 'A story.',
            'translations': {
                'translations': [{
                    'iso_639_1': 'en',
                    'iso_3166_1': 'US',
                    'data': {'title': 'A Separation', 'overview': 'A story.'},
                }],
            },
            'images': {'posters': [], 'backdrops': []},
        }
        ensure_persian_metadata(
            details,
            content_type='movie',
            english_details={'title': 'A Separation', 'original_title': 'جدایی نادر از سیمین'},
        )
        self.assertEqual(details['title'], 'جدایی نادر از سیمین')
        self.assertEqual(details['original_title'], 'A Separation')
        self.assertTrue(contains_persian(details['_native_original_title']))

    def test_prefer_original_poster_over_localized(self):
        details = {
            'poster_path': '/fa-local.jpg',
            'images': {
                'posters': [
                    {'file_path': '/fa-local.jpg', 'iso_639_1': 'fa', 'vote_average': 9, 'vote_count': 10},
                    {'file_path': '/original.jpg', 'iso_639_1': None, 'vote_average': 8, 'vote_count': 20},
                    {'file_path': '/en.jpg', 'iso_639_1': 'en', 'vote_average': 7, 'vote_count': 5},
                ],
            },
        }
        prefer_original_artwork(details)
        self.assertEqual(details['poster_path'], '/original.jpg')

    @override_settings(TMDB_TIMEOUT_SECONDS=8)
    def test_machine_translates_title_and_overview(self):
        details = {
            'title': 'Hello',
            'overview': 'A short English story.',
            'translations': {'translations': []},
        }

        def fake_translate(text):
            return {
                'Hello': 'سلام',
                'A short English story.': 'یک داستان کوتاه انگلیسی.',
            }.get(text, '')

        from apps.catalog import localization
        original = localization.translate_to_persian
        localization.translate_to_persian = fake_translate
        try:
            ensure_persian_metadata(details, content_type='movie')
        finally:
            localization.translate_to_persian = original

        self.assertEqual(details['title'], 'سلام')
        self.assertEqual(details['original_title'], 'Hello')
        self.assertEqual(details['overview'], 'یک داستان کوتاه انگلیسی.')
        self.assertEqual(details['_title_source'], 'machine_translation')
        self.assertEqual(details['_persian_overview_source'], 'machine_translation')

    def test_normalize_title_pair_swaps_misordered_rows(self):
        from apps.catalog.localization import normalize_title_pair
        persian, english = normalize_title_pair('A Separation', 'جدایی نادر از سیمین', translate=False)
        self.assertEqual(persian, 'جدایی نادر از سیمین')
        self.assertEqual(english, 'A Separation')


class TMDBRatingEnrichmentTests(SimpleTestCase):
    def test_uses_tmdb_vote_average(self):
        details = {'vote_average': 7.8, 'vote_count': 1200}
        enrich_imdb_rating(details, enabled=True)
        self.assertEqual(details['imdb_rating'], 7.8)
        self.assertEqual(details['imdb_rating_source'], 'tmdb')
        self.assertEqual(details['imdb_votes'], 1200)

    def test_disabled_leaves_rating_empty(self):
        details = {'vote_average': 8.0}
        enrich_imdb_rating(details, enabled=False)
        self.assertNotIn('imdb_rating', details)
