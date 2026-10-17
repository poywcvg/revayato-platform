"""«بازسازی کامل از صفر»: fresh answer replaces stale rows, reversibly, never empty."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from . import title_completion, title_rebuild
from .models import Episode, Movie, MovieSyncAudit, Season, Series
from .provider_import.exceptions import ProviderImportError

OLD = {'url': 'https://dl.example/old/film.2026.720p.mp4', 'quality': '720p'}
NEW = {'url': 'https://dl.example/new/film.2026.1080p.mp4', 'quality': '1080p'}
DORNA = {'url': 'https://dl.example/dorna/film.2026.480p.mp4', 'quality': '480p', 'source': 'dornatv'}
KARGADAN = {'url': 'https://dl.example/k/film.2026.1080p.mp4', 'quality': '1080p', 'source': 'kargadan'}
MANUAL = {'url': 'https://mine.example/film.mp4', 'quality': '1080p', 'source': 'manual'}


def _ep(season, episode, tag='new'):
    return {
        'url': f'https://dl.example/{tag}/show.s{season:02d}e{episode:02d}.1080p.mp4',
        'quality': '1080p', 'season_number': season, 'episode_number': episode,
    }


def _no_gate():
    return mock.patch('apps.catalog.playback_gate.gate_enabled', return_value=False)


class _Base(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = get_user_model().objects.create_user(
            username='rebuilder', email='r@example.test', password='x-Pass-12345', is_staff=True,
        )

    def movie(self, links, **extra):
        return Movie.objects.create(
            title='فیلم', original_title='Film', slug=f'film-{Movie.objects.count()}',
            tmdb_id=77, download_links=links, **extra,
        )


class PruneTests(_Base):
    def test_answered_providers_lose_stale_rows_others_keep_theirs(self):
        movie = self.movie([OLD, NEW, DORNA, KARGADAN, MANUAL])
        verdicts = {'myf2m': 'filled', 'dornatv': 'not_found', 'kargadan': 'error'}
        result = title_rebuild.prune_stale(movie, verdicts, title_rebuild._identities([NEW]))
        movie.refresh_from_db()
        urls = {row['url'] for row in movie.download_links}
        self.assertEqual(result['removed'], 2)
        self.assertEqual(urls, {NEW['url'], KARGADAN['url'], MANUAL['url']})

    def test_no_fresh_answer_changes_nothing(self):
        movie = self.movie([OLD, DORNA])
        result = title_rebuild.prune_stale(movie, {'myf2m': 'not_found', 'dornatv': 'not_found'}, set())
        movie.refresh_from_db()
        self.assertEqual(result['removed'], 0)
        self.assertEqual(len(movie.download_links), 2)

    def test_player_moves_off_a_removed_file(self):
        movie = self.movie([OLD, NEW], video_url=OLD['url'])
        gate = mock.patch('apps.catalog.playback_gate.gate_links', return_value=(mock.Mock(), []))
        with gate:
            title_rebuild.prune_stale(movie, {'myf2m': 'filled'}, title_rebuild._identities([NEW]))
        movie.refresh_from_db()
        self.assertEqual(movie.video_url, NEW['url'])
        self.assertIsNone(movie.playback_checked_at)

    def test_hand_set_player_source_is_left_alone(self):
        movie = self.movie([OLD, NEW], video_url='uploads/film/master.m3u8')
        title_rebuild.prune_stale(movie, {'myf2m': 'filled'}, title_rebuild._identities([NEW]))
        movie.refresh_from_db()
        self.assertEqual(movie.video_url, 'uploads/film/master.m3u8')


class EpisodeTests(_Base):
    def setUp(self):
        super().setUp()
        self.series = Series.objects.create(
            title='سریال', original_title='Show', slug='show-2026', download_links=[_ep(1, 1), _ep(1, 2)],
        )
        self.s1 = Season.objects.create(series=self.series, season_number=1, is_published=True)
        self.s2 = Season.objects.create(series=self.series, season_number=2, is_published=True)
        self.e1 = Episode.objects.create(season=self.s1, episode_number=1, is_published=True, video_url=_ep(1, 1)['url'])
        self.e3 = Episode.objects.create(season=self.s1, episode_number=3, is_published=True, video_url=_ep(1, 3, 'old')['url'])
        self.e4 = Episode.objects.create(season=self.s1, episode_number=4, is_published=True, video_url='uploads/show/e4.m3u8')
        self.s2e1 = Episode.objects.create(season=self.s2, episode_number=1, is_published=True, video_url=_ep(2, 1, 'old')['url'])

    def test_unbacked_cdn_episodes_are_hidden_uploads_are_not(self):
        result = title_rebuild.reconcile_episodes(self.series)
        for row in (self.e1, self.e3, self.e4, self.s2e1, self.s1, self.s2):
            row.refresh_from_db()
        self.assertEqual(result['unpublished'], 2)
        self.assertTrue(self.e1.is_published)
        self.assertFalse(self.e3.is_published)
        self.assertTrue(self.e4.is_published)
        self.assertFalse(self.s2e1.is_published)
        self.assertTrue(self.s1.is_published)
        self.assertFalse(self.s2.is_published)
        self.assertEqual(result['seasons_hidden'], 1)

    def test_link_set_without_episodes_judges_nothing(self):
        Series.objects.filter(pk=self.series.pk).update(download_links=[])
        self.series.refresh_from_db()
        result = title_rebuild.reconcile_episodes(self.series)
        self.assertEqual(result['unpublished'], 0)
        self.e3.refresh_from_db()
        self.assertTrue(self.e3.is_published)

    def test_restore_puts_episodes_links_and_seasons_back(self):
        before = list(self.series.download_links)
        title_rebuild.save_backup(self.series, user=self.staff)
        Series.objects.filter(pk=self.series.pk).update(download_links=[_ep(1, 1)])
        self.series.refresh_from_db()
        with _no_gate():
            title_rebuild.reconcile_episodes(self.series)
        extra = Episode.objects.create(season=self.s1, episode_number=9, is_published=True, video_url=_ep(1, 9)['url'])

        result = title_rebuild.restore_backup(self.series, user=self.staff)

        self.series.refresh_from_db()
        for row in (self.e3, self.s2e1, self.s2, extra):
            row.refresh_from_db()
        self.assertTrue(result['restored'])
        self.assertEqual([row['url'] for row in self.series.download_links], [row['url'] for row in before])
        self.assertTrue(self.e3.is_published)
        self.assertTrue(self.s2e1.is_published)
        self.assertTrue(self.s2.is_published)
        self.assertFalse(extra.is_published)
        self.assertIsNone(title_rebuild.latest_backup(self.series))
        self.assertEqual(title_rebuild.restore_backup(self.series)['error'], 'no_rebuild_backup')


def _crawl_movie(fresh_by_provider):
    """A provider crawl stand-in: merges its rows (as the real one does) and returns them."""
    def crawl(slug, movie, *, replace, queue_softsub):
        rows = fresh_by_provider.get(slug)
        if rows is None:
            raise ProviderImportError('nothing', code=f'{slug}_not_found')
        Movie.objects.filter(pk=movie.pk).update(download_links=[*(movie.download_links or []), *rows])
        return {'download_links': rows}
    return crawl


class RebuildPipelineTests(_Base):
    def _run(self, movie, crawl, **overrides):
        base = {
            'apps.catalog.admin_ops._resync_tmdb': mock.Mock(return_value={'synced': True}),
            'apps.catalog.title_repair.repair_titles': mock.Mock(return_value={'changed': {}}),
            'apps.catalog.provider_import.source_fill.wanted_providers': mock.Mock(
                return_value=(['myf2m', 'dornatv'], ''),
            ),
            'apps.catalog.provider_import.multi_provider_crawl._crawl_one_movie': mock.Mock(side_effect=crawl),
            'apps.catalog.link_sizes.size_title': mock.Mock(return_value={'sized': 0, 'left': 0}),
            'apps.catalog.media_verification.verify_target': mock.Mock(return_value={'status': 'passed'}),
            'apps.catalog.completeness.publish_blockers': mock.Mock(return_value=[]),
            'apps.catalog.media_verification.media_publish_blockers': mock.Mock(return_value=[]),
            'apps.catalog.tasks.enqueue_movie_softsub_urgent': mock.Mock(return_value=True),
            'apps.catalog.playback_gate.gate_links': mock.Mock(return_value=(mock.Mock(), [])),
            'apps.catalog.playback_gate.gate_enabled': mock.Mock(return_value=False),
        }
        base.update(overrides)
        patches = [mock.patch(target, new) for target, new in base.items()]
        for patcher in patches:
            patcher.start()
        try:
            return title_completion.run_completion(
                'movie', movie.pk, user_id=self.staff.pk, publish=True, mode='rebuild',
            )
        finally:
            for patcher in patches:
                patcher.stop()

    def test_rebuild_backs_up_then_keeps_only_the_fresh_answer(self):
        movie = self.movie([OLD, DORNA, MANUAL])
        state = self._run(movie, _crawl_movie({'myf2m': [NEW]}))
        steps = {row['key']: row for row in state['steps']}
        movie.refresh_from_db()
        self.assertEqual(state['mode'], 'rebuild')
        self.assertEqual(list(steps), list(title_completion.REBUILD_STEPS))
        self.assertEqual(steps['backup']['status'], 'ok')
        self.assertEqual(steps['sources']['removed'], 2)
        self.assertEqual(steps['episodes']['status'], 'skipped')
        self.assertEqual({row['url'] for row in movie.download_links}, {NEW['url'], MANUAL['url']})
        backup = title_rebuild.latest_backup(movie)
        self.assertEqual(len(backup.details['snapshot']['download_links']), 3)
        self.assertTrue(MovieSyncAudit.objects.filter(movie=movie, details__reason='rebuild_title').exists())

    def test_rebuild_re_extracts_player_and_subtitles_from_scratch(self):
        movie = self.movie([OLD, NEW], video_url=OLD['url'], playback_mode='direct', is_published=True)
        seen = []

        def crawl(slug, obj, *, replace, queue_softsub):
            seen.append(title_rebuild.is_fresh_fetch())
            return _crawl_movie({'myf2m': [OLD, NEW], 'dornatv': []})(slug, obj, replace=replace, queue_softsub=queue_softsub)

        hunt = mock.Mock(return_value=True)
        bump = mock.Mock(return_value=3)
        state = self._run(
            movie, crawl, **{
                'apps.catalog.tasks.enqueue_movie_softsub_urgent': hunt,
                'apps.catalog.cache.bump_catalog_cache_version': bump,
            },
        )
        steps = {row['key']: row for row in state['steps']}
        movie.refresh_from_db()
        self.assertEqual(seen, [True, True])
        self.assertEqual(steps['playback']['status'], 'ok')
        self.assertEqual(movie.video_url, NEW['url'])
        self.assertEqual(movie.playback_mode, 'unverified')
        hunt.assert_called_once_with(movie.pk, force=True)
        bump.assert_any_call(force=True)

    def test_no_fresh_links_leaves_the_player_alone(self):
        movie = self.movie([OLD], video_url=OLD['url'], playback_mode='direct')
        state = self._run(movie, _crawl_movie({}))
        playback = next(row for row in state['steps'] if row['key'] == 'playback')
        movie.refresh_from_db()
        self.assertEqual(playback['status'], 'skipped')
        self.assertEqual((movie.video_url, movie.playback_mode), (OLD['url'], 'direct'))

    def test_empty_answer_leaves_the_title_untouched(self):
        movie = self.movie([OLD, DORNA])
        state = self._run(movie, _crawl_movie({}))
        sources = next(row for row in state['steps'] if row['key'] == 'sources')
        movie.refresh_from_db()
        self.assertEqual(sources['status'], 'empty')
        self.assertEqual(len(movie.download_links), 2)

    def test_no_backup_no_rebuild(self):
        movie = self.movie([OLD])
        crawl = mock.Mock()
        state = self._run(
            movie, crawl,
            **{'apps.catalog.title_rebuild.save_backup': mock.Mock(side_effect=RuntimeError('db'))},
        )
        self.assertEqual(state['state'], 'failed')
        self.assertEqual(state['error'], 'backup_failed')
        crawl.assert_not_called()
        movie.refresh_from_db()
        self.assertEqual(movie.download_links[0]['url'], OLD['url'])


class DeskTests(_Base):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def desk(self, pk, action):
        return self.client.post(f'/api/admin/catalog/movie/{pk}/media/', {'action': action}, format='json')

    def test_rebuild_queues_on_the_admin_lane_in_rebuild_mode(self):
        movie = self.movie([OLD])
        with mock.patch('apps.catalog.tasks.complete_title_task.apply_async') as queued:
            response = self.desk(movie.pk, 'rebuild')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(queued.call_args.kwargs['queue'], title_completion.DESK_QUEUE)
        self.assertEqual(queued.call_args.kwargs['kwargs']['mode'], 'rebuild')
        completion = response.data['desk']['completion']
        self.assertEqual(completion['steps'][0]['key'], 'backup')

    def test_undo_restores_and_payload_never_ships_the_snapshot(self):
        movie = self.movie([OLD, DORNA])
        title_rebuild.save_backup(movie, user=self.staff)
        Movie.objects.filter(pk=movie.pk).update(download_links=[NEW])
        desk = self.client.get(f'/api/admin/catalog/movie/{movie.pk}/media/').data
        self.assertEqual(desk['rebuild_backup']['links'], 2)
        self.assertTrue(all('snapshot' not in row['details'] for row in desk['audits']))

        response = self.desk(movie.pk, 'rebuild_undo')
        self.assertEqual(response.status_code, 200, response.data)
        movie.refresh_from_db()
        self.assertEqual({row['url'] for row in movie.download_links}, {OLD['url'], DORNA['url']})
        self.assertIsNone(response.data['desk']['rebuild_backup'])

    def test_undo_without_backup_says_so(self):
        movie = self.movie([OLD])
        response = self.desk(movie.pk, 'rebuild_undo')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'no_rebuild_backup')


def _verdicts(modes):
    from .playback_gate import SourceVerdict

    def test(url, **_kwargs):
        return SourceVerdict(url=url, mode=modes.get(url, 'none'), reason='test')
    return test


class ReplayPlaybackTests(_Base):
    def test_player_is_chosen_again_with_fresh_probes(self):
        movie = self.movie([OLD, NEW], video_url=OLD['url'], playback_mode='direct')
        test = mock.Mock(side_effect=_verdicts({NEW['url']: 'direct', OLD['url']: 'gateway'}))
        with mock.patch('apps.catalog.playback_gate.gate_enabled', return_value=True), \
                mock.patch('apps.catalog.playback_gate.test_source', test):
            result = title_rebuild.replay_playback(movie)
        movie.refresh_from_db()
        self.assertEqual(movie.video_url, NEW['url'])
        self.assertEqual(movie.playback_mode, 'direct')
        self.assertIsNotNone(movie.playback_checked_at)
        self.assertFalse(any(call.kwargs.get('use_cache') for call in test.call_args_list))
        self.assertEqual((result['tested'], result['direct'], result['browser_safe']), (1, 1, True))

    def test_nothing_playable_never_blanks_the_player(self):
        movie = self.movie([OLD], video_url=OLD['url'], playback_mode='direct')
        with mock.patch('apps.catalog.playback_gate.gate_enabled', return_value=True), \
                mock.patch('apps.catalog.playback_gate.test_source', side_effect=_verdicts({})):
            title_rebuild.replay_playback(movie)
        movie.refresh_from_db()
        self.assertEqual(movie.video_url, OLD['url'])

    def test_our_own_hls_stream_stays(self):
        movie = self.movie([NEW], video_url='uploads/film/master.m3u8', playback_mode='direct')
        with mock.patch('apps.catalog.playback_gate.test_source') as test:
            result = title_rebuild.replay_playback(movie)
        test.assert_not_called()
        movie.refresh_from_db()
        self.assertEqual(movie.video_url, 'uploads/film/master.m3u8')
        self.assertEqual(result['kept_own'], 1)

    def test_episodes_get_fresh_players_and_the_rest_queue_for_the_sweep(self):
        series = Series.objects.create(
            title='سریال', original_title='Show', slug='show-replay',
            download_links=[_ep(1, 1), _ep(1, 1, 'alt'), _ep(1, 2)],
        )
        season = Season.objects.create(series=series, season_number=1, is_published=True)
        e1 = Episode.objects.create(
            season=season, episode_number=1, is_published=True, video_url=_ep(1, 1, 'alt')['url'],
            playback_mode='direct',
        )
        e2 = Episode.objects.create(
            season=season, episode_number=2, is_published=True, video_url=_ep(1, 2)['url'],
            playback_mode='direct',
        )
        modes = {_ep(1, 1)['url']: 'direct', _ep(1, 1, 'alt')['url']: 'none'}
        with mock.patch('apps.catalog.playback_gate.gate_enabled', return_value=True), \
                mock.patch('apps.catalog.playback_gate.test_source', side_effect=_verdicts(modes)):
            title_rebuild.replay_playback(series)
            e1.refresh_from_db()
            self.assertEqual(e1.video_url, _ep(1, 1)['url'])
            e1.playback_mode = 'direct'
            e1.save()
            result = title_rebuild.replay_playback(series, budget_seconds=0)
        e1.refresh_from_db()
        e2.refresh_from_db()
        self.assertEqual(result['deferred'], 2)
        self.assertEqual((e2.playback_mode, e2.playback_checked_at), ('unverified', None))
        self.assertEqual(e2.video_url, _ep(1, 2)['url'])

    def test_provider_page_cache_is_skipped_during_a_rebuild(self):
        from .provider_import.providers.dornatv import DornatvConnector

        connector = DornatvConnector()
        path = '/movie/film-2026/'
        with mock.patch.object(connector, '_cacheable_detail_path', return_value=True):
            connector._detail_to_cache(path, '<html>old</html>')
            self.assertEqual(connector._detail_from_cache(path), '<html>old</html>')
            with title_rebuild.fresh_fetch():
                self.assertIsNone(connector._detail_from_cache(path))
