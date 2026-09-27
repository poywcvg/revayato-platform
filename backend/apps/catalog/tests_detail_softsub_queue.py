from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.catalog.models import Episode, Movie, Season, Series


@override_settings(SUBTITLESTAR_ENABLED=True)
class DetailSoftsubQueueTests(TestCase):
    def test_movie_detail_queues_when_track_payload_is_not_usable(self):
        movie = Movie.objects.create(
            title='Queue Movie',
            original_title='Queue Movie',
            slug='queue-movie',
            imdb_id='tt0111161',
            is_published=True,
            download_links=[{'url': 'https://cdn.example/movie.mkv'}],
            subtitle_tracks=[{'label': 'broken track without a source'}],
        )

        with patch('apps.catalog.tasks.enqueue_movie_softsub') as enqueue:
            response = self.client.get('/api/movies/queue-movie/')

        self.assertEqual(response.status_code, 200)
        enqueue.assert_called_once_with(movie.pk, force=False)

    def test_movie_detail_does_not_queue_when_softsub_is_ready(self):
        movie = Movie.objects.create(
            title='Ready Movie',
            original_title='Ready Movie',
            slug='ready-movie',
            imdb_id='tt0068646',
            is_published=True,
            download_links=[{'url': 'https://cdn.example/movie.mkv'}],
            subtitle_tracks=[{
                'id': 'fa-ready',
                'language': 'fa',
                'label': 'فارسی',
                'src': 'https://cdn.example/movie.vtt',
            }],
        )

        with patch('apps.catalog.tasks.enqueue_movie_softsub') as enqueue:
            response = self.client.get('/api/movies/ready-movie/')

        self.assertEqual(response.status_code, 200)
        enqueue.assert_not_called()

    def test_series_detail_queues_when_an_episode_track_is_not_usable(self):
        series = Series.objects.create(
            title='Queue Series',
            original_title='Queue Series',
            slug='queue-series',
            imdb_id='tt0944947',
            start_year=2011,
            is_published=True,
            download_links=[{'url': 'https://cdn.example/series-s01e01.mkv'}],
        )
        season = Season.objects.create(series=series, season_number=1, is_published=True)
        Episode.objects.create(
            season=season,
            episode_number=1,
            title='Episode 1',
            is_published=True,
            video_url='https://cdn.example/series-s01e01.mkv',
            subtitle_tracks=[{'label': 'broken track without a source'}],
        )

        with patch('apps.catalog.tasks.enqueue_series_softsub') as enqueue:
            response = self.client.get('/api/series/queue-series/')

        self.assertEqual(response.status_code, 200)
        enqueue.assert_called_once_with(series.pk, force=False, episode_limit=40)

    def test_detail_cache_hit_still_queues_missing_movie_softsub(self):
        movie = Movie.objects.create(
            title='Cached Movie',
            original_title='Cached Movie',
            slug='cached-movie',
            imdb_id='tt0133093',
            is_published=True,
            download_links=[{'url': 'https://cdn.example/movie.mkv'}],
            subtitle_tracks=[],
        )

        with patch('apps.catalog.tasks.enqueue_movie_softsub') as enqueue:
            first = self.client.get('/api/movies/cached-movie/')
            second = self.client.get('/api/movies/cached-movie/')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(enqueue.call_count, 2)
        self.assertEqual(enqueue.call_args.args, (movie.pk,))
