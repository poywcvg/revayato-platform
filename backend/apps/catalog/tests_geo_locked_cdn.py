"""Iran-only CDNs (myf2m's abrtech.top → mehracdn.com): flagged, never sent to the gateway."""

from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.catalog import stream_gateway as gw
from apps.catalog.models import Movie
from config.public_urls import is_geo_locked_url, public_download_links

ABRTECH = 'https://bnrhd3fvb374s4bkwzxm54xf.abrtech.top/Serial/Breaking.Bad/S01/Breaking.Bad.S01E01.1080p.mkv'
PARSDL = 'https://dl.parsdl.top/Breaking.Bad.S01E01.720p.mkv'


@override_settings(GEO_LOCKED_CDN_HOSTS=['abrtech.top', 'mehracdn.com'])
class GeoLockedHostTests(SimpleTestCase):
    def test_subdomains_of_a_listed_host_are_locked(self):
        self.assertTrue(is_geo_locked_url(ABRTECH))
        self.assertTrue(is_geo_locked_url('https://sjdcbjdhbscjnhsdjcbjsd.mehracdn.com/x.mkv'))

    def test_lookalikes_and_other_hosts_are_not(self):
        self.assertFalse(is_geo_locked_url(PARSDL))
        self.assertFalse(is_geo_locked_url('https://notabrtech.top/x.mkv'))
        self.assertFalse(is_geo_locked_url('https://cdn.example/abrtech.top/x.mkv'))
        self.assertFalse(is_geo_locked_url(''))

    @override_settings(GEO_LOCKED_CDN_HOSTS=[])
    def test_the_list_is_configuration(self):
        self.assertFalse(is_geo_locked_url(ABRTECH))

    def test_public_links_carry_the_flag_only_where_true(self):
        movie = Movie(download_links=[
            {'quality': '1080p', 'url': ABRTECH},
            {'quality': '720p', 'url': PARSDL},
        ])
        rows = {row['url']: row for row in public_download_links(movie)}
        self.assertIs(rows[ABRTECH].get('iran_only'), True)
        self.assertNotIn('iran_only', rows[PARSDL])


@override_settings(GEO_LOCKED_CDN_HOSTS=['abrtech.top'])
class GatewayRefusesGeoLockedTests(TestCase):
    def setUp(self):
        cache.clear()
        self.movie = Movie.objects.create(
            title='بریکینگ', original_title='Breaking', slug='breaking-geo',
            is_published=True, download_links=[{'quality': '1080p', 'url': ABRTECH}],
        )

    def test_refused_fast_without_probing(self):
        with mock.patch.object(gw, 'probe_tech') as probe:
            response = self.client.post(
                reverse('stream_open'),
                data={'kind': 'movie', 'id': self.movie.pk, 'url': ABRTECH},
                content_type='application/json',
            )
        probe.assert_not_called()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['code'], 'geo_locked')
