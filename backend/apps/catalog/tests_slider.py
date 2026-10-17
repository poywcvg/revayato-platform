"""Admin-curated home slider: one choice feeds the website and the app.

Membership is the existing ``is_featured`` flag; ``featured_order`` decides the
position (lower first) and ``slider_platform`` (all/web/app) decides which
client shows it. These tests pin the contract: ordering, platform filtering,
the public slider endpoint both clients read, and the admin list/reorder API.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Movie, Series
from .slider import slider_items, slider_platforms


def _movie(title, **extra):
    extra.setdefault('slug', title.lower().replace(' ', '-'))
    extra.setdefault('is_published', True)
    return Movie.objects.create(title=title, **extra)


def _series(title, **extra):
    extra.setdefault('slug', title.lower().replace(' ', '-'))
    extra.setdefault('is_published', True)
    return Series.objects.create(title=title, **extra)


class SliderPlatformTests(TestCase):
    def test_all_is_visible_everywhere(self):
        self.assertEqual(slider_platforms('web'), ['all', 'web'])
        self.assertEqual(slider_platforms('app'), ['all', 'app'])
        self.assertEqual(slider_platforms(None), ['all', 'web', 'app'])
        self.assertEqual(slider_platforms('bogus'), ['all', 'web', 'app'])


class SliderOrderingTests(TestCase):
    def test_order_then_recency_across_types(self):
        old = _movie('Old Film', featured_order=1, is_featured=True)
        new = _series('New Show', featured_order=1, is_featured=True)
        last = _movie('Last Film', featured_order=2, is_featured=True)
        hidden = _movie('Draft Film', featured_order=0, is_featured=True, is_published=False)
        items = slider_items()
        got = [(entry['content_type'], entry[entry['content_type']].pk) for entry in items]
        # Same order step: the newer row first; order 2 after both order-1 rows.
        self.assertEqual(got[0], ('series', new.pk))
        self.assertEqual(got[1], ('movie', old.pk))
        self.assertEqual(got[2], ('movie', last.pk))
        self.assertNotIn(('movie', hidden.pk), got)

    def test_platform_filtering(self):
        web_only = _movie('Web Film', is_featured=True, slider_platform='web')
        app_only = _series('App Show', is_featured=True, slider_platform='app')
        both = _movie('Both Film', is_featured=True, slider_platform='all')
        web = {(e['content_type'], e[e['content_type']].pk) for e in slider_items(platform='web')}
        app = {(e['content_type'], e[e['content_type']].pk) for e in slider_items(platform='app')}
        self.assertIn(('movie', web_only.pk), web)
        self.assertIn(('movie', both.pk), web)
        self.assertNotIn(('series', app_only.pk), web)
        self.assertIn(('series', app_only.pk), app)
        self.assertIn(('movie', both.pk), app)
        self.assertNotIn(('movie', web_only.pk), app)


class SliderPublicApiTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_home_slider_endpoint_serves_both_types_in_order(self):
        _movie('Second Film', featured_order=2, is_featured=True)
        show = _series('First Show', featured_order=1, is_featured=True)
        response = self.client.get('/api/home/slider/', {'platform': 'app', 'limit': 10})
        self.assertEqual(response.status_code, 200)
        results = response.json()['results']
        self.assertEqual(results[0]['content_type'], 'series')
        self.assertEqual(results[0]['id'], show.pk)
        self.assertTrue(all(item['content_type'] in {'movie', 'series'} for item in results))

    def test_home_rails_hero_follows_admin_order_and_platform(self):
        _movie('Web Film', featured_order=1, is_featured=True, slider_platform='web')
        _movie('App Film', featured_order=1, is_featured=True, slider_platform='app')
        web = self.client.get('/api/home/rails/', {'platform': 'web', 'limit': 7})
        app = self.client.get('/api/home/rails/', {'platform': 'app', 'limit': 7})
        self.assertEqual(web.status_code, 200)
        self.assertEqual(app.status_code, 200)
        web_titles = [item['title'] for item in web.json()['hero']]
        app_titles = [item['title'] for item in app.json()['hero']]
        self.assertIn('Web Film', web_titles)
        self.assertNotIn('App Film', web_titles)
        self.assertIn('App Film', app_titles)
        self.assertNotIn('Web Film', app_titles)


class SliderAdminApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = get_user_model().objects.create_user(
            username='slider-staffer', email='slider@example.test', password='x-Pass-12345', is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_patch_accepts_order_and_platform(self):
        movie = _movie('Film')
        response = self.client.patch(
            f'/api/admin/movies/{movie.pk}/',
            {'is_featured': True, 'featured_order': 3, 'slider_platform': 'app'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        movie.refresh_from_db()
        self.assertTrue(movie.is_featured)
        self.assertEqual(movie.featured_order, 3)
        self.assertEqual(movie.slider_platform, 'app')

    def test_admin_list_filters_and_ordering(self):
        _movie('Featured Film', is_featured=True, featured_order=5)
        _movie('Plain Film')
        response = self.client.get('/api/admin/movies/', {'featured': '1', 'ordering': 'featured_order'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['title'] for item in response.json()['results']], ['Featured Film'])

    def test_slider_list_and_reorder_roundtrip(self):
        first = _movie('First Film', is_featured=True, featured_order=1)
        second = _series('Second Show', is_featured=True, featured_order=2)
        listed = self.client.get('/api/admin/slider/')
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            [(item['content_type'], item['id']) for item in listed.json()['results']],
            [('movie', first.pk), ('series', second.pk)],
        )
        reorder = self.client.post(
            '/api/admin/slider/reorder/',
            {'items': [
                {'content_type': 'series', 'id': second.pk, 'featured_order': 1, 'slider_platform': 'app'},
                {'content_type': 'movie', 'id': first.pk, 'featured_order': 2, 'slider_platform': 'web'},
            ]},
            format='json',
        )
        self.assertEqual(reorder.status_code, 200, reorder.data)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.featured_order, first.slider_platform), (2, 'web'))
        self.assertEqual((second.featured_order, second.slider_platform), (1, 'app'))
        # The public slider now leads with the series.
        public = self.client.get('/api/home/slider/')
        self.assertEqual(public.json()['results'][0]['content_type'], 'series')

    def test_reorder_rejects_bad_platform(self):
        movie = _movie('Film', is_featured=True)
        response = self.client.post(
            '/api/admin/slider/reorder/',
            {'items': [{'content_type': 'movie', 'id': movie.pk, 'slider_platform': 'tv'}]},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_reorder_warns_about_unpublished(self):
        hidden = _movie('Hidden Film', is_featured=True, is_published=False)
        response = self.client.post(
            '/api/admin/slider/reorder/',
            {'items': [{'content_type': 'movie', 'id': hidden.pk, 'featured_order': 1}]},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            response.json()['unpublished'],
            [{'content_type': 'movie', 'id': hidden.pk, 'title': 'Hidden Film'}],
        )
        # …and it stays out of the public slider.
        public = self.client.get('/api/home/slider/')
        self.assertNotIn(hidden.pk, [item['id'] for item in public.json()['results']])


class SliderFreshnessTests(TestCase):
    """The slider never serves a stale copy after an editorial save."""

    def setUp(self):
        cache.clear()

    def test_no_stale_hero_after_version_bump(self):
        import hashlib

        from .cache import bump_catalog_cache_version

        _movie('Fresh Film', featured_order=1, is_featured=True)
        query = 'platform=app&limit=10'
        digest = hashlib.sha256(f'/api/home/slider/?{query}'.encode()).hexdigest()[:24]
        stale_key = f'catalog:resp:last:home-slider:app:10:{digest}'
        cache.set(stale_key, {'platform': 'app', 'results': [{'id': -1}]}, timeout=3600)
        bump_catalog_cache_version(force=True)
        response = self.client.get('/api/home/slider/', {'platform': 'app', 'limit': 10})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Catalog-Cache'], 'MISS')
        self.assertNotEqual([item['id'] for item in response.json()['results']], [-1])
