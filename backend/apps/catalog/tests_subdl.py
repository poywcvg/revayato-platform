import io
import json
import zipfile
from types import SimpleNamespace
from unittest import mock
from urllib.error import HTTPError

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from apps.catalog import subdl

_SRT = (
    '1\n00:00:01,000 --> 00:00:03,000\nسلام، این یک زیرنویس فارسی آزمایشی است\n\n'
    '2\n00:00:04,000 --> 00:00:06,000\nخط دوم زیرنویس برای بررسی\n'
).encode('utf-8')

_MOVIE_URL = 'https://dl.example.com/The.Batman.2022.1080p.WEB-DL.x264.mkv'


def _zip(*names: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name in names:
            archive.writestr(name, _SRT)
    return buffer.getvalue()


def _api(results, subtitles) -> bytes:
    return json.dumps({'status': True, 'results': results, 'subtitles': subtitles}).encode()


@override_settings(
    SUBDL_API_KEY='secret-key-123',
    SUBDL_ENABLED=True,
    SUBDL_REQUEST_INTERVAL_SECONDS=0.1,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class SubdlProviderTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.movie = SimpleNamespace(pk=1, imdb_id='tt1877830', tmdb_id=414906)
        self.series = SimpleNamespace(pk=2, imdb_id='tt11280740', tmdb_id=None)

    def _serve(self, routes):
        """Patch ``_fetch``: API calls → JSON, dl.subdl.com paths → zip bytes."""
        calls = []

        def fake(url, *, max_bytes, timeout_seconds, urgent):
            calls.append(url)
            if url.startswith(subdl.API_URL):
                return routes['api'](url), url
            return routes[url], url

        return mock.patch.object(subdl, '_fetch', side_effect=fake), calls

    @override_settings(SUBDL_API_KEY='')
    def test_off_without_api_key(self):
        with mock.patch.object(subdl, '_fetch') as fetch:
            self.assertIsNone(subdl.find_movie_subtitle(self.movie, video_urls=[_MOVIE_URL]))
            self.assertEqual(subdl.find_series_episode_subtitles(
                self.series, episode_videos={(1, 1): [_MOVIE_URL]},
            ), [])
        fetch.assert_not_called()

    def test_movie_exact_id_match_downloads_persian_release(self):
        zip_url = 'https://dl.subdl.com/subtitle/1-2.zip'
        routes = {
            'api': lambda url: _api(
                [{'imdb_id': 'tt1877830', 'tmdb_id': 414906, 'name': 'The Batman'}],
                [
                    {'lang': 'english', 'language': 'EN', 'url': '/subtitle/9-9.zip',
                     'release_name': 'The.Batman.2022.1080p.WEB-DL'},
                    {'lang': 'farsi_persian', 'language': 'FA', 'url': '/subtitle/1-2.zip',
                     'release_name': 'The.Batman.2022.1080p.WEB-DL.x264'},
                ],
            ),
            zip_url: _zip('The.Batman.2022.1080p.WEB-DL.x264.srt'),
        }
        patcher, calls = self._serve(routes)
        with patcher:
            match = subdl.find_movie_subtitle(self.movie, video_urls=[_MOVIE_URL], timeout_seconds=30)
        self.assertIsNotNone(match)
        self.assertIn(_MOVIE_URL, match.source_urls)
        self.assertEqual(match.imdb_id, 'tt1877830')
        self.assertIn('imdb_id=tt1877830', calls[0])
        self.assertIn('languages=FA', calls[0])
        self.assertNotIn('https://dl.subdl.com/subtitle/9-9.zip', calls)  # English row never fetched
        self.assertNotIn('secret-key-123', match.page_url + match.download_url)

    def test_movie_identity_mismatch_is_rejected(self):
        routes = {
            'api': lambda url: _api(
                [{'imdb_id': 'tt0000001', 'name': 'Someone Else'}],
                [{'lang': 'farsi_persian', 'url': '/subtitle/1-2.zip', 'release_name': 'x'}],
            ),
        }
        patcher, calls = self._serve(routes)
        with patcher:
            self.assertIsNone(subdl.find_movie_subtitle(self.movie, video_urls=[_MOVIE_URL]))
        self.assertEqual(len(calls), 1)  # no download from an unverified title

    def test_movie_without_ids_never_searches_by_title(self):
        movie = SimpleNamespace(pk=3, imdb_id='', tmdb_id=None)
        with mock.patch.object(subdl, '_fetch') as fetch:
            self.assertIsNone(subdl.find_movie_subtitle(movie, video_urls=[_MOVIE_URL]))
        fetch.assert_not_called()

    def test_series_season_pack_binds_only_the_right_episode(self):
        pack_url = 'https://dl.subdl.com/subtitle/5-5.zip'
        ep_url = 'https://dl.example.com/Show.S02E03.1080p.WEB-DL.mkv'
        routes = {
            'api': lambda url: _api(
                [{'imdb_id': 'tt11280740'}],
                [{'lang': 'farsi_persian', 'url': '/subtitle/5-5.zip', 'season': 2,
                  'full_season': True, 'release_name': 'Show.S02.1080p.WEB-DL'}],
            ),
            pack_url: _zip(
                'Show.S02E01.1080p.WEB-DL.srt',
                'Show.S02E03.1080p.WEB-DL.srt',
            ),
        }
        patcher, calls = self._serve(routes)
        with patcher:
            matches = subdl.find_series_episode_subtitles(
                self.series, episode_videos={(2, 3): [ep_url]}, timeout_seconds=30,
            )
        self.assertEqual(len(matches), 1)
        self.assertEqual((matches[0].season_number, matches[0].episode_number), (2, 3))
        self.assertIn('S02E03', matches[0].filename)
        self.assertIn('season_number=2', calls[0])

    def test_series_episode_range_outside_is_skipped(self):
        entry = subdl._Entry(
            url='https://dl.subdl.com/x.zip', release_name='x', season=1, episode=None,
            full_season=False, episode_from=1, episode_end=4, page_url='',
        )
        self.assertTrue(entry.covers(1, 4))
        self.assertFalse(entry.covers(1, 5))
        self.assertFalse(entry.covers(2, 1))

    def test_rejected_key_opens_circuit_and_never_leaks_key(self):
        url = f'{subdl.API_URL}?api_key=secret-key-123&imdb_id=tt1'
        opener = mock.Mock()
        opener.open.side_effect = HTTPError(url, 403, 'Forbidden', {}, None)
        with mock.patch.object(subdl, 'build_opener', return_value=opener):
            with self.assertRaises(subdl.SubdlBlocked) as ctx:
                subdl._fetch(url, max_bytes=1024, timeout_seconds=3, urgent=True)
        self.assertNotIn('secret-key-123', str(ctx.exception))
        self.assertIsNone(ctx.exception.__cause__)
        self.assertTrue(cache.get(subdl.CIRCUIT_OPEN_KEY))
        with self.assertRaises(subdl.SubdlBlocked):
            subdl._fetch(url, max_bytes=1024, timeout_seconds=3, urgent=True)
        self.assertEqual(opener.open.call_count, 1)

    def test_only_subdl_hosts_are_contacted(self):
        with self.assertRaises(subdl.SubdlError):
            subdl._fetch('https://evil.example/x.zip', max_bytes=10, timeout_seconds=3, urgent=True)

    def test_clear_miss_forgets_negative_cache(self):
        cache.set('catalog:subdl:miss:tt1877830', True)
        subdl.clear_subdl_miss_for_movie(self.movie)
        self.assertIsNone(cache.get('catalog:subdl:miss:tt1877830'))
