from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from . import cache as catalog_cache
from .models import Movie


def _run_now(job):
    catalog_cache._run_refresh_sync(job)
    return True


@mock.patch.object(catalog_cache, 'catalog_stale_ttl', return_value=3600)
@mock.patch.object(catalog_cache, '_spawn_refresh', side_effect=_run_now)
class StaleWhileRevalidateTests(TestCase):
    def setUp(self):
        cache.clear()

    def slugs(self, response):
        return [item['slug'] for item in response.json()['results']]

    def test_version_bump_serves_last_answer_then_refreshes_in_background(self, spawn, _ttl):
        Movie.objects.create(title='First', slug='first', is_published=True)
        first = self.client.get('/api/movies/', {'limit': 5})
        self.assertEqual(first['X-Catalog-Cache'], 'MISS')

        # The save bumps the global version: the old fresh key is gone.
        Movie.objects.create(title='Second', slug='second', is_published=True)
        stale = self.client.get('/api/movies/', {'limit': 5})
        self.assertEqual(stale['X-Catalog-Cache'], 'STALE')
        self.assertEqual(self.slugs(stale), self.slugs(first))
        self.assertEqual(spawn.call_count, 1)

        fresh = self.client.get('/api/movies/', {'limit': 5})
        self.assertEqual(fresh['X-Catalog-Cache'], 'HIT')
        self.assertEqual(set(self.slugs(fresh)), {'first', 'second'})

    def test_one_refresh_per_url_while_it_runs(self, spawn, _ttl):
        spawn.side_effect = lambda job: True  # refresh never finishes
        Movie.objects.create(title='First', slug='first', is_published=True)
        self.client.get('/api/movies/', {'limit': 5})
        Movie.objects.create(title='Second', slug='second', is_published=True)

        for _ in range(3):
            self.assertEqual(self.client.get('/api/movies/', {'limit': 5})['X-Catalog-Cache'], 'STALE')
        self.assertEqual(spawn.call_count, 1)

    def test_unpublished_detail_is_not_served_stale_again(self, spawn, _ttl):
        movie = Movie.objects.create(title='Gone Soon', slug='gone-soon', is_published=True)
        self.assertEqual(self.client.get('/api/movies/gone-soon/').status_code, 200)

        movie.is_published = False
        movie.save(update_fields=['is_published', 'updated_at'])
        # At most one stale answer; the background rebuild 404s and drops it.
        self.client.get('/api/movies/gone-soon/')
        self.assertEqual(self.client.get('/api/movies/gone-soon/').status_code, 404)

    def test_disabled_under_tests_by_default(self, spawn, ttl):
        ttl.return_value = 0
        Movie.objects.create(title='First', slug='first', is_published=True)
        self.client.get('/api/movies/', {'limit': 5})
        Movie.objects.create(title='Second', slug='second', is_published=True)
        self.assertEqual(self.client.get('/api/movies/', {'limit': 5})['X-Catalog-Cache'], 'MISS')
        spawn.assert_not_called()
