"""Tests for Iranian catalog exclusion + myf2m reconcile helpers."""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.catalog.iranian import is_iranian_catalog_item, is_iranian_tmdb_details
from apps.catalog.models import Country, Movie, Series
from apps.catalog.myf2m_reconcile import purge_iranian_catalog, reconcile_catalog_with_myf2m


class IranianDetectionTests(TestCase):
    def test_tmdb_details_by_language(self):
        self.assertTrue(is_iranian_tmdb_details({'original_language': 'fa'}))
        self.assertFalse(is_iranian_tmdb_details({'original_language': 'en'}))

    def test_tmdb_details_by_production_country(self):
        self.assertTrue(is_iranian_tmdb_details({
            'original_language': 'en',
            'production_countries': [{'iso_3166_1': 'IR', 'name': 'Iran'}],
        }))

    def test_tmdb_details_by_origin_country(self):
        self.assertTrue(is_iranian_tmdb_details({
            'original_language': 'en',
            'origin_country': ['IR'],
        }))

    def test_catalog_item_by_language_and_country(self):
        iran = Country.objects.create(code='IR', name='ایران')
        us = Country.objects.create(code='US', name='آمریکا')
        iranian = Movie.objects.create(
            title='جدایی',
            original_title='A Separation',
            slug='a-separation',
            original_language='fa',
            is_published=True,
        )
        hollywood = Movie.objects.create(
            title='Inception',
            original_title='Inception',
            slug='inception',
            original_language='en',
            is_published=True,
        )
        hollywood.countries.add(us)
        co_prod = Movie.objects.create(
            title='CoProd',
            original_title='CoProd',
            slug='coprod',
            original_language='en',
            is_published=True,
        )
        co_prod.countries.add(iran)
        self.assertTrue(is_iranian_catalog_item(iranian))
        self.assertFalse(is_iranian_catalog_item(hollywood))
        self.assertTrue(is_iranian_catalog_item(co_prod))


@override_settings(
    CATALOG_LINK_PROVIDER='myf2m',
    CATALOG_EXCLUDE_IRANIAN=True,
    CATALOG_DELETE_WHEN_PROVIDER_MISSING=True,
    MYF2M_BASE_URL='https://www.myf2m.info',
)
class MyF2MReconcileTests(TestCase):
    def setUp(self):
        Country.objects.create(code='IR', name='ایران')
        self.iranian = Movie.objects.create(
            title='ایرانی',
            original_title='Iranian Film',
            slug='iranian-film',
            original_language='fa',
            is_published=True,
        )
        self.hollywood = Movie.objects.create(
            title='Inception',
            original_title='Inception',
            slug='inception-2010',
            original_language='en',
            release_year=2010,
            is_published=True,
            popularity=90,
        )
        self.missing = Movie.objects.create(
            title='Obscure',
            original_title='Obscure Nowhere Film',
            slug='obscure-nowhere',
            original_language='en',
            release_year=1999,
            is_published=True,
            popularity=1,
        )
        self.series = Series.objects.create(
            title='Lost',
            original_title='Lost',
            slug='lost',
            original_language='en',
            start_year=2004,
            is_published=True,
            popularity=80,
        )

    def test_purge_iranian_catalog(self):
        result = purge_iranian_catalog(dry_run=False)
        self.assertEqual(result['iranian_movies_deleted'], 1)
        self.assertFalse(Movie.objects.filter(pk=self.iranian.pk).exists())
        self.assertTrue(Movie.objects.filter(pk=self.hollywood.pk).exists())

    @patch('apps.catalog.provider_import.registry.get_connector')
    @patch('apps.catalog.myf2m_reconcile._crawl_movie_links')
    @patch('apps.catalog.myf2m_reconcile._crawl_series_links')
    def test_reconcile_fills_links_and_deletes_missing(self, crawl_series, crawl_movie, get_connector):
        connector = MagicMock()
        connector.authenticate.return_value = MagicMock(ok=True, message='ok')
        get_connector.return_value = connector

        def movie_side_effect(movie, _connector, replace=True):
            if movie.pk == self.hollywood.pk:
                movie.download_links = [{
                    'url': 'https://cdn.example/Inception.1080p.SoftSub.mkv',
                    'quality': '1080p SoftSub',
                    'label': '1080p SoftSub',
                    'kind': 'subtitle',
                    'subtitle_type': 'soft',
                }]
                movie.video_url = movie.download_links[0]['url']
                movie.has_subtitle = True
                movie.save(update_fields=['download_links', 'video_url', 'has_subtitle', 'updated_at'])
                return {'status': 'ok', 'imported_count': 1, 'page_path': '/inception-2010/'}
            return {'status': 'page_not_found'}

        def series_side_effect(series, _connector, replace=True):
            series.download_links = [{
                'url': 'https://cdn.example/Lost.S01E01.mkv',
                'quality': '1080p SoftSub',
                'label': 'S01E01',
                'kind': 'subtitle',
                'subtitle_type': 'soft',
            }]
            series.has_subtitle = True
            series.save(update_fields=['download_links', 'has_subtitle', 'updated_at'])
            return {'status': 'ok', 'imported_count': 1, 'page_path': '/series/lost/'}

        crawl_movie.side_effect = movie_side_effect
        crawl_series.side_effect = series_side_effect

        stats = reconcile_catalog_with_myf2m(
            delete_missing=True,
            purge_iranian=True,
            crawl_delay_seconds=0,
            dry_run=False,
        )

        self.assertEqual(stats['iranian_movies_deleted'], 1)
        self.assertFalse(Movie.objects.filter(pk=self.iranian.pk).exists())
        self.assertFalse(Movie.objects.filter(pk=self.missing.pk).exists())
        self.hollywood.refresh_from_db()
        self.assertTrue(self.hollywood.download_links)
        self.assertTrue(self.hollywood.video_url)
        self.series.refresh_from_db()
        self.assertTrue(self.series.download_links)
        self.assertGreaterEqual(stats['movies_crawled_ok'], 1)
        self.assertGreaterEqual(stats['movies_deleted'], 1)
        self.assertGreaterEqual(stats['series_crawled_ok'], 1)
