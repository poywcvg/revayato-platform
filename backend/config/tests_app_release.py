"""The Android update channel, tested against real files on a real directory.

The one failure that matters here is advertising a build the app cannot then
download — so most of these assert the *refusals*, not the happy path.
"""

import hashlib
import json
import os
import tempfile

from django.test import TestCase, override_settings
from django.urls import reverse


def _manifest(directory, **overrides):
    payload = {
        'package': 'com.revayato.app',
        'version_code': 16,
        'version_name': '1.0.15',
        'apk': 'revayato-1.0.15.apk',
        'min_supported_version_code': 0,
        'released_at': '2026-09-19',
        'notes': ['تست'],
    }
    payload.update(overrides)
    with open(os.path.join(directory, 'app-release.json'), 'w', encoding='utf-8') as handle:
        json.dump(payload, handle)
    return payload


class AppVersionEndpointTests(TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.directory = self._dir.name
        self.settings_patch = override_settings(
            APP_RELEASE_DIR=self.directory,
            APP_RELEASE_MANIFEST='',
            APP_DOWNLOAD_BASE_URL='https://revayato.com/downloads',
        )
        self.settings_patch.enable()
        self.addCleanup(self.settings_patch.disable)
        self.url = reverse('app_version')

    def _write_apk(self, name='revayato-1.0.15.apk', body=b'PK\x03\x04revayato'):
        path = os.path.join(self.directory, name)
        with open(path, 'wb') as handle:
            handle.write(body)
        return path, body

    # ------------------------------------------------------------------ refuse

    def test_no_manifest_is_no_update_not_an_error(self):
        # A launch check must never look like a broken app.
        response = self.client.get(self.url, {'version_code': 1})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['available'])
        self.assertFalse(response.json()['update_available'])

    def test_a_manifest_whose_apk_is_missing_offers_nothing(self):
        _manifest(self.directory)  # no APK written
        response = self.client.get(self.url, {'version_code': 1})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['available'])

    def test_malformed_manifest_offers_nothing(self):
        with open(os.path.join(self.directory, 'app-release.json'), 'w', encoding='utf-8') as fh:
            fh.write('{not json at all')
        self._write_apk()
        self.assertFalse(self.client.get(self.url).json()['available'])

    def test_an_incomplete_manifest_offers_nothing(self):
        _manifest(self.directory, version_code=0)
        self._write_apk()
        self.assertFalse(self.client.get(self.url).json()['available'])

    def test_a_traversing_apk_name_is_refused(self):
        outside = os.path.join(self.directory, 'outside.apk')
        with open(outside, 'wb') as handle:
            handle.write(b'x')
        _manifest(self.directory, apk='../%s/outside.apk' % os.path.basename(self.directory))
        self.assertFalse(self.client.get(self.url).json()['available'])

    def test_an_empty_apk_file_is_not_a_release(self):
        _manifest(self.directory)
        self._write_apk(body=b'')
        self.assertFalse(self.client.get(self.url).json()['available'])

    # ------------------------------------------------------------------ offer

    def test_a_present_apk_is_offered_with_its_real_size_and_checksum(self):
        _manifest(self.directory)
        _, body = self._write_apk()
        data = self.client.get(self.url, {'version_code': 15}).json()
        self.assertTrue(data['available'])
        self.assertTrue(data['update_available'])
        self.assertFalse(data['mandatory'])
        self.assertEqual(data['version_code'], 16)
        self.assertEqual(data['version_name'], '1.0.15')
        self.assertEqual(data['download_url'],
                         'https://revayato.com/downloads/revayato-1.0.15.apk')
        self.assertEqual(data['size_bytes'], len(body))
        self.assertEqual(data['sha256'], hashlib.sha256(body).hexdigest())
        self.assertEqual(data['notes'], ['تست'])

    def test_the_current_build_is_told_it_is_current(self):
        _manifest(self.directory)
        self._write_apk()
        data = self.client.get(self.url, {'version_code': 16}).json()
        self.assertTrue(data['available'])
        self.assertFalse(data['update_available'])

    def test_a_newer_build_than_we_publish_is_not_downgraded(self):
        # A tester sideloads a build ahead of the manifest; never push them back.
        _manifest(self.directory)
        self._write_apk()
        self.assertFalse(self.client.get(self.url, {'version_code': 99}).json()['update_available'])

    def test_below_the_minimum_supported_build_the_update_is_mandatory(self):
        _manifest(self.directory, min_supported_version_code=14)
        self._write_apk()
        data = self.client.get(self.url, {'version_code': 13}).json()
        self.assertTrue(data['mandatory'])
        self.assertTrue(data['update_available'])

    def test_at_the_minimum_supported_build_the_update_is_optional(self):
        _manifest(self.directory, min_supported_version_code=14)
        self._write_apk()
        self.assertFalse(self.client.get(self.url, {'version_code': 14}).json()['mandatory'])

    def test_without_a_version_code_we_describe_but_do_not_judge(self):
        # An old client that does not send its build still gets the facts and
        # compares them itself.
        _manifest(self.directory)
        self._write_apk()
        data = self.client.get(self.url).json()
        self.assertTrue(data['available'])
        self.assertFalse(data['update_available'])
        self.assertEqual(data['version_code'], 16)

    def test_a_junk_version_code_is_treated_as_unknown_not_as_zero(self):
        _manifest(self.directory)
        self._write_apk()
        data = self.client.get(self.url, {'version_code': 'latest'}).json()
        self.assertFalse(data['update_available'])
        self.assertFalse(data['mandatory'])

    def test_notes_are_trimmed_and_capped(self):
        _manifest(self.directory, notes=['  a  ', '', 'b'] + [f'n{i}' for i in range(10)])
        self._write_apk()
        notes = self.client.get(self.url).json()['notes']
        self.assertEqual(notes[:2], ['a', 'b'])
        self.assertLessEqual(len(notes), 8)

    def test_the_answer_is_cacheable_at_the_edge(self):
        _manifest(self.directory)
        self._write_apk()
        response = self.client.get(self.url, {'version_code': 1})
        self.assertIn('max-age', response['Cache-Control'])
