from django.db import IntegrityError, transaction
from django.core.management import call_command
from django.test import TestCase

from .models import Country, Director, Episode, Movie, Season, Series


def make_movie(**kwargs):
    defaults = {
        'title': 'Test Movie',
        'slug': 'test-movie',
        'is_published': False,
    }
    defaults.update(kwargs)
    return Movie.objects.create(**defaults)


class MovieVisibilityTests(TestCase):
    def test_draft_movie_excluded_from_public_list(self):
        make_movie(title='Draft Movie', slug='draft-movie', is_published=False)

        response = self.client.get('/api/movies/')

        self.assertEqual(response.status_code, 200)
        slugs = [item['slug'] for item in response.json()['results']]
        self.assertNotIn('draft-movie', slugs)

    def test_draft_movie_detail_not_found(self):
        make_movie(title='Draft Movie', slug='draft-movie', is_published=False)

        response = self.client.get('/api/movies/draft-movie/')

        self.assertEqual(response.status_code, 404)

    def test_published_movie_visible_in_list_and_detail(self):
        make_movie(title='Published Movie', slug='published-movie', is_published=True)

        list_response = self.client.get('/api/movies/')
        detail_response = self.client.get('/api/movies/published-movie/')

        self.assertEqual(list_response.status_code, 200)
        slugs = [item['slug'] for item in list_response.json()['results']]
        self.assertIn('published-movie', slugs)

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()['title'], 'Published Movie')

    def test_slug_lookup_returns_correct_movie(self):
        make_movie(title='Movie A', slug='movie-a', is_published=True)
        make_movie(title='Movie B', slug='movie-b', is_published=True)

        response = self.client.get('/api/movies/movie-b/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['title'], 'Movie B')

    def test_seo_fields_fall_back_when_not_set(self):
        movie = make_movie(
            title='Movie C', slug='movie-c', is_published=True,
            short_description='A short teaser.',
        )

        self.assertEqual(movie.seo_title, 'Movie C')
        self.assertEqual(movie.seo_description, 'A short teaser.')


class MovieExternalIdTests(TestCase):
    def test_duplicate_tmdb_id_rejected(self):
        make_movie(title='Movie A', slug='movie-a', tmdb_id=101)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_movie(title='Movie B', slug='movie-b', tmdb_id=101)

    def test_duplicate_imdb_id_rejected(self):
        make_movie(title='Movie A', slug='movie-a', imdb_id='tt0000001')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_movie(title='Movie B', slug='movie-b', imdb_id='tt0000001')

    def test_multiple_movies_without_external_ids_allowed(self):
        make_movie(title='Movie A', slug='movie-a')
        make_movie(title='Movie B', slug='movie-b')

        self.assertEqual(Movie.objects.count(), 2)


class CatalogApiContractTests(TestCase):
    def test_movie_list_filters_and_exposes_card_metadata(self):
        director = Director.objects.create(name='Hana Noor', slug='hana-noor')
        country = Country.objects.create(name='Iran', code='IR')
        movie = make_movie(
            title='Visible Movie', slug='visible-movie', is_published=True,
            release_year=2025, language='Persian', age_rating='15+',
            imdb_rating='8.7', is_featured=True, trailer_url='movies/animated/trailer.m3u8',
            content_format='animation', is_dubbed=True, has_subtitle=True,
            is_uncensored=True, content_warnings=['violence'],
        )
        movie.directors.add(director)
        movie.countries.add(country)
        make_movie(title='Other Movie', slug='other-movie', is_published=True, release_year=2020)

        response = self.client.get('/api/movies/', {
            'q': 'Hana',
            'year': '2025',
            'country': 'IR',
            'language': 'Persian',
            'age': '15+',
            'min_rating': '8',
            'availability': 'dubbed',
            'content_format': 'animation',
        })

        self.assertEqual(response.status_code, 200)
        results = response.json()['results']
        self.assertEqual([item['slug'] for item in results], ['visible-movie'])
        self.assertEqual(results[0]['directors'][0]['name'], 'Hana Noor')
        self.assertEqual(results[0]['countries'][0]['code'], 'IR')
        self.assertTrue(results[0]['is_featured'])
        self.assertTrue(results[0]['is_dubbed'])
        self.assertTrue(results[0]['has_subtitle'])
        self.assertTrue(results[0]['is_uncensored'])
        self.assertEqual(results[0]['content_format'], 'animation')
        self.assertEqual(results[0]['trailer_url'], '/media/movies/animated/trailer.m3u8')

        detail_response = self.client.get('/api/movies/visible-movie/')
        self.assertEqual(detail_response.json()['content_warnings'], ['violence'])

    def test_rating_sort_and_invalid_numeric_filters_are_safe(self):
        make_movie(title='Lower', slug='lower', is_published=True, imdb_rating='6.5')
        make_movie(title='Higher', slug='higher', is_published=True, imdb_rating='9.1')

        sorted_response = self.client.get('/api/movies/', {'sort': 'rating'})
        invalid_response = self.client.get('/api/movies/', {'year': 'not-a-year', 'min_rating': 'invalid'})
        trending_response = self.client.get('/api/trending/', {'limit': 'invalid'})

        self.assertEqual(sorted_response.status_code, 200)
        self.assertEqual(sorted_response.json()['results'][0]['slug'], 'higher')
        self.assertEqual(invalid_response.status_code, 200)
        self.assertEqual(trending_response.status_code, 200)

    def test_offset_past_last_page_returns_empty_results(self):
        make_movie(title='Only Movie', slug='only-movie', is_published=True)

        response = self.client.get('/api/movies/', {'offset': 500})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'], [])


class SeriesPublicationApiTests(TestCase):
    def test_detail_exposes_only_published_seasons_and_episodes(self):
        series = Series.objects.create(title='Test Series', slug='test-series', is_published=True)
        published_season = Season.objects.create(
            series=series, season_number=1, title='Published Season', is_published=True,
        )
        draft_season = Season.objects.create(
            series=series, season_number=2, title='Draft Season', is_published=False,
        )
        Episode.objects.create(
            season=published_season, episode_number=1, title='Published Episode', is_published=True,
        )
        Episode.objects.create(
            season=published_season, episode_number=2, title='Draft Episode', is_published=False,
        )
        Episode.objects.create(
            season=draft_season, episode_number=1, title='Hidden Season Episode', is_published=True,
        )

        response = self.client.get('/api/series/test-series/')

        self.assertEqual(response.status_code, 200)
        seasons = response.json()['seasons']
        self.assertEqual([season['season_number'] for season in seasons], [1])
        self.assertEqual([episode['episode_number'] for episode in seasons[0]['episodes']], [1])


class SeedCatalogTests(TestCase):
    def test_seed_creates_public_playable_metadata_and_is_repeatable(self):
        call_command('seed_catalog', verbosity=0)
        call_command('seed_catalog', verbosity=0)

        movie = Movie.objects.get(slug='silent-orbit')
        series = Series.objects.get(slug='red-signal')
        season = series.seasons.get(season_number=1)

        self.assertTrue(movie.has_subtitle)
        self.assertTrue(movie.is_dubbed)
        self.assertTrue(movie.video_url.endswith('.m3u8'))
        self.assertEqual(movie.countries.get().code, 'GB')
        self.assertTrue(season.is_published)
        self.assertEqual(season.episode_count, 3)
        self.assertTrue(season.episodes.filter(is_published=True).exists())
