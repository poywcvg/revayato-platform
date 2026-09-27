"""Provider discovery must keep running on its own.

On 2026-09-24 production stopped importing new titles for hours without a single
error line. Beat was firing, the worker was busy, every container was healthy —
but the ``imports`` lane was ~790 messages deep with ``auto_crawl_*`` retries and
each discovery tick carried ``expires`` *shorter than its own schedule*, so it
aged out while queued and the worker logged ``Discarding revoked task``.

Fixing that exposed two more silent stoppages underneath it, both of which had been
running for far longer. Every failure in this file shares one shape: **the importer
stopped producing titles while every signal said it was fine.**

Four things have to hold for "always importing" to be true:

1. Configuration: a discovery tick must outlive a realistic backlog, and must not
   share a lane with the bulk retries that create the backlog.
2. Behaviour: when a lane stops finishing runs for any reason at all — killed
   worker still holding the lock, dropped message, dead beat — something has to
   notice and start it again.
3. Parsing: no pattern may pin a provider's domain, or a domain move turns into
   "listing walked, zero items, status ok" with nothing logged.
4. Budget: a tick must end on its own terms and return a result, instead of being
   killed at the soft time limit having reported nothing.
"""

import inspect
import re
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.catalog.provider_import import dornatv_import, myf2m_discover
from apps.catalog.provider_import import tasks as import_tasks
from apps.catalog.provider_import.tasks import (
    DISCOVERY_LANES,
    discovery_silent_minutes,
    import_watchdog_task,
    mark_discovery_alive,
)
from config import settings as app_settings


class DiscoveryScheduleContractTests(TestCase):
    """The settings that let a tick survive a backed-up queue."""

    SCHEDULE = app_settings.CELERY_BEAT_SCHEDULE
    ROUTES = app_settings.CELERY_TASK_ROUTES

    def test_discovery_ticks_outlive_their_own_schedule(self):
        for entry in ('catalog-dornatv-import-missing', 'catalog-myf2m-import-missing',
                      'catalog-kargadan-import-missing', 'catalog-top250-complete'):
            with self.subTest(entry=entry):
                spec = self.SCHEDULE[entry]
                expires = spec['options']['expires']
                self.assertGreater(
                    expires, spec['schedule'],
                    'an expiry at or below the schedule discards the tick the moment '
                    'the lane backs up, which is exactly how imports silently stopped',
                )

    def test_discovery_does_not_share_a_lane_with_bulk_retries(self):
        bulk = self.ROUTES['apps.catalog.provider_import.tasks.auto_crawl_myf2m_series_downloads_task']['queue']
        for task in (
            'apps.catalog.provider_import.tasks.import_missing_dornatv_task',
            'apps.catalog.provider_import.tasks.import_missing_myf2m_task',
            'apps.catalog.provider_import.tasks.import_missing_kargadan_task',
        ):
            with self.subTest(task=task):
                self.assertNotEqual(self.ROUTES[task]['queue'], bulk)

    def test_the_watchdog_is_not_queued_behind_what_it_watches(self):
        watchdog = self.ROUTES['apps.catalog.provider_import.tasks.import_watchdog_task']['queue']
        for task in (
            'apps.catalog.provider_import.tasks.import_missing_dornatv_task',
            'apps.catalog.provider_import.tasks.auto_crawl_myf2m_movie_downloads_task',
        ):
            with self.subTest(task=task):
                self.assertNotEqual(self.ROUTES[task]['queue'], watchdog)
        self.assertIn('catalog-import-watchdog', self.SCHEDULE)

    def test_top250_has_a_lane_of_its_own(self):
        """The shelf users see first must not wait behind discovery or the retry backlog."""
        top250 = self.ROUTES['apps.catalog.provider_import.tasks.complete_top250_task']['queue']
        self.assertEqual(top250, 'imports-top250')
        self.assertEqual(self.SCHEDULE['catalog-top250-complete']['options']['queue'], top250)
        self.assertEqual(DISCOVERY_LANES['top250']['queue'], top250)
        for other in (
            'apps.catalog.provider_import.tasks.import_missing_myf2m_task',
            'apps.catalog.provider_import.tasks.auto_crawl_myf2m_series_downloads_task',
            'apps.catalog.provider_import.tasks.import_watchdog_task',
        ):
            with self.subTest(task=other):
                self.assertNotEqual(self.ROUTES[other]['queue'], top250)

    def test_hot_titles_have_a_lane_of_their_own(self):
        """What is trending now must not wait behind Top 250, discovery or retries."""
        hot = self.ROUTES['apps.catalog.provider_import.tasks.complete_hot_titles_task']['queue']
        self.assertEqual(hot, 'imports-hot')
        self.assertEqual(self.SCHEDULE['catalog-hot-titles-complete']['options']['queue'], hot)
        self.assertEqual(DISCOVERY_LANES['hot']['queue'], hot)
        for other in (
            'apps.catalog.provider_import.tasks.complete_top250_task',
            'apps.catalog.provider_import.tasks.import_missing_myf2m_task',
            'apps.catalog.provider_import.tasks.import_watchdog_task',
        ):
            with self.subTest(task=other):
                self.assertNotEqual(self.ROUTES[other]['queue'], hot)
        schedule = self.SCHEDULE['catalog-hot-titles-complete']
        self.assertGreater(schedule['options']['expires'], schedule['schedule'])
        hard_minutes = import_tasks.complete_hot_titles_task.time_limit / 60
        self.assertGreater(app_settings.CATALOG_IMPORT_SILENCE_MINUTES, schedule['schedule'] / 60 + hard_minutes)

    def test_top250_silence_window_exceeds_a_slow_but_healthy_run(self):
        schedule_minutes = self.SCHEDULE['catalog-top250-complete']['schedule'] / 60
        hard_minutes = import_tasks.complete_top250_task.time_limit / 60
        self.assertGreater(app_settings.CATALOG_IMPORT_SILENCE_MINUTES, schedule_minutes + hard_minutes)

    def test_silence_window_exceeds_a_slow_but_healthy_run(self):
        """A lane that is merely slow must never be restarted underneath itself."""
        slowest_schedule_minutes = self.SCHEDULE['catalog-myf2m-import-missing']['schedule'] / 60
        hard_time_limit_minutes = 15
        self.assertGreater(
            app_settings.CATALOG_IMPORT_SILENCE_MINUTES,
            slowest_schedule_minutes + hard_time_limit_minutes,
        )


class ListingPatternsSurviveADomainMoveTests(TestCase):
    """The provider host is configuration. No pattern may pin it.

    Film2Media moved myf2m.info -> myf2ms.top and both item patterns still named the
    old domain. The listings answered 200 with a full page of cards, every pattern
    matched nothing, the walk read that as "past the final page" and reported
    ``status: ok`` with ``listing_items: 0``. Ingestion from that provider stopped
    completely and silently. Pinning the *configured* host instead is no safer: the
    fetch follows redirects, so the old domain keeps answering with pages served
    from the new one.
    """

    HOSTS = ('https://www.myf2ms.top', 'http://myf2ms.top', 'https://www.myf2m.info')

    # The "no pattern may pin a host" rule is enforced exhaustively, across every
    # regex literal in the provider trees, by
    # apps.catalog.tests_provider_domain.NoPatternPinsAProviderHostTests. What
    # follows is the behaviour that rule exists to protect.

    def test_movie_cards_match_on_any_host_and_relative(self):
        for host in self.HOSTS:
            with self.subTest(host=host):
                match = myf2m_discover.MOVIE_ITEM_RE.search(
                    f'<a href="{host}/86974/26f-seeking-friend-2026/">x</a>'
                )
                self.assertIsNotNone(match)
                self.assertEqual(match.group('path'), '/86974/26f-seeking-friend-2026/')
                self.assertEqual(match.group('id'), '86974')
        relative = myf2m_discover.MOVIE_ITEM_RE.search('<a href="/86906/little-lorraine-2025/">x</a>')
        self.assertIsNotNone(relative)

    def test_series_cards_match_on_any_host_and_relative(self):
        for host in self.HOSTS:
            with self.subTest(host=host):
                match = myf2m_discover.SERIES_ITEM_RE.search(f'<a href="{host}/series/ludwig/">x</a>')
                self.assertIsNotNone(match)
                self.assertEqual(match.group('path'), '/series/ludwig/')
        relative = myf2m_discover.SERIES_ITEM_RE.search('<a href="/series/minerva-academy/">x</a>')
        self.assertIsNotNone(relative)

    def test_foreign_links_in_the_listing_are_not_mistaken_for_cards(self):
        """The permissive host half must not drag in the page's social/CDN links."""
        markup = (
            '<a href="https://www.instagram.com/film2media/">ig</a>'
            '<a href="https://ble.ir/film2media">ble</a>'
            '<a href="https://intocdn.top/">cdn</a>'
            '<a href="https://www.myf2ms.top/movies/page/2/">next</a>'
        )
        self.assertIsNone(myf2m_discover.MOVIE_ITEM_RE.search(markup))
        self.assertIsNone(myf2m_discover.SERIES_ITEM_RE.search(markup))


class TickBudgetTests(TestCase):
    """A tick has to stop itself before Celery stops it.

    Every dornatv run walked until the 12-minute soft limit killed it, so it never
    returned a result and never logged its stats. The walks are checkpointed and
    resumable, so ending early costs nothing and the next tick continues.
    """

    def _soft_limit_seconds(self, task):
        return task.soft_time_limit

    def test_each_budget_leaves_room_under_its_soft_time_limit(self):
        for label, budget, task in (
            ('dornatv', app_settings.DORNATV_IMPORT_BUDGET_SECONDS,
             import_tasks.import_missing_dornatv_task),
            ('myf2m', app_settings.MYF2M_IMPORT_BUDGET_SECONDS,
             import_tasks.import_missing_myf2m_task),
            ('kargadan', app_settings.KARGADAN_IMPORT_BUDGET_SECONDS,
             import_tasks.import_missing_kargadan_task),
            ('top250', app_settings.CATALOG_TOP250_BUDGET_SECONDS,
             import_tasks.complete_top250_task),
            ('hot', app_settings.CATALOG_HOT_BUDGET_SECONDS,
             import_tasks.complete_hot_titles_task),
        ):
            with self.subTest(provider=label):
                soft = self._soft_limit_seconds(task)
                self.assertGreater(budget, 0)
                self.assertLess(
                    budget, soft,
                    'a budget at or above the soft limit never fires — the task is '
                    'killed first, which is the bug this replaced',
                )
                self.assertGreaterEqual(
                    soft - budget, 120,
                    'the budget is only checked between items, so leave room for one '
                    'slow title to finish after the deadline passes',
                )

    def test_checkpoints_do_not_live_on_a_tmpfs(self):
        """The crawl cursor has to outlive the container.

        Both catalog workers run ``read_only: true`` with ``/tmp`` mounted as a 512m
        tmpfs, so anything written there is gone on the next restart. dornatv's
        checkpoint was configured to ``/tmp``: every deploy silently rewound
        discovery to the newest year and page 1 and made it re-walk the whole
        archive, which looks exactly like "the importer keeps stopping".
        """
        for name in ('DORNATV_IMPORT_CHECKPOINT', 'MYF2M_IMPORT_CHECKPOINT', 'KARGADAN_IMPORT_CHECKPOINT'):
            with self.subTest(setting=name):
                path = getattr(app_settings, name)
                self.assertFalse(
                    path.startswith('/tmp/'),
                    f'{name}={path} sits on a tmpfs and is wiped on every restart; '
                    'it belongs on the persistent /app/media volume',
                )

    def test_a_budget_stop_is_reported_as_its_own_status(self):
        """``budget`` must be distinguishable from ``ok`` in the tick log."""
        source = inspect.getsource(dornatv_import.run_dornatv_missing_import)
        self.assertIn("return 'budget'", source)
        self.assertIn("'status': status", source)


@override_settings(CATALOG_IMPORT_SILENCE_MINUTES=45)
class ImportWatchdogTests(TestCase):
    def setUp(self):
        cache.clear()
        self.sent = []
        patcher = patch(
            'config.celery.app.send_task',
            side_effect=lambda name, **kw: self.sent.append((name, kw.get('queue'))),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _silent_for(self, lane, minutes):
        stamped = timezone.now() - timezone.timedelta(minutes=minutes)
        cache.set(f'catalog:import:last_success:{lane}', stamped.isoformat(), timeout=3600)

    def test_a_lane_that_never_reported_is_restarted(self):
        """No heartbeat must read as 'stopped', not as 'fine' — fail toward importing."""
        self.assertIsNone(discovery_silent_minutes('dornatv'))
        result = import_watchdog_task()
        self.assertEqual(sorted(result['restarted']), ['dornatv', 'hot', 'kargadan', 'myf2m', 'top250'])

    def test_a_recently_finished_lane_is_left_alone(self):
        self._silent_for('dornatv', 2)
        self._silent_for('myf2m', 7)
        self._silent_for('top250', 12)
        self._silent_for('kargadan', 5)
        self._silent_for('hot', 9)
        result = import_watchdog_task()
        self.assertEqual(result['restarted'], [])
        self.assertEqual(self.sent, [])

    def test_a_silent_lane_is_restarted_on_its_own_queue(self):
        self._silent_for('dornatv', 90)
        self._silent_for('myf2m', 3)
        self._silent_for('top250', 3)
        self._silent_for('kargadan', 3)
        self._silent_for('hot', 3)
        result = import_watchdog_task()
        self.assertEqual(result['restarted'], ['dornatv'])
        self.assertEqual(
            self.sent,
            [('apps.catalog.provider_import.tasks.import_missing_dornatv_task',
              'imports-discovery')],
        )

    def test_a_silent_top250_lane_is_restarted_on_its_own_queue(self):
        """Sending it to ``imports-discovery`` would park it behind the walks it bypasses."""
        self._silent_for('dornatv', 1)
        self._silent_for('myf2m', 1)
        self._silent_for('kargadan', 1)
        self._silent_for('hot', 1)
        self._silent_for('top250', 60)
        result = import_watchdog_task()
        self.assertEqual(result['restarted'], ['top250'])
        self.assertEqual(
            self.sent,
            [('apps.catalog.provider_import.tasks.complete_top250_task', 'imports-top250')],
        )

    def test_a_silent_hot_lane_is_restarted_on_its_own_queue(self):
        for lane in ('dornatv', 'myf2m', 'kargadan', 'top250'):
            self._silent_for(lane, 1)
        self._silent_for('hot', 60)
        result = import_watchdog_task()
        self.assertEqual(result['restarted'], ['hot'])
        self.assertEqual(
            self.sent,
            [('apps.catalog.provider_import.tasks.complete_hot_titles_task', 'imports-hot')],
        )

    @override_settings(CATALOG_HOT_ENABLED=False)
    def test_a_disabled_hot_lane_is_never_restarted(self):
        self.assertNotIn('hot', import_watchdog_task()['restarted'])

    @override_settings(CATALOG_TOP250_ENABLED=False)
    def test_a_disabled_top250_lane_is_never_restarted(self):
        self.assertNotIn('top250', import_watchdog_task()['restarted'])

    def test_a_run_in_flight_is_never_restarted_underneath_itself(self):
        """A lane that has never reported is usually just on its first run.

        Deleting its lock and sending another tick started a second copy beside
        the first — seen live on the top250 lane's first deploy.
        """
        cache.set(DISCOVERY_LANES['dornatv']['lock'], 'live-task-id', timeout=14 * 60)
        self._silent_for('myf2m', 1)
        self._silent_for('top250', 1)
        self._silent_for('kargadan', 1)
        self._silent_for('hot', 1)
        result = import_watchdog_task()
        self.assertEqual(result['restarted'], [])
        self.assertEqual(result['running'], ['dornatv'])
        self.assertEqual(cache.get(DISCOVERY_LANES['dornatv']['lock']), 'live-task-id')

    def test_every_lock_lapses_inside_the_silence_window(self):
        """An orphaned lock is retired by its TTL, so the watchdog never has to delete one."""
        from pathlib import Path

        source = Path(import_tasks.__file__).read_text(encoding='utf-8')
        for lane, spec in DISCOVERY_LANES.items():
            with self.subTest(lane=lane):
                task = getattr(import_tasks, spec['task'].rsplit('.', 1)[1])
                body = inspect.getsource(task)
                self.assertIn('cache.add(lock', body)
                timeouts = [int(m) for m in re.findall(r'timeout=(\d+) \* 60', body)]
                self.assertTrue(timeouts, f'{lane}: lock timeout not found')
                self.assertLess(max(timeouts), 45)
        self.assertIn('cache.get(spec[\'lock\'])', source)

    @override_settings(DORNATV_IMPORT_ENABLED=False)
    def test_a_disabled_provider_is_never_restarted(self):
        result = import_watchdog_task()
        self.assertNotIn('dornatv', result['restarted'])
        self.assertIn('myf2m', result['restarted'])

    def test_heartbeat_round_trips(self):
        mark_discovery_alive('myf2m')
        silent = discovery_silent_minutes('myf2m')
        self.assertIsNotNone(silent)
        self.assertLess(silent, 1)


class DiscoveryHeartbeatIsRecordedTests(TestCase):
    """The stamp must mean "finished a run", not "started one"."""

    def setUp(self):
        cache.clear()

    def test_a_run_that_raises_does_not_stamp_a_heartbeat(self):
        """A lane that fails every tick must not read as healthy.

        This assertion used to run the other way, on the reasoning that one bad tick
        should not look like death. It hid a real outage instead: dornatv exceeded
        its soft time limit on every tick for hours and imported nothing, but the
        stamp sat in a ``finally``, so the watchdog saw a fresh heartbeat each time
        and never restarted it. A wide silence window already absorbs the occasional
        failure; masking every failure does not.
        """
        with patch(
            'apps.catalog.provider_import.dornatv_import.run_dornatv_missing_import',
            side_effect=RuntimeError('provider down'),
        ):
            with self.assertRaises(RuntimeError):
                import_tasks.import_missing_dornatv_task.apply(throw=True).get()
        self.assertIsNone(discovery_silent_minutes('dornatv'))

    def test_a_run_that_returns_stamps_a_heartbeat(self):
        with patch(
            'apps.catalog.provider_import.dornatv_import.run_dornatv_missing_import',
            return_value={'status': 'ok', 'movies_kept': 0},
        ):
            import_tasks.import_missing_dornatv_task.apply(throw=True).get()
        silent = discovery_silent_minutes('dornatv')
        self.assertIsNotNone(silent)
        self.assertLess(silent, 1)

    def test_a_budget_stop_counts_as_a_completed_run(self):
        """Ending early on the wall-clock budget is a success, not a failure."""
        with patch(
            'apps.catalog.provider_import.myf2m_discover.run_myf2m_missing_import',
            return_value={'status': 'budget', 'listing_items': 24},
        ):
            import_tasks.import_missing_myf2m_task.apply(throw=True).get()
        self.assertIsNotNone(discovery_silent_minutes('myf2m'))

    def test_the_lock_is_released_even_when_the_import_raises(self):
        with patch(
            'apps.catalog.provider_import.dornatv_import.run_dornatv_missing_import',
            side_effect=RuntimeError('provider down'),
        ):
            with self.assertRaises(RuntimeError):
                import_tasks.import_missing_dornatv_task.apply(throw=True).get()
        self.assertIsNone(cache.get(DISCOVERY_LANES['dornatv']['lock']))


class Top250LaneTests(TestCase):
    """The Top 250 lane keeps the same promise as discovery: it finishes, or it is restarted."""

    def setUp(self):
        cache.clear()
        for target in ('apps.catalog.top250.refresh_chart',):
            patcher = patch(target, return_value={'status': 'fresh'})
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_a_completed_pass_stamps_a_heartbeat_and_uses_the_budget(self):
        with patch('apps.catalog.top250.complete_chart', return_value={'status': 'budget', 'attempted': 3}) as run:
            result = import_tasks.complete_top250_task.apply(throw=True).get()
        self.assertEqual(result['status'], 'budget')
        budget = run.call_args.kwargs['budget_seconds']
        self.assertGreater(budget, 0)
        self.assertLessEqual(budget, app_settings.CATALOG_TOP250_BUDGET_SECONDS)
        self.assertIsNotNone(discovery_silent_minutes('top250'))
        self.assertIsNone(cache.get(DISCOVERY_LANES['top250']['lock']))

    def test_a_pass_that_times_out_does_not_stamp_and_releases_the_lock(self):
        from celery.exceptions import SoftTimeLimitExceeded

        with patch('apps.catalog.top250.complete_chart', side_effect=SoftTimeLimitExceeded()):
            with self.assertRaises(SoftTimeLimitExceeded):
                import_tasks.complete_top250_task.apply(throw=True).get()
        self.assertIsNone(discovery_silent_minutes('top250'))
        self.assertIsNone(cache.get(DISCOVERY_LANES['top250']['lock']))

    def test_a_failed_chart_refresh_still_completes_the_stored_chart(self):
        with patch('apps.catalog.top250.refresh_chart', side_effect=RuntimeError('imdb down')), \
                patch('apps.catalog.top250.complete_chart', return_value={'status': 'ok'}) as run:
            import_tasks.complete_top250_task.apply(throw=True).get()
        run.assert_called_once()

    def test_a_second_tick_does_not_run_alongside_the_first(self):
        cache.set(DISCOVERY_LANES['top250']['lock'], 'other', timeout=60)
        with patch('apps.catalog.top250.complete_chart') as run:
            result = import_tasks.complete_top250_task.apply(throw=True).get()
        self.assertEqual(result['status'], 'already_running')
        run.assert_not_called()


class HotTitlesLaneTests(TestCase):
    """The hot lane keeps the same promise as the others: it finishes, or it is restarted."""

    def setUp(self):
        cache.clear()
        patcher = patch('apps.catalog.hot_titles.refresh_hot_chart', return_value={'status': 'fresh'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_completed_pass_stamps_a_heartbeat_and_uses_the_budget(self):
        with patch('apps.catalog.hot_titles.complete_hot_titles',
                   return_value={'status': 'budget', 'attempted': 3}) as run:
            result = import_tasks.complete_hot_titles_task.apply(throw=True).get()
        self.assertEqual(result['status'], 'budget')
        self.assertEqual(result['chart'], 'fresh')
        budget = run.call_args.kwargs['budget_seconds']
        self.assertGreater(budget, 0)
        self.assertLessEqual(budget, app_settings.CATALOG_HOT_BUDGET_SECONDS)
        self.assertIsNotNone(discovery_silent_minutes('hot'))
        self.assertIsNone(cache.get(DISCOVERY_LANES['hot']['lock']))

    def test_a_pass_that_times_out_does_not_stamp_and_releases_the_lock(self):
        from celery.exceptions import SoftTimeLimitExceeded

        with patch('apps.catalog.hot_titles.complete_hot_titles', side_effect=SoftTimeLimitExceeded()):
            with self.assertRaises(SoftTimeLimitExceeded):
                import_tasks.complete_hot_titles_task.apply(throw=True).get()
        self.assertIsNone(discovery_silent_minutes('hot'))
        self.assertIsNone(cache.get(DISCOVERY_LANES['hot']['lock']))

    def test_a_failed_chart_refresh_still_completes_the_stored_chart(self):
        with patch('apps.catalog.hot_titles.refresh_hot_chart', side_effect=RuntimeError('tmdb down')), \
                patch('apps.catalog.hot_titles.complete_hot_titles', return_value={'status': 'ok'}) as run:
            import_tasks.complete_hot_titles_task.apply(throw=True).get()
        run.assert_called_once()

    def test_a_second_tick_does_not_run_alongside_the_first(self):
        cache.set(DISCOVERY_LANES['hot']['lock'], 'other', timeout=60)
        with patch('apps.catalog.hot_titles.complete_hot_titles') as run:
            result = import_tasks.complete_hot_titles_task.apply(throw=True).get()
        self.assertEqual(result['status'], 'already_running')
        run.assert_not_called()
