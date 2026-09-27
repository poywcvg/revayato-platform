"""IMDb Top 250 shelves: the stored chart, the completion lane, the public API.

The promise is "all 250, complete". These tests pin the pieces that make it
checkable: the chart is stored even for titles we do not hold, a daily rank
shuffle never trips the uniqueness constraints, a position that cannot go live
says *why*, and nothing is ever published past the normal metadata gate.
"""

from __future__ import annotations

import gzip
import io
import itertools
from unittest import mock

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog import imdb_charts, top250
from apps.catalog.imdb_charts import ImdbChartTitle
from apps.catalog.models import ImdbChartEntry, Movie, Series

LINK = [{'url': 'https://cdn.example.test/Movies/Film.2020.1080p.mp4', 'quality': '1080p'}]


def _chart(kind: str, ids: list[str]) -> list[ImdbChartTitle]:
    title_type = 'movie' if kind == 'movie' else 'tvSeries'
    return [
        ImdbChartTitle(
            imdb_id=imdb_id, title_type=title_type, primary_title=f'Title {imdb_id}',
            original_title=f'Title {imdb_id}', start_year=2000, average_rating=9.0 - rank / 1000,
            num_votes=500_000 - rank, weighted_rating=9.0, rank=rank,
        )
        for rank, imdb_id in enumerate(ids, start=1)
    ]


def _ids(prefix: str, count: int = 250) -> list[str]:
    return [f'tt{prefix}{n:05d}' for n in range(count)]


class ChartModelTests(TestCase):
    def test_a_position_holds_one_title_and_a_title_one_position(self):
        ImdbChartEntry.objects.create(kind='movie', rank=1, imdb_id='tt0111161')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ImdbChartEntry.objects.create(kind='movie', rank=1, imdb_id='tt0068646')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ImdbChartEntry.objects.create(kind='movie', rank=2, imdb_id='tt0111161')
        # The two charts are independent.
        ImdbChartEntry.objects.create(kind='series', rank=1, imdb_id='tt0903747')


class RefreshChartTests(TestCase):
    def _refresh(self, movies, series, **kwargs):
        with mock.patch.object(imdb_charts, 'imdb_top_movies', return_value=movies), \
                mock.patch.object(imdb_charts, 'imdb_top_series', return_value=series), \
                mock.patch.object(imdb_charts, 'clear_imdb_chart_cache'):
            return top250.refresh_chart(force=True, **kwargs)

    def test_stores_every_position_even_for_titles_we_do_not_hold(self):
        stats = self._refresh(_chart('movie', _ids('1')), _chart('series', _ids('2')))
        self.assertEqual(stats['movie'], 250)
        self.assertEqual(ImdbChartEntry.objects.filter(kind='movie').count(), 250)
        self.assertEqual(ImdbChartEntry.objects.filter(kind='series').count(), 250)
        self.assertEqual(top250.coverage()['movie'], {'total': 250, 'in_catalog': 0, 'published': 0})

    def test_a_reshuffled_chart_does_not_collide_and_drops_departed_titles(self):
        movie_ids = _ids('1')
        self._refresh(_chart('movie', movie_ids), _chart('series', _ids('2')))
        # Next day: order reversed, the old #250 left the chart, a newcomer entered.
        shuffled = list(reversed(movie_ids[:-1])) + ['tt9999999']
        stats = self._refresh(_chart('movie', shuffled), _chart('series', _ids('2')))
        self.assertEqual(stats['dropped'], 1)
        self.assertFalse(ImdbChartEntry.objects.filter(imdb_id=movie_ids[-1]).exists())
        self.assertEqual(ImdbChartEntry.objects.get(kind='movie', imdb_id=movie_ids[-2]).rank, 1)
        self.assertEqual(ImdbChartEntry.objects.get(kind='movie', imdb_id='tt9999999').rank, 250)

    def test_restamps_rank_and_exact_rating_but_never_a_manual_score(self):
        ids = _ids('1')
        held = Movie.objects.create(title='رستگاری', original_title='Held', slug='held', imdb_id=ids[0], imdb_rating=5.0)
        manual = Movie.objects.create(
            title='دستی', original_title='Manual', slug='manual', imdb_id=ids[1],
            imdb_rating=7.7, imdb_rating_source='manual',
        )
        stale = Movie.objects.create(title='قدیمی', original_title='Stale', slug='stale', imdb_id='tt0000001', imdb_rank=3)
        self._refresh(_chart('movie', ids), _chart('series', _ids('2')))
        held.refresh_from_db(); manual.refresh_from_db(); stale.refresh_from_db()
        self.assertEqual(held.imdb_rank, 1)
        self.assertEqual(held.imdb_rating_source, 'imdb')
        self.assertGreater(float(held.imdb_rating), 8.9)
        self.assertEqual(manual.imdb_rank, 2)
        self.assertEqual(float(manual.imdb_rating), 7.7)
        self.assertIsNone(stale.imdb_rank)
        self.assertEqual(ImdbChartEntry.objects.get(kind='movie', rank=1).movie, held)

    def test_refuses_to_replace_a_good_chart_with_a_truncated_download(self):
        self._refresh(_chart('movie', _ids('1')), _chart('series', _ids('2')))
        with self.assertRaises(RuntimeError):
            self._refresh(_chart('movie', _ids('1', 40)), _chart('series', _ids('2')))
        self.assertEqual(ImdbChartEntry.objects.filter(kind='movie').count(), 250)

    def test_a_fresh_chart_is_not_downloaded_again(self):
        ImdbChartEntry.objects.create(kind='movie', rank=1, imdb_id='tt0111161')
        with mock.patch.object(imdb_charts, 'imdb_top_movies') as download:
            stats = top250.refresh_chart(max_age_hours=20)
        download.assert_not_called()
        self.assertEqual(stats['status'], 'fresh')


class LinkEntriesTests(TestCase):
    def test_a_title_imported_by_another_lane_joins_the_shelf(self):
        entry = ImdbChartEntry.objects.create(kind='series', rank=7, imdb_id='tt0903747')
        series = Series.objects.create(title='برکینگ بد', original_title='Breaking Bad', slug='bb', imdb_id='TT0903747')
        self.assertEqual(top250.link_entries(), {'relinked': 1})
        entry.refresh_from_db(); series.refresh_from_db()
        self.assertEqual(entry.series, series)
        self.assertEqual(series.imdb_rank, 7)
        self.assertEqual(top250.link_entries(), {'relinked': 0})


class CompleteChartTests(TestCase):
    def setUp(self):
        patches = {
            'crawl': mock.patch('apps.catalog.top_catalog._crawl_movie_links'),
            'publish': mock.patch('apps.catalog.top_catalog._publish_movie'),
            'blockers': mock.patch('apps.catalog.completeness.publish_blockers', return_value=[]),
            'client': mock.patch('apps.catalog.tmdb.configured_tmdb_client'),
        }
        self.mocks = {name: patcher.start() for name, patcher in patches.items()}
        for patcher in patches.values():
            self.addCleanup(patcher.stop)
        self.tmdb = self.mocks['client'].return_value

    def _run(self, **kwargs):
        return top250.complete_chart(limit=10, delay=0, kinds=('movie',), **kwargs)

    def _entry(self, rank, imdb_id, movie=None):
        return ImdbChartEntry.objects.create(kind='movie', rank=rank, imdb_id=imdb_id, movie=movie)

    def test_a_title_tmdb_cannot_resolve_is_recorded_not_dropped(self):
        entry = self._entry(1, 'tt0000009')
        self.tmdb.resolve_imdb_to_tmdb.return_value = None
        stats = self._run()
        entry.refresh_from_db()
        self.assertEqual(entry.gap_reason, top250.GAP_TMDB_MISS)
        self.assertEqual(entry.attempts, 1)
        self.assertEqual(stats['gaps'], {top250.GAP_TMDB_MISS: 1})

    def test_no_provider_source_is_its_own_gap(self):
        movie = Movie.objects.create(title='فیلم', original_title='Film', slug='film', imdb_id='tt0000010')
        entry = self._entry(1, 'tt0000010', movie)
        stats = self._run()
        entry.refresh_from_db()
        self.mocks['crawl'].assert_called_once()
        self.assertEqual(stats['crawled'], 1)
        self.assertEqual(entry.gap_reason, top250.GAP_NO_SOURCE)
        self.mocks['publish'].assert_not_called()
        self.assertTrue(Movie.objects.filter(pk=movie.pk).exists(), 'a sourceless title must never be deleted')

    def test_the_normal_metadata_gate_still_applies(self):
        movie = Movie.objects.create(title='Film', original_title='Film', slug='film', imdb_id='tt0000011', download_links=LINK)
        entry = self._entry(1, 'tt0000011', movie)
        self.mocks['blockers'].return_value = ['missing_persian_title']
        self._run()
        entry.refresh_from_db()
        self.assertEqual(entry.gap_reason, 'metadata:missing_persian_title')
        self.mocks['publish'].assert_not_called()

    def test_a_blocked_title_gets_one_tmdb_refresh_before_being_judged(self):
        movie = Movie.objects.create(
            title='Film', original_title='Film', slug='film', imdb_id='tt0000012', tmdb_id=12, download_links=LINK,
        )
        entry = self._entry(1, 'tt0000012', movie)
        self.mocks['blockers'].side_effect = [['missing_persian_title'], []]
        self.mocks['publish'].side_effect = lambda obj: Movie.objects.filter(pk=obj.pk).update(is_published=True)
        with mock.patch.object(top250, '_refresh_from_tmdb') as refresh:
            stats = self._run()
        refresh.assert_called_once()
        entry.refresh_from_db()
        self.assertEqual(entry.gap_reason, '')
        self.assertEqual(stats['published'], 1)

    def test_a_ready_title_is_published_and_leaves_the_queue(self):
        movie = Movie.objects.create(title='فیلم', original_title='Film', slug='film', imdb_id='tt0000013', download_links=LINK)
        self._entry(1, 'tt0000013', movie)
        self.mocks['publish'].side_effect = lambda obj: Movie.objects.filter(pk=obj.pk).update(is_published=True)
        stats = self._run()
        self.assertEqual(stats['published'], 1)
        self.assertEqual(stats['coverage']['movie']['published'], 1)
        self.assertEqual(self._run(retry_hours=0)['attempted'], 0)

    def test_a_recent_failure_waits_its_turn_so_the_lane_rotates(self):
        self._entry(1, 'tt0000014')
        ImdbChartEntry.objects.filter(rank=1).update(attempted_at=timezone.now())
        self._entry(2, 'tt0000015')
        self.tmdb.resolve_imdb_to_tmdb.return_value = None
        stats = self._run(retry_hours=24)
        self.assertEqual(stats['attempted'], 1)
        self.tmdb.resolve_imdb_to_tmdb.assert_called_once_with('tt0000015', content_type='movie')

    def test_one_failing_title_does_not_end_the_pass(self):
        self._entry(1, 'tt0000016')
        self._entry(2, 'tt0000017')
        self.tmdb.resolve_imdb_to_tmdb.side_effect = [RuntimeError('boom'), None]
        stats = self._run()
        self.assertEqual(stats['attempted'], 2)
        self.assertEqual(ImdbChartEntry.objects.get(rank=1).gap_reason, top250.GAP_IMPORT_FAILED)
        self.assertEqual(ImdbChartEntry.objects.get(rank=2).gap_reason, top250.GAP_TMDB_MISS)


    def test_a_position_is_claimed_before_its_crawl_starts(self):
        """A crawl killed mid-title must still rotate that title to the back."""
        movie = Movie.objects.create(title='فیلم', original_title='Film', slug='film', imdb_id='tt0000018')
        entry = self._entry(1, 'tt0000018', movie)
        seen = {}

        def crawl(obj, **kwargs):
            row = ImdbChartEntry.objects.get(pk=entry.pk)
            seen.update(attempted_at=row.attempted_at, attempts=row.attempts)

        self.mocks['crawl'].side_effect = crawl
        self._run()
        self.assertIsNotNone(seen['attempted_at'])
        self.assertEqual(seen['attempts'], 1)
        entry.refresh_from_db()
        self.assertEqual(entry.attempts, 1, 'the claim and the result must not count twice')

    def test_a_killed_crawl_is_recorded_and_the_next_pass_moves_on(self):
        from celery.exceptions import SoftTimeLimitExceeded

        first = Movie.objects.create(title='فیلم', original_title='Film', slug='film-a', imdb_id='tt0000019')
        second = Movie.objects.create(title='فیلم ب', original_title='Film B', slug='film-b', imdb_id='tt0000020')
        self._entry(1, 'tt0000019', first)
        self._entry(2, 'tt0000020', second)
        self.mocks['crawl'].side_effect = SoftTimeLimitExceeded()
        with self.assertRaises(SoftTimeLimitExceeded):
            self._run()
        stalled = ImdbChartEntry.objects.get(rank=1)
        self.assertEqual(stalled.gap_reason, top250.GAP_CRAWL_TIMEOUT)
        self.assertIsNotNone(stalled.attempted_at)

        self.mocks['crawl'].side_effect = None
        self.mocks['crawl'].reset_mock()
        stats = self._run(retry_hours=24)
        self.assertEqual(stats['attempted'], 1)
        self.assertEqual(self.mocks['crawl'].call_args.args[0].pk, second.pk)

    def test_the_budget_ends_the_pass_between_positions(self):
        self._entry(1, 'tt0000021')
        self._entry(2, 'tt0000022')
        self.tmdb.resolve_imdb_to_tmdb.return_value = None
        clock = itertools.chain([0.0, 0.0], itertools.repeat(100.0))
        fake_time = mock.Mock(monotonic=lambda: next(clock))
        with mock.patch.object(top250, 'time', fake_time):
            stats = self._run(budget_seconds=50)
        self.assertEqual(stats['status'], 'budget')
        self.assertEqual(stats['attempted'], 1)
        self.assertIsNone(ImdbChartEntry.objects.get(rank=2).attempted_at, 'an unstarted position is not claimed')


class Top250ApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        live = Movie.objects.create(
            title='رستگاری در شاوشنک', original_title='The Shawshank Redemption', slug='shawshank',
            imdb_id='tt0111161', is_published=True, download_links=LINK,
        )
        draft = Movie.objects.create(title='پدرخوانده', original_title='The Godfather', slug='godfather', imdb_id='tt0068646')
        ImdbChartEntry.objects.create(kind='movie', rank=1, imdb_id='tt0111161', movie=live, primary_title='The Shawshank Redemption')
        ImdbChartEntry.objects.create(kind='movie', rank=2, imdb_id='tt0068646', movie=draft, primary_title='The Godfather', start_year=1972)
        ImdbChartEntry.objects.create(kind='movie', rank=3, imdb_id='tt0468569', primary_title='The Dark Knight')

    def test_returns_every_position_in_chart_order_with_honest_availability(self):
        body = self.client.get('/api/catalog/top250/?type=movie').json()
        self.assertEqual(body['count'], 3)
        self.assertEqual([row['imdb_rank'] for row in body['results']], [1, 2, 3])
        self.assertEqual([row['available'] for row in body['results']], [True, False, False])
        self.assertEqual(body['results'][0]['slug'], 'shawshank')
        # An unpublished draft never leaks its slug or catalog payload.
        self.assertIsNone(body['results'][1]['slug'])
        self.assertEqual(body['results'][1]['title'], 'The Godfather')
        self.assertEqual(body['coverage'], {'total': 3, 'in_catalog': 2, 'published': 1})

    def test_available_only_is_what_rails_use(self):
        body = self.client.get('/api/catalog/top250/?type=movie&available=1').json()
        self.assertEqual(body['count'], 1)
        self.assertEqual(body['results'][0]['imdb_rank'], 1)

    def test_paginates(self):
        body = self.client.get('/api/catalog/top250/?type=movie&limit=2').json()
        self.assertEqual(len(body['results']), 2)
        self.assertIn('offset=2', body['next'])


class ChartStreamTests(TestCase):
    """The chart build must stay inside the crawler's 768 MB memory limit."""

    @staticmethod
    def _gz(rows: list[str]) -> io.BytesIO:
        return io.BytesIO(gzip.compress(('\n'.join(rows) + '\n').encode('utf-8')))

    def test_titles_under_the_vote_floor_are_dropped_while_streaming(self):
        floor = imdb_charts.CHART_MIN_VOTES
        ratings = self._gz([
            'tconst\taverageRating\tnumVotes',
            f'tt0000001\t9.0\t{floor + 10}',
            f'tt0000002\t9.9\t{floor - 1}',
        ])
        basics = self._gz([
            'tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\tstartYear',
            'tt0000001\tmovie\tKept\tKept\t0\t1990',
            'tt0000002\tmovie\tUnder floor\tUnder floor\t0\t1991',
        ])
        responses = {imdb_charts.IMDB_RATINGS_URL: ratings, imdb_charts.IMDB_BASICS_URL: basics}

        def fake_urlopen(request, timeout=None):
            return responses[request.full_url]

        imdb_charts.clear_imdb_chart_cache()
        self.addCleanup(imdb_charts.clear_imdb_chart_cache)
        with mock.patch.object(imdb_charts.urllib.request, 'urlopen', side_effect=fake_urlopen):
            chart = imdb_charts.imdb_top_movies(limit=250)
        self.assertEqual([row.imdb_id for row in chart], ['tt0000001'])
