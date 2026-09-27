"""Hot titles: the chart, the completion lane and the hot-first order.

The promise is "what people are watching this week comes first, everywhere".
These tests pin what would quietly break it: a title in several feeds must
outrank a one-feed title, unreleased/Iranian/talk-show rows must never cost a
crawl, a TMDB outage must not empty the chart, a claimed title must not be
crawled twice, and every queue must put hot titles before stale popularity.
"""

from __future__ import annotations

import itertools
from datetime import date, timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.catalog import draft_sources, hot_titles
from apps.catalog.models import Movie, PlaybackSourceGap, Series

LINK = [{'url': 'https://cdn.example.test/Movies/Film.2026.1080p.mp4', 'quality': '1080p'}]


class FakeTmdb:
    """Feeds keyed ``kind:label``; a key in ``fail`` raises when read."""

    def __init__(self, feeds, fail=()):
        self.feeds = feeds
        self.fail = set(fail)

    def _feed(self, key):
        if key in self.fail:
            raise RuntimeError(f'{key} down')
        yield from self.feeds.get(key, [])

    def trending_movies(self, *, window, max_pages):
        return self._feed(f'movie:trending_{window}')

    def now_playing_movies(self, *, max_pages):
        return self._feed('movie:now_playing')

    def discover_movies(self, **_):
        return self._feed('movie:new_releases')

    def trending_tv(self, *, window, max_pages):
        return self._feed(f'series:trending_{window}')

    def discover_tv(self, **_):
        return self._feed('series:new_releases')


TODAY = date(2026, 9, 27)


def _m(tmdb_id, released='2026-09-01', **extra):
    return {'id': tmdb_id, 'title': f'Film {tmdb_id}', 'original_title': f'Film {tmdb_id}',
            'release_date': released, 'original_language': 'en', **extra}


def _tv(tmdb_id, aired='2026-08-01', **extra):
    return {'id': tmdb_id, 'name': f'Show {tmdb_id}', 'original_name': f'Show {tmdb_id}',
            'first_air_date': aired, 'original_language': 'en', **extra}


def _chart(movies=(), series=()):
    return {
        'built_at': timezone.now().isoformat(),
        'movie': [{'tmdb_id': t, 'rank': r, 'score': 10 - r, 'released': '2026-09-01'}
                  for r, t in enumerate(movies, start=1)],
        'series': [{'tmdb_id': t, 'rank': r, 'score': 10 - r, 'released': '2026-08-01'}
                   for r, t in enumerate(series, start=1)],
    }


class BuildChartTests(TestCase):
    def test_a_title_in_several_feeds_outranks_a_single_feed_leader(self):
        client = FakeTmdb({
            'movie:trending_day': [_m(1), _m(2)],
            'movie:trending_week': [_m(2)],
            'movie:now_playing': [_m(2)],
        })
        chart = hot_titles.build_hot_chart(client, today=TODAY)
        self.assertEqual([row['tmdb_id'] for row in chart['movie']], [2, 1])
        self.assertEqual(chart['movie'][0]['rank'], 1)
        self.assertEqual(set(chart['movie'][0]['signals']), {'trending_day', 'trending_week', 'now_playing'})

    def test_newer_release_wins_a_tie(self):
        client = FakeTmdb({
            'movie:trending_day': [_m(1, released='2024-01-01')],
            'movie:trending_week': [_m(2, released='2026-09-20')],
        })
        # By feed alone 1 leads (today's #1 beats this week's #1). A release from
        # last week still goes first: the newest titles are the point.
        chart = hot_titles.build_hot_chart(client, today=TODAY)
        ranks = {row['tmdb_id']: row['rank'] for row in chart['movie']}
        self.assertEqual(ranks[2], 1)

    def test_rows_that_can_never_be_watchable_are_left_out(self):
        client = FakeTmdb({
            'movie:trending_day': [
                _m(1, released='2026-12-25'),          # not out yet
                _m(2, original_language='fa'),         # Iranian
                _m(3, released=''),                    # no date at all
                _m(4, adult=True),
                _m(5),
            ],
            'series:trending_day': [_tv(10, genre_ids=[10767]), _tv(11, genre_ids=[18])],
        })
        chart = hot_titles.build_hot_chart(client, today=TODAY)
        self.assertEqual([row['tmdb_id'] for row in chart['movie']], [5])
        self.assertEqual([row['tmdb_id'] for row in chart['series']], [11])

    def test_a_dead_feed_is_recorded_and_the_others_still_rank(self):
        client = FakeTmdb({'movie:trending_week': [_m(7)]}, fail={'movie:trending_day'})
        chart = hot_titles.build_hot_chart(client, today=TODAY)
        self.assertEqual(chart['feeds']['movie:trending_day'], 'error')
        self.assertEqual([row['tmdb_id'] for row in chart['movie']], [7])


class RefreshChartTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_a_young_chart_is_not_rebuilt(self):
        cache.set(hot_titles.CHART_CACHE_KEY, _chart(movies=[1]))
        with mock.patch.object(hot_titles, 'build_hot_chart') as build:
            self.assertEqual(hot_titles.refresh_hot_chart(max_age_hours=2)['status'], 'fresh')
        build.assert_not_called()

    def test_an_outage_keeps_the_previous_ranking(self):
        cache.set(hot_titles.CHART_CACHE_KEY, _chart(movies=[1, 2], series=[9]))
        dead = FakeTmdb({}, fail={
            'movie:trending_day', 'movie:trending_week', 'movie:now_playing', 'movie:new_releases',
            'series:trending_day', 'series:trending_week', 'series:new_releases',
        })
        result = hot_titles.refresh_hot_chart(force=True, client=dead)
        self.assertEqual(result['status'], 'empty')
        self.assertEqual(hot_titles.hot_rank_map('movie'), {1: 1, 2: 2})

    def test_one_dead_kind_keeps_its_previous_half(self):
        cache.set(hot_titles.CHART_CACHE_KEY, _chart(movies=[1], series=[9]))
        client = FakeTmdb({'movie:trending_day': [_m(5)]}, fail={
            'series:trending_day', 'series:trending_week', 'series:new_releases',
        })
        self.assertEqual(hot_titles.refresh_hot_chart(force=True, client=client)['status'], 'refreshed')
        self.assertEqual(hot_titles.hot_rank_map('movie'), {5: 1})
        self.assertEqual(hot_titles.hot_rank_map('series'), {9: 1})


class HotOrderTests(TestCase):
    def setUp(self):
        cache.clear()
        today = timezone.localdate()
        self.old_hit = Movie.objects.create(title='قدیمی', original_title='Old Hit', slug='old-hit',
                                            tmdb_id=1, popularity=900, release_date=today - timedelta(days=3000))
        self.new = Movie.objects.create(title='تازه', original_title='New', slug='new', tmdb_id=2,
                                        popularity=5, release_date=today - timedelta(days=10))
        self.upcoming = Movie.objects.create(title='آینده', original_title='Upcoming', slug='upcoming',
                                             tmdb_id=3, popularity=50, release_date=today + timedelta(days=60))
        self.trending = Movie.objects.create(title='ترند', original_title='Trending', slug='trending',
                                             tmdb_id=4, popularity=1, release_date=today - timedelta(days=400))

    def _order(self):
        return list(hot_titles.hot_order(Movie.objects.all()).values_list('slug', flat=True))

    def test_without_a_chart_newest_released_comes_first(self):
        self.assertEqual(self._order(), ['new', 'trending', 'old-hit', 'upcoming'])

    def test_chart_rank_beats_everything(self):
        cache.set(hot_titles.CHART_CACHE_KEY, _chart(movies=[4]))
        self.assertEqual(self._order()[0], 'trending')

    def test_series_sort_by_their_latest_season(self):
        Series.objects.create(title='الف', original_title='Old Show', slug='old-show', tmdb_id=20,
                              start_year=2010, end_year=None, popularity=500)
        Series.objects.create(title='ب', original_title='Back Again', slug='back', tmdb_id=21,
                              start_year=2012, end_year=timezone.localdate().year, popularity=1)
        order = list(hot_titles.hot_order(Series.objects.all()).values_list('slug', flat=True))
        self.assertEqual(order, ['back', 'old-show'])

    def test_hot_head_is_capped_rested_and_keeps_the_tail_order(self):
        cache.set(hot_titles.CHART_CACHE_KEY, _chart(movies=[4]))
        rows = [self.old_hit, self.upcoming, self.new, self.trending]
        first = hot_titles.hot_head(rows, 'movie', limit=2)
        self.assertEqual([m.slug for m in first], ['trending', 'old-hit', 'upcoming', 'new'])
        # Both head titles now rest; the next round starts on the stale rotation.
        second = hot_titles.hot_head(rows, 'movie', limit=4)
        self.assertEqual([m.slug for m in second][:1], ['new'])
        self.assertEqual([m.slug for m in second][1:], ['old-hit', 'upcoming', 'trending'])


class CompleteHotTitlesTests(TestCase):
    def setUp(self):
        cache.clear()
        self.patches = {
            'crawl': mock.patch('apps.catalog.top_catalog._crawl_movie_links'),
            'publish': mock.patch('apps.catalog.top_catalog._publish_movie'),
            'blockers': mock.patch('apps.catalog.completeness.publish_blockers', return_value=[]),
            'client': mock.patch('apps.catalog.tmdb.configured_tmdb_client'),
        }
        self.mocks = {name: p.start() for name, p in self.patches.items()}
        for p in self.patches.values():
            self.addCleanup(p.stop)

    def _run(self, chart, **kw):
        kw.setdefault('delay', 0)
        return hot_titles.complete_hot_titles(chart=chart, kinds=('movie',), **kw)

    def test_a_watchable_title_costs_nothing(self):
        Movie.objects.create(title='فیلم', original_title='Film', slug='film', tmdb_id=1,
                             is_published=True, download_links=LINK)
        stats = self._run(_chart(movies=[1]))
        self.assertEqual(stats['watchable'], 1)
        self.assertEqual(stats['attempted'], 0)
        self.mocks['crawl'].assert_not_called()

    def test_a_missing_title_is_imported_crawled_and_published(self):
        def fake_import(kind, tmdb_id, client):
            return Movie.objects.create(title='تازه', original_title='New', slug='new', tmdb_id=tmdb_id), ''

        def fake_crawl(movie, **_):
            Movie.objects.filter(pk=movie.pk).update(download_links=LINK)

        self.mocks['crawl'].side_effect = fake_crawl
        with mock.patch.object(hot_titles, '_import_from_tmdb', side_effect=fake_import):
            stats = self._run(_chart(movies=[42]))
        self.assertEqual((stats['imported'], stats['crawled']), (1, 1))
        self.mocks['publish'].assert_called_once()
        self.assertEqual(self.mocks['crawl'].call_args.kwargs, {'replace': False, 'resolve_english': True})

    def test_no_source_keeps_the_draft_and_the_claim_rests_it(self):
        Movie.objects.create(title='فیلم', original_title='Film', slug='film', tmdb_id=1)
        first = self._run(_chart(movies=[1]))
        self.assertEqual(first['gaps'], {hot_titles.GAP_NO_SOURCE: 1})
        self.assertTrue(Movie.objects.filter(tmdb_id=1).exists())
        second = self._run(_chart(movies=[1]))
        self.assertEqual((second['attempted'], second['resting']), (0, 1))
        self.assertEqual(self.mocks['crawl'].call_count, 1)

    def test_the_claim_is_taken_before_the_crawl(self):
        Movie.objects.create(title='فیلم', original_title='Film', slug='film', tmdb_id=1)
        key = hot_titles.ATTEMPT_KEY.format(kind='movie', tmdb_id=1)
        self.mocks['crawl'].side_effect = lambda *a, **k: self.assertIsNotNone(cache.get(key))
        self._run(_chart(movies=[1]))
        self.mocks['crawl'].assert_called_once()

    def test_a_blocked_title_is_never_published(self):
        Movie.objects.create(title='Film', original_title='Film', slug='film', tmdb_id=1, download_links=LINK)
        self.mocks['blockers'].return_value = ['missing_fa_title']
        with mock.patch('apps.catalog.top250._refresh_from_tmdb'):
            stats = self._run(_chart(movies=[1]))
        self.mocks['publish'].assert_not_called()
        self.assertEqual(stats['gaps'], {'metadata:missing_fa_title': 1})

    def test_limit_and_budget_bound_a_pass(self):
        for n in range(1, 6):
            Movie.objects.create(title='فیلم', original_title=f'Film {n}', slug=f'film-{n}', tmdb_id=n)
        self.assertEqual(self._run(_chart(movies=[1, 2, 3, 4, 5]), limit=2)['attempted'], 2)
        clock = mock.Mock(monotonic=mock.Mock(side_effect=itertools.chain([0.0], itertools.repeat(999.0))))
        with mock.patch.object(hot_titles, 'time', clock):
            stats = self._run(_chart(movies=[3, 4, 5]), budget_seconds=60)
        self.assertEqual(stats['status'], 'budget')


class HotFirstDraftHuntTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_the_hunt_starts_with_the_hot_draft_then_keeps_its_rotation(self):
        cold = Movie.objects.create(title='سرد', original_title='Cold Film', slug='cold', tmdb_id=1,
                                    release_date=date(2001, 1, 1))
        hot = Movie.objects.create(title='داغ', original_title='Hot Film', slug='hot', tmdb_id=2,
                                   release_date=date(2002, 1, 1))
        draft_sources.scan(series=False)
        # The cold gap is the older one, so the plain rotation would pick it first.
        PlaybackSourceGap.objects.filter(object_id=hot.pk).update(updated_at=timezone.now())
        PlaybackSourceGap.objects.filter(object_id=cold.pk).update(updated_at=timezone.now() - timedelta(days=3))
        cache.set(hot_titles.CHART_CACHE_KEY, _chart(movies=[2]))
        seen = []
        with mock.patch.object(draft_sources, 'hunt',
                               side_effect=lambda obj: seen.append(obj.slug) or {'outcome': 'unavailable'}):
            draft_sources.hunt_open_gaps(limit=2)
        self.assertEqual(seen, ['hot', 'cold'])

    def test_the_plain_rotation_is_still_available(self):
        cold = Movie.objects.create(title='سرد', original_title='Cold Film', slug='cold', tmdb_id=1)
        Movie.objects.create(title='داغ', original_title='Hot Film', slug='hot', tmdb_id=2)
        draft_sources.scan(series=False)
        PlaybackSourceGap.objects.filter(object_id=cold.pk).update(updated_at=timezone.now() - timedelta(days=3))
        cache.set(hot_titles.CHART_CACHE_KEY, _chart(movies=[2]))
        seen = []
        with mock.patch.object(draft_sources, 'hunt',
                               side_effect=lambda obj: seen.append(obj.slug) or {'outcome': 'unavailable'}):
            draft_sources.hunt_open_gaps(limit=1, order='stale')
        self.assertEqual(seen, ['cold'])
