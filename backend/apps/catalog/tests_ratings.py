from django.test import SimpleTestCase, TestCase, override_settings
from django.contrib.auth import get_user_model

from apps.catalog.models import Movie
from apps.catalog.ratings import (
    build_ratings_from_local,
    get_media_ratings,
    validate_rating,
)


class RatingValidationTests(SimpleTestCase):
    def test_accepts_valid_imdb(self):
        result = validate_rating({
            'source': 'imdb',
            'value': 8.2,
            'scale': 10,
            'voteCount': 100,
            'isVerified': True,
        })
        self.assertIsNotNone(result)
        self.assertEqual(result['displayValue'], '8.2')

    def test_rejects_out_of_range(self):
        self.assertIsNone(validate_rating({'source': 'imdb', 'value': 12, 'scale': 10}))
        self.assertIsNone(validate_rating({'source': 'tmdb', 'value': -1, 'scale': 10}))
        self.assertIsNone(validate_rating({'source': 'metacritic', 'value': 140, 'scale': 100}))

    def test_rejects_unknown_source(self):
        self.assertIsNone(validate_rating({'source': 'fake', 'value': 8, 'scale': 10}))


@override_settings(OMDB_API_KEY='')
class LocalRatingAggregationTests(TestCase):
    def test_tmdb_score_is_not_labeled_imdb_when_equal(self):
        movie = Movie.objects.create(
            title='Polluted',
            slug='polluted-rating',
            imdb_rating='7.8',
            rating_average='7.8',
            vote_count=500,
            tmdb_id=4242,
            source_metadata={'imdb_rating_source': 'tmdb'},
            is_published=True,
        )
        ratings = build_ratings_from_local(movie)
        sources = {item['source'] for item in ratings}
        self.assertIn('tmdb', sources)
        self.assertIn('imdb', sources)

    def test_distinct_imdb_score_is_kept(self):
        movie = Movie.objects.create(
            title='Real Imdb',
            slug='real-imdb-rating',
            imdb_id='tt0111161',
            imdb_rating='9.3',
            rating_average='8.7',
            vote_count=2000,
            tmdb_id=278,
            source_metadata={'imdb_rating_source': 'omdb'},
            is_published=True,
        )
        ratings = build_ratings_from_local(movie)
        by_source = {item['source']: item for item in ratings}
        self.assertEqual(by_source['imdb']['value'], 9.3)
        self.assertEqual(by_source['tmdb']['value'], 8.7)

    def test_get_media_ratings_caches_payload(self):
        movie = Movie.objects.create(
            title='Cached',
            slug='cached-rating',
            rating_average='7.1',
            vote_count=10,
            tmdb_id=99,
            is_published=True,
        )
        first = get_media_ratings(movie)
        second = get_media_ratings(movie)
        self.assertEqual(first['ratings'], second['ratings'])
        self.assertTrue(first['fetchedAt'])
