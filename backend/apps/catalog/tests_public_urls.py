from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings

from config.public_urls import (
    media_url, normalize_download_links, object_key, public_download_links,
    signed_download_url, validate_object_key,
)
from apps.catalog.provider_import.media_links import (
    browser_playback_score,
    is_browser_native_video_url,
    video_container,
)


@override_settings(
    MEDIA_CDN_BASE_URL='https://cdn.example.test',
    DOWNLOAD_CDN_BASE_URL='https://dl.example.test',
)
class PublicURLTests(SimpleTestCase):
    def test_browser_playback_ranking_prefers_native_containers_and_safe_codecs(self):
        self.assertEqual(video_container('https://cdn.example/movie.MP4?token=x'), 'mp4')
        self.assertTrue(is_browser_native_video_url('https://cdn.example/movie.mp4'))
        self.assertFalse(is_browser_native_video_url('https://cdn.example/movie.mkv'))
        self.assertGreater(
            browser_playback_score('https://cdn.example/movie.720p.x264.mp4'),
            browser_playback_score('https://cdn.example/movie.1080p.x265.mkv'),
        )

    def test_import_primary_source_prefers_playable_mp4_over_dubbed_mkv(self):
        from apps.catalog.provider_import.catalog_lookup import _prefer_streamable_download
        from apps.catalog.subtitle_extract import _prefer_episode_stream_url

        links = [
            {
                'url': 'https://cdn.example/Movie.1080p.x265.Farsi.Dubbed.mkv',
                'quality': '1080p x265',
                'kind': 'dubbed',
            },
            {
                'url': 'https://cdn.example/Movie.720p.x264.HardSub.mp4',
                'quality': '720p x264',
                'kind': 'hardsub',
            },
        ]
        expected = links[1]['url']
        self.assertEqual(_prefer_streamable_download(links), expected)
        self.assertEqual(_prefer_episode_stream_url(links), expected)

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

    def test_full_url_is_accepted_for_persistence(self):
        # Crawlers store external CDN URLs directly; relative keys are not enforced.
        validate_object_key('https://cdn.example.test/movies/123/master.m3u8')

    def test_bare_scheme_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_object_key('https://')

    def test_normalize_keeps_external_download_urls(self):
        links = normalize_download_links([
            {
                'label': '۱۰۸۰',
                'url': 'https://provider.example/files/movie-1080.mp4?token=abc',
                'quality': '1080p',
                'size_label': '2GB',
            },
        ])
        self.assertEqual(links[0]['url'], 'https://provider.example/files/movie-1080.mp4?token=abc')
        self.assertNotIn('key', links[0])

        class FakeMovie:
            download_key = ''
            quality = ''
            download_links = links

        public = public_download_links(FakeMovie)
        self.assertEqual(public[0]['url'], 'https://provider.example/files/movie-1080.mp4?token=abc')
        self.assertEqual(public[0]['label'], '۱۰۸۰')

    def test_trailer_assets_are_not_persisted_or_exposed(self):
        links = normalize_download_links([
            {'label': 'تریلر', 'url': 'https://cdn.example/Movie.Trailer.mp4'},
            {'label': '720p', 'url': 'https://cdn.example/Movie.720p.WEB-DL.mkv'},
        ])
        self.assertEqual(len(links), 1)

        class FakeMovie:
            download_key = ''
            quality = ''
            download_links = [
                {'label': '1080p', 'url': 'https://cdn.example/Movie_t.mp4'},
                *links,
            ]

        public = public_download_links(FakeMovie)
        self.assertEqual([row['url'] for row in public], ['https://cdn.example/Movie.720p.WEB-DL.mkv'])

    def test_dead_and_malformed_provider_media_are_not_persisted(self):
        links = normalize_download_links([
            {'label': 'dead', 'url': 'https://dl5.cdnhost.lol/Movies/Soft/a.mkv'},
            {'label': 'bad tls', 'url': 'https://s13.dlyar.top/Movies/a.mp4'},
            {'label': 'bad mp4', 'url': 'https://cdn.example/Show.E01.mp41'},
            {'label': 'bad mkv', 'url': 'https://cdn.example/Show.E02.mkvر'},
            {'label': 'live', 'url': 'https://cdn.example/Show.E03.mp4'},
        ])
        self.assertEqual(
            [row['url'] for row in links],
            ['https://cdn.example/Show.E03.mp4'],
        )

    def test_public_download_links_falls_back_to_download_key(self):
        class FakeMovie:
            download_key = 'movies/9/file.mp4'
            quality = '720p'
            download_links = []

        public = public_download_links(FakeMovie)
        self.assertEqual(len(public), 1)
        self.assertEqual(public[0]['url'], 'https://dl.example.test/movies/9/file.mp4')
        self.assertEqual(public[0]['quality'], '720p')

    def test_public_download_links_sorted_by_quality_desc(self):
        class FakeMovie:
            download_key = ''
            quality = ''
            download_links = [
                {'label': 'SD', 'quality': '480p', 'url': 'https://cdn.example/a-480.mp4'},
                {'label': 'FHD', 'quality': '1080p', 'url': 'https://cdn.example/a-1080.mp4'},
                {'label': 'HD', 'quality': '720p', 'url': 'https://cdn.example/a-720.mp4'},
            ]

        public = public_download_links(FakeMovie)
        self.assertEqual([row['quality'] for row in public], ['1080p', '720p', '480p'])

    def test_public_download_links_backfill_season_episode_from_label(self):
        class FakeSeries:
            download_key = ''
            quality = ''
            download_links = [
                {
                    'label': 'فصل 1 · قسمت 9 · زیرنویس چسبیده · WEB-DL 720p',
                    'quality': '720p',
                    'url': 'https://cdn.example/s1e9.mp4',
                    'kind': 'subtitle',
                },
                {
                    'label': 'فصل 1 · قسمت 2 · زیرنویس چسبیده · WEB-DL 720p',
                    'quality': '720p',
                    'url': 'https://cdn.example/s1e2.mp4',
                    'kind': 'subtitle',
                },
            ]

        public = public_download_links(FakeSeries)
        self.assertEqual(public[0]['season_number'], 1)
        self.assertEqual(public[0]['episode_number'], 2)
        self.assertEqual(public[1]['episode_number'], 9)
        self.assertEqual(public[0]['episode'], 'قسمت 2')

    def test_normalize_backfills_season_episode_from_label(self):
        links = normalize_download_links([
            {
                'label': 'فصل 2 · قسمت 12 · دوبله فارسی · 1080p',
                'url': 'https://cdn.example/s2e12.mp4',
                'quality': '1080p',
                'kind': 'dub',
            },
        ])
        self.assertEqual(links[0]['season_number'], 2)
        self.assertEqual(links[0]['episode_number'], 12)
        self.assertEqual(links[0]['season'], 'فصل 2')
        self.assertEqual(links[0]['episode'], 'قسمت 12')
