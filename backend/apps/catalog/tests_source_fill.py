"""Every title draws on every provider that has it (provider_import/source_fill.py),
and the Dornatv walk no longer throws away, re-crawls or starves on what it finds."""

from __future__ import annotations

import tempfile
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.catalog.models import Movie, Series
from apps.catalog.provider_import import source_fill
from apps.catalog.provider_import.dornatv_import import _DonePaths, run_dornatv_missing_import
from apps.catalog.provider_import.exceptions import ProviderImportError

MYF2M = {'url': 'https://dl3.abrtech.xyz/film/Dune.2021.1080p.mkv', 'quality': '1080p', 'source': 'myf2m'}
# dlyar.top itself is on the dead-host list, so stored rows use a live host + source.
DORNA = {'url': 'https://dl.dornacdn.example/Dune.2021.720p.mkv?sig=1', 'quality': '720p', 'source': 'dornatv'}
KARGADAN = {'url': 'https://dl.kargadanmovie.com/Dune.2021.480p.mkv', 'quality': '480p'}
WEEK = 7 * 24 * 60 * 60
DAY = 24 * 60 * 60


def _asked(obj, provider):
    return cache.get(source_fill._asked_key(obj._meta.label_lower, obj.pk, provider))


class _Clean(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)


class LinkProviderTests(TestCase):
    def test_source_field_wins(self):
        self.assertEqual(source_fill.link_provider({'url': 'https://x.dlyar.top/a', 'source': 'kargadan'}), 'kargadan')

    def test_untagged_rows_are_named_by_host(self):
        self.assertEqual(source_fill.link_provider({'url': 'https://s1.dlyar.top/a.mkv'}), 'dornatv')
        self.assertEqual(source_fill.link_provider(KARGADAN), 'kargadan')
        self.assertEqual(source_fill.link_provider({'url': 'https://dl3.abrtech.xyz/a.mkv'}), 'myf2m')
        self.assertEqual(source_fill.link_provider({'url': ''}), '')

    def test_present_set(self):
        self.assertEqual(source_fill.providers_present([MYF2M, DORNA, {'url': ''}]), {'myf2m', 'dornatv'})


class MissingForTests(_Clean):
    def test_only_absent_and_not_recently_asked_providers(self):
        movie = Movie.objects.create(title='تلماسه', slug='dune', download_links=[MYF2M])
        wanted = ['myf2m', 'dornatv', 'kargadan']
        self.assertEqual(source_fill.missing_for(movie, wanted), ['dornatv', 'kargadan'])
        source_fill._remember(movie, ['dornatv'], WEEK)
        self.assertEqual(source_fill.missing_for(movie, wanted), ['kargadan'])

    def test_a_title_with_every_provider_needs_nothing(self):
        movie = Movie.objects.create(title='تلماسه', slug='dune', download_links=[MYF2M, DORNA, KARGADAN])
        self.assertEqual(source_fill.missing_for(movie, ['myf2m', 'dornatv', 'kargadan']), [])


class FillTitleTests(_Clean):
    def setUp(self):
        super().setUp()
        self.movie = Movie.objects.create(title='تلماسه', slug='dune', download_links=[MYF2M])

    def _crawl(self, outcomes):
        """Patch the per-provider crawl: ``outcomes`` maps slug → links to add, or an exception."""
        calls = []

        def crawl(slug, obj, *, replace, queue_softsub):
            calls.append((slug, replace, queue_softsub))
            outcome = outcomes[slug]
            if isinstance(outcome, Exception):
                raise outcome
            type(obj).objects.filter(pk=obj.pk).update(download_links=[*obj.download_links, *outcome])
            return {'imported_count': len(outcome)}

        return calls, mock.patch(
            'apps.catalog.provider_import.multi_provider_crawl._crawl_one_movie', side_effect=crawl,
        )

    def test_merges_found_links_and_keeps_existing(self):
        calls, patcher = self._crawl({'dornatv': [DORNA]})
        with patcher, mock.patch('apps.catalog.tasks.enqueue_movie_softsub') as softsub:
            verdicts = source_fill.fill_title(self.movie, ['dornatv'])
        self.assertEqual(verdicts, {'dornatv': 'filled'})
        # Merge only, and the soft-sub extraction is left to one queued job.
        self.assertEqual(calls, [('dornatv', False, False)])
        self.movie.refresh_from_db()
        self.assertEqual(source_fill.providers_present(self.movie.download_links), {'myf2m', 'dornatv'})
        softsub.assert_called_once_with(self.movie.pk, force=False)
        self.assertTrue(_asked(self.movie, 'dornatv'))

    def test_not_found_is_remembered_for_a_week_and_transient_for_a_day(self):
        _calls, patcher = self._crawl({
            'dornatv': ProviderImportError('none', code='dornatv_page_required'),
            'kargadan': ProviderImportError('down', code='kargadan_unreachable'),
        })
        with patcher, mock.patch.object(source_fill.cache, 'set_many', wraps=cache.set_many) as set_many:
            verdicts = source_fill.fill_title(self.movie, ['dornatv', 'kargadan'])
        self.assertEqual(verdicts, {'dornatv': 'not_found', 'kargadan': 'error'})
        ttls = {next(iter(args[0])).rsplit(':', 1)[1]: args[1] for args, _kw in set_many.call_args_list if args[0]}
        self.assertEqual(ttls, {'dornatv': WEEK, 'kargadan': DAY})

    def test_one_provider_crashing_does_not_stop_the_next(self):
        _calls, patcher = self._crawl({'dornatv': RuntimeError('boom'), 'kargadan': [KARGADAN]})
        with patcher, mock.patch('apps.catalog.tasks.enqueue_movie_softsub'):
            verdicts = source_fill.fill_title(self.movie, ['dornatv', 'kargadan'])
        self.assertEqual(verdicts, {'dornatv': 'error', 'kargadan': 'filled'})


class RunSourceFillTests(_Clean):
    def _run(self, *, blocker='', hot=None, **kw):
        order = []

        def fill(obj, providers):
            order.append((obj.pk, tuple(providers)))
            return {p: 'not_found' for p in providers}

        with mock.patch(
            'apps.catalog.provider_import.providers.kargadan.session_blocker', return_value=blocker,
        ), mock.patch('apps.catalog.link_sizes._hot_ids', return_value=hot or {}), \
                mock.patch.object(source_fill, 'fill_title', side_effect=fill):
            result = source_fill.run_source_fill(budget_seconds=60, **kw)
        return result, order

    def test_kargadan_is_not_asked_or_remembered_without_a_session(self):
        movie = Movie.objects.create(title='تلماسه', slug='dune', is_published=True, download_links=[MYF2M])
        result, order = self._run(blocker='kargadan_session_missing')
        self.assertEqual(order, [(movie.pk, ('dornatv',))])
        self.assertEqual(result['kargadan'], 'kargadan_session_missing')
        self.assertIsNone(_asked(movie, 'kargadan'))

    def test_hot_titles_come_first_and_complete_titles_are_skipped(self):
        popular = Movie.objects.create(title='الف', slug='a', is_published=True, popularity=900,
                                       download_links=[MYF2M])
        hot = Movie.objects.create(title='ب', slug='b', is_published=True, popularity=1, tmdb_id=77,
                                   download_links=[DORNA])
        Movie.objects.create(title='پ', slug='c', is_published=True, popularity=500,
                             download_links=[MYF2M, DORNA])
        Movie.objects.create(title='ت', slug='d', is_published=False, download_links=[])
        series = Series.objects.create(title='س', slug='s', is_published=True, download_links=[])
        result, order = self._run(blocker='kargadan_session_missing', hot={Movie: [77]})
        self.assertEqual([pk for pk, _ in order][:2], [hot.pk, popular.pk])
        self.assertIn((series.pk, ('myf2m', 'dornatv')), order)
        self.assertEqual(result['complete'], 1)
        self.assertEqual(result['titles'], 3)

    def test_the_title_cap_bounds_a_tick(self):
        for i in range(5):
            Movie.objects.create(title=f'ف{i}', slug=f'f{i}', is_published=True, download_links=[])
        result, order = self._run(blocker='x', titles=2)
        self.assertEqual(len(order), 2)
        self.assertEqual(result['titles'], 2)


class DonePathsTests(TestCase):
    def test_cap_keeps_the_most_recent_not_the_alphabetically_last(self):
        done = _DonePaths.fromkeys(['/zzz-old/', '/yyy-old/'])
        done.add('/aaa-new/')
        done.add('/bbb-new/')
        self.assertEqual(done.recent(2), ['/aaa-new/', '/bbb-new/'])
        self.assertIn('/zzz-old/', done)


class _FakeDornatv:
    def __init__(self, rows=(), crawled=None):
        self.rows = list(rows)
        self.crawled = crawled or {}

    def validate_credentials(self):
        return SimpleNamespace(ok=True, message='')

    def _rest_list_by_category(self, *, page=1, **_kw):
        return (self.rows if page == 1 else []), {'total_pages': 1}

    def resolve_release_term_id(self, year):
        return None

    def crawl_download_links(self, page_path, *, content_type='movie'):
        return dict(self.crawled)

    def close(self):
        pass


@override_settings(DORNATV_REFRESH_PER_TICK=1, DORNATV_REFRESH_LINK_MAX_AGE_SECONDS=300)
class DornatvWalkTests(_Clean):
    def _run(self, connector, **patches):
        checkpoint = Path(tempfile.mkdtemp()) / 'cp.json'
        with mock.patch('apps.catalog.provider_import.registry.get_connector', return_value=connector), \
                mock.patch('apps.catalog.tmdb.configured_tmdb_client', return_value=mock.Mock()), \
                mock.patch('apps.catalog.provider_import.dornatv_sync.ensure_dornatv_provider'):
            with ExitStack() as stack:
                for target, value in patches.items():
                    stack.enter_context(mock.patch(target, **value))
                return run_dornatv_missing_import(
                    movies_limit=0, series_limit=0, checkpoint_path=str(checkpoint), budget_seconds=60,
                )

    def _stale(self, n):
        rows = []
        for i in range(n):
            movie = Movie.objects.create(
                title=f'ف{i}', slug=f'f{i}', is_published=True,
                download_links=[{**DORNA, 'url': f'https://dl.dornacdn.example/f{i}.mkv',
                                 'page_path': f'/f{i}/'}],
            )
            rows.append(movie)
            # Oldest first, so the refresh order is deterministic.
            Movie.objects.filter(pk=movie.pk).update(
                updated_at=timezone.now() - timezone.timedelta(days=3, hours=-i),
            )
        return rows

    def test_failing_refreshes_cool_down_instead_of_holding_every_slot(self):
        broken = self._stale(3)
        refreshed = []

        def crawl(*, movie, provider_item_id, replace, queue_softsub_extract):
            if movie.pk in {m.pk for m in broken[:2]}:
                raise ProviderImportError('page gone', code='dornatv_page_required')
            refreshed.append(movie.pk)
            return {'code': 'ok'}

        target = 'apps.catalog.provider_import.dornatv_sync.crawl_dornatv_downloads_for_movie'
        first = self._run(_FakeDornatv(), **{target: {'side_effect': crawl}})
        # The two stalest rows fail and use up a 1-slot tick's attempt allowance...
        self.assertEqual(first['refresh_cooled'], 2)
        self.assertEqual(refreshed, [])
        second = self._run(_FakeDornatv(), **{target: {'side_effect': crawl}})
        # ...and next tick they sit out, so the healthy row finally refreshes.
        self.assertNotIn('refresh_cooled', second)
        self.assertEqual(refreshed, [broken[2].pk])

    def test_existing_title_gains_the_dornatv_links_it_lacked(self):
        movie = Movie.objects.create(
            title='تلماسه', original_title='Dune', slug='dune', release_year=2021,
            imdb_id='tt1160419', is_published=True, download_links=[MYF2M],
        )
        row = {'id': 1, 'modified': '2026-09-27T00:00:00'}
        parsed = {
            'content_type': 'movie', 'provider_item_id': '/dune-2021/', 'imdb_id': 'tt1160419',
            'title_fa': 'تلماسه', 'title_en': 'Dune', 'year': 2021,
        }
        crawled = {
            'title_fa': 'تلماسه', 'title_en': 'Dune', 'year': 2021, 'imdb_id': 'tt1160419',
            'page_path': '/dune-2021/', 'available_links': [DORNA],
        }
        with mock.patch('apps.catalog.provider_import.link_apply.apply_provider_download_links') as apply:
            result = self._run(
                _FakeDornatv(rows=[row], crawled=crawled),
                **{'apps.catalog.provider_import.providers.dornatv_parser.parse_wp_rest_item':
                   {'return_value': parsed}},
            )
        self.assertEqual(result['merged_existing'], 1)
        (obj, links), kwargs = apply.call_args
        self.assertEqual(obj.pk, movie.pk)
        self.assertFalse(kwargs['replace'])
        self.assertEqual(links[0]['source'], 'dornatv')
        self.assertEqual(links[0]['page_path'], '/dune-2021/')

    def test_existing_title_that_already_has_dornatv_is_not_crawled(self):
        Movie.objects.create(
            title='تلماسه', original_title='Dune', slug='dune', release_year=2021,
            imdb_id='tt1160419', is_published=True, download_links=[MYF2M, DORNA],
        )
        parsed = {'content_type': 'movie', 'provider_item_id': '/dune-2021/', 'imdb_id': 'tt1160419'}
        connector = _FakeDornatv(rows=[{'id': 1}])
        connector.crawl_download_links = mock.Mock()
        result = self._run(
            connector,
            **{'apps.catalog.provider_import.providers.dornatv_parser.parse_wp_rest_item':
               {'return_value': parsed}},
        )
        connector.crawl_download_links.assert_not_called()
        self.assertEqual(result['merged_existing'], 0)
        self.assertGreaterEqual(result['skipped_existing'], 1)
