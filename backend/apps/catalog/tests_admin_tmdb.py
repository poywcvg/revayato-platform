from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .ingestion import upsert_tmdb_movie
from .models import Genre, Movie, MovieSyncAudit, Series
from .tests_ingestion import MOVIE_DETAILS


SERIES_DETAILS = {
    'id': 7001,
    'name': 'Imported Series',
    'original_name': 'Imported Series',
    'overview': 'A series imported by entering only its TMDB ID.',
    'first_air_date': '2024-01-10',
    'last_air_date': '2025-02-20',
    'episode_run_time': [48],
    'original_language': 'en',
    'vote_average': 8.4,
    'vote_count': 530,
    'popularity': 31.2,
    'genres': [{'id': 10765, 'name': 'Sci-Fi & Fantasy'}],
    'production_countries': [{'iso_3166_1': 'GB', 'name': 'United Kingdom'}],
    'external_ids': {'imdb_id': 'tt7001001'},
    'content_ratings': {'results': [{'iso_3166_1': 'US', 'rating': 'TV-14'}]},
    'credits': {
        'cast': [{'id': 21, 'name': 'Series Actor', 'character': 'Hero', 'popularity': 5.1}],
        'crew': [{'id': 22, 'name': 'Series Director', 'job': 'Director', 'popularity': 2.8}],
    },
    'created_by': [],
    'status': 'Ended',
    'number_of_seasons': 1,
    'number_of_episodes': 8,
    'poster_path': '/series-poster.jpg',
    'backdrop_path': '/series-backdrop.jpg',
    'videos': {'results': [{'site': 'YouTube', 'type': 'Trailer', 'official': True, 'key': 'series-trailer'}]},
    'seasons': [{
        'id': 7101,
        'season_number': 1,
        'name': 'Season 1',
        'overview': 'The first season.',
        'air_date': '2024-01-10',
        'episode_count': 8,
        'poster_path': '/season-1.jpg',
    }],
}


class FakeSearchClient:
    uses_proxy = False

    def image_url(self, path, size='w500'):
        return f'https://image.tmdb.org/t/p/{size}{path}' if path else ''

    def search_movies(self, query, *, page=1, include_adult=False, language=None):
        return {
            'page': 1,
            'total_pages': 1,
            'total_results': 1,
            'results': [{
                'id': 9001,
                'title': 'Automated Release',
                'original_title': 'Automated Release',
                'overview': 'Overview',
                'release_date': '2026-07-01',
                'poster_path': '/poster.jpg',
                'backdrop_path': '/backdrop.jpg',
                'vote_average': 7.5,
                'popularity': 12,
                'original_language': 'en',
            }],
        }

    def movie_details(self, movie_id):
        return MOVIE_DETAILS

    def preview_movie(self, movie_id):
        return {
            'tmdb_id': 9001,
            'title': 'Automated Release',
            'original_title': 'Automated Release',
            'overview': 'Overview',
            'poster_url': 'https://image.tmdb.org/t/p/w500/poster.jpg',
            'cast': [],
            'crew': [],
        }

    def tv_details(self, series_id):
        return SERIES_DETAILS

    def preview_tv(self, series_id):
        return {
            'content_type': 'series',
            'tmdb_id': SERIES_DETAILS['id'],
            'title': SERIES_DETAILS['name'],
            'original_title': SERIES_DETAILS['original_name'],
            'overview': SERIES_DETAILS['overview'],
            'poster_url': 'https://image.tmdb.org/t/p/w500/series-poster.jpg',
            'cast': [],
            'crew': [],
            'season_count': 1,
            'episode_count': 8,
        }


@override_settings(
    TMDB_BASE_URL='https://api.themoviedb.org/3',
    TMDB_READ_ACCESS_TOKEN='test-token',
)
class AdminTMDBApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            email='staff@example.com',
            username='staff',
            password='test-pass-123',
            is_staff=True,
        )
        self.user = User.objects.create_user(
            email='user@example.com',
            username='user',
            password='test-pass-123',
            is_staff=False,
        )
        self.client = APIClient()

    def test_search_requires_staff(self):
        self.client.force_authenticate(self.user)
        response = self.client.get('/api/admin/tmdb/search/', {'query': 'test'})
        self.assertEqual(response.status_code, 403)

    @override_settings()
    def test_search_and_import_dry_run(self):
        from unittest.mock import patch

        self.client.force_authenticate(self.staff)
        with patch('apps.catalog.admin_api.configured_tmdb_client', return_value=FakeSearchClient()):
            search = self.client.get('/api/admin/tmdb/search/', {'query': 'Automated'})
            self.assertEqual(search.status_code, 200)
            self.assertEqual(search.data['results'][0]['tmdb_id'], 9001)

            preview = self.client.get('/api/admin/tmdb/movie/9001/preview/')
            self.assertEqual(preview.status_code, 200)

            dry = self.client.post('/api/admin/tmdb/movie/9001/import/', {'dry_run': True}, format='json')
            self.assertEqual(dry.status_code, 200)
            self.assertTrue(dry.data['dry_run'])
            self.assertEqual(Movie.objects.count(), 0)

            imported = self.client.post('/api/admin/tmdb/movie/9001/import/', {}, format='json')
            self.assertEqual(imported.status_code, 201)
            movie = Movie.objects.get(tmdb_id=9001)
            self.assertFalse(movie.is_published)
            self.assertEqual(str(movie.rating_average), '7.8')
            self.assertIsNone(movie.imdb_rating)

            sync = self.client.post(f'/api/admin/movies/{movie.id}/sync-tmdb/', {'dry_run': True}, format='json')
            self.assertEqual(sync.status_code, 200)
            self.assertTrue(sync.data['dry_run'])

    def test_manual_update_tracks_only_fields_that_really_changed(self):
        self.client.force_authenticate(self.staff)
        movie, _created, _published, _skipped = upsert_tmdb_movie(MOVIE_DETAILS)

        response = self.client.patch(
            f'/api/admin/movies/{movie.id}/',
            {'title': movie.title, 'short_description': 'Editorial summary'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        movie.refresh_from_db()
        self.assertEqual(movie.manual_override_fields, ['short_description'])
        audit = MovieSyncAudit.objects.filter(movie=movie, action=MovieSyncAudit.Action.MANUAL_UPDATE).first()
        self.assertEqual(audit.changed_fields, ['short_description'])

    def test_series_preview_and_import_by_tmdb_id(self):
        from unittest.mock import patch

        self.client.force_authenticate(self.staff)
        with patch('apps.catalog.admin_api.configured_tmdb_client', return_value=FakeSearchClient()):
            preview = self.client.get('/api/admin/tmdb/series/7001/preview/')
            self.assertEqual(preview.status_code, 200)
            self.assertEqual(preview.data['content_type'], 'series')

            dry = self.client.post('/api/admin/tmdb/series/7001/import/', {'dry_run': True}, format='json')
            self.assertEqual(dry.status_code, 200)
            self.assertEqual(Series.objects.count(), 0)

            imported = self.client.post('/api/admin/tmdb/series/7001/import/', {}, format='json')
            self.assertEqual(imported.status_code, 201)

        series = Series.objects.get(tmdb_id=7001)
        self.assertFalse(series.is_published)
        self.assertEqual(series.status, Series.Status.ENDED)
        self.assertEqual(str(series.rating_average), '8.4')
        self.assertTrue(series.genres.filter(slug__in=['sci-fi', 'fantasy', 'sci-fi-fantasy']).exists())
        self.assertEqual(series.series_actors.get().actor.name, 'Series Actor')
        # TMDB import must not materialize empty season shells; playable seasons
        # appear only after provider download links create episode rows.
        self.assertFalse(series.seasons.exists())
        self.assertEqual(series.source_metadata.get('number_of_seasons'), 1)
        self.assertEqual(imported.data['series']['season_count'], 1)

    def test_publishing_without_rights_or_media_is_allowed(self):
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            '/api/admin/movies/',
            {'title': 'Open publication', 'publication_status': 'published'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        movie = Movie.objects.get(title='Open publication')
        self.assertTrue(movie.is_published)
        self.assertEqual(movie.publication_status, Movie.PublicationStatus.PUBLISHED)

    def test_empty_genre_list_can_be_saved_over_multipart(self):
        self.client.force_authenticate(self.staff)
        genre = Genre.objects.create(title='Drama Admin', slug='drama-admin')
        movie = Movie.objects.create(title='Genre test', slug='genre-test')
        movie.genres.add(genre)

        response = self.client.patch(
            f'/api/admin/movies/{movie.id}/',
            {'clear_genres': True},
            format='multipart',
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(movie.genres.exists())
