"""Sitemap feed + SEO flags that the web sitemap / detail pages are built on."""

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Actor, Country, Genre, Movie, MovieActor, Series, SeriesActor
from .sitemap_api import MIN_LANDING_TITLES


class CatalogSitemapTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        # Migrations seed the common genres/countries, so reuse them when present.
        self.action, _ = Genre.objects.get_or_create(slug='action', defaults={'title': 'test-action'})
        self.drama, _ = Genre.objects.get_or_create(slug='drama', defaults={'title': 'test-drama'})
        self.us, _ = Country.objects.get_or_create(code='us', defaults={'name': 'test-us'})
        self.kr, _ = Country.objects.get_or_create(code='kr', defaults={'name': 'test-kr'})
        for i in range(MIN_LANDING_TITLES):
            movie = Movie.objects.create(title=f'فیلم {i}', slug=f'movie-{i}', release_year=2020, is_published=True)
            movie.genres.add(self.action)
            movie.countries.add(self.us)
        # Below the threshold: drama / kr / 1999 must not become landing pages.
        thin = Movie.objects.create(title='کم', slug='thin-1999', release_year=1999, is_published=True)
        thin.genres.add(self.drama)
        thin.countries.add(self.kr)
        self.draft = Movie.objects.create(title='پیش‌نویس', slug='draft-movie', release_year=2020, is_published=False)
        self.draft.genres.add(self.action)
        self.series = Series.objects.create(title='سریال', slug='show-2019', start_year=2019, is_published=True)
        Series.objects.create(title='پیش‌نویس سریال', slug='draft-show', is_published=False)

    def test_summary_counts_only_published_and_lists_only_dense_facets(self):
        response = self.client.get('/api/catalog/sitemap/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['counts']['movies'], MIN_LANDING_TITLES + 1)
        self.assertEqual(data['counts']['series'], 1)
        self.assertEqual(data['page_size'], 5000)
        self.assertEqual(data['genres'], [{'slug': 'action', 'movies': MIN_LANDING_TITLES, 'series': 0}])
        self.assertEqual(data['countries'], [{'code': 'US', 'movies': MIN_LANDING_TITLES, 'series': 0}])
        self.assertEqual(data['years'], {'movies': [2020], 'series': []})

    def test_part_lists_published_rows_only(self):
        data = self.client.get('/api/catalog/sitemap/', {'kind': 'movies', 'page': 1}).json()
        slugs = {row['slug'] for row in data['results']}
        self.assertIn('movie-0', slugs)
        self.assertIn('thin-1999', slugs)
        self.assertNotIn('draft-movie', slugs)
        self.assertTrue(all(row['lastmod'] for row in data['results']))

        series = self.client.get('/api/catalog/sitemap/', {'kind': 'series'}).json()
        self.assertEqual([row['slug'] for row in series['results']], ['show-2019'])

    def test_page_past_the_end_is_empty(self):
        data = self.client.get('/api/catalog/sitemap/', {'kind': 'movies', 'page': 2}).json()
        self.assertEqual(data['results'], [])

    def test_actors_only_when_they_appear_in_a_published_title(self):
        in_movie = Actor.objects.create(name='الف', slug='actor-a')
        in_series = Actor.objects.create(name='ب', slug='actor-b')
        only_draft = Actor.objects.create(name='ج', slug='actor-c')
        Actor.objects.create(name='د', slug='actor-d')
        MovieActor.objects.create(movie=Movie.objects.get(slug='movie-0'), actor=in_movie)
        SeriesActor.objects.create(series=self.series, actor=in_series)
        MovieActor.objects.create(movie=self.draft, actor=only_draft)

        data = self.client.get('/api/catalog/sitemap/', {'kind': 'actors'}).json()
        self.assertEqual(sorted(row['slug'] for row in data['results']), ['actor-a', 'actor-b'])
        cache.clear()
        self.assertEqual(self.client.get('/api/catalog/sitemap/').json()['counts']['actors'], 2)

    def test_unknown_kind_is_rejected(self):
        self.assertEqual(self.client.get('/api/catalog/sitemap/', {'kind': 'users'}).status_code, 400)

    def test_bad_page_falls_back_to_first(self):
        data = self.client.get('/api/catalog/sitemap/', {'kind': 'movies', 'page': 'x'}).json()
        self.assertEqual(data['page'], 1)


class DetailSeoCustomFlagTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_generated_meta_is_not_flagged_custom(self):
        Movie.objects.create(title='تلقین', slug='inception-2010', is_published=True, meta_title='x')
        data = self.client.get('/api/movies/inception-2010/').json()
        self.assertEqual(data['seo_custom'], {'title': False, 'description': False})

    def test_hand_written_meta_is_flagged_custom(self):
        Movie.objects.create(
            title='تلقین', slug='inception-2010', is_published=True,
            meta_title='عنوان دستی', manual_override_fields=['meta_title'],
        )
        data = self.client.get('/api/movies/inception-2010/').json()
        self.assertEqual(data['seo_custom'], {'title': True, 'description': False})
