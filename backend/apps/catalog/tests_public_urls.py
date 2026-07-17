from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings

from config.public_urls import (
    media_url, object_key, signed_download_url, validate_object_key,
)


@override_settings(
    MEDIA_CDN_BASE_URL='https://cdn.example.test',
    DOWNLOAD_CDN_BASE_URL='https://dl.example.test',
)
class PublicURLTests(SimpleTestCase):
    def test_media_url_is_built_from_relative_key(self):
        self.assertEqual(
            media_url('movies/123/hls/master.m3u8'),
            'https://cdn.example.test/movies/123/hls/master.m3u8',
        )

    def test_download_signing_hook_uses_download_origin(self):
        self.assertEqual(
            signed_download_url('movies/123/download/movie.mp4'),
            'https://dl.example.test/movies/123/download/movie.mp4',
        )

    def test_legacy_absolute_value_is_reduced_to_object_key(self):
        self.assertEqual(
            object_key('https://old.example.test/movies/123/master.m3u8?token=old'),
            'movies/123/master.m3u8',
        )

    def test_full_url_is_rejected_for_persistence(self):
        with self.assertRaises(ValidationError):
            validate_object_key('https://cdn.example.test/movies/123/master.m3u8')
