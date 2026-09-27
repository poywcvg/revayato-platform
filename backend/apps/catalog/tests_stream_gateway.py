"""Tests for the playback gateway.

Nothing here spawns ffmpeg or touches the network. The parts worth pinning down
are the ones that would fail *silently* in production: the path-traversal
boundary, the ownership check that keeps the endpoint from becoming an open
proxy, the playlist rewriter (whose last bug was rewriting durations), and the
reaper that is the only thing standing between this feature and a full disk.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.catalog import stream_gateway as gw
from apps.catalog.models import Movie


class _SessionRootMixin:
    """Give each test its own session root so the reaper cannot see real work."""

    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        patch = override_settings(STREAM_SESSION_ROOT=str(self.root))
        patch.enable()
        self.addCleanup(patch.disable)
        self.addCleanup(self._tmp.cleanup)

    def make_session(self, sid: str, *, pid: int = 0, beat_age: float = 0.0):
        """A session directory that looks exactly like a live one.

        ``pid`` defaults to 0 — deliberately not this process. A test must never
        write its own pid here: the reaper signals what it finds.
        """
        directory = self.root / sid
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'meta.json').write_text(json.dumps({
            'pid': pid,
            'start': 0.0,
            'created': time.time(),
            'tech': {'video_codec': 'h264', 'audio_codec': 'aac'},
        }), 'utf-8')
        # The heartbeat is the file's *contents*, not its mtime.
        (directory / 'beat').write_text(str(time.time() - beat_age), 'utf-8')
        return directory

    def spawn_stub_session(self, sid: str, **kwargs):
        """A session backed by a real process that looks like one of ours.

        Its command line carries the session directory and it leads its own
        process group, which is exactly what the gateway uses to decide that a
        process is genuinely its own.
        """
        directory = self.root / sid
        directory.mkdir(parents=True, exist_ok=True)
        # Two commands, so the shell cannot exec-optimize itself away and lose
        # the directory from its cmdline — the real ffmpeg keeps it, because
        # -hls_segment_filename names that directory.
        proc = subprocess.Popen(
            ['sh', '-c', f'sleep 600; : {directory}'],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        def cleanup():
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            proc.wait(timeout=5)

        self.addCleanup(cleanup)
        self.make_session(sid, pid=proc.pid, **kwargs)
        return proc


class SegmentNameBoundaryTests(_SessionRootMixin, TestCase):
    """``name`` comes straight off the URL, so this is a security boundary."""

    def test_accepts_the_two_real_shapes(self):
        self.assertTrue(str(gw.segment_file('s', 'init.mp4')).endswith('/s/init.mp4'))
        self.assertTrue(str(gw.segment_file('s', 'seg00042.m4s')).endswith('/s/seg00042.m4s'))

    def test_rejects_traversal_and_lookalikes(self):
        for bad in ('../meta.json', '..%2Fmeta.json', 'seg1.m4s', 'seg000001.m4s',
                    'init.mp4.bak', '/etc/passwd', 'ffmpeg.log', 'meta.json',
                    'init.mp4\n', '', 'seg00001.m4s/../meta.json'):
            with self.subTest(name=bad):
                with self.assertRaises(gw.StreamGatewayError):
                    gw.segment_file('s', bad)

    def test_a_segment_path_never_escapes_its_session(self):
        # Belt and braces: whatever the pattern admits must stay inside.
        path = gw.segment_file('sess', 'seg00001.m4s').resolve()
        self.assertTrue(str(path).startswith(str((self.root / 'sess').resolve())))


class SessionIdentityTests(TestCase):
    def test_same_url_and_position_share_one_session(self):
        # This is what lets two viewers at the same point in a film share a
        # single ffmpeg process instead of each starting their own.
        url = 'https://cdn.example/a.mkv'
        self.assertEqual(gw.session_id(url, 300.0), gw.session_id(url, 300.04))

    def test_different_position_is_a_different_session(self):
        url = 'https://cdn.example/a.mkv'
        self.assertNotEqual(gw.session_id(url, 300.0), gw.session_id(url, 900.0))

    def test_different_source_is_a_different_session(self):
        self.assertNotEqual(
            gw.session_id('https://cdn.example/a.mkv', 0.0),
            gw.session_id('https://cdn.example/b.mkv', 0.0),
        )


class CandidateClassificationTests(TestCase):
    def test_browser_hostile_containers_are_candidates(self):
        for url in ('https://cdn.example/Film.1080p.mkv',
                    'https://cdn.example/Film.avi?md5=x&expires=1',
                    'https://cdn.example/Film.ts'):
            with self.subTest(url=url):
                self.assertTrue(gw.container_needs_rewrap(url))
                self.assertTrue(gw.gateway_candidate(url))

    def test_friendly_containers_need_no_rewrap(self):
        for url in ('https://cdn.example/Film.mp4',
                    'https://cdn.example/Film.webm',
                    'https://cdn.example/stream/index.m3u8'):
            with self.subTest(url=url):
                self.assertFalse(gw.container_needs_rewrap(url))
                # Still a candidate: an MP4 can hold HEVC, which only a probe
                # reveals — the filename is a hint, never the verdict.
                self.assertTrue(gw.gateway_candidate(url))

    def test_non_http_sources_are_never_candidates(self):
        for url in ('magnet:?xt=urn:btih:abc', 'file:///etc/passwd', '', 'ftp://x/y.mkv'):
            with self.subTest(url=url):
                self.assertFalse(gw.gateway_candidate(url))


class PlaylistRewriteTests(_SessionRootMixin, TestCase):
    def test_names_are_rewritten_and_durations_are_not(self):
        directory = self.make_session('abc')
        (directory / 'index.m3u8').write_text(
            '#EXTM3U\n'
            '#EXT-X-VERSION:7\n'
            '#EXT-X-TARGETDURATION:11\n'
            '#EXT-X-PLAYLIST-TYPE:EVENT\n'
            '#EXT-X-MAP:URI="init.mp4"\n'
            '#EXTINF:10.375000,\n'
            'seg00000.m4s\n'
            '#EXTINF:9.958667,\n'
            'seg00001.m4s\n',
            'utf-8',
        )
        text = gw.playlist_text('abc', url_for=lambda name: f'/api/stream/abc/{name}')

        self.assertIn('#EXT-X-MAP:URI="/api/stream/abc/init.mp4"', text)
        self.assertIn('/api/stream/abc/seg00000.m4s', text)
        self.assertIn('/api/stream/abc/seg00001.m4s', text)
        # The previous design's fatal bug was inventing these numbers. ffmpeg
        # knows where the keyframes are; we must repeat it verbatim.
        self.assertIn('#EXTINF:10.375000,', text)
        self.assertIn('#EXTINF:9.958667,', text)
        self.assertNotIn('\nseg00000.m4s', text)


class ReaperTests(_SessionRootMixin, TestCase):
    def test_a_beating_session_survives(self):
        self.make_session('live')
        gw.reap_sessions()
        self.assertTrue((self.root / 'live').exists())

    def test_an_idle_session_is_removed(self):
        self.make_session('idle', beat_age=gw.SESSION_IDLE_SECONDS + 30)
        self.assertEqual(gw.reap_sessions(), 1)
        self.assertFalse((self.root / 'idle').exists())

    def test_debris_without_metadata_is_cleaned_up(self):
        # A crash between mkdir and the meta write would otherwise leave a
        # directory nothing ever looks at again.
        debris = self.root / 'debris'
        debris.mkdir()
        old = time.time() - 900
        os.utime(debris, (old, old))
        gw.reap_sessions()
        self.assertFalse(debris.exists())

    def test_reaping_an_empty_root_is_not_an_error(self):
        self.assertEqual(gw.reap_sessions(), 0)

    def test_a_stale_pid_is_never_signalled(self):
        # Regression: the reaper used to call killpg() with a *pid*. meta.json
        # outlives its process and Linux recycles pids, so a stale entry could
        # name an unrelated process group — in the worst case this worker's
        # own. Here the pid is this very test process: reaping must clean the
        # directory and leave the process completely alone.
        self.make_session('stale', pid=os.getpid(),
                          beat_age=gw.SESSION_IDLE_SECONDS + 30)
        self.assertEqual(gw.reap_sessions(), 1)
        self.assertFalse((self.root / 'stale').exists())
        # Reaching this line at all is the assertion that matters.
        self.assertTrue(gw._pid_alive(os.getpid()))

    def test_our_own_process_is_not_mistaken_for_a_session(self):
        self.make_session('mine', pid=os.getpid())
        self.assertFalse(gw._pid_owns_session(os.getpid(), 'mine'))
        self.assertIsNone(gw._session_pgid(os.getpid()))

    def test_a_real_session_process_is_recognised_and_killed(self):
        proc = self.spawn_stub_session('real', beat_age=gw.SESSION_IDLE_SECONDS + 30)
        self.assertTrue(gw._pid_owns_session(proc.pid, 'real'))
        self.assertEqual(gw.reap_sessions(), 1)
        self.assertFalse((self.root / 'real').exists())
        proc.wait(timeout=10)
        self.assertFalse(gw._pid_alive(proc.pid))

    def test_a_live_session_process_survives_a_reap(self):
        proc = self.spawn_stub_session('busy')
        self.assertEqual(gw.reap_sessions(), 0)
        self.assertTrue((self.root / 'busy').exists())
        self.assertIsNone(proc.poll())


class SourceTechTests(TestCase):
    def test_h264_is_copied_not_transcoded(self):
        tech = gw.SourceTech(ok=True, container='matroska', video_codec='h264',
                             audio_codec='aac', duration=7200.0)
        self.assertTrue(tech.video_copyable)
        self.assertFalse(tech.needs_transcode)
        self.assertTrue(tech.seekable)

    def test_hevc_requires_transcode(self):
        tech = gw.SourceTech(ok=True, container='matroska', video_codec='hevc',
                             audio_codec='aac', duration=7200.0)
        self.assertFalse(tech.video_copyable)
        self.assertTrue(tech.needs_transcode)

    def test_a_failed_probe_asks_for_nothing(self):
        tech = gw.SourceTech(ok=False, reason='unreachable')
        self.assertFalse(tech.needs_transcode)
        self.assertFalse(tech.seekable)


class SignedSourceTests(TestCase):
    def test_round_trip_preserves_the_url(self):
        url = 'https://cdn.example/Film.mkv?md5=abc&expires=123'
        payload = gw.unsign_source(gw.sign_source(url, kind='movie', obj_id=7))
        self.assertEqual(payload['u'], url)
        self.assertEqual(payload['k'], 'movie')
        self.assertEqual(payload['o'], 7)

    def test_the_provider_signature_never_appears_in_the_token(self):
        # The point of signing is to keep ?md5=…&expires=… out of our own URLs
        # and out of browser history.
        token = gw.sign_source('https://cdn.example/Film.mkv?md5=secret123',
                               kind='movie', obj_id=7)
        self.assertNotIn('secret123', token)

    def test_a_tampered_token_is_refused(self):
        token = gw.sign_source('https://cdn.example/a.mkv', kind='movie', obj_id=1)
        with self.assertRaises(gw.StreamGatewayError):
            gw.unsign_source(token[:-4] + 'zzzz')

    def test_garbage_is_refused_rather_than_crashing(self):
        for bad in ('', 'not-a-token', '...'):
            with self.subTest(token=bad):
                with self.assertRaises(gw.StreamGatewayError):
                    gw.unsign_source(bad)


@override_settings(REST_FRAMEWORK={
    'DEFAULT_THROTTLE_CLASSES': [],
    'DEFAULT_THROTTLE_RATES': {'stream_open': None, 'stream_segment': None},
    'DEFAULT_RENDERER_CLASSES': ('rest_framework.renderers.JSONRenderer',),
})
class StreamOpenOwnershipTests(_SessionRootMixin, TestCase):
    """``stream_open`` must only ever be pointable at our own catalog's bytes."""

    def setUp(self):
        super().setUp()
        self.movie = Movie.objects.create(
            title='فیلم آزمایشی',
            original_title='Test Film',
            slug='test-film-gateway',
            is_published=True,
            video_url='https://cdn.example/Test.Film.1080p.mkv',
            download_links=[
                {'quality': '720p', 'url': 'https://cdn.example/Test.Film.720p.mkv'},
                {'quality': '1080p'},  # malformed entries must not explode
            ],
        )
        self.url = reverse('stream_open')

    def post(self, **payload):
        return self.client.post(self.url, data=payload,
                                content_type='application/json')

    def test_a_foreign_url_is_refused(self):
        response = self.post(kind='movie', id=self.movie.pk,
                             url='https://evil.example/anything.mkv')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['code'], 'unknown_source')

    def test_another_titles_url_is_refused(self):
        other = Movie.objects.create(
            title='دیگر', original_title='Other', slug='other-film-gateway',
            is_published=True, video_url='https://cdn.example/Other.mkv',
        )
        response = self.post(kind='movie', id=self.movie.pk, url=other.video_url)
        self.assertEqual(response.status_code, 404)

    def test_an_unpublished_title_exposes_nothing(self):
        self.movie.is_published = False
        self.movie.save(update_fields=['is_published'])
        response = self.post(kind='movie', id=self.movie.pk, url=self.movie.video_url)
        self.assertEqual(response.status_code, 404)

    def test_a_non_http_source_is_refused_before_any_lookup(self):
        response = self.post(kind='movie', id=self.movie.pk,
                             url='file:///etc/passwd')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'unsupported_source')

    def test_missing_fields_are_a_bad_request(self):
        for payload in ({'kind': 'movie'},
                        {'kind': 'nonsense', 'id': 1, 'url': 'https://x/y.mkv'},
                        {'id': self.movie.pk, 'url': self.movie.video_url}):
            with self.subTest(payload=payload):
                response = self.client.post(self.url, data=payload,
                                            content_type='application/json')
                self.assertEqual(response.status_code, 400)

    def test_download_links_are_accepted_as_owned_sources(self):
        # The gate must let a download_links entry through to the probe. The
        # probe itself is stubbed: this asserts ownership, not networking.
        stub = gw.SourceTech(ok=False, reason='stubbed')
        with mock.patch.object(gw, 'probe_tech', return_value=stub) as probe:
            response = self.post(kind='movie', id=self.movie.pk,
                                 url='https://cdn.example/Test.Film.720p.mkv')
        probe.assert_called_once_with('https://cdn.example/Test.Film.720p.mkv')
        self.assertEqual(response.json()['code'], 'probe_failed')

    def test_a_foreign_url_never_reaches_the_probe(self):
        # The ownership check has to come first, or the endpoint is a scanner:
        # anyone could make the server fetch arbitrary hosts.
        with mock.patch.object(gw, 'probe_tech') as probe:
            self.post(kind='movie', id=self.movie.pk,
                      url='https://evil.example/anything.mkv')
        probe.assert_not_called()

    def test_a_malformed_download_link_does_not_break_the_gate(self):
        # The second entry in this movie's download_links has no url at all.
        with mock.patch.object(gw, 'probe_tech') as probe:
            response = self.post(kind='movie', id=self.movie.pk,
                                 url='https://cdn.example/Other.Film.mkv')
        probe.assert_not_called()
        self.assertEqual(response.status_code, 404)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)


class SessionRouteTests(_SessionRootMixin, TestCase):
    def test_unknown_session_playlist_is_404(self):
        response = self.client.get('/api/stream/deadbeefdeadbeefdead/index.m3u8')
        self.assertEqual(response.status_code, 404)

    def test_unknown_session_segment_is_404(self):
        response = self.client.get('/api/stream/deadbeefdeadbeefdead/seg00000.m4s')
        self.assertEqual(response.status_code, 404)

    def test_a_traversal_segment_name_is_404_not_a_file(self):
        self.make_session('aaaabbbbccccddddeeee')
        response = self.client.get('/api/stream/aaaabbbbccccddddeeee/meta.json')
        self.assertEqual(response.status_code, 404)


class PruningTests(_SessionRootMixin, TestCase):
    """The box this runs on has a few gigabytes free, total.

    Without pruning a session holds everything it has ever written, so its disk
    cost is the film's length; with it, the cost is how far ffmpeg runs ahead.
    That difference is the difference between this feature working and the site
    going down, so the arithmetic is pinned here rather than trusted.
    """

    #: How many segments the gateway keeps behind the one being served.
    behind = gw.KEEP_BEHIND_SECONDS // gw.SEGMENT_SECONDS

    def make_segments(self, sid: str, count: int):
        directory = self.make_session(sid)
        for index in range(count):
            (directory / f'seg{index:05d}.m4s').write_bytes(b'x' * 16)
        (directory / 'init.mp4').write_bytes(b'i' * 8)
        # With no live pid, a finished playlist is what keeps the session
        # servable — which is exactly the shape these tests need.
        (directory / 'index.m3u8').write_text('#EXTM3U\n', 'utf-8')
        return directory

    def surviving(self, directory: Path) -> list[int]:
        return sorted(int(p.name[3:8]) for p in directory.glob('seg*.m4s'))

    def test_nothing_is_dropped_before_the_window_fills(self):
        directory = self.make_segments('early', self.behind)
        self.assertEqual(gw.prune_consumed('early', f'seg{self.behind - 1:05d}.m4s'), 0)
        self.assertEqual(len(self.surviving(directory)), self.behind)

    def test_everything_older_than_the_window_goes(self):
        directory = self.make_segments('rolling', 60)
        served = 50
        gw.prune_consumed('rolling', f'seg{served:05d}.m4s')
        # What is left starts exactly one window behind the segment served.
        self.assertEqual(self.surviving(directory)[0], served - self.behind)
        self.assertEqual(self.surviving(directory)[-1], 59)

    def test_a_second_pass_costs_nothing(self):
        # The loop stops at the first name already gone, so a session that has
        # been running for an hour does not walk a thousand dead indices on
        # every segment it serves.
        directory = self.make_segments('twice', 60)
        gw.prune_consumed('twice', 'seg00050.m4s')
        self.assertEqual(gw.prune_consumed('twice', 'seg00050.m4s'), 0)
        self.assertEqual(self.surviving(directory)[0], 50 - self.behind)

    def test_the_init_segment_is_never_pruned(self):
        # Every segment in the session needs it to decode; losing it would make
        # the whole stream unplayable rather than merely un-rewindable.
        directory = self.make_segments('init', 60)
        gw.prune_consumed('init', 'seg00050.m4s')
        self.assertTrue((directory / 'init.mp4').exists())
        self.assertEqual(gw.prune_consumed('init', 'init.mp4'), 0)
        self.assertTrue((directory / 'init.mp4').exists())

    def test_a_junk_name_prunes_nothing(self):
        directory = self.make_segments('junk', 60)
        self.assertEqual(gw.prune_consumed('junk', '../../etc/passwd'), 0)
        self.assertEqual(len(self.surviving(directory)), 60)

    def test_serving_a_segment_prunes_behind_it(self):
        directory = self.make_segments('aaaabbbbccccddddeeee', 60)
        response = self.client.get('/api/stream/aaaabbbbccccddddeeee/seg00050.m4s')
        self.assertEqual(response.status_code, 200)
        response.close()
        self.assertEqual(self.surviving(directory)[0], 50 - self.behind)

    def test_the_segment_being_served_survives_its_own_pruning(self):
        # It is opened before pruning runs, but it must also still be on disk:
        # the same viewer's player may well ask for it again after a stall.
        directory = self.make_segments('bbbbccccddddeeeeffff', 60)
        response = self.client.get('/api/stream/bbbbccccddddeeeeffff/seg00050.m4s')
        self.assertEqual(b''.join(response.streaming_content), b'x' * 16)
        response.close()
        self.assertTrue((directory / 'seg00050.m4s').exists())


class DiskBudgetTests(_SessionRootMixin, TestCase):
    def test_an_empty_root_measures_zero(self):
        self.assertEqual(gw.root_bytes(), 0)

    def test_every_session_counts_towards_the_total(self):
        for sid in ('one', 'two'):
            directory = self.make_session(sid)
            (directory / 'seg00000.m4s').write_bytes(b'x' * 1024)
        # meta.json and beat are counted too; the segments are the floor.
        self.assertGreaterEqual(gw.root_bytes(), 2048)

    def test_a_missing_root_is_zero_not_an_error(self):
        # The first request after a fresh container start arrives before
        # anything has created the directory.
        with override_settings(STREAM_SESSION_ROOT=str(self.root / 'not-there')):
            self.assertEqual(gw.root_bytes(), 0)

    def test_the_budget_has_a_floor_however_it_is_configured(self):
        with override_settings(STREAM_DISK_BUDGET_MB=1):
            self.assertEqual(gw.disk_budget_bytes(), 256 * 1024 * 1024)

    def test_a_full_volume_refuses_new_sessions_rather_than_filling_up(self):
        tech = gw.SourceTech(ok=True, container='matroska', video_codec='h264',
                             audio_codec='aac', duration=7200.0)
        budget = gw.disk_budget_bytes()
        with mock.patch.object(gw, 'root_bytes', return_value=budget):
            with mock.patch.object(gw.shutil, 'which', return_value='/usr/bin/ffmpeg'):
                with self.assertRaises(gw.StreamGatewayError) as caught:
                    gw.start_session('https://cdn.example/a.mkv', 0.0, tech)
        self.assertEqual(caught.exception.code, 'gateway_busy')
        # Refusing must not leave the directory it was about to use behind.
        self.assertFalse((self.root / gw.session_id('https://cdn.example/a.mkv', 0.0)).exists())


class SessionReuseTests(_SessionRootMixin, TestCase):
    """Sharing one ffmpeg between two viewers is worth a lot — but only while
    the session can still serve its own beginning."""

    def test_a_session_that_has_written_nothing_yet_is_reusable(self):
        self.make_session('young')
        self.assertTrue(gw.session_reusable('young'))

    def test_a_session_with_its_opening_intact_is_reusable(self):
        directory = self.make_session('intact')
        (directory / 'index.m3u8').write_text('#EXTM3U\n', 'utf-8')
        (directory / 'seg00000.m4s').write_bytes(b'x')
        self.assertTrue(gw.session_reusable('intact'))

    def test_a_pruned_session_is_not_handed_to_a_new_viewer(self):
        # Its playlist still lists seg00000, so a second viewer would 404 on
        # the first thing they fetched.
        directory = self.make_session('pruned')
        (directory / 'index.m3u8').write_text('#EXTM3U\n', 'utf-8')
        (directory / 'seg00040.m4s').write_bytes(b'x')
        self.assertFalse(gw.session_reusable('pruned'))

    def test_a_pruned_session_gets_the_arriving_viewer_their_own(self):
        url = 'https://cdn.example/a.mkv'
        sid = gw.session_id(url, 0.0)
        directory = self.make_session(sid)
        (directory / 'index.m3u8').write_text('#EXTM3U\n', 'utf-8')
        (directory / 'seg00040.m4s').write_bytes(b'x')
        tech = gw.SourceTech(ok=True, container='matroska', video_codec='h264',
                             audio_codec='aac', duration=7200.0)
        spawned: list[list[str]] = []

        class _Proc:
            pid = 999999

        def fake_popen(cmd, **kwargs):
            spawned.append(cmd)
            return _Proc()

        with mock.patch.object(gw.shutil, 'which', return_value='/usr/bin/ffmpeg'):
            with mock.patch.object(gw.subprocess, 'Popen', side_effect=fake_popen):
                fresh = gw.start_session(url, 0.0, tech)

        self.assertNotEqual(fresh, sid)
        self.assertTrue(spawned, 'a pruned session must not be reused, so ffmpeg has to run')
        # The viewer still watching the original is left entirely alone.
        self.assertTrue((directory / 'seg00040.m4s').exists())

    def test_the_salt_is_what_separates_two_sessions_at_one_point(self):
        plain = gw.session_id('https://cdn.example/a.mkv', 12.0)
        self.assertEqual(plain, gw.session_id('https://cdn.example/a.mkv', 12.0))
        self.assertNotEqual(plain, gw.session_id('https://cdn.example/a.mkv', 12.0, salt='ab12'))


class ReaperDaemonTests(_SessionRootMixin, TestCase):
    """The sweep must not start anywhere except the gateway container."""

    def setUp(self):
        super().setUp()
        # start_reaper() latches, so each test needs a clean slate.
        gw._REAPER_STARTED = False
        for fd in gw._REAPER_LOCK:
            os.close(fd)
        gw._REAPER_LOCK.clear()
        self.addCleanup(self._release)

    def _release(self):
        gw._REAPER_STARTED = False
        for fd in gw._REAPER_LOCK:
            os.close(fd)
        gw._REAPER_LOCK.clear()

    def test_it_stays_off_unless_the_container_asks_for_it(self):
        # Every web worker and every celery worker imports this app. A sweep in
        # any of them would read a pid namespace where no session process
        # exists and conclude that all of them are dead.
        with override_settings(STREAM_GATEWAY_REAPER=False):
            self.assertFalse(gw.start_reaper())

    def test_only_one_worker_in_the_container_sweeps(self):
        with override_settings(STREAM_GATEWAY_REAPER=True):
            self.assertTrue(gw.start_reaper())
            gw._REAPER_STARTED = False  # pretend to be a second worker
            self.assertFalse(gw.start_reaper())

    def test_the_lock_file_is_not_mistaken_for_a_session(self):
        with override_settings(STREAM_GATEWAY_REAPER=True):
            gw.start_reaper()
        self.make_session('idle', beat_age=gw.SESSION_IDLE_SECONDS + 30)
        self.assertEqual(gw.reap_sessions(), 1)
        self.assertTrue((self.root / '.reaper.lock').exists())


class SessionStartTruthTests(_SessionRootMixin, TestCase):
    """Where a session says it begins must be where the picture begins.

    Copy-mode cutting snaps back to the keyframe at or before the requested
    point — measured at 5s on a 10s-GOP file and over 20s on a real catalog
    source. The player reads film time as ``start + mediaTime``, so a session
    that reports the request instead of the truth runs that far ahead of its
    own picture, subtitles included, for its whole life.
    """

    def _tech(self):
        return gw.SourceTech(ok=True, video_codec='h264', audio_codec='mp3',
                             duration=7200.0, width=1920, height=1080)

    def test_the_cap_is_absolute_because_copyts_makes_it_so(self):
        # -copyts measures -t against source timestamps, so -t 1800 on a
        # session opened an hour in is already spent: ffmpeg writes one segment
        # and zero seconds of content. -to expresses the same cap in the units
        # -copyts actually counts in.
        cmd = gw._build_command('http://x/f.mkv', 3600.0, self._tech(), Path('/tmp/s'))
        self.assertIn('-copyts', cmd)
        self.assertNotIn('-t', cmd)
        self.assertEqual(cmd[cmd.index('-to') + 1],
                         f'{3600.0 + gw.SESSION_MAX_CONTENT_SECONDS:.3f}')

    def test_the_cap_is_still_the_cap_from_the_very_beginning(self):
        cmd = gw._build_command('http://x/f.mkv', 0.0, self._tech(), Path('/tmp/s'))
        self.assertNotIn('-ss', cmd)
        self.assertEqual(cmd[cmd.index('-to') + 1],
                         f'{float(gw.SESSION_MAX_CONTENT_SECONDS):.3f}')

    def _measured(self, sid, requested, stdout):
        directory = self.root / sid
        (directory / 'init.mp4').write_bytes(b'ftyp-stub')
        (directory / 'seg00000.m4s').write_bytes(b'moof-stub')
        completed = subprocess.CompletedProcess([], 0, stdout=stdout, stderr='')
        with mock.patch.object(gw.subprocess, 'run', return_value=completed):
            return gw.true_start(sid, requested)

    def test_it_reports_where_the_picture_actually_starts(self):
        self.make_session('snap')
        # Asked for 300; copy-mode landed on the keyframe at 277.
        self.assertAlmostEqual(self._measured('snap', 300.0, '277.167000\n'), 277.167, places=3)

    def test_the_measurement_is_remembered_not_repeated(self):
        self.make_session('once')
        self._measured('once', 300.0, '277.167000\n')
        # A second call must not shell out again — the answer cannot change
        # once ffmpeg has started, and stream_open is on the play path.
        with mock.patch.object(gw.subprocess, 'run',
                               side_effect=AssertionError('probed twice')):
            self.assertAlmostEqual(gw.true_start('once', 300.0), 277.167, places=3)

    def test_an_unreadable_segment_falls_back_to_the_request(self):
        # No init.mp4 at all: the old behaviour (trust the request) is a bounded
        # error, where a crash or a zero would be a broken session.
        self.make_session('blind')
        self.assertEqual(gw.true_start('blind', 300.0), 300.0)

    def test_nonsense_from_the_demuxer_is_refused(self):
        self.make_session('liar')
        # A start *after* the request cannot be a keyframe we snapped back to.
        self.assertEqual(self._measured('liar', 300.0, '9999.0\n'), 300.0)
        self.make_session('neg')
        self.assertEqual(self._measured('neg', 300.0, '-4.0\n'), 300.0)

    def test_the_probe_leaves_nothing_behind_in_the_session(self):
        self.make_session('tidy')
        self._measured('tidy', 300.0, '277.167000\n')
        left = sorted(p.name for p in (self.root / 'tidy').iterdir())
        self.assertNotIn('.start-probe.mp4', left)
        # And nothing it wrote can ever be served or pruned as a segment.
        for name in left:
            if name.startswith('.'):
                with self.assertRaises(gw.StreamGatewayError):
                    gw.segment_file('tidy', name)
