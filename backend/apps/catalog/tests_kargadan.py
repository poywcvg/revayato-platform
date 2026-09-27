"""Kargadan Movie (kargadanmovie.com): parser, session gate, sync and discovery lane.

The HTML below is cut down from real pages (``/movies/tt0070849/`` and
``/series/tt2137109/``) and keeps their exact class names and nesting. The
signed-in markup (``a.dllink`` inside a row's second ``div.side``) is the shape
the theme's own "copy all links" script reads.
"""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.catalog.models import Movie
from apps.catalog.provider_import.exceptions import ProviderImportError
from apps.catalog.provider_import.kargadan_import import pending_entries, run_kargadan_missing_import
from apps.catalog.provider_import.providers.kargadan import (
    SESSION_STATE_CACHE_KEY,
    _cookie_pairs,
    inventory_says_missing,
    record_inventory,
    record_session_state,
    session_blocker,
)
from apps.catalog.provider_import.providers.kargadan_parser import (
    detail_path,
    imdb_from_path,
    login_state,
    parse_download_links,
    parse_sitemap,
    parse_sitemap_index,
)

CDN = 'https://dl8.kargadandl1.com'


def _head(*, kind='movies', imdb='tt0070849', title='Last Tango in Paris', year=1972, logged=''):
    word = 'سریال' if kind == 'series' else 'فیلم'
    return f'''<html><head>
<link rel="canonical" href="https://kargadanmovie.com/{kind}/{imdb}/" />
<script>var ajax_var = {{"ajaxurl":"https://kargadanmovie.com/wp-admin/admin-ajax.php","logged":"{logged}","nonce":"9b07bc2fd1"}};</script>
</head><body>
<h1>دانلود {word} {title} {year}</h1>
<a href="https://kargadanmovie.com/release/{year}/">{year}</a>
<div class="imdb-rate ">
  <a href="https://www.imdb.com/title/{imdb}/" class="imdb-btn">IMDb</a>
  <span class="rate">6.9</span>
</div>
'''


LOCKED_SIDE = '''<div class="side">
  <div class="need-vip">
    <p class="desc">برای دانلود باید ثبت نام کنید یا وارد شوید</p>
    <div class="btns">
      <a href="https://kargadanmovie.com/sign-up" class="btn-vip register">عضویت</a>
      <a href="https://kargadanmovie.com/sign-in" class="btn-vip login">ورود به حساب</a>
    </div>
  </div>
</div>'''


def _open_side(url):
    return f'<div class="side"><a class="dllink" href="{url}">دانلود</a></div>'


def _movie_item(second_side, quality='1080p', size='2.03 GB', subtype='SoftSub'):
    return f'''<li class="item-type">
  <div class="side">
    <span class="q-info type sub">زیرنویس</span>
    <span class="q-info">کیفیت : {quality}</span>
    <span class="q-info">حجم : {size}</span>
    <span class="q-info">انکودر : KargadanMovie</span>
    <span class="q-info sub-type">{subtype}</span>
  </div>
  {second_side}
</li>'''


ENGLISH_SUB_BOX = '''<div class="main-side-item download-box subtitle">
  <div class="headline-title"><h3 class="title"><span>باکس دانلود زیرنویس انگلیسی</span></h3></div>
  <ul class="type-list" data-type="sub"><li class="item-type">
    <div class="side"><span class="q-info">کیفیت : 1080p</span></div>
    <div class="side"><a class="dllink" href="https://subsource.net/subtitles/last-tango">subsource</a></div>
  </li></ul>
</div>'''

FOOTER = '<footer><a href="https://t.me/kargadanmovie">Telegram</a><a href="https://kargadanmovie.com/series/">سریال</a></footer></body></html>'


def movie_page(items, *, logged='', **head):
    return (
        _head(logged=logged, **head)
        + '<div class="main-side-item download-box movies">'
        + '<div class="headline-title"><h3 class="title"><span>باکس دانلود</span></h3></div>'
        + '<div class="dl-box"><ul class="type-list" data-type="sub" style="display: block;">'
        + ''.join(items)
        + '</ul></div></div>'
        + ENGLISH_SUB_BOX
        + FOOTER
    )


def _episode(n, second_side):
    return f'''<li class="ep-item">
  <div class="headline"><div class="right"><span class="item-info">قسمت {n}</span></div></div>
  <div class="inner-episode"><ul class="qualities-q">
    <li class="item-q"
        data-quality="1080p"
        data-subtype="SoftSub"
        data-type="sub"
        data-episode="قسمت {n}">
      <div class="side">
        <span class="q-info">کیفیت : 1080p</span>
        <span class="q-info">حجم : 1.17 GB</span>
        <span class="q-info sub-type">SoftSub</span>
      </div>
      {second_side}
    </li>
  </ul></div>
</li>'''


def series_page(episodes, *, logged='1'):
    return (
        _head(kind='series', imdb='tt2137109', title='Masters of Sex', year=2013, logged=logged)
        + '<div class="dlbox-episodes"><ul class="episode-list" data-seasonid="فصل 1" style="display: block;">'
        + '<div class="type-list" data-type="sub" data-nametag="رنگی" style="display: block;">'
        + ''.join(episodes)
        + '</div></ul></div>'
        # The theme's inline script carries a bare, attribute-less row in a comment.
        + '<script>/* template: <li class="item-q"> ... */</script>'
        + FOOTER
    )


class KargadanParserTests(SimpleTestCase):
    def test_page_identity_comes_from_the_url_and_heading(self):
        parsed = parse_download_links(movie_page([_movie_item(LOCKED_SIDE)]), page_path='/movies/tt0070849/')
        self.assertEqual(parsed['imdb_id'], 'tt0070849')
        self.assertEqual(parsed['content_type'], 'movie')
        self.assertEqual(parsed['title_en'], 'Last Tango in Paris')
        self.assertEqual(parsed['year'], 1972)
        self.assertEqual(parsed['imdb_rating'], 6.9)

    def test_an_anonymous_page_reports_login_required_not_empty(self):
        parsed = parse_download_links(movie_page([_movie_item(LOCKED_SIDE), _movie_item(LOCKED_SIDE, quality='720p')]))
        self.assertFalse(parsed['ok'])
        self.assertEqual(parsed['code'], 'kargadan_login_required')
        self.assertEqual(parsed['locked_rows'], 2)
        self.assertEqual(parsed['available_links'], [])

    def test_a_signed_in_page_still_locked_means_the_account_tier(self):
        parsed = parse_download_links(movie_page([_movie_item(LOCKED_SIDE)], logged='1'))
        self.assertEqual(parsed['code'], 'kargadan_vip_required')

    def test_signed_in_movie_rows_become_links(self):
        url = f'{CDN}/Movies/1972/Last.Tango.in.Paris.1972.1080p.BluRay.SoftSub.KargadanMovie.mkv'
        parsed = parse_download_links(movie_page([_movie_item(_open_side(url))], logged='1'),
                                      page_path='/movies/tt0070849/')
        self.assertTrue(parsed['ok'])
        self.assertEqual([r['url'] for r in parsed['available_links']], [url])
        row = parsed['available_links'][0]
        self.assertEqual(row['source'], 'kargadan')
        self.assertIn('1080p', row['quality'])
        self.assertEqual(row['kind'], 'softsub')
        self.assertEqual(row['page_path'], '/movies/tt0070849/')
        self.assertIn('size_label', row)
        self.assertNotIn('needs_resolve', row)

    def test_the_english_subtitle_box_and_footer_never_become_links(self):
        url = f'{CDN}/Movies/1972/Last.Tango.1080p.mkv'
        parsed = parse_download_links(movie_page([_movie_item(_open_side(url))], logged='1'))
        urls = [r['url'] for r in parsed['available_links']]
        self.assertEqual(urls, [url])

    def test_an_on_site_link_is_marked_for_resolution(self):
        parsed = parse_download_links(
            movie_page([_movie_item(_open_side('https://kargadanmovie.com/dl/?id=991'))], logged='1'),
        )
        self.assertTrue(parsed['available_links'][0]['needs_resolve'])

    def test_series_rows_carry_season_and_episode(self):
        html = series_page([
            _episode(1, _open_side(f'{CDN}/Series/Masters of Sex 2013/S01/Masters.of.Sex.S01E01.1080p.mkv')),
            _episode(2, _open_side(f'{CDN}/Series/Masters of Sex 2013/S01/Masters.of.Sex.S01E02.1080p.mkv')),
        ])
        parsed = parse_download_links(html, page_path='/series/tt2137109/')
        self.assertEqual(parsed['content_type'], 'series')
        rows = parsed['available_links']
        self.assertEqual(len(rows), 2, [r['url'] for r in rows])
        self.assertEqual(sorted((r['season_number'], r['episode_number']) for r in rows), [(1, 1), (1, 2)])
        self.assertEqual(parsed['total_entries'], 2, 'the commented template row must not count')

    def test_locked_series_page(self):
        parsed = parse_download_links(series_page([_episode(1, LOCKED_SIDE)], logged=''))
        self.assertEqual(parsed['code'], 'kargadan_login_required')
        self.assertEqual(parsed['locked_rows'], 1)

    def test_login_state(self):
        self.assertIs(login_state(_head(logged='')), False)
        self.assertIs(login_state(_head(logged='1')), True)
        self.assertIsNone(login_state('<html>no theme script</html>'))

    def test_paths(self):
        self.assertEqual(imdb_from_path('https://kargadanmovie.com/series/tt2137109/'), ('series', 'tt2137109'))
        self.assertEqual(detail_path('tt0070849', content_type='movie'), '/movies/tt0070849/')
        self.assertEqual(detail_path('tt2137109', content_type='series'), '/series/tt2137109/')

    def test_sitemaps(self):
        index = (
            '<sitemapindex>'
            '<sitemap><loc>https://kargadanmovie.com/wp-sitemap-posts-post-1.xml</loc></sitemap>'
            '<sitemap><loc>https://kargadanmovie.com/wp-sitemap-posts-movies-1.xml</loc></sitemap>'
            '<sitemap><loc>https://kargadanmovie.com/wp-sitemap-posts-series-1.xml</loc></sitemap>'
            '<sitemap><loc>https://kargadanmovie.com/wp-sitemap-taxonomies-genre-1.xml</loc></sitemap>'
            '</sitemapindex>'
        )
        self.assertEqual([kind for kind, _url in parse_sitemap_index(index)], ['movie', 'series'])
        part = (
            '<urlset>'
            '<url><loc>https://kargadanmovie.com/movies/tt9104736/</loc><lastmod>2025-12-21T05:44:50+03:30</lastmod></url>'
            '<url><loc>https://kargadanmovie.com/series/tt2137109/</loc><lastmod>2026-06-07T13:24:18+03:30</lastmod></url>'
            '<url><loc>https://kargadanmovie.com/about-us/</loc></url>'
            '</urlset>'
        )
        entries = parse_sitemap(part)
        self.assertEqual(
            [(e['content_type'], e['imdb_id'], e['lastmod']) for e in entries],
            [('movie', 'tt9104736', '2025-12-21T05:44:50+03:30'), ('series', 'tt2137109', '2026-06-07T13:24:18+03:30')],
        )

    def test_cookie_header_parsing(self):
        self.assertEqual(
            _cookie_pairs('wordpress_logged_in_abc=user%7C123; PHPSESSID=xyz ; junk'),
            {'wordpress_logged_in_abc': 'user%7C123', 'PHPSESSID': 'xyz'},
        )


class KargadanSessionGateTests(TestCase):
    def setUp(self):
        cache.clear()

    @override_settings(KARGADAN_SESSION_COOKIE='')
    def test_no_cookie_blocks_without_a_request(self):
        self.assertEqual(session_blocker(), 'kargadan_session_missing')

    @override_settings(KARGADAN_SESSION_COOKIE='a=1')
    def test_a_recent_signed_out_answer_blocks(self):
        self.assertEqual(session_blocker(), '')
        record_session_state(False)
        self.assertEqual(session_blocker(), 'kargadan_login_required')
        record_session_state(True)
        self.assertEqual(session_blocker(), '')

    @override_settings(KARGADAN_SESSION_COOKIE='a=1', KARGADAN_SESSION_RECHECK_MINUTES=30)
    def test_the_block_lapses_so_the_session_is_rechecked(self):
        record_session_state(False)
        state = cache.get(SESSION_STATE_CACHE_KEY)
        state['checked_at'] = (timezone.now() - timezone.timedelta(minutes=31)).isoformat()
        cache.set(SESSION_STATE_CACHE_KEY, state)
        self.assertEqual(session_blocker(), '')

    def test_a_new_cookie_is_tried_at_once(self):
        with override_settings(KARGADAN_SESSION_COOKIE='a=1'):
            record_session_state(False)
        with override_settings(KARGADAN_SESSION_COOKIE='a=2'):
            self.assertEqual(session_blocker(), '')

    def test_inventory(self):
        self.assertFalse(inventory_says_missing('tt1', content_type='movie'), 'no inventory → unknown → try')
        record_inventory([{'content_type': 'movie', 'imdb_id': 'tt1'}, {'content_type': 'series', 'imdb_id': 'tt2'}])
        self.assertFalse(inventory_says_missing('tt1', content_type='movie'))
        self.assertTrue(inventory_says_missing('tt9', content_type='movie'))
        self.assertTrue(inventory_says_missing('tt1', content_type='series'))


class _PageConnector:
    def __init__(self, crawled=None, error=None):
        self.crawled, self.error, self.calls = crawled, error, []

    def crawl_download_links(self, imdb_id, *, content_type):
        self.calls.append((imdb_id, content_type))
        if self.error:
            raise self.error
        return self.crawled

    def close(self):
        pass


class KargadanSyncTests(TestCase):
    def setUp(self):
        cache.clear()

    def _crawl(self, connector, imdb='tt0070849', content_type='movie'):
        from apps.catalog.provider_import import kargadan_sync

        with patch('apps.catalog.provider_import.registry.get_connector', return_value=connector):
            return kargadan_sync._crawl(SimpleNamespace(imdb_id=imdb), content_type=content_type)

    @override_settings(KARGADAN_SESSION_COOKIE='')
    def test_no_session_short_circuits_before_any_request(self):
        connector = _PageConnector()
        with self.assertRaises(ProviderImportError) as ctx:
            self._crawl(connector)
        self.assertEqual(ctx.exception.code, 'kargadan_session_missing')
        self.assertEqual(connector.calls, [])

    @override_settings(KARGADAN_SESSION_COOKIE='a=1')
    def test_a_title_missing_from_the_inventory_is_not_fetched(self):
        record_inventory([{'content_type': 'movie', 'imdb_id': 'tt0000001'}])
        connector = _PageConnector()
        with self.assertRaises(ProviderImportError) as ctx:
            self._crawl(connector)
        self.assertEqual(ctx.exception.code, 'kargadan_page_missing')
        self.assertEqual(connector.calls, [])

    @override_settings(KARGADAN_SESSION_COOKIE='a=1')
    def test_another_titles_page_is_rejected(self):
        connector = _PageConnector({'imdb_id': 'tt9999999', 'content_type': 'movie',
                                    'available_links': [{'url': f'{CDN}/x.mkv'}]})
        with self.assertRaises(ProviderImportError) as ctx:
            self._crawl(connector)
        self.assertEqual(ctx.exception.code, 'kargadan_identity_mismatch')

    @override_settings(KARGADAN_SESSION_COOKIE='a=1')
    def test_a_series_page_never_feeds_a_movie(self):
        connector = _PageConnector({'imdb_id': 'tt0070849', 'content_type': 'series',
                                    'available_links': [{'url': f'{CDN}/x.mkv'}]})
        with self.assertRaises(ProviderImportError) as ctx:
            self._crawl(connector)
        self.assertEqual(ctx.exception.code, 'kargadan_identity_mismatch')

    @override_settings(KARGADAN_SESSION_COOKIE='a=1')
    def test_a_locked_page_surfaces_its_own_code(self):
        connector = _PageConnector({'imdb_id': 'tt0070849', 'content_type': 'movie', 'available_links': [],
                                    'code': 'kargadan_login_required', 'message': 'sign in'})
        with self.assertRaises(ProviderImportError) as ctx:
            self._crawl(connector)
        self.assertEqual(ctx.exception.code, 'kargadan_login_required')

    def test_kargadan_is_a_default_link_provider(self):
        from apps.catalog.provider_import.multi_provider_crawl import catalog_link_providers
        from apps.catalog.provider_import.registry import list_connectors

        self.assertIn('kargadan', catalog_link_providers())
        self.assertIn('kargadan', list_connectors())


class _LaneConnector:
    """Fake connector for the discovery lane: a fixed sitemap and per-title answers."""

    def __init__(self, entries, answers=None):
        self.entries = entries
        self.answers = answers or {}
        self.crawled = []

    def validate_credentials(self):
        return SimpleNamespace(ok=True, message='')

    def sitemap_entries(self):
        return list(self.entries)

    def crawl_download_links(self, imdb_id, *, content_type):
        self.crawled.append(imdb_id)
        answer = self.answers.get(imdb_id)
        if isinstance(answer, Exception):
            raise answer
        return answer or {'imdb_id': imdb_id, 'available_links': [], 'code': 'kargadan_links_empty'}

    def close(self):
        pass


class _NoTmdb:
    def resolve_imdb_to_tmdb(self, imdb_id, *, content_type):
        return None


class KargadanDiscoveryLaneTests(TestCase):
    def setUp(self):
        cache.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.checkpoint = str(Path(self.tmp.name) / 'kargadan.json')

    def run_tick(self, connector, **kw):
        kw.setdefault('delay', 0)
        kw.setdefault('queue_softsub', False)
        return run_kargadan_missing_import(
            connector=connector, tmdb_client=_NoTmdb(), checkpoint_path=self.checkpoint, **kw,
        )

    def entries(self):
        return [
            {'content_type': 'movie', 'imdb_id': 'tt0000001', 'lastmod': '2026-01-01T00:00:00+03:30'},
            {'content_type': 'movie', 'imdb_id': 'tt0000002', 'lastmod': '2026-03-01T00:00:00+03:30'},
        ]

    @override_settings(KARGADAN_SESSION_COOKIE='')
    def test_without_a_session_the_tick_completes_and_keeps_the_inventory(self):
        connector = _LaneConnector(self.entries())
        stats = self.run_tick(connector)
        self.assertEqual(stats['status'], 'session_required')
        self.assertEqual(stats['code'], 'kargadan_session_missing')
        self.assertEqual(stats['sitemap_movies'], 2)
        self.assertEqual(connector.crawled, [])
        self.assertTrue(inventory_says_missing('tt7777777', content_type='movie'))

    @override_settings(KARGADAN_SESSION_COOKIE='a=1')
    def test_new_titles_first_and_known_pages_are_not_refetched(self):
        Movie.objects.create(title='موجود', slug='existing-one', imdb_id='tt0000001')
        connector = _LaneConnector(self.entries())
        with patch('apps.catalog.provider_import.kargadan_sync.crawl_kargadan_downloads_for_movie') as refresh:
            stats = self.run_tick(connector)
        self.assertEqual(stats['status'], 'ok')
        self.assertEqual(connector.crawled, ['tt0000002'], 'newest lastmod first; existing one is refreshed')
        self.assertEqual(stats['no_links'], 1)
        self.assertEqual(refresh.call_count, 1)
        self.assertFalse(refresh.call_args.kwargs['replace'], 'a refresh merges, it never replaces')
        self.assertEqual(stats['refreshed'], 1)

        seen = json.loads(Path(self.checkpoint).read_text())['seen']
        self.assertEqual(set(seen), {'movie:tt0000001', 'movie:tt0000002'})

        connector.crawled.clear()
        with patch('apps.catalog.provider_import.kargadan_sync.crawl_kargadan_downloads_for_movie') as refresh:
            again = self.run_tick(connector)
        self.assertEqual(again['pending'], 0)
        self.assertEqual(connector.crawled, [])
        refresh.assert_not_called()

    @override_settings(KARGADAN_SESSION_COOKIE='a=1')
    def test_an_edited_page_is_visited_again(self):
        connector = _LaneConnector(self.entries())
        self.run_tick(connector)
        connector.entries[0] = {**connector.entries[0], 'lastmod': '2026-09-01T00:00:00+03:30'}
        connector.crawled.clear()
        self.run_tick(connector)
        self.assertEqual(connector.crawled, ['tt0000001'])

    @override_settings(KARGADAN_SESSION_COOKIE='a=1')
    def test_a_lapsed_session_stops_the_tick_and_forgets_nothing(self):
        connector = _LaneConnector(self.entries(), {
            'tt0000002': ProviderImportError('sign in', code='kargadan_login_required'),
        })
        stats = self.run_tick(connector)
        self.assertEqual(stats['status'], 'session_expired')
        self.assertEqual(connector.crawled, ['tt0000002'], 'the tick stops at the first signed-out page')
        self.assertEqual(json.loads(Path(self.checkpoint).read_text())['seen'], {})

    @override_settings(KARGADAN_SESSION_COOKIE='a=1')
    def test_vip_locked_titles_are_parked_not_settled(self):
        connector = _LaneConnector(self.entries(), {
            'tt0000002': ProviderImportError('vip', code='kargadan_vip_required'),
        })
        stats = self.run_tick(connector)
        self.assertEqual(stats['vip_required'], 1)
        state = json.loads(Path(self.checkpoint).read_text())
        self.assertIn('movie:tt0000002', state['deferred'])
        self.assertNotIn('movie:tt0000002', state['seen'])
        connector.crawled.clear()
        self.run_tick(connector)
        self.assertNotIn('tt0000002', connector.crawled, 'parked for the retry window')

    @override_settings(KARGADAN_SESSION_COOKIE='a=1')
    def test_a_title_tmdb_cannot_resolve_is_settled(self):
        connector = _LaneConnector(self.entries()[:1], {
            'tt0000001': {'imdb_id': 'tt0000001', 'available_links': [{'url': f'{CDN}/a.mkv'}]},
        })
        stats = self.run_tick(connector)
        self.assertEqual(stats['skipped_tmdb_miss'], 1)
        self.assertIn('movie:tt0000001', json.loads(Path(self.checkpoint).read_text())['seen'])

    @override_settings(KARGADAN_SESSION_COOKIE='a=1')
    def test_per_tick_limits_hold(self):
        entries = [{'content_type': 'movie', 'imdb_id': f'tt00000{i:02d}', 'lastmod': f'2026-01-{i:02d}'}
                   for i in range(1, 11)]
        connector = _LaneConnector(entries)
        stats = self.run_tick(connector, movies_limit=3, series_limit=0, refresh_limit=0)
        self.assertEqual(len(connector.crawled), 3)
        self.assertEqual(stats['tried'], 3)

    def test_pending_order_and_filters(self):
        entries = self.entries()
        seen = {'movie:tt0000001': entries[0]['lastmod']}
        out = pending_entries(entries, seen=seen, deferred={}, retry_hours=24)
        self.assertEqual([e['imdb_id'] for e in out], ['tt0000002'])


class KargadanLaneTaskTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_waiting_for_a_session_still_counts_as_alive(self):
        """Otherwise the watchdog would restart a lane that is only waiting on an operator."""
        from apps.catalog.provider_import import tasks as import_tasks

        with patch(
            'apps.catalog.provider_import.kargadan_import.run_kargadan_missing_import',
            return_value={'status': 'session_required'},
        ):
            import_tasks.import_missing_kargadan_task.apply(throw=True).get()
        self.assertIsNotNone(import_tasks.discovery_silent_minutes('kargadan'))
        self.assertIsNone(cache.get(import_tasks.DISCOVERY_LANES['kargadan']['lock']))
