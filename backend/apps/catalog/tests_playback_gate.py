"""Tests for the test an online-playback link has to pass.

The catalog used to pick its playback URL by reading the file name, which has
no floor: when a title's only sources are x265 MKVs, the best MKV still became
``video_url`` and the title shipped as watchable to browsers that cannot demux
MKV at all. These tests pin the replacement and, just as importantly, the
limits that stop it doing damage of its own:

* only a positive "every candidate is gone" may clear a link — an unreachable
  host, an ffprobe timeout or a spent probe budget never does;
* an importer may never clear a link at all, whatever it finds;
* an undecodable-but-real source is *routed*, not deleted, because that is what
  the playback gateway exists for;
* not knowing falls back to the old filename heuristic, so the gate is never
  worse than what it replaced;
* and even a positive "gone" does not delete on its own: these CDNs refuse
  requests for files that are really there, so the sweep waits for a second
  verdict from a separate run before it blanks a link.
"""

from datetime import timedelta
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.catalog import playback_gate as gate
from apps.catalog.media_probe import Probe
from apps.catalog.models import (
    Episode, Movie, PlaybackMode, PlaybackSourceGap, Season, Series,
)

MP4 = 'https://cdn.example/Film.2021.1080p.x264.mp4'
MKV = 'https://cdn.example/Film.2021.1080p.x265.mkv'
HLS = 'https://cdn.example/film/master.m3u8'


def live(url=MP4, *, ranges=True):
    return Probe(
        url=url, verdict='live', reason='', status=206,
        content_type='video/mp4', content_length=900_000_000, accept_ranges=ranges,
    )


def dead(url=MP4, reason='http_404'):
    return Probe(url=url, verdict='dead', reason=reason, status=404)


def unreachable(url=MP4, reason='timeout'):
    return Probe(url=url, verdict='unknown', reason=reason)


def safe(container='mp4', video='h264'):
    return {'verdict': 'safe', 'reason': '', 'container': container, 'video': video, 'audio': 'aac'}


def unsafe(reason='container_matroska'):
    return {'verdict': 'unsafe', 'reason': reason, 'container': 'matroska', 'video': 'hevc', 'audio': 'ac3'}


def inconclusive(reason='ffprobe_timeout'):
    return {'verdict': 'unknown', 'reason': reason}


class _Base(TestCase):
    def movie(self, links=None, video_url='', **kw):
        return Movie.objects.create(
            title='فیلم', slug=kw.pop('slug', 'film'), is_published=True,
            download_links=links or [], video_url=video_url, **kw,
        )

    def series(self, links=None, **kw):
        return Series.objects.create(
            title='سریال', slug=kw.pop('slug', 'serial'), is_published=True,
            download_links=links or [], **kw,
        )

    def probes(self, probe_map, tech_map=None):
        """Patch both probe layers with per-URL answers."""
        tech_map = tech_map or {}
        return (
            patch('apps.catalog.media_probe.probe_url', side_effect=lambda url, **kw: probe_map[url]),
            patch('apps.catalog.media_probe.probe_manifest', side_effect=lambda url, **kw: probe_map[url]),
            patch('apps.catalog.media_tech.verify_source',
                  side_effect=lambda url, **kw: tech_map.get(url, inconclusive())),
        )

    def run_with(self, probe_map, tech_map=None):
        """Context-manager stack for the three patches above."""
        from contextlib import ExitStack

        stack = ExitStack()
        for patcher in self.probes(probe_map, tech_map):
            stack.enter_context(patcher)
        return stack


class TestSourceTests(_Base):
    """What one candidate URL is judged to be, and why."""

    def test_object_storage_key_is_trusted_without_a_probe(self):
        """Our own HLS output. There is no third party here to distrust."""
        with patch('apps.catalog.media_probe.probe_url') as probe:
            verdict = gate.test_source('catalog/hls/12/master.m3u8')
        self.assertEqual(verdict.mode, gate.MODE_DIRECT)
        self.assertEqual(verdict.reason, 'internal_storage')
        probe.assert_not_called()

    def test_empty_url_is_none(self):
        self.assertEqual(gate.test_source('   ').mode, gate.MODE_NONE)

    def test_gone_file_is_the_only_dead_verdict(self):
        with self.run_with({MP4: dead()}):
            verdict = gate.test_source(MP4)
        self.assertEqual(verdict.mode, gate.MODE_NONE)
        self.assertEqual(verdict.reason, 'http_404')

    def test_unreachable_host_is_unverified_not_dead(self):
        """A CDN outage is not a broken film."""
        with self.run_with({MP4: unreachable()}):
            verdict = gate.test_source(MP4)
        self.assertEqual(verdict.mode, gate.MODE_UNVERIFIED)
        self.assertFalse(verdict.dead)

    def test_probe_exception_is_unverified(self):
        with patch('apps.catalog.media_probe.probe_url', side_effect=RuntimeError('boom')):
            verdict = gate.test_source(MP4)
        self.assertEqual(verdict.mode, gate.MODE_UNVERIFIED)
        self.assertEqual(verdict.reason, 'probe_error')

    def test_no_byte_ranges_routes_to_the_gateway(self):
        """Without ranges there is no seek and no resume, however fine the file."""
        with self.run_with({MP4: live(ranges=False)}, {MP4: safe()}):
            verdict = gate.test_source(MP4)
        self.assertEqual(verdict.mode, gate.MODE_GATEWAY)
        self.assertEqual(verdict.reason, 'no_byte_ranges')

    def test_manifest_does_not_need_byte_ranges(self):
        with self.run_with({HLS: live(HLS, ranges=False)}, {HLS: safe('hls')}):
            verdict = gate.test_source(HLS)
        self.assertEqual(verdict.mode, gate.MODE_DIRECT)

    def test_reachable_seekable_and_decodable_is_direct(self):
        with self.run_with({MP4: live()}, {MP4: safe()}):
            verdict = gate.test_source(MP4)
        self.assertEqual(verdict.mode, gate.MODE_DIRECT)
        self.assertEqual(verdict.tech['container'], 'mp4')

    def test_matroska_behind_an_mp4_name_is_caught_by_ffprobe(self):
        """The failure a filename check can never see: the name says mp4."""
        with self.run_with({MP4: live()}, {MP4: unsafe()}):
            verdict = gate.test_source(MP4)
        self.assertEqual(verdict.mode, gate.MODE_GATEWAY)
        self.assertEqual(verdict.reason, 'container_matroska')

    def test_inconclusive_ffprobe_falls_back_to_the_old_heuristic(self):
        with self.run_with({MP4: live()}, {MP4: inconclusive()}):
            good = gate.test_source(MP4)
        with self.run_with({MKV: live(MKV)}, {MKV: inconclusive()}):
            bad = gate.test_source(MKV)
        self.assertEqual(good.mode, gate.MODE_DIRECT)
        self.assertEqual(bad.mode, gate.MODE_GATEWAY)
        # Said so, so the row is re-tested rather than trusted.
        self.assertTrue(good.reason.startswith('name_only:'))

    def test_allow_tech_false_skips_ffprobe_entirely(self):
        with self.run_with({MP4: live()}, {MP4: unsafe()}) as _stack:
            with patch('apps.catalog.media_tech.verify_source') as tech:
                verdict = gate.test_source(MP4, allow_tech=False)
        tech.assert_not_called()
        self.assertEqual(verdict.reason, 'name_only')


class RankCandidatesTests(_Base):
    """Ordering only decides what to probe first. It never decides the outcome."""

    def test_browser_safe_container_is_probed_before_mkv(self):
        ranked = gate.rank_candidates([
            {'url': MKV, 'quality': '1080p'},
            {'url': MP4, 'quality': '1080p'},
        ])
        self.assertEqual([row['url'] for row in ranked], [MP4, MKV])

    def test_sidecars_are_not_playback_candidates(self):
        ranked = gate.rank_candidates([
            {'url': 'https://cdn.example/Film.2021.fa.srt', 'quality': ''},
            {'url': MP4, 'quality': '1080p'},
        ])
        self.assertEqual([row['url'] for row in ranked], [MP4])

    def test_duplicate_urls_are_probed_once(self):
        ranked = gate.rank_candidates([{'url': MP4}, {'url': MP4}])
        self.assertEqual(len(ranked), 1)


class ChooseTests(_Base):
    """Which link the title ends up serving."""

    def test_stops_at_the_first_source_that_passes(self):
        with self.run_with({MP4: live()}, {MP4: safe()}) as _s:
            with patch('apps.catalog.media_probe.probe_url', return_value=live()) as probe:
                choice = gate.choose_playback_link(
                    [{'url': MP4}, {'url': 'https://cdn.example/b.1080p.mp4'}],
                )
        self.assertEqual(choice.mode, gate.MODE_DIRECT)
        self.assertEqual(probe.call_count, 1)

    def test_mkv_only_title_keeps_its_link_and_is_routed(self):
        """The central regression: 10,495 movies looked like this."""
        with self.run_with({MKV: live(MKV)}, {MKV: unsafe()}):
            choice = gate.choose_playback_link([{'url': MKV, 'quality': '1080p x265'}])
        self.assertEqual(choice.mode, gate.MODE_GATEWAY)
        self.assertEqual(choice.url, MKV)

    def test_a_routed_source_beats_an_unmeasurable_one(self):
        other = 'https://cdn.example/Film.720p.mp4'
        with self.run_with({MP4: unreachable(), other: live(other, ranges=False)}):
            choice = gate.choose_playback_link([{'url': MP4}, {'url': other}])
        self.assertEqual(choice.mode, gate.MODE_GATEWAY)
        self.assertEqual(choice.url, other)

    def test_every_candidate_gone_is_the_only_none(self):
        with self.run_with({MP4: dead(), MKV: dead(MKV)}):
            choice = gate.choose_playback_link([{'url': MP4}, {'url': MKV}])
        self.assertEqual(choice.mode, gate.MODE_NONE)
        self.assertEqual(choice.reason, 'all_candidates_dead')

    def test_a_spent_budget_never_condemns_untested_mirrors(self):
        # Sized off the budget, not off a number that happened to exceed it:
        # MAX_CANDIDATES is tunable, and this invariant holds at any value.
        links = [{'url': f'https://cdn.example/m{index}.1080p.mp4'}
                 for index in range(gate.MAX_CANDIDATES + 4)]
        probe_map = {row['url']: dead(row['url']) for row in links}
        with self.run_with(probe_map):
            choice = gate.choose_playback_link(links, current=links[0]['url'])
        self.assertEqual(choice.mode, gate.MODE_UNVERIFIED)
        self.assertEqual(choice.reason, 'partially_probed')
        self.assertEqual(choice.tested, gate.MAX_CANDIDATES)

    def test_no_video_candidates_at_all(self):
        choice = gate.choose_playback_link([{'url': 'https://cdn.example/a.srt'}])
        self.assertEqual(choice.mode, gate.MODE_NONE)
        self.assertEqual(choice.reason, 'no_candidates')

    def test_ffprobe_budget_is_capped_per_title(self):
        links = [{'url': f'https://cdn.example/m{index}.1080p.mp4'} for index in range(5)]
        probe_map = {row['url']: live(row['url'], ranges=False) for row in links}
        with self.run_with(probe_map) as _s:
            with patch('apps.catalog.media_tech.verify_source', return_value=unsafe()) as tech:
                gate.choose_playback_link(links)
        # Every one of these fails on byte ranges before ffprobe is reached.
        self.assertEqual(tech.call_count, 0)

    @override_settings(CATALOG_VERIFY_PLAYBACK_LINK=False)
    def test_flag_off_restores_the_old_behaviour_and_says_so(self):
        with patch('apps.catalog.media_probe.probe_url') as probe:
            choice = gate.choose_playback_link([{'url': MKV}, {'url': MP4}])
        probe.assert_not_called()
        self.assertEqual(choice.mode, gate.MODE_UNVERIFIED)
        self.assertEqual(choice.reason, 'gate_disabled')
        self.assertEqual(choice.url, MP4)


class ApplyChoiceTests(_Base):
    """What a verdict is allowed to write."""

    def test_direct_choice_stores_link_and_verdict(self):
        movie = self.movie()
        fields = gate.apply_choice(
            movie, gate.PlaybackChoice(url=MP4, mode=gate.MODE_DIRECT),
        )
        self.assertEqual(movie.video_url, MP4)
        self.assertEqual(movie.playback_mode, PlaybackMode.DIRECT)
        self.assertIn('playback_checked_at', fields)
        self.assertIsNotNone(movie.playback_checked_at)

    def test_unverified_never_replaces_a_working_link(self):
        movie = self.movie(video_url=MP4)
        gate.apply_choice(movie, gate.PlaybackChoice(url=MKV, mode=gate.MODE_UNVERIFIED))
        self.assertEqual(movie.video_url, MP4)

    def test_unverified_still_fills_an_empty_link(self):
        movie = self.movie()
        gate.apply_choice(movie, gate.PlaybackChoice(url=MKV, mode=gate.MODE_UNVERIFIED))
        self.assertEqual(movie.video_url, MKV)

    def test_none_clears_only_when_clearing_is_allowed(self):
        movie = self.movie(video_url=MP4)
        gate.apply_choice(movie, gate.PlaybackChoice(mode=gate.MODE_NONE), allow_clear=False)
        self.assertEqual(movie.video_url, MP4)
        gate.apply_choice(movie, gate.PlaybackChoice(mode=gate.MODE_NONE), allow_clear=True)
        self.assertEqual(movie.video_url, '')
        self.assertEqual(movie.playback_mode, PlaybackMode.NONE)


class GateLinksTests(_Base):
    """The call every import path makes."""

    def test_an_import_can_never_blank_a_link(self):
        """A bad network day must not empty the catalog."""
        movie = self.movie(links=[{'url': MP4}], video_url=MP4)
        with self.run_with({MP4: dead()}):
            choice, fields = gate.gate_links(movie, movie.download_links)
        self.assertEqual(choice.mode, gate.MODE_NONE)
        self.assertEqual(movie.video_url, MP4)
        self.assertNotIn('video_url', fields)

    def test_import_promotes_a_tested_mp4_over_the_incumbent_mkv(self):
        movie = self.movie(links=[{'url': MKV}, {'url': MP4}], video_url=MKV)
        with self.run_with({MP4: live(), MKV: live(MKV)}, {MP4: safe()}):
            choice, fields = gate.gate_links(movie, movie.download_links)
        self.assertEqual(choice.mode, gate.MODE_DIRECT)
        self.assertEqual(movie.video_url, MP4)
        self.assertIn('video_url', fields)


class CandidateLinksTests(_Base):
    """An episode's links live on its series, so they have to be scoped."""

    def setUp(self):
        self.show = self.series([
            {'url': 'https://cdn.example/Show.S01E01.1080p.mp4'},
            {'url': 'https://cdn.example/Show.S01E07.1080p.mp4'},
        ])
        season = Season.objects.create(series=self.show, season_number=1, title='S1', is_published=True)
        self.episode = Episode.objects.create(
            season=season, episode_number=7, title='E7', is_published=True,
        )

    def test_only_this_episodes_sources_are_candidates(self):
        rows = gate.candidate_links(self.show, self.episode)
        self.assertEqual(
            [row['url'] for row in rows],
            ['https://cdn.example/Show.S01E07.1080p.mp4'],
        )

    def test_the_link_in_use_is_tested_first(self):
        self.episode.video_url = 'https://cdn.example/Show.S01E07.720p.mp4'
        rows = gate.candidate_links(self.show, self.episode)
        self.assertEqual(rows[0]['url'], self.episode.video_url)


class SweepCommandTests(_Base):
    """The backfill over titles that are already on the site."""

    def call(self, **kw):
        options = {'verbosity': 0, 'quiet': True, 'recheck_hours': 0}
        options.update(kw)
        return call_command('verify_playback_links', **options)

    def test_a_routed_title_is_marked_and_queued_for_a_re_crawl(self):
        movie = self.movie(links=[{'url': MKV}], video_url=MKV)
        with self.run_with({MKV: live(MKV)}, {MKV: unsafe()}):
            self.call(movies=True, limit=10)
        movie.refresh_from_db()
        self.assertEqual(movie.playback_mode, PlaybackMode.GATEWAY)
        self.assertEqual(movie.video_url, MKV)
        gap = PlaybackSourceGap.objects.get(object_id=movie.pk)
        self.assertEqual(gap.status, PlaybackSourceGap.Status.OPEN)
        self.assertEqual(gap.reason, 'needs_gateway')

    def test_a_title_that_now_passes_closes_its_gap(self):
        movie = self.movie(links=[{'url': MP4}], video_url=MP4)
        with self.run_with({MP4: live()}, {MP4: unsafe()}):
            self.call(movies=True, limit=10)
        self.assertTrue(PlaybackSourceGap.objects.filter(
            object_id=movie.pk, status=PlaybackSourceGap.Status.OPEN,
        ).exists())
        with self.run_with({MP4: live()}, {MP4: safe()}):
            self.call(movies=True, limit=10)
        movie.refresh_from_db()
        self.assertEqual(movie.playback_mode, PlaybackMode.DIRECT)
        self.assertFalse(PlaybackSourceGap.objects.filter(
            object_id=movie.pk, status=PlaybackSourceGap.Status.OPEN,
        ).exists())

    def test_a_first_gone_verdict_records_the_problem_without_deleting(self):
        """One sighting starts the repair; it does not do the damage.

        Provider CDNs answer the same ranged GET differently minute to minute,
        so the first "every candidate is gone" is recorded and queued for a
        re-crawl — the link itself stays, because a viewer with a working link
        to a flapping host is better off than a viewer with no link at all.
        """
        movie = self.movie(links=[{'url': MP4}], video_url=MP4)
        with self.run_with({MP4: dead()}):
            self.call(movies=True, limit=10)
        movie.refresh_from_db()
        self.assertEqual(movie.video_url, MP4)
        self.assertEqual(movie.playback_mode, PlaybackMode.NONE)
        self.assertTrue(PlaybackSourceGap.objects.filter(
            object_id=movie.pk, reason='no_playable_source',
        ).exists())

    def test_a_second_gone_verdict_a_day_later_clears_the_link(self):
        """Two separate runs, far enough apart not to share one bad night on a
        CDN, and the repair queued in between found nothing: now it is gone."""
        movie = self.movie(links=[{'url': MP4}], video_url=MP4)
        movie.playback_mode = PlaybackMode.NONE
        movie.playback_checked_at = timezone.now() - timedelta(hours=21)
        movie.save(update_fields=['playback_mode', 'playback_checked_at'])
        with self.run_with({MP4: dead()}):
            self.call(movies=True, limit=10)
        movie.refresh_from_db()
        self.assertEqual(movie.video_url, '')
        self.assertEqual(movie.playback_mode, PlaybackMode.NONE)

    def test_two_verdicts_an_hour_apart_are_one_outage_not_two_opinions(self):
        movie = self.movie(links=[{'url': MP4}], video_url=MP4)
        movie.playback_mode = PlaybackMode.NONE
        movie.playback_checked_at = timezone.now() - timedelta(hours=1)
        movie.save(update_fields=['playback_mode', 'playback_checked_at'])
        with self.run_with({MP4: dead()}):
            self.call(movies=True, limit=10)
        movie.refresh_from_db()
        self.assertEqual(movie.video_url, MP4)

    def test_a_title_that_recovered_does_not_carry_its_old_strike(self):
        """DIRECT between two failures resets the count: the second failure is
        a first sighting again, because the title demonstrably came back."""
        movie = self.movie(links=[{'url': MP4}], video_url=MP4)
        movie.playback_mode = PlaybackMode.DIRECT
        movie.playback_checked_at = timezone.now() - timedelta(days=30)
        movie.save(update_fields=['playback_mode', 'playback_checked_at'])
        with self.run_with({MP4: dead()}):
            self.call(movies=True, limit=10)
        movie.refresh_from_db()
        self.assertEqual(movie.video_url, MP4)

    def test_dry_run_writes_nothing(self):
        movie = self.movie(links=[{'url': MKV}], video_url=MKV)
        with self.run_with({MKV: live(MKV)}, {MKV: unsafe()}):
            self.call(movies=True, limit=10, dry_run=True)
        movie.refresh_from_db()
        self.assertEqual(movie.playback_mode, PlaybackMode.UNVERIFIED)
        self.assertIsNone(movie.playback_checked_at)
        self.assertFalse(PlaybackSourceGap.objects.exists())

    def test_never_checked_titles_are_swept_before_rechecked_ones(self):
        fresh = self.movie(slug='fresh', links=[{'url': MP4}], video_url=MP4)
        fresh.playback_checked_at = timezone.now()
        fresh.save(update_fields=['playback_checked_at'])
        never = self.movie(slug='never', links=[{'url': MP4}], video_url=MP4)
        with self.run_with({MP4: live()}, {MP4: safe()}):
            self.call(movies=True, limit=1)
        never.refresh_from_db()
        self.assertEqual(never.playback_mode, PlaybackMode.DIRECT)

    def test_one_gap_per_series_however_many_episodes_fail(self):
        show = self.series([
            {'url': 'https://cdn.example/Show.S01E01.1080p.x265.mkv'},
            {'url': 'https://cdn.example/Show.S01E02.1080p.x265.mkv'},
        ])
        season = Season.objects.create(series=show, season_number=1, title='S1', is_published=True)
        for number in (1, 2):
            Episode.objects.create(
                season=season, episode_number=number, title=f'E{number}',
                is_published=True,
                video_url=f'https://cdn.example/Show.S01E0{number}.1080p.x265.mkv',
            )
        probe_map = {
            link['url']: live(link['url']) for link in show.download_links
        }
        tech_map = {link['url']: unsafe() for link in show.download_links}
        with self.run_with(probe_map, tech_map):
            self.call(episodes=True, limit=10)
        self.assertEqual(
            Episode.objects.filter(playback_mode=PlaybackMode.GATEWAY).count(), 2,
        )
        self.assertEqual(PlaybackSourceGap.objects.filter(object_id=show.pk).count(), 1)

    def test_an_untested_verdict_never_deletes_however_often_it_repeats(self):
        """``no_candidates`` is not a test result.

        Every link skipped before a request went out — the usual cause is that
        all of this title's signed URLs expired — must leave the link alone no
        matter how many runs agree, because no run asked a server anything. The
        repair is still queued: a refreshed signature is what fixes it.
        """
        movie = self.movie(links=[], video_url=MP4)
        movie.playback_mode = PlaybackMode.NONE
        movie.playback_checked_at = timezone.now() - timedelta(days=9)
        movie.save(update_fields=['playback_mode', 'playback_checked_at'])
        with patch.object(gate, 'rank_candidates', return_value=[]):
            self.call(movies=True, limit=10)
        movie.refresh_from_db()
        self.assertEqual(movie.video_url, MP4)
        self.assertTrue(PlaybackSourceGap.objects.filter(object_id=movie.pk).exists())

    def test_shards_split_the_catalog_without_overlap(self):
        made = [self.movie(slug=f'shard-{n}', links=[{'url': MP4}], video_url=MP4)
                for n in range(6)]
        seen: set[int] = set()
        for shard in range(3):
            with self.run_with({MP4: live()}, {MP4: safe()}):
                self.call(movies=True, limit=50, shards=3, shard=shard)
            done = {m.pk for m in made if m.pk % 3 == shard}
            self.assertTrue(done.isdisjoint(seen))
            seen |= done
        self.assertEqual(seen, {m.pk for m in made})

    def test_a_sweep_longer_than_one_chunk_visits_every_title_exactly_once(self):
        """The loop rewrites the column the queryset is ordered by.

        A full shard is too large to hold in memory, so the sweep takes a
        snapshot of ids and reloads them a chunk at a time. That snapshot is
        the point: stamping ``playback_checked_at`` moves a row to the back of
        a live "stalest first" cursor, which would serve some rows twice and
        never reach others. Five titles across chunks of two would expose it.
        """
        urls = [f'https://cdn.example/Film{n}.1080p.x264.mp4' for n in range(5)]
        for n, url in enumerate(urls):
            self.movie(slug=f'chunked-{n}', links=[{'url': url}], video_url=url)
        probe_map = {url: live(url) for url in urls}
        tech_map = {url: safe() for url in urls}

        with patch('apps.catalog.management.commands.verify_playback_links.FETCH_CHUNK', 2):
            with self.run_with(probe_map, tech_map):
                self.call(movies=True, limit=50)

        swept = Movie.objects.filter(slug__startswith='chunked-')
        self.assertEqual(swept.count(), 5)
        for movie in swept:
            self.assertEqual(movie.playback_mode, PlaybackMode.DIRECT)
            self.assertIsNotNone(movie.playback_checked_at)

    def test_a_title_deleted_mid_sweep_is_skipped_not_fatal(self):
        """The snapshot is a list of ids, so some of them can stop existing.

        A backfill over the whole catalogue runs for hours next to the admin
        and the importer. A row unpublished or deleted in that window must drop
        out of the sweep quietly, not take the rest of the chunk with it.
        """
        for n in range(3):
            self.movie(slug=f'vanishing-{n}', links=[{'url': MP4}], video_url=MP4)
        doomed = Movie.objects.get(slug='vanishing-2')
        survivor = Movie.objects.get(slug='vanishing-1')
        real_choose = gate.choose_playback_link

        def delete_the_last_one(*a, **kw):
            Movie.objects.filter(pk=doomed.pk).delete()
            return real_choose(*a, **kw)

        with patch('apps.catalog.management.commands.verify_playback_links.FETCH_CHUNK', 1):
            with patch('apps.catalog.playback_gate.choose_playback_link',
                       side_effect=delete_the_last_one):
                with self.run_with({MP4: live()}, {MP4: safe()}):
                    self.call(movies=True, limit=50)

        survivor.refresh_from_db()
        self.assertEqual(survivor.playback_mode, PlaybackMode.DIRECT)
        self.assertFalse(Movie.objects.filter(pk=doomed.pk).exists())

    def test_a_shard_outside_the_split_is_refused(self):
        with self.assertRaises(CommandError):
            self.call(movies=True, shards=3, shard=3)

    def test_ids_need_a_single_kind(self):
        with self.assertRaises(CommandError):
            self.call(ids='1,2')

    def test_a_row_with_no_link_is_not_this_sweeps_problem(self):
        self.movie(links=[{'url': MP4}])
        with patch('apps.catalog.media_probe.probe_url') as probe:
            self.call(movies=True, limit=10)
        probe.assert_not_called()
