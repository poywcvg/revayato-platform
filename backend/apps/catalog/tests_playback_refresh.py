from unittest.mock import patch

from django.test import TestCase

from apps.catalog.models import Movie
from apps.catalog.playback_refresh import collect_broken, refresh_broken_playback
from apps.catalog.provider_import.exceptions import ProviderImportError


class PlaybackRefreshTests(TestCase):
    def make_movie(self, **overrides):
        values = {
            'title': 'فیلم آزمایشی',
            'original_title': 'Test Movie',
            'slug': f'test-movie-{Movie.objects.count() + 1}',
            'is_published': True,
            'download_links': [],
        }
        values.update(overrides)
        return Movie.objects.create(**values)

    def test_collect_includes_missing_and_expired_but_not_fresh(self):
        missing = self.make_movie()
        expired = self.make_movie(download_links=[{
            # A real lapsed timestamp (2001): signature_expiry only reads a
            # plausible 9-13 digit one, so 'expires=1' is not an expiry at all.
            'url': 'https://cdn.example/movie.mp4?expires=1000000000',
        }])
        self.make_movie(download_links=[{'url': 'https://cdn.example/movie.mp4'}])

        ids = [pk for kind, pk, _ in collect_broken(series=False)]

        self.assertEqual(ids, [missing.pk, expired.pk])

    @patch('apps.catalog.provider_import.multi_provider_crawl.catalog_link_providers')
    @patch('apps.catalog.playback_refresh._crawl_one')
    def test_merges_second_provider_after_first_success(self, crawl, providers):
        providers.return_value = ['myf2m', 'dornatv']
        movie = self.make_movie()

        def succeed(slug, obj, *, replace, queue_softsub):
            links = [] if replace else list(obj.download_links or [])
            links.append({'url': f'https://cdn.example/{slug}.mp4'})
            Movie.objects.filter(pk=obj.pk).update(download_links=links)
            return {'imported_count': 1}

        crawl.side_effect = succeed
        stats = refresh_broken_playback(delay=0, delete=False)

        movie.refresh_from_db()
        self.assertEqual(stats['refreshed'], 1)
        self.assertEqual(len(movie.download_links), 2)
        self.assertTrue(crawl.call_args_list[0].kwargs['replace'])
        self.assertFalse(crawl.call_args_list[1].kwargs['replace'])

    @patch('apps.catalog.provider_import.multi_provider_crawl.catalog_link_providers')
    @patch('apps.catalog.playback_refresh._crawl_one')
    def test_deletes_only_when_every_provider_is_definitive_miss(self, crawl, providers):
        providers.return_value = ['myf2m', 'dornatv']
        movie = self.make_movie()

        def miss(slug, obj, *, replace, queue_softsub):
            code = 'myf2m_page_required' if slug == 'myf2m' else 'dornatv_page_required'
            raise ProviderImportError('missing', code=code)

        crawl.side_effect = miss
        stats = refresh_broken_playback(delay=0, delete=True)

        self.assertEqual(stats['deleted'], 1)
        self.assertFalse(Movie.objects.filter(pk=movie.pk).exists())

    @patch('apps.catalog.provider_import.multi_provider_crawl.catalog_link_providers')
    @patch('apps.catalog.playback_refresh._crawl_one')
    def test_keeps_title_on_any_transient_or_unexpected_failure(self, crawl, providers):
        providers.return_value = ['myf2m', 'dornatv']
        movie = self.make_movie()

        def mixed(slug, obj, *, replace, queue_softsub):
            if slug == 'myf2m':
                raise ProviderImportError('missing', code='myf2m_page_required')
            raise RuntimeError('temporary network failure')

        crawl.side_effect = mixed
        stats = refresh_broken_playback(delay=0, delete=True)

        self.assertEqual(stats['failed'], 1)
        self.assertTrue(Movie.objects.filter(pk=movie.pk).exists())
