from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from .ingestion import apply_media_manifest, sync_recent_tmdb_movies, upsert_tmdb_movie
from .models import CatalogSyncRun, Movie


MOVIE_DETAILS = {
    'id': 9001,
    'title': 'Automated Release',
    'original_title': 'Automated Release',
    'overview': 'A complete licensed catalog ingestion test movie.',
    'translations': {
        'translations': [
            {
                'iso_639_1': 'fa',
                'data': {
                    'title': 'انتشار خودکار',
                    'overview': 'فیلمی کامل برای آزمون فرآیند درون‌ریزی کاتالوگ.',
                    'tagline': '',
                },
            },
        ],
    },
    'release_date': '2026-07-01',
    'runtime': 112,
    'original_language': 'en',
    'vote_average': 7.8,
    'vote_count': 1240,
    'popularity': 23.5,
    'genres': [{'id': 18, 'name': 'Drama'}],
    'production_countries': [{'iso_3166_1': 'US', 'name': 'United States'}],
    'external_ids': {'imdb_id': 'tt99009001'},
    'credits': {
        'cast': [{'id': 11, 'name': 'Test Actor', 'character': 'Lead', 'popularity': 4.2}],
        'crew': [{'id': 12, 'name': 'Test Director', 'job': 'Director', 'popularity': 3.1}],
    },
    'status': 'Released',
    'poster_path': '/poster.jpg',
    'backdrop_path': '/backdrop.jpg',
}


class FakeTMDBClient:
    def discover_movies(self, **_kwargs):
        return iter([{'id': MOVIE_DETAILS['id']}])

    def movie_details(self, _movie_id):
        return MOVIE_DETAILS


@override_settings(CATALOG_AUTO_PUBLISH=True)
class CatalogIngestionTests(TestCase):
    def test_sync_imports_details_and_publishes_only_licensed_ready_media(self):
        stats = sync_recent_tmdb_movies(
            client=FakeTMDBClient(),
            manifest={
                '9001': {
                    'hls_key': 'movies/9001/hls/master.m3u8',
                    'poster_key': 'movies/9001/images/poster.jpg',
                    'backdrop_key': 'movies/9001/images/backdrop.jpg',
                    'subtitles': [{
                        'language': 'fa',
                        'label': 'فارسی',
                        'key': 'movies/9001/subtitles/fa.vtt',
                        'default': True,
                    }],
                    'rights_verified': True,
                    'auto_publish': True,
                },
            },
            max_pages=1,
            lookback_days=1,
            lookahead_days=1,
        )

        movie = Movie.objects.get(tmdb_id=9001)
        self.assertTrue(movie.is_published)
        self.assertEqual(movie.video_url, 'movies/9001/hls/master.m3u8')
        self.assertEqual(movie.subtitle_tracks[0]['key'], 'movies/9001/subtitles/fa.vtt')
        self.assertEqual(movie.genres.get().slug, 'drama')
        self.assertEqual(movie.directors.get().name, 'Test Director')
        self.assertEqual(str(movie.rating_average), '7.8')
        self.assertEqual(str(movie.imdb_rating), '7.8')
        self.assertEqual(movie.original_language, 'en')
        self.assertEqual(movie.poster_path, '/poster.jpg')
        self.assertEqual(movie.publication_status, Movie.PublicationStatus.PUBLISHED)
        self.assertEqual(stats['published'], 1)
        self.assertEqual(CatalogSyncRun.objects.get().status, CatalogSyncRun.Status.SUCCEEDED)

    def test_complete_metadata_stays_draft_without_playback_links(self):
        movie, created, published, _skipped = upsert_tmdb_movie(MOVIE_DETAILS, auto_publish=True)
        self.assertTrue(created)
        self.assertFalse(published)
        self.assertFalse(movie.is_published)
        self.assertTrue(movie.auto_publish)
        self.assertIn('missing_playback_links', movie.auto_publish_blockers)
        self.assertEqual(movie.publication_status, Movie.PublicationStatus.DRAFT)

    def test_metadata_without_auto_publish_flag_remains_draft(self):
        movie, created, published, _skipped = upsert_tmdb_movie(MOVIE_DETAILS, auto_publish=False)
        self.assertTrue(created)
        self.assertFalse(published)
        self.assertFalse(movie.is_published)
        self.assertFalse(movie.auto_publish)
        self.assertEqual(movie.publication_status, Movie.PublicationStatus.DRAFT)

    def test_manifest_accepts_absolute_cdn_urls_but_rejects_malformed_values(self):
        movie = Movie(title='Unsafe', slug='unsafe')
        apply_media_manifest(movie, {'hls_key': 'https://cdn.example/movie.m3u8'})
        self.assertEqual(movie.video_url, 'https://cdn.example/movie.m3u8')
        with self.assertRaises(ValidationError):
            apply_media_manifest(movie, {'hls_key': 'https:///broken.m3u8'})

    def test_explicitly_cleared_manual_field_is_not_refilled(self):
        movie, _created, _published, _skipped = upsert_tmdb_movie(MOVIE_DETAILS)
        movie.short_description = ''
        movie.manual_override_fields = ['short_description']
        movie.save(update_fields=['short_description', 'manual_override_fields', 'updated_at'])

        synced, _created, _published, skipped = upsert_tmdb_movie(MOVIE_DETAILS)

        self.assertEqual(synced.short_description, '')
        self.assertIn('short_description', skipped)

    def test_actors_sync_even_when_existing_directors_are_protected(self):
        from .models import Director

        movie, _created, _published, _skipped = upsert_tmdb_movie(MOVIE_DETAILS)
        movie.movie_actors.all().delete()
        movie.metadata_source = 'manual'
        movie.manual_override_fields = []
        movie.save(update_fields=['metadata_source', 'manual_override_fields', 'updated_at'])
        self.assertTrue(movie.directors.exists())
        self.assertFalse(movie.movie_actors.exists())

        synced, _created, _published, skipped = upsert_tmdb_movie(MOVIE_DETAILS)

        self.assertTrue(synced.movie_actors.exists())
        self.assertEqual(synced.movie_actors.get().actor.name, 'Test Actor')
        self.assertIn('directors', skipped)
        self.assertNotIn('actors', skipped)
        self.assertEqual(synced.directors.get().name, 'Test Director')
        self.assertTrue(Director.objects.filter(name='Test Director').exists())

    @override_settings(TMDB_IMAGE_BASE_URL='https://image.tmdb.org/t/p')
    def test_upsert_downloads_poster_and_backdrop_files(self):
        from unittest import mock

        class FakeResponse:
            def __init__(self, payload, content_type='image/jpeg'):
                self._payload = payload
                self.headers = {'Content-Type': content_type}

            def read(self):
                return self._payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        with mock.patch('apps.catalog.ingestion.urllib.request.urlopen') as urlopen:
            urlopen.side_effect = lambda *_args, **_kwargs: FakeResponse(b'image-bytes')
            movie, created, _published, _skipped = upsert_tmdb_movie(MOVIE_DETAILS)

        movie.refresh_from_db()
        self.assertTrue(created)
        self.assertTrue(movie.poster.name)
        self.assertTrue(movie.backdrop.name)
        self.assertTrue(movie.poster_external_url.endswith('/poster.jpg'))
        self.assertTrue(movie.backdrop_external_url.endswith('/backdrop.jpg'))
        self.assertGreaterEqual(urlopen.call_count, 2)
