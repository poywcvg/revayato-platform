"""IndexNow: published title saves queue their URL once; the flush sends and drains."""

from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from . import indexnow
from .models import Movie, Series
from .sitemap_api import _image


def _response(status):
    return mock.Mock(status_code=status, text='')


@override_settings(INDEXNOW_ENABLED=True, INDEXNOW_KEY='abc123abc123', SITE_BASE_URL='https://example.test')
class IndexNowTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_published_save_queues_once_and_drafts_never(self):
        movie = Movie.objects.create(title='فیلم', slug='film-2020', is_published=True)
        Movie.objects.create(title='پیش‌نویس', slug='draft-2020', is_published=False)
        series = Series.objects.create(title='سریال', slug='show-2021', is_published=True)
        movie.save()  # crawler churn re-saves the row: no second entry
        self.assertEqual(cache.get(indexnow.PENDING_KEY), ['/movies/film-2020', '/series/show-2021'])

    def test_publishing_a_draft_queues_it(self):
        movie = Movie.objects.create(title='فیلم', slug='late-2020', is_published=False)
        self.assertFalse(cache.get(indexnow.PENDING_KEY))
        movie.is_published = True
        movie.save()
        self.assertEqual(cache.get(indexnow.PENDING_KEY), ['/movies/late-2020'])

    @override_settings(INDEXNOW_ENABLED=False)
    def test_disabled_queues_nothing(self):
        Movie.objects.create(title='فیلم', slug='off-2020', is_published=True)
        self.assertFalse(cache.get(indexnow.PENDING_KEY))
        self.assertEqual(indexnow.flush_pending(), {'status': 'disabled'})

    def test_flush_posts_absolute_urls_with_key_and_drains(self):
        Movie.objects.create(title='فیلم', slug='film-2020', is_published=True)
        with mock.patch.object(indexnow.requests, 'post', return_value=_response(202)) as post:
            result = indexnow.flush_pending()
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['host'], 'example.test')
        self.assertEqual(payload['key'], 'abc123abc123')
        self.assertEqual(payload['keyLocation'], 'https://example.test/indexnow-key.txt')
        self.assertEqual(payload['urlList'], ['https://example.test/movies/film-2020'])
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(cache.get(indexnow.PENDING_KEY), [])

    def test_rejected_batch_stays_queued(self):
        Movie.objects.create(title='فیلم', slug='film-2020', is_published=True)
        with mock.patch.object(indexnow.requests, 'post', return_value=_response(429)):
            result = indexnow.flush_pending()
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(cache.get(indexnow.PENDING_KEY), ['/movies/film-2020'])

    def test_network_error_keeps_queue(self):
        Movie.objects.create(title='فیلم', slug='film-2020', is_published=True)
        with mock.patch.object(indexnow.requests, 'post', side_effect=indexnow.requests.ConnectionError):
            self.assertEqual(indexnow.flush_pending()['status'], 'error')
        self.assertEqual(cache.get(indexnow.PENDING_KEY), ['/movies/film-2020'])

    def test_key_file_endpoint(self):
        response = APIClient().get('/api/catalog/indexnow-key/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), 'abc123abc123')
        self.assertTrue(response['Content-Type'].startswith('text/plain'))


@override_settings(SITE_BASE_URL='https://example.test', MEDIA_CDN_BASE_URL='')
class SitemapImageTests(TestCase):
    def test_local_poster_becomes_absolute_on_site_host(self):
        movie = Movie(title='فیلم', slug='img-2020')
        movie.poster.name = 'posters/img.jpg'
        with mock.patch('apps.catalog.sitemap_api.media_url', return_value='/media/posters/img.jpg'):
            self.assertEqual(_image(movie), 'https://example.test/media/posters/img.jpg')

    def test_external_poster_used_when_no_file(self):
        movie = Movie(title='فیلم', slug='ext-2020', poster_external_url='https://img.example/p.jpg')
        self.assertEqual(_image(movie), 'https://img.example/p.jpg')
