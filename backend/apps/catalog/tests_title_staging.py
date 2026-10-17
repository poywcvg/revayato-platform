"""«بازسازی تست‌شده»: staged off to the side, tested, applied only when it passes."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from . import title_completion, title_rebuild, title_staging
from .models import MediaCheck, Movie, MovieSyncAudit, Series
from .provider_import.exceptions import ProviderImportError

OLD = {'url': 'https://dl.example/old/film.2026.720p.mp4', 'quality': '720p'}
NEW = {'url': 'https://dl.example/new/film.2026.1080p.mp4', 'quality': '1080p'}
NEW_480 = {'url': 'https://dl.example/new/film.2026.480p.mp4', 'quality': '480p'}
DORNA = {'url': 'https://dl.example/dorna/film.2026.480p.mp4', 'quality': '480p', 'source': 'dornatv'}
KARGADAN = {'url': 'https://dl.example/k/film.2026.1080p.mp4', 'quality': '1080p', 'source': 'kargadan'}
MANUAL = {'url': 'https://mine.example/film.mp4', 'quality': '1080p', 'source': 'manual'}


def _ep(season, episode, tag='new'):
    return {
        'url': f'https://dl.example/{tag}/show.s{season:02d}e{episode:02d}.1080p.mp4',
        'quality': '1080p', 'season_number': season, 'episode_number': episode,
    }


def _crawl(fresh_by_provider, errors=()):
    """A provider crawl stand-in that writes the way the real ones do: onto ``obj``, then ``save()``."""
    def crawl(slug, obj, *, replace, queue_softsub):
        if slug in errors:
            raise ProviderImportError('timeout', code=f'{slug}_crawl_failed')
        rows = fresh_by_provider.get(slug)
        if rows is None:
            raise ProviderImportError('nothing', code=f'{slug}_not_found')
        obj.download_links = [*(obj.download_links or []), *rows]
        obj.save(update_fields=['download_links', 'updated_at'])
        return {'download_links': rows}
    return crawl


def _probe(verdicts):
    """``_probe`` stand-in: ``verdicts`` maps URL → live/dead/unknown (default live)."""
    return mock.Mock(side_effect=lambda url, use_cache=True: mock.Mock(verdict=verdicts.get(url, 'live')))


class _Base(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = get_user_model().objects.create_user(
            username='stager', email='s@example.test', password='x-Pass-12345', is_staff=True,
        )

    def movie(self, links, **extra):
        return Movie.objects.create(
            title='فیلم', original_title='Film', slug=f'film-{Movie.objects.count()}',
            tmdb_id=77, download_links=links, **extra,
        )


class StageTests(_Base):
    def test_crawl_writes_land_on_the_shadow_not_the_title(self):
        movie = self.movie([OLD])
        with mock.patch(
            'apps.catalog.provider_import.multi_provider_crawl._crawl_one_movie',
            side_effect=_crawl({'myf2m': [NEW]}),
        ):
            staged = title_staging.stage(movie, ['myf2m', 'dornatv'])
        self.assertEqual(staged['verdicts'], {'myf2m': 'filled', 'dornatv': 'not_found'})
        self.assertEqual([row['url'] for row in staged['rows']['myf2m']], [NEW['url']])
        movie.refresh_from_db()
        self.assertEqual([row['url'] for row in movie.download_links], [OLD['url']])
        self.assertEqual(movie.download_links, Movie.objects.get(pk=movie.pk).download_links)

    def test_staging_holds_back_episode_creation_and_vtt_ingest(self):
        from .provider_import.dornatv_sync import _ingest_embedded_subtitle_tracks
        from .subtitle_extract import ensure_episodes_from_download_links

        series = Series.objects.create(title='سریال', original_title='Show', slug='show', download_links=[_ep(1, 1)])
        movie = self.movie([OLD])
        with title_staging.staging(), mock.patch(
            'apps.catalog.subtitle_extract.extract_webvtt_from_url',
        ) as fetch:
            self.assertEqual(ensure_episodes_from_download_links(series), 0)
            self.assertFalse(_ingest_embedded_subtitle_tracks(movie, [{'source_url': 'https://x.example/a.vtt'}]))
        fetch.assert_not_called()
        self.assertFalse(series.seasons.exists())
        self.assertFalse(title_staging.is_staging())


class JudgeTests(_Base):
    def test_verdicts(self):
        movie = self.movie([OLD])
        cases = [
            ([], {}, title_staging.REJECT_NO_LINKS),
            ([NEW], {'live': 0, 'dead': 2}, title_staging.REJECT_DEAD),
            ([NEW], {'live': 0, 'dead': 0, 'unknown': 3}, title_staging.REJECT_INCONCLUSIVE),
            ([NEW], {'live': 1, 'dead': 2}, title_staging.REJECT_MOSTLY_DEAD),
            ([NEW], {'live': 2, 'dead': 1}, ''),
        ]
        for links, tally, reason in cases:
            verdict = title_staging.judge(movie, links, tally)
            self.assertEqual(verdict['ok'], not reason, (tally, verdict))
            self.assertEqual(verdict['reason'], reason)

    def test_series_may_not_lose_most_episodes_unless_today_is_broken(self):
        series = Series.objects.create(
            title='سریال', original_title='Show', slug='show',
            download_links=[_ep(1, n, 'old') for n in range(1, 11)],
        )
        staged = [_ep(1, 1), _ep(1, 2)]
        verdict = title_staging.judge(series, staged, {'live': 2})
        self.assertEqual(verdict['reason'], title_staging.REJECT_COVERAGE)
        self.assertEqual((verdict['episodes_now'], verdict['episodes_staged']), (10, 2))

        MediaCheck.objects.create(content_type='series', object_id=series.pk, status=MediaCheck.Status.FAILED)
        self.assertTrue(title_staging.judge(series, staged, {'live': 2})['ok'])

    def test_series_probes_spread_over_the_episodes(self):
        series = Series.objects.create(title='سریال', original_title='Show', slug='show')
        links = [_ep(1, n) for n in range(1, 31)]
        urls = title_staging.probe_targets(series, links)
        self.assertEqual(len(urls), title_staging.SERIES_TEST_PROBES)
        self.assertIn(_ep(1, 1)['url'], urls)
        self.assertIn(_ep(1, 30)['url'], urls)


class StagedPipelineTests(_Base):
    def _run(self, movie, crawl, probe, providers=('myf2m', 'dornatv', 'kargadan')):
        patches = {
            'apps.catalog.admin_ops._resync_tmdb': mock.Mock(return_value={'synced': True}),
            'apps.catalog.title_repair.repair_titles': mock.Mock(return_value={'changed': {}}),
            'apps.catalog.provider_import.source_fill.wanted_providers': mock.Mock(
                return_value=(list(providers), ''),
            ),
            'apps.catalog.provider_import.multi_provider_crawl._crawl_one_movie': mock.Mock(side_effect=crawl),
            'apps.catalog.media_verification._probe': probe,
            'apps.catalog.link_sizes.size_title': mock.Mock(return_value={'sized': 0, 'left': 0}),
            'apps.catalog.media_verification.verify_target': mock.Mock(return_value={'status': 'passed'}),
            'apps.catalog.completeness.publish_blockers': mock.Mock(return_value=[]),
            'apps.catalog.media_verification.media_publish_blockers': mock.Mock(return_value=[]),
            'apps.catalog.tasks.enqueue_movie_softsub_urgent': mock.Mock(return_value=True),
            'apps.catalog.playback_gate.gate_links': mock.Mock(return_value=(mock.Mock(), [])),
        }
        started = [mock.patch(target, new) for target, new in patches.items()]
        for patcher in started:
            patcher.start()
        try:
            return title_completion.run_completion(
                'movie', movie.pk, user_id=self.staff.pk, publish=True, mode='staged',
            )
        finally:
            for patcher in started:
                patcher.stop()

    @staticmethod
    def steps(state):
        return {row['key']: row for row in state['steps']}

    def test_passing_set_replaces_answered_providers_and_keeps_the_rest(self):
        movie = self.movie([OLD, DORNA, KARGADAN, MANUAL], video_url=OLD['url'])
        state = self._run(movie, _crawl({'myf2m': [NEW, NEW_480]}, errors={'kargadan'}), _probe({}))
        steps = self.steps(state)
        movie.refresh_from_db()

        self.assertEqual(list(steps), list(title_completion.STAGED_STEPS))
        self.assertEqual(state['verdict'], 'applied')
        self.assertEqual(steps['test']['status'], 'ok')
        self.assertEqual(steps['apply']['status'], 'ok')
        # myf2m answered → its old row is gone; dornatv answered "not there" →
        # gone too; kargadan errored → kept; the hand-added row is never touched.
        self.assertEqual(
            {row['url'] for row in movie.download_links},
            {NEW['url'], NEW_480['url'], KARGADAN['url'], MANUAL['url']},
        )
        self.assertNotEqual(movie.video_url, OLD['url'])
        self.assertEqual(len(title_rebuild.latest_backup(movie).details['snapshot']['download_links']), 4)
        self.assertTrue(MovieSyncAudit.objects.filter(
            movie=movie, details__reason='staged_rebuild', details__verdict='applied',
        ).exists())

    def test_dead_staged_set_is_rejected_and_the_title_is_untouched(self):
        movie = self.movie([OLD, DORNA])
        state = self._run(movie, _crawl({'myf2m': [NEW]}), _probe({NEW['url']: 'dead'}))
        steps = self.steps(state)
        movie.refresh_from_db()

        self.assertEqual(state['verdict'], 'rejected')
        self.assertEqual(state['verdict_reason'], title_staging.REJECT_DEAD)
        self.assertEqual(steps['test']['status'], 'blocked')
        for key in ('backup', 'apply', 'sizes', 'verify', 'publish', 'subtitles'):
            self.assertEqual(steps[key]['status'], 'skipped', key)
        self.assertEqual({row['url'] for row in movie.download_links}, {OLD['url'], DORNA['url']})
        self.assertIsNone(title_rebuild.latest_backup(movie))

    def test_unanswered_probes_are_not_a_pass(self):
        movie = self.movie([OLD])
        state = self._run(movie, _crawl({'myf2m': [NEW]}), _probe({NEW['url']: 'unknown'}))
        movie.refresh_from_db()
        self.assertEqual(state['verdict_reason'], title_staging.REJECT_INCONCLUSIVE)
        self.assertEqual(movie.download_links[0]['url'], OLD['url'])

    def test_a_dead_file_in_a_passing_set_is_left_out(self):
        movie = self.movie([OLD])
        state = self._run(movie, _crawl({'myf2m': [NEW, NEW_480]}), _probe({NEW_480['url']: 'dead'}))
        movie.refresh_from_db()
        self.assertEqual(state['verdict'], 'applied')
        self.assertEqual({row['url'] for row in movie.download_links}, {NEW['url']})

    def test_no_provider_answer_rejects_without_touching_anything(self):
        movie = self.movie([OLD])
        probe = _probe({})
        state = self._run(movie, _crawl({}), probe)
        self.assertEqual(state['verdict_reason'], title_staging.REJECT_NO_LINKS)
        self.assertEqual(self.steps(state)['stage']['status'], 'empty')
        probe.assert_not_called()


class StagedDeskTests(_Base):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_bulk_queues_staged_rebuilds_on_the_imports_lane(self):
        movie = self.movie([OLD])
        with mock.patch('apps.catalog.tasks.complete_title_task.apply_async') as queued:
            response = self.client.post(
                '/api/admin/catalog/bulk/',
                {'kind': 'movie', 'action': 'rebuild_staged', 'ids': [movie.pk]}, format='json',
            )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['succeeded'], 1)
        self.assertEqual(queued.call_args.kwargs['queue'], title_completion.BULK_QUEUE)
        self.assertEqual(queued.call_args.kwargs['kwargs']['mode'], 'staged')

    def test_bulk_queues_untested_rebuilds_on_the_imports_lane(self):
        # «جایگزینی از صفر بدون تست»: the plain rebuild (backup + replace, undoable),
        # queued per title on the imports lane like the staged one.
        movies = [self.movie([OLD]), Movie.objects.create(
            title='فیلم دوم', original_title='Film Two', slug='film-two', tmdb_id=78, download_links=[OLD],
        )]
        with mock.patch('apps.catalog.tasks.complete_title_task.apply_async') as queued:
            response = self.client.post(
                '/api/admin/catalog/bulk/',
                {'kind': 'movie', 'action': 'rebuild', 'ids': [m.pk for m in movies]}, format='json',
            )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['succeeded'], 2)
        self.assertEqual(queued.call_count, 2)
        for call in queued.call_args_list:
            self.assertEqual(call.kwargs['queue'], title_completion.BULK_QUEUE)
            self.assertEqual(call.kwargs['kwargs']['mode'], 'rebuild')

    def test_a_desk_rebuild_stays_on_the_desk_lane(self):
        movie = self.movie([OLD])
        with mock.patch('apps.catalog.tasks.complete_title_task.apply_async') as queued:
            response = self.client.post(
                f'/api/admin/catalog/movie/{movie.pk}/media/', {'action': 'rebuild'}, format='json',
            )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(queued.call_args.kwargs['queue'], title_completion.DESK_QUEUE)

    def test_health_rows_carry_the_last_verdict(self):
        movie = self.movie([OLD], is_published=True)
        MediaCheck.objects.create(content_type='movie', object_id=movie.pk, status=MediaCheck.Status.FAILED)
        cache.set(title_completion._key('movie', movie.pk), {
            'state': 'done', 'mode': 'staged', 'verdict': 'rejected',
            'verdict_reason': title_staging.REJECT_DEAD, 'finished_at': '2026-10-01T10:00:00+00:00',
            'started_ts': 0, 'steps': [],
        })
        response = self.client.get('/api/admin/catalog/health/', {'queue': 'failed_checks'})
        self.assertEqual(response.status_code, 200, response.data)
        row = next(item for item in response.data['results'] if item['target']['id'] == movie.pk)
        self.assertEqual(row['repair']['verdict'], 'rejected')
        self.assertEqual(row['repair']['verdict_reason'], title_staging.REJECT_DEAD)
        self.assertEqual(row['repair']['state'], 'done')
