"""Tests for Dornatv (dornatv.com) BartarTheme parser/crawler."""

from django.test import SimpleTestCase, TestCase, override_settings

from apps.catalog.provider_import.providers.dornatv_parser import (
    _decode_player_vtt,
    _dedupe_download_rows,
    extract_embedded_subtitle_tracks,
    parse_download_links,
    parse_wp_rest_item,
    split_fa_en_titles,
)
from apps.catalog.models import Movie, Series
from apps.catalog.provider_import.dornatv_sync import (
    _validate_dornatv_identity,
    ensure_dornatv_provider,
)
from apps.catalog.provider_import.exceptions import ProviderImportError
from apps.catalog.provider_import.registry import list_connectors


SAMPLE_HTML = '''
<html><body>
<h1>دانلود فیلم ضربهٔ شانس Lucky Strike 2026</h1>
<img class="wp-post-image" src="https://dornatv.com/wp-content/uploads/2026/06/poster.jpg" />
<span class="title">سال انتشار : </span><a href="https://dornatv.com/release/2026/">2026</a></p>
<span class="title">کارگردان : </span><a href="#">Rod Lurie</a></p>
<span class="title">ستارگان : </span><a href="#">Scott Eastwood</a></p>
<span class="title">مدت زمان : </span>102 دقیقه</p>
<span class="rate">6.8</span>
خلاصه داستان : یک سرباز آمریکایی زخمی در پشت خطوط آلمان‌ها.
<div class="downloadWrapper"><div class="downloadBox "><div class="boxHead"><p>زیرنویس چسبیده</p></div>
<a class="download userRefLogin" href="https://s8.dlyar.top/Movies/2026/08/Lucky.Strike.2026/Lucky.Strike.2026.1080p.WEBRip.x264.AAC5.1-YTS.SoftSub.mp4">دانلود</a>
<a class="download userRefLogin" href="https://s8.dlyar.top/Movies/2026/08/Lucky.Strike.2026/Lucky.Strike.2026.720p.WEBRip.x264.AAC-YTS.SoftSub.mp4">دانلود</a>
</div></div>
</body></html>
'''


class DornatvParserTests(SimpleTestCase):
    def test_split_fa_en_titles(self):
        out = split_fa_en_titles('دانلود فیلم ضربهٔ شانس Lucky Strike 2026')
        self.assertEqual(out['title_fa'], 'ضربهٔ شانس')
        self.assertEqual(out['title_en'], 'Lucky Strike')
        self.assertEqual(out['year'], 2026)
        self.assertTrue(out['has_both'])

    def test_year_window_newest_first(self):
        from apps.catalog.provider_import.dornatv_import import _year_window
        from django.test.utils import override_settings

        with override_settings(DORNATV_IMPORT_YEAR_START=2026, DORNATV_IMPORT_YEAR_END=2020):
            hi, lo = _year_window(year_start=None, year_end=None)
            self.assertEqual((hi, lo), (2026, 2020))
        hi, lo = _year_window(year_start=2024, year_end=2026)
        self.assertEqual((hi, lo), (2026, 2024))

    def test_parse_download_links(self):
        parsed = parse_download_links(SAMPLE_HTML, page_path='/lucky-strike-2026/')
        self.assertGreaterEqual(parsed['total_entries'], 2)
        self.assertTrue(all(row['source'] == 'dornatv' for row in parsed['available_links']))
        self.assertEqual(parsed['title_fa'], 'ضربهٔ شانس')
        self.assertEqual(parsed['title_en'], 'Lucky Strike')
        self.assertEqual(parsed['year'], 2026)
        self.assertTrue(parsed['has_both_titles'])
        self.assertTrue(parsed['description'])
        self.assertEqual(parsed['directors'], ['Rod Lurie'])
        # SoftSub filename under «چسبیده» heading must classify as softsub.
        kinds = {row['kind'] for row in parsed['available_links']}
        self.assertEqual(kinds, {'softsub'})
        self.assertTrue(all('زیرنویس نرم' in row['label'] for row in parsed['available_links']))
        qualities = {row['quality'] for row in parsed['available_links']}
        self.assertTrue(any(q.startswith('1080p') for q in qualities))
        self.assertTrue(any(q.startswith('720p') for q in qualities))

    def test_dornatv_duble_and_hardsub_filenames(self):
        html = '''
        <html><body>
        <h1>دانلود فیلم تست Test Movie 2026</h1>
        <div class="boxHead"><p>زیرنویس چسبیده</p></div>
        <a class="download" href="https://cdn.example/Satluj.2026.Hindi.1080p.WEBDL.HardSub.mkv">دانلود</a>
        <div class="boxHead"><p>دوبله فارسی</p></div>
        <a class="download" href="https://cdn.example/Satluj.2026.1080p.WEB.DL.Duble.mp4">دانلود</a>
        <a class="download" href="https://cdn.example/Satluj.2026.DUBLE.mka">صوت</a>
        </body></html>
        '''
        parsed = parse_download_links(html, page_path='/test-2026/')
        kinds = sorted({row['kind'] for row in parsed['available_links']})
        self.assertEqual(kinds, ['dubbed', 'hardsub'])
        self.assertTrue(all(not str(row['url']).endswith('.mka') for row in parsed['available_links']))

    def test_trailers_and_short_t_files_are_not_download_qualities(self):
        html = '''
        <html><body>
        <h1>دانلود فیلم تست Test Movie 2026</h1>
        <div class="boxHead"><p>دوبله فارسی</p></div>
        <a class="download" href="https://cdn.example/Test.Movie.2026_t.mp4">تریلر</a>
        <a class="download" href="https://cdn.example/Test.Movie.Official.Trailer.mp4">تریلر</a>
        <a class="download" href="https://cdn.example/Test.Movie.2026.720p.WEB-DL.Dubbed.mkv">دانلود</a>
        </body></html>
        '''
        rows = parse_download_links(html, page_path='/test-2026/')['available_links']
        self.assertEqual(len(rows), 1)
        self.assertIn('720p', rows[0]['quality'])

    def test_trailer_word_in_real_episode_title_is_allowed(self):
        html = '''
        <a class="download" href="https://cdn.example/Trailer.Park.Boys.S01E01.720p.WEB-DL.mkv">دانلود</a>
        '''
        rows = parse_download_links(html, page_path='/trailer-park-boys/')['available_links']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['episode_number'], 1)

    def test_series_season_heading_and_episode_labels(self):
        html = '''
        <html><body>
        <h1>دانلود سریال تست Test Series</h1>
        <div class="boxHead"><p>فصل ۲ · زیرنویس نرم</p></div>
        <a class="download" href="https://cdn.example/series/tt123/SoftSub/S02/1080p/Show.E01.1080p.SoftSub.mkv">قسمت ۱</a>
        <a class="download" href="https://cdn.example/series/tt123/SoftSub/S02/720p/Show.E02.720p.SoftSub.mkv">قسمت ۲</a>
        <div class="boxHead"><p>دوبله فارسی</p></div>
        <a class="download" href="https://cdn.example/series/tt123/Dubbed/S02/720p/Show.S02E01.720p.Dubbed.mkv">قسمت ۱</a>
        </body></html>
        '''
        parsed = parse_download_links(html, page_path='/test-series/')
        rows = parsed['available_links']
        self.assertGreaterEqual(len(rows), 3)
        self.assertEqual(parsed['content_type'], 'series')
        soft = [row for row in rows if row.get('kind') == 'softsub']
        self.assertGreaterEqual(len(soft), 2)
        self.assertTrue(all(row.get('season_number') == 2 for row in soft))
        self.assertEqual(sorted(row.get('episode_number') for row in soft), [1, 2])
        dub = [row for row in rows if row.get('kind') == 'dubbed']
        self.assertEqual(len(dub), 1)
        self.assertEqual(dub[0].get('season_number'), 2)
        self.assertEqual(dub[0].get('episode_number'), 1)
        qualities = {row.get('quality') for row in rows}
        self.assertTrue(any(str(q).startswith('1080p') for q in qualities))
        self.assertTrue(any(str(q).startswith('720p') for q in qualities))

    def test_parse_wp_rest_item_categories(self):
        movie = parse_wp_rest_item({
            'id': 1,
            'link': 'https://dornatv.com/foo/',
            'slug': 'foo',
            'title': {'rendered': 'دانلود فیلم تست Test Movie 2024'},
            'categories': [27, 1],
        })
        self.assertEqual(movie['content_type'], 'movie')
        self.assertTrue(movie['has_both_titles'])
        series = parse_wp_rest_item({
            'id': 2,
            'link': 'https://dornatv.com/bar/',
            'slug': 'bar',
            'title': {'rendered': 'دانلود سریال سیلو Silo'},
            'categories': [28, 7],
        })
        self.assertEqual(series['content_type'], 'series')


class DornatvOptimizationTests(SimpleTestCase):
    """New: link de-dup, player ``sub=`` subtitle capture, and page caching."""

    def test_dedupe_repeated_cdn_rows_preserves_distinct_qualities(self):
        # Same CDN path, same episode, same kind+quality repeated across release
        # groups must collapse to one row; distinct qualities must both survive.
        rows = [
            {'url': 'https://s8.dlyar.top/x/Show.S01E01.1080p.SoftSub.mkv?md5=a&expires=1',
             'kind': 'softsub', 'quality': '1080p',
             'season_number': 1, 'episode_number': 1},
            {'url': 'https://s8.dlyar.top/x/Show.S01E01.1080p.SoftSub.mkv?md5=b&expires=2',
             'kind': 'softsub', 'quality': '1080p',
             'season_number': 1, 'episode_number': 1},
            {'url': 'https://s8.dlyar.top/x/Show.S01E01.720p.SoftSub.mkv?md5=c&expires=3',
             'kind': 'softsub', 'quality': '720p',
             'season_number': 1, 'episode_number': 1},
            # A genuinely different file (dubbed) must be kept.
            {'url': 'https://s8.dlyar.top/x/Show.S01E01.1080p.Dubbed.mkv?md5=d&expires=4',
             'kind': 'dubbed', 'quality': '1080p',
             'season_number': 1, 'episode_number': 1},
        ]
        out = _dedupe_download_rows(rows)
        self.assertEqual(len(out), 3)  # 720p softsub, 1080p softsub, 1080p dubbed
        self.assertEqual(len({r['url'] for r in out}), 3)

    def test_dedupe_keeps_distinct_seasons_and_episodes(self):
        rows = [
            {'url': 'https://s8.dlyar.top/x/Show.S01E01.720p.mkv', 'kind': 'dubbed',
             'quality': '720p', 'season_number': 1, 'episode_number': 1},
            {'url': 'https://s8.dlyar.top/x/Show.S01E02.720p.mkv', 'kind': 'dubbed',
             'quality': '720p', 'season_number': 1, 'episode_number': 2},
            {'url': 'https://s8.dlyar.top/x/Show.S02E01.720p.mkv', 'kind': 'dubbed',
             'quality': '720p', 'season_number': 2, 'episode_number': 1},
        ]
        out = _dedupe_download_rows(rows)
        self.assertEqual(len(out), 3)

    def test_player_sub_payload_decodes_to_signed_vtt(self):
        import base64
        import urllib.parse
        vtt_url = 'https://s8.dlyar.top/subtitles/Show.S01E01.fa.vtt?md5=abc&expires=9999999999'
        token = base64.b64encode(urllib.parse.quote(vtt_url, safe='').encode()).decode()
        decoded = _decode_player_vtt(token)
        self.assertEqual(decoded, vtt_url)

    def test_parse_download_links_extracts_subtitle_tracks(self):
        import base64
        import urllib.parse
        vtt_url = 'https://s8.dlyar.top/subtitles/Show.S01E01.fa.vtt?md5=abc&expires=9999999999'
        token = base64.b64encode(urllib.parse.quote(vtt_url, safe='').encode()).decode()
        html = f'''
        <html><body>
        <h1>دانلود سریال تست Test Series</h1>
        <div class="boxHead"><p>زیرنویس نرم</p></div>
        <a class="download" href="https://cdn.example/series/tt/SoftSub/S01/1080p/Show.S01E01.1080p.SoftSub.mkv">قسمت</a>
        </body></html>
        <iframe src="https://dornatv.com/player?pid=1&file=abc&sub={token}"></iframe>
        '''
        parsed = parse_download_links(html, page_path='/test-series/')
        tracks = parsed.get('subtitle_tracks') or []
        self.assertEqual(len(tracks), 1)
        track = tracks[0]
        self.assertEqual(track['source_url'], vtt_url)
        self.assertEqual(track['language'], 'fa')
        self.assertEqual(track['provider'], 'dornatv')
        self.assertEqual(track['id'], 'dornatv-S1E1')
        self.assertEqual(track['season_number'], 1)
        self.assertEqual(track['episode_number'], 1)

    def test_extract_embedded_subtitle_tracks_dedupes(self):
        import base64
        import urllib.parse
        def token(url):
            return base64.b64encode(urllib.parse.quote(url, safe='').encode()).decode()
        html = (
            f'<a href="?pid=1&file=a&sub={token("https://s8.dlyar.top/S1E1.fa.vtt?x=1")}">'
            f'<a href="?pid=1&file=b&#038;sub={token("https://s8.dlyar.top/S1E1.fa.vtt?x=2")}">'
        )
        tracks = extract_embedded_subtitle_tracks(html, rows=[])
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0]['id'], 'dornatv-S1E1')

    def test_detail_page_cache_serves_second_request_from_cache(self):
        """A second GET for the same detail path must not re-hit the network."""
        import types

        from django.core.cache import cache
        from apps.catalog.provider_import.providers.dornatv import DornatvConnector
        from apps.catalog.provider_import.exceptions import ProviderImportError

        calls = {'n': 0}

        class _FakeClient:
            def request(self, method, path, **kwargs):
                calls['n'] += 1
                if path.startswith('/wp-json/'):
                    return types.SimpleNamespace(
                        status_code=200,
                        headers={'X-WP-Total': '1', 'X-WP-TotalPages': '1'},
                        json=lambda: [],
                    )
                req = types.SimpleNamespace(
                    status_code=200,
                    headers={'content-type': 'text/html'},
                    text='<h1>دانلود فیلم تست Test Movie 2026</h1>'
                         '<div class="downloadBox"><div class="boxHead"><p>دوبله فارسی</p></div>'
                         '<a class="download" href="https://s8.dlyar.top/x/Test.2026.1080p.Dubbed.mkv">د</a>'
                         '</div>',
                    url=path,
                )
                req.raise_for_status = lambda: None
                return req

            def close(self):
                pass

        with override_settings(DORNATV_PAGE_CACHE_TTL_SECONDS=300):
            cache.clear()
            conn = DornatvConnector()
            conn._client = _FakeClient()
            conn._client_or_create = lambda: _FakeClient()
            try:
                r1 = conn.crawl_download_links('/test-movie-2026/', content_type='movie')
                calls_before = calls['n']
                self.assertEqual(r1.get('code'), 'ok')
                self.assertEqual(r1.get('total_entries'), 1)
                # Second crawl of the same path — served from the page cache, so
                # no new network request.
                r2 = conn.crawl_download_links('/test-movie-2026/', content_type='movie')
                self.assertEqual(calls['n'], calls_before)
                self.assertEqual(r2.get('page_path'), r1.get('page_path'))
                self.assertEqual(r2.get('code'), 'ok')
            finally:
                cache.clear()


class DornatvIdentityTests(SimpleTestCase):
    def test_accepts_exact_imdb_movie(self):
        movie = Movie(
            title='اتاق', original_title='Room', release_year=2015,
            imdb_id='tt3170832', tmdb_id=264644, slug='room',
        )
        _validate_dornatv_identity(movie, {
            'title_en': 'Anything', 'year': 2020, 'imdb_id': 'tt3170832',
        })

    def test_rejects_shared_word_wrong_movie(self):
        movie = Movie(
            title='اتاق', original_title='Room', release_year=2015,
            imdb_id='tt3170832', tmdb_id=264644, slug='room',
        )
        with self.assertRaisesMessage(ProviderImportError, 'identity mismatch'):
            _validate_dornatv_identity(movie, {
                'title_en': 'Lunana: A Yak in the Classroom',
                'year': 2019,
                'imdb_id': 'tt10189300',
            })

    def test_accepts_exact_title_and_year_from_canonical_path(self):
        movie = Movie(
            title='تاپ گان: ماوریک', original_title='Top Gun: Maverick',
            release_year=2022, imdb_id='tt1745960', tmdb_id=361743,
            slug='top-gun-maverick',
        )
        _validate_dornatv_identity(movie, {
            'title_en': 'Malformed heading',
            'year': None,
            'imdb_id': '',
            'page_path': '/download-top-gun-maverick-2022/',
        })

    def test_path_cannot_override_explicit_imdb_conflict(self):
        movie = Movie(
            title='اتاق', original_title='Room', release_year=2015,
            imdb_id='tt3170832', tmdb_id=264644, slug='room',
        )
        with self.assertRaisesMessage(ProviderImportError, 'identity mismatch'):
            _validate_dornatv_identity(movie, {
                'title_en': 'Wrong heading',
                'year': 2015,
                'imdb_id': 'tt10189300',
                'page_path': '/room-2015/',
            })

    def test_accepts_exact_title_and_year_without_imdb(self):
        series = Series(
            title='وایر', original_title='The Wire', start_year=2002,
            imdb_id='tt0306414', tmdb_id=1438, slug='the-wire',
        )
        _validate_dornatv_identity(series, {
            'title_en': 'The Wire', 'year': 2002, 'imdb_id': '',
        })

    def test_rejects_substring_series_match(self):
        series = Series(
            title='هانتر هانتر', original_title='Hunter x Hunter', start_year=2011,
            imdb_id='tt2098220', tmdb_id=46298, slug='hunter-x-hunter',
        )
        with self.assertRaisesMessage(ProviderImportError, 'identity mismatch'):
            _validate_dornatv_identity(series, {
                'title_en': 'Trollhunters: Tales of Arcadia',
                'year': 2016,
                'imdb_id': 'tt1734135',
            })


@override_settings(DORNATV_BASE_URL='https://dornatv.com', DORNATV_VERIFY_SSL=True)
class DornatvProviderSeedTests(TestCase):
    def test_staff_lists_dornatv_source(self):
        provider = ensure_dornatv_provider()
        self.assertEqual(provider.slug, 'dornatv')
        self.assertTrue(provider.is_active)
        self.assertIn('dornatv', list_connectors())
