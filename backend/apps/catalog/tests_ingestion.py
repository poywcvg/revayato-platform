from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from .ingestion import apply_media_manifest, sync_recent_tmdb_movies, upsert_tmdb_movie
from .models import CatalogSyncRun, Movie


MOVIE_DETAILS = {
    'id': 9001,
    'title': 'Automated Release',
    'original_title': 'Automated Release',
    'overview': 'A complete licensed catalog ingestion test movie.',
    'release_date': '2026-07-01',
    'runtime': 112,
    'original_language': 'en',
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
        self.assertEqual(stats['published'], 1)
        self.assertEqual(CatalogSyncRun.objects.get().status, CatalogSyncRun.Status.SUCCEEDED)

    def test_metadata_without_rights_or_media_remains_draft(self):
        movie, created, published = upsert_tmdb_movie(MOVIE_DETAILS, auto_publish=True)
        self.assertTrue(created)
        self.assertFalse(published)
        self.assertFalse(movie.is_published)
        self.assertIn('rights_not_verified', movie.auto_publish_blockers)

    def test_manifest_rejects_full_media_urls(self):
        movie = Movie(title='Unsafe', slug='unsafe')
        with self.assertRaises(ValidationError):
            apply_media_manifest(movie, {'hls_key': 'https://unauthorized.example/movie.m3u8'})
