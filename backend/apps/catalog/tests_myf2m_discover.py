"""Tests for the listing-driven Film2Media (myf2m) missing-title importer.

The walk itself is what these cover: listing pagination and the stored cursor,
id-based dedupe, the ``no_links`` skip, the strict year window, cancellation and
series episode materialisation. Provider HTML parsing is covered by
``tests_myf2m_series_parser``, so ``parse_download_links`` is faked here.
"""

import json
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from apps.catalog.models import Movie, Series
from apps.catalog.provider_import.myf2m_discover import (
    _page_meta,
    _year_window,
    run_myf2m_missing_import,
)


class _Response:
    def __init__(self, text: str = '', status_code: int = 200):
        self.text = text
        self.status_code = status_code


class _Auth:
    ok = True
    message = ''


class _FakeConnector:
    """Serves canned listing/detail pages and records what was requested."""

    def __init__(self, pages: dict):
        self.pages = pages
        self.requested: list[str] = []
        self.closed = False

    def validate_credentials(self):
        return _Auth()

    def _request(self, method, path, **kwargs):
        self.requested.append(path)
        # An unknown path behaves like the live site's 404, not an exception.
        return self.pages.get(path) or _Response('', 404)

    def close(self):
        self.closed = True


class _FakeTmdb:
    """Minimal TMDB client: one search hit and one details payload per type."""

    def __init__(self, *, tmdb_id=901, year='2024', title='Sample', imdb_hit=None):
        self.tmdb_id = tmdb_id
        self.year = year
        self.title = title
        self.imdb_hit = imdb_hit
        self.searches: list[str] = []

    def resolve_imdb_to_tmdb(self, imdb_id, content_type='movie'):
        return self.imdb_hit

    def _hit(self, date_key):
        return {'results': [{
            'id': self.tmdb_id,
            'title': self.title,
            'name': self.title,
            date_key: f'{self.year}-05-01',
        }]}

    def search_movies(self, query, page=1):
        self.searches.append(query)
        return self._hit('release_date')

    def search_tv(self, query, page=1):
        self.searches.append(query)
        return self._hit('first_air_date')

    def movie_details(self, tmdb_id):
        return {'id': tmdb_id, 'title': self.title, 'release_date': f'{self.year}-05-01'}

    def tv_details(self, tmdb_id):
        return {'id': tmdb_id, 'name': self.title, 'first_air_date': f'{self.year}-05-01'}


def _fake_upsert_movie(details, **kwargs):
    obj = Movie.objects.create(
        title=f"فیلم {details['id']}",
        original_title=details.get('title') or '',
        slug=f"movie-{details['id']}",
        tmdb_id=details['id'],
        release_year=int(str(details.get('release_date') or '')[:4] or 0) or None,
        original_language='en',
    )
    return obj, True, False, False


def _fake_upsert_series(details, **kwargs):
    obj = Series.objects.create(
        title=f"سریال {details['id']}",
        original_title=details.get('name') or '',
        slug=f"series-{details['id']}",
        tmdb_id=details['id'],
        start_year=int(str(details.get('first_air_date') or '')[:4] or 0) or None,
        original_language='en',
    )
    return obj, True


def _publish(obj):
    obj.is_published = True
    obj.save(update_fields=['is_published', 'updated_at'])


MOVIE_LISTING = (
    '<a href="/12345/lucky-strike-2024/">اول</a>'
    '<a href="/67890/second-title-2024/">دوم</a>'
    '<a href="/genres/action/">اکشن</a>'
)
SERIES_LISTING = '<a href="/series/dark-matter-2024/">سریال</a>'
EMPTY_LISTING = '<html><body><a href="/genres/action/">اکشن</a></body></html>'
DETAIL_HTML = '<h1>دانلود فیلم شانس Lucky Strike 2024</h1><a href="https://www.imdb.com/title/tt1234567/">imdb</a>'
LINKS = [{'url': 'https://cdn.example/Lucky.Strike.2024.1080p.WEB-DL.mkv', 'quality': '1080p'}]


@override_settings(MYF2M_IMPORT_YEAR_START=0, MYF2M_IMPORT_YEAR_END=1970)
class Myf2mMissingImportTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.checkpoint = Path(self._tmp.name) / 'myf2m_checkpoint.json'
        self.tmdb = _FakeTmdb()
        self.links = list(LINKS)

    def _pages(self, extra=None):
        pages = {
            '/movies/': _Response(MOVIE_LISTING),
            '/movies/page/2/': _Response(EMPTY_LISTING),
            '/series/': _Response(SERIES_LISTING),
            '/series/page/2/': _Response(EMPTY_LISTING),
            '/12345/lucky-strike-2024/': _Response(DETAIL_HTML),
            '/67890/second-title-2024/': _Response(DETAIL_HTML),
            '/series/dark-matter-2024/': _Response(DETAIL_HTML),
        }
        pages.update(extra or {})
        return pages

    def _run(self, *, pages=None, episodes=2, **kwargs):
        """Run the importer with provider HTTP, TMDB and publish side effects faked."""
        self.connector = _FakeConnector(pages or self._pages())
        options = {
            'movies_limit': 1, 'series_limit': 0, 'delay': 0,
            'checkpoint_path': str(self.checkpoint),
        }
        options.update(kwargs)
        with ExitStack() as stack:
            def parse(html, *, page_path=''):
                return {'available_links': list(self.links), 'page_path': page_path}

            patches = {
                'apps.catalog.provider_import.registry.get_connector': lambda *a, **k: self.connector,
                'apps.catalog.tmdb.configured_tmdb_client': lambda *a, **k: self.tmdb,
                'apps.catalog.provider_import.providers.myf2m_parser.parse_download_links': parse,
                'apps.catalog.ingestion.upsert_tmdb_movie': _fake_upsert_movie,
                'apps.catalog.ingestion.upsert_tmdb_series': _fake_upsert_series,
                'apps.catalog.iranian.is_iranian_tmdb_details': lambda *a, **k: False,
                'apps.catalog.iranian.is_iranian_catalog_item': lambda *a, **k: False,
                'apps.catalog.top_catalog._publish_movie': _publish,
                'apps.catalog.top_catalog._publish_series': _publish,
                'apps.catalog.subtitle_extract.ensure_episodes_from_download_links': lambda *a, **k: episodes,
                'apps.catalog.tasks.enqueue_movie_softsub': lambda *a, **k: True,
                'apps.catalog.tasks.enqueue_series_softsub': lambda *a, **k: True,
            }
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))
            return run_myf2m_missing_import(**options)

    def _checkpoint_state(self):
        return json.loads(self.checkpoint.read_text(encoding='utf-8'))

    def test_creates_missing_movie_with_links_and_remembers_the_path(self):
        stats = self._run()
        self.assertEqual(stats['status'], 'ok')
        self.assertEqual(stats['movies_created'], 1)
        movie = Movie.objects.get(tmdb_id=self.tmdb.tmdb_id)
        self.assertTrue(movie.is_published)
        self.assertEqual(movie.imdb_id, 'tt1234567')
        self.assertEqual(len(movie.download_links), 1)
        # A movie with a playable link gets one, so the watch page is not empty.
        self.assertTrue(movie.video_url)
        state = self._checkpoint_state()
        self.assertIn('/12345/lucky-strike-2024/', state['done_movie_paths'])
        # Budget spent mid-page: the cursor stays put so the rest is picked up next tick.
        self.assertEqual(state['movie_page'], 1)
        self.assertNotIn('/67890/second-title-2024/', state['done_movie_paths'])

    def test_second_tick_skips_paths_already_walked(self):
        self._run()
        stats = self._run()
        self.assertEqual(stats['skipped_seen'], 1)
        self.assertEqual(Movie.objects.filter(tmdb_id=self.tmdb.tmdb_id).count(), 1)

    def test_existing_tmdb_id_is_skipped_without_creating_a_duplicate(self):
        Movie.objects.create(title='قبلاً هست', slug='already-here', tmdb_id=self.tmdb.tmdb_id)
        stats = self._run()
        self.assertEqual(stats['movies_created'], 0)
        # Nothing was kept, so the keep budget stays unspent and both listing
        # entries (plus the empty next page) are walked in the same tick.
        self.assertEqual(stats['skipped_existing'], 2)
        self.assertEqual(Movie.objects.count(), 1)

    def test_existing_imdb_id_is_skipped_before_tmdb_is_queried(self):
        Movie.objects.create(title='قبلاً هست', slug='already-imdb', imdb_id='tt1234567')
        stats = self._run()
        self.assertEqual(stats['skipped_existing'], 2)
        self.assertEqual(stats['movies_created'], 0)
        self.assertEqual(self.tmdb.searches, [])

    def test_page_without_download_links_is_skipped(self):
        self.links = []
        stats = self._run()
        self.assertEqual(stats['movies_created'], 0)
        self.assertGreaterEqual(stats['no_links'], 1)
        self.assertFalse(Movie.objects.exists())

    def test_strict_year_window_rejects_out_of_window_title(self):
        self.tmdb = _FakeTmdb(year='2019')
        stats = self._run(year_start=2024, year_end=2024, strict_year_window=True)
        self.assertEqual(stats['skipped_wrong_year'], 2)
        self.assertEqual(stats['movies_created'], 0)
        self.assertFalse(Movie.objects.exists())

    def test_end_of_listing_rewinds_the_cursor_to_page_one(self):
        self.checkpoint.write_text(json.dumps({'movie_page': 2}), encoding='utf-8')
        stats = self._run()
        self.assertEqual(stats['movies_created'], 0)
        self.assertEqual(stats['movie_page'], 1)
        self.assertEqual(self._checkpoint_state()['movie_page'], 1)

    def test_cancellation_stops_before_any_provider_request(self):
        stats = self._run(should_cancel=lambda: True)
        self.assertEqual(stats['status'], 'cancelled')
        self.assertEqual(stats['movies_created'], 0)
        self.assertEqual(self.connector.requested, [])

    def test_series_walk_materialises_episodes_and_queues_softsub(self):
        stats = self._run(movies_limit=0, series_limit=1, episodes=3)
        self.assertEqual(stats['series_created'], 1)
        self.assertEqual(stats['episodes_created'], 3)
        self.assertEqual(stats['softsub_queued'], 1)
        self.assertTrue(Series.objects.filter(tmdb_id=self.tmdb.tmdb_id).exists())
        self.assertFalse(Movie.objects.exists())

    def test_dry_run_counts_without_writing(self):
        stats = self._run(dry_run=True)
        self.assertEqual(stats['movies_created'], 1)
        self.assertFalse(Movie.objects.exists())

    def test_unreachable_provider_reports_instead_of_walking(self):
        connector = _FakeConnector(self._pages())
        connector.validate_credentials = lambda: type('Auth', (), {'ok': False, 'message': 'down'})()
        with patch('apps.catalog.provider_import.registry.get_connector', lambda *a, **k: connector), \
                patch('apps.catalog.tmdb.configured_tmdb_client', lambda *a, **k: self.tmdb):
            stats = run_myf2m_missing_import(checkpoint_path=str(self.checkpoint), delay=0)
        self.assertEqual(stats['status'], 'unreachable')
        self.assertEqual(connector.requested, [])


class Myf2mHelperTests(SimpleTestCase):
    @override_settings(MYF2M_IMPORT_YEAR_START=0, MYF2M_IMPORT_YEAR_END=1970)
    def test_year_window_defaults_follow_the_clock(self):
        from django.utils import timezone

        start, end = _year_window(year_start=None, year_end=None)
        self.assertEqual(start, timezone.now().year + 1)
        self.assertEqual(end, 1970)

    @override_settings(MYF2M_IMPORT_YEAR_START=2020, MYF2M_IMPORT_YEAR_END=2010)
    def test_configured_window_wins_over_the_clock(self):
        self.assertEqual(_year_window(year_start=None, year_end=None), (2020, 2010))

    def test_year_window_normalises_reversed_bounds(self):
        self.assertEqual(_year_window(year_start=2015, year_end=2022), (2022, 2015))

    def test_page_meta_reads_imdb_id_title_and_year(self):
        meta = _page_meta(DETAIL_HTML, 'lucky-strike-2024')
        self.assertEqual(meta['imdb_id'], 'tt1234567')
        self.assertEqual(meta['year'], 2024)
        self.assertIn('Lucky Strike', meta['title'])

    def test_page_meta_falls_back_to_the_slug(self):
        meta = _page_meta('<html></html>', 'dark-matter-2021')
        self.assertEqual(meta['imdb_id'], '')
        self.assertEqual(meta['year'], 2021)
        self.assertEqual(meta['title'], 'dark matter 2021')


class CatalogYearImportRequestTests(SimpleTestCase):
    """The admin request contract: both providers by default, any year window."""

    def _validated(self, payload):
        from apps.catalog.provider_import.serializers import CatalogYearImportRequestSerializer

        serializer = CatalogYearImportRequestSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def test_defaults_cover_both_providers_and_all_years(self):
        data = self._validated({})
        self.assertEqual(data['providers'], ['dornatv', 'myf2m'])
        self.assertIsNone(data['year_start'])
        self.assertIsNone(data['year_end'])
        self.assertEqual(data['myf2m_rounds'], 6)

    def test_legacy_year_field_becomes_a_single_year_window(self):
        data = self._validated({'year': 2026})
        self.assertEqual((data['year_start'], data['year_end']), (2026, 2026))
        self.assertNotIn('year', data)

    def test_one_bound_means_one_year(self):
        self.assertEqual(self._validated({'year_end': 2019})['year_start'], 2019)
        self.assertEqual(self._validated({'year_start': 2019})['year_end'], 2019)

    def test_reversed_bounds_are_normalised(self):
        data = self._validated({'year_start': 2024, 'year_end': 2018})
        self.assertEqual((data['year_start'], data['year_end']), (2018, 2024))

    def test_single_provider_is_accepted(self):
        self.assertEqual(self._validated({'providers': ['myf2m']})['providers'], ['myf2m'])

    def test_empty_provider_list_is_rejected(self):
        from rest_framework.exceptions import ValidationError

        with self.assertRaises(ValidationError) as caught:
            self._validated({'providers': []})
        self.assertIn('providers', caught.exception.detail)

    def test_unknown_provider_is_rejected(self):
        from rest_framework.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            self._validated({'providers': ['pirate-site']})
