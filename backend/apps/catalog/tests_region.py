from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.catalog.region_api import playback_allowed_from, viewer_country


class _Request:
    """The one thing the resolver reads."""

    def __init__(self, **meta):
        self.META = meta


class ViewerCountryTests(TestCase):
    def test_reads_the_cloudflare_country(self):
        self.assertEqual(viewer_country(_Request(HTTP_CF_IPCOUNTRY='fr')), 'FR')

    def test_cloudflare_placeholders_are_not_countries(self):
        # XX is "no country for this address" and T1 is a Tor exit. Neither
        # says the viewer is abroad, so neither may block playback.
        for placeholder in ('XX', 'T1'):
            self.assertEqual(viewer_country(_Request(HTTP_CF_IPCOUNTRY=placeholder)), '')
            self.assertTrue(playback_allowed_from(_Request(HTTP_CF_IPCOUNTRY=placeholder)))

    def test_no_header_means_no_claim_about_the_viewer(self):
        # Served without an edge in front, nothing resolved a country. Guessing
        # "abroad" here would show the modal to every local viewer.
        self.assertEqual(viewer_country(_Request()), '')
        self.assertTrue(playback_allowed_from(_Request()))

    def test_country_outside_the_served_set_is_blocked(self):
        self.assertFalse(playback_allowed_from(_Request(HTTP_CF_IPCOUNTRY='DE')))
        self.assertTrue(playback_allowed_from(_Request(HTTP_CF_IPCOUNTRY='IR')))

    @override_settings(SITE_PLAYBACK_REGIONS='IR, TR')
    def test_the_served_set_is_configurable(self):
        self.assertTrue(playback_allowed_from(_Request(HTTP_CF_IPCOUNTRY='TR')))
        self.assertFalse(playback_allowed_from(_Request(HTTP_CF_IPCOUNTRY='DE')))

    @override_settings(SITE_PLAYBACK_REGIONS='   ')
    def test_an_empty_setting_falls_back_to_iran_rather_than_blocking_everyone(self):
        self.assertTrue(playback_allowed_from(_Request(HTTP_CF_IPCOUNTRY='IR')))
        self.assertFalse(playback_allowed_from(_Request(HTTP_CF_IPCOUNTRY='DE')))


class PlaybackRegionEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_reports_a_foreign_viewer(self):
        response = self.client.get('/api/playback/region/', HTTP_CF_IPCOUNTRY='DE')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['country'], 'DE')
        self.assertFalse(response.json()['allowed'])
        self.assertTrue(response.json()['known'])

    def test_reports_an_iranian_viewer(self):
        response = self.client.get('/api/playback/region/', HTTP_CF_IPCOUNTRY='IR')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['allowed'])

    def test_anonymous_viewers_get_an_answer(self):
        # The modal has to work before anyone signs in; that is the whole point.
        self.assertEqual(self.client.get('/api/playback/region/').status_code, 200)

    def test_the_answer_is_never_stored_in_a_shared_cache(self):
        # One cached body would tell every later viewer they are in the country
        # of whoever asked first.
        response = self.client.get('/api/playback/region/', HTTP_CF_IPCOUNTRY='DE')
        self.assertIn('no-store', response['Cache-Control'])
