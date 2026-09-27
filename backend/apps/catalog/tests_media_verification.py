"""Tests for the pre-publish media check.

The importer used to publish on link *presence*. These tests pin the difference
between "a URL is written down" and "a server serves a video", and the rules
that keep the check from doing damage of its own:

* only a positive "it is gone" answer (404/410/soft-404/truncated) may drop a
  link — a timeout or a datacenter 403 never does, and one such answer is not
  enough either, because these CDNs 404 files that are demonstrably there;
* subtitles and other sidecars in ``download_links`` are never probed as video;
* our own object-storage keys are trusted instead of probed;
* a failing sweep re-crawls rather than unpublishes, unless nothing is left.
"""

import re
from datetime import timedelta
from unittest.mock import patch

import httpx
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.catalog import media_probe, media_verification as verification
from apps.catalog.media_probe import Probe
from apps.catalog.models import Episode, MediaCheck, Movie, PlaybackMode, Season, Series

MP4_URL = 'https://cdn.example/film.1080p.mp4'
MKV_URL = 'https://cdn.example/film.1080p.mkv'
MP4_HEADER = b'\x00\x00\x00\x18ftypmp42'


def live(url=MP4_URL, reason=''):
    return Probe(
        url=url, verdict='live', reason=reason, status=206,
        content_type='video/mp4', content_length=900_000_000, accept_ranges=True,
    )


def dead(url=MP4_URL, reason='http_404'):
    return Probe(url=url, verdict='dead', reason=reason, status=404)


def unknown(url=MP4_URL, reason='timeout'):
    return Probe(url=url, verdict='unknown', reason=reason)


def responder(routes: dict):
    """Map URL → ``(status, headers, body)`` for a mocked httpx transport.

    A route may instead be a *list* of those triples, answered in order and
    then repeating the last one — which is how a host that flaps is written
    down.
    """
    seen: dict[str, int] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        route = routes[url]
        if isinstance(route, list):
            index = min(seen.get(url, 0), len(route) - 1)
            seen[url] = index + 1
            route = route[index]
        status, headers, body = route
        return httpx.Response(status, headers=headers, content=body)
    return handle


class _MockedTransport:
    """Force every probe through an in-memory transport (no real network)."""

    def __init__(self, routes):
        self.routes = routes

    def __enter__(self):
        handler = responder(self.routes)
        real_client = httpx.Client

        def build(*args, **kwargs):
            kwargs.pop('verify', None)
            kwargs['transport'] = httpx.MockTransport(handler)
            return real_client(*args, **kwargs)

        self._patch = patch.object(httpx, 'Client', build)
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()
        return False


@override_settings(CATALOG_VERIFY_CODEC_BEFORE_PUBLISH=False)
class _Base(TestCase):
    """Reachability in isolation.

    The codec check is switched off here on purpose: these tests are about what
    the *network* layer concludes, and leaving it on would send every one of
    them to ffprobe against a hostname that does not resolve. Its own behaviour
    is covered in :mod:`tests_media_tech`.
    """

    def setUp(self):
        cache.clear()

    def movie(self, links=None, video_url='', **kw):
        return Movie.objects.create(
            title='فیلم', slug=kw.pop('slug', 'film'), download_links=links or [],
            video_url=video_url, **kw,
        )

    def series(self, links=None, **kw):
        return Series.objects.create(
            title='سریال', slug=kw.pop('slug', 'serial'), download_links=links or [], **kw,
        )


class ProbeTests(_Base):
    """What the network layer concludes from a real HTTP exchange."""

    def setUp(self):
        super().setUp()
        # The pauses between corroboration attempts are real seconds. What is
        # under test is the unanimity rule, not the waiting — so keep however
        # many attempts production makes, and make them instant.
        patcher = patch.object(
            media_probe, '_DEAD_CONFIRM_BACKOFF',
            (0,) * len(media_probe._DEAD_CONFIRM_BACKOFF),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def probe(self, url, status, headers, body=b'\x00\x00\x00\x18ftypmp42', expect='video'):
        with _MockedTransport({url: (status, headers, body)}):
            return media_probe.probe_url(url, expect=expect, use_cache=False)

    def answers(self, url, sequence, expect='video'):
        """Probe a host that gives different answers to identical requests."""
        with _MockedTransport({url: sequence}):
            return media_probe.probe_url(url, expect=expect, use_cache=False)

    def test_partial_content_with_range_total_is_live_and_seekable(self):
        result = self.probe(MP4_URL, 206, {
            'content-type': 'video/mp4',
            'content-range': 'bytes 0-2047/1400000000',
            'content-length': '2048',
        })
        self.assertTrue(result.live)
        self.assertTrue(result.accept_ranges)
        # The size must come from the range total, not from the 2 KB slice.
        self.assertEqual(result.content_length, 1_400_000_000)

    def test_missing_file_is_dead(self):
        result = self.probe(MP4_URL, 404, {'content-type': 'text/html'}, b'not found')
        self.assertTrue(result.dead)
        self.assertEqual(result.reason, 'http_404')

    def test_soft_404_html_served_as_video_is_dead(self):
        """The failure the string checks could never catch: 200 OK, ``.mkv`` in the
        path, an HTML error page in the body."""
        result = self.probe(MKV_URL, 200, {'content-type': 'text/html'}, b'<!DOCTYPE html><html>gone')
        self.assertTrue(result.dead)
        self.assertEqual(result.reason, 'html_not_video')

    def test_geo_block_html_is_unknown_not_dead(self):
        """Some provider CDNs serve Iranian catalogues only to Iranian egress
        IPs and answer anyone else with a styled "turn your VPN off" page. That
        describes where the probe ran, not the file: the same URL plays in an
        Iranian browser. It must never read as a missing file."""
        body = '<!DOCTYPE html><html>فیلتر شکن را خاموش کنید کاربر'.encode('utf-8')
        result = self.probe(MKV_URL, 200, {'content-type': 'text/html'}, body)
        self.assertFalse(result.dead)
        self.assertFalse(result.live)
        self.assertEqual(result.verdict, 'unknown')
        self.assertEqual(result.reason, 'geo_blocked')

    def ranged(self, url, body, content_type='text/html; charset=utf-8'):
        """Probe a host that honours ``Range`` the way nginx does."""
        def handle(request):
            match = re.match(r'bytes=(\d+)-(\d+)', request.headers.get('range', ''))
            if not match:
                return httpx.Response(200, headers={'content-type': content_type}, content=body)
            start, end = int(match.group(1)), min(int(match.group(2)), len(body) - 1)
            return httpx.Response(206, headers={
                'content-type': content_type,
                'content-range': f'bytes {start}-{end}/{len(body)}',
            }, content=body[start:end + 1])

        real_client = httpx.Client

        def build(*args, **kwargs):
            kwargs.pop('verify', None)
            kwargs['transport'] = httpx.MockTransport(handle)
            return real_client(*args, **kwargs)

        with patch.object(httpx, 'Client', build):
            return media_probe.probe_url(url, use_cache=False)

    def test_geo_block_page_whose_words_sit_past_the_first_slice_is_unknown(self):
        """mehracdn's VPN page is 4 KB, the first 3 KB of it inline CSS. Judged on
        the 2 KB slice alone it read as a soft 404, the links were pruned and the
        sweep unpublished films that play fine in Iran."""
        style = '<style>' + ('.box{margin:0 auto;padding:12px}' * 120) + '</style>'
        body = (
            '<!DOCTYPE html><html><head>' + style + '</head><body>'
            '<p>لطفا فیلتر شکن خود را خاموش کنید</p></body></html>'
        ).encode('utf-8')
        self.assertGreater(body.index('فیلتر'.encode('utf-8')), media_probe.PROBE_BYTES)
        result = self.ranged(MKV_URL, body)
        self.assertEqual(result.verdict, 'unknown')
        self.assertEqual(result.reason, 'geo_blocked')

    def test_long_error_page_without_block_words_is_still_dead(self):
        style = '<style>' + ('.box{margin:0 auto;padding:12px}' * 120) + '</style>'
        body = ('<!DOCTYPE html><html><head>' + style + '</head><body>404</body></html>').encode()
        result = self.ranged(MKV_URL, body)
        self.assertTrue(result.dead)
        self.assertEqual(result.reason, 'html_not_video')

    def test_truncated_placeholder_is_dead(self):
        result = self.probe(MP4_URL, 200, {
            'content-type': 'video/mp4', 'content-length': '5120',
        })
        self.assertTrue(result.dead)
        self.assertEqual(result.reason, 'too_small')

    def test_one_404_from_a_flapping_host_is_not_a_dead_file(self):
        """The bug that would have emptied the catalog.

        Measured against the real providers: one file, five identical ranged
        GETs a second apart, answered ``404 206 404 404 206`` — the same host
        improvising two different replies to one question. Here the second
        answer is the real file, and reading only the first would have cleared
        the playback link of a film that plays.
        """
        result = self.answers(MP4_URL, [
            (404, {'content-type': 'text/html'}, b'not found'),
            (206, {'content-type': 'video/mp4',
                   'content-range': 'bytes 0-2047/1400000000'}, MP4_HEADER),
        ])
        self.assertTrue(result.live)
        self.assertFalse(result.dead)
        # And it says why it changed its mind, so the log shows a flap for what
        # it is rather than a probe that silently disagrees with itself.
        self.assertEqual(result.detail.get('flapped'), 'http_404')

    def test_a_host_that_keeps_saying_gone_is_dead(self):
        """Corroboration must not turn into never deciding: a repeated refusal
        is the positive answer the rest of the system waits for."""
        result = self.answers(MP4_URL, [(404, {'content-type': 'text/html'}, b'not found')])
        self.assertTrue(result.dead)
        self.assertEqual(result.reason, 'http_404')
        self.assertEqual(result.detail.get('attempts'),
                         len(media_probe._DEAD_CONFIRM_BACKOFF) + 1)

    def test_gone_then_unreachable_is_unknown_not_dead(self):
        """One answer says the file is gone, the next cannot tell. A link is
        deleted on proof, and disagreement is not proof."""
        result = self.answers(MP4_URL, [
            (404, {'content-type': 'text/html'}, b'not found'),
            (503, {}, b''),
        ])
        self.assertEqual(result.verdict, 'unknown')
        self.assertEqual(result.reason, 'unconfirmed_http_404')
        self.assertFalse(result.dead)

    def test_a_soft_404_page_is_also_only_believed_twice_over(self):
        """The corroboration covers what the *body* said too — an error page
        served under load is the same kind of lie as a 404."""
        result = self.answers(MKV_URL, [
            (200, {'content-type': 'text/html'}, b'<!DOCTYPE html>busy'),
            (206, {'content-type': 'video/mp4',
                   'content-range': 'bytes 0-2047/1400000000'}, MP4_HEADER),
        ])
        self.assertTrue(result.live)

    def test_forbidden_is_never_treated_as_missing(self):
        """Hotlink protection and datacenter blocks answer 403 for files that play
        fine in a viewer's browser — deleting those links would be the bug."""
        result = self.probe(MP4_URL, 403, {'content-type': 'text/html'}, b'denied')
        self.assertEqual(result.verdict, 'unknown')
        self.assertFalse(result.dead)

    def test_server_error_is_unknown(self):
        result = self.probe(MP4_URL, 503, {}, b'')
        self.assertEqual(result.verdict, 'unknown')

    def test_no_byte_ranges_is_live_but_flagged(self):
        result = self.probe(MP4_URL, 200, {
            'content-type': 'video/mp4', 'content-length': '900000000',
        })
        self.assertTrue(result.live)
        self.assertEqual(result.reason, 'no_byte_ranges')

    def test_manifest_must_actually_be_a_manifest(self):
        url = 'https://cdn.example/stream/master.m3u8'
        result = self.probe(url, 200, {'content-type': 'application/vnd.apple.mpegurl'},
                            b'<html>expired</html>', expect='manifest')
        self.assertTrue(result.dead)
        self.assertEqual(result.reason, 'not_a_manifest')

    def test_valid_manifest_is_live(self):
        url = 'https://cdn.example/stream/master.m3u8'
        result = self.probe(url, 200, {'content-type': 'application/vnd.apple.mpegurl'},
                            b'#EXTM3U\n#EXT-X-VERSION:3\n', expect='manifest')
        self.assertTrue(result.live)

    def test_transport_failure_is_unknown_not_dead(self):
        def explode(request):
            raise httpx.ConnectTimeout('timed out')

        real_client = httpx.Client

        def build(*args, **kwargs):
            kwargs.pop('verify', None)
            kwargs['transport'] = httpx.MockTransport(explode)
            return real_client(*args, **kwargs)

        with patch.object(httpx, 'Client', build):
            result = media_probe.probe_url(MP4_URL, use_cache=False)
        self.assertEqual(result.verdict, 'unknown')
        self.assertEqual(result.reason, 'timeout')

    def test_host_circuit_opens_after_repeated_transport_failures(self):
        """One unreachable host must not spend the whole import budget timing out."""
        def explode(request):
            raise httpx.ConnectTimeout('timed out')

        real_client = httpx.Client

        def build(*args, **kwargs):
            kwargs.pop('verify', None)
            kwargs['transport'] = httpx.MockTransport(explode)
            return real_client(*args, **kwargs)

        with patch.object(httpx, 'Client', build):
            for index in range(media_probe._HOST_FAIL_LIMIT):
                media_probe.probe_url(f'{MP4_URL}?v={index}', use_cache=False)
            result = media_probe.probe_url(f'{MP4_URL}?v=last', use_cache=False)
        self.assertEqual(result.reason, 'host_circuit_open')


class VerifyTargetTests(_Base):
    """The verdict stored for a title, and what it is allowed to change."""

    def test_live_browser_safe_source_passes_as_playable(self):
        movie = self.movie([{'url': MP4_URL, 'quality': '1080p'}])
        with patch.object(verification, '_probe', return_value=live()):
            verdict = verification.verify_target(movie)
        self.assertEqual(verdict['status'], MediaCheck.Status.PASSED)
        self.assertTrue(verdict['playable'])
        self.assertTrue(verdict['downloadable'])

    def test_live_mkv_only_is_downloadable_but_not_playable(self):
        """An x265/MKV title is not broken — it just cannot stream in a browser.
        Publishing it as a download while the playback crawler hunts a mirror is
        the correct outcome, so this must not be recorded as a failure."""
        movie = self.movie([{'url': MKV_URL, 'quality': '1080p'}])
        with patch.object(verification, '_probe', return_value=live(MKV_URL)):
            verdict = verification.verify_target(movie)
        self.assertEqual(verdict['status'], MediaCheck.Status.PASSED)
        self.assertFalse(verdict['playable'])
        self.assertTrue(verdict['downloadable'])
        self.assertEqual(verdict['reason'], 'download_only')

    def test_geo_blocked_mirror_counts_as_downloadable_for_the_audience(self):
        """This server is outside Iran; the viewers are not. A CDN that answers
        with its VPN page is up — the title must stay publishable."""
        movie = self.movie([{'url': MKV_URL, 'quality': '1080p'}])
        with patch.object(verification, '_probe', return_value=unknown(MKV_URL, 'geo_blocked')):
            verdict = verification.verify_target(movie)
        movie.refresh_from_db()
        self.assertEqual(verdict['status'], MediaCheck.Status.PASSED)
        self.assertEqual(verdict['reason'], 'geo_blocked')
        self.assertTrue(verdict['downloadable'])
        self.assertFalse(verdict['playable'])
        self.assertEqual(len(movie.download_links), 1)

    def test_plain_unreachable_mirror_is_still_unknown(self):
        movie = self.movie([{'url': MKV_URL, 'quality': '1080p'}])
        with patch.object(verification, '_probe', return_value=unknown(MKV_URL)):
            verdict = verification.verify_target(movie)
        self.assertEqual(verdict['status'], MediaCheck.Status.UNKNOWN)

    def test_source_without_ranges_is_not_promoted_to_playable(self):
        movie = self.movie([{'url': MP4_URL, 'quality': '1080p'}])
        with patch.object(verification, '_probe', return_value=live(reason='no_byte_ranges')):
            verdict = verification.verify_target(movie)
        self.assertFalse(verdict['playable'])
        self.assertTrue(verdict['downloadable'])

    def test_dead_mirror_leaves_the_download_list_at_once(self):
        """A dead mirror is one of several and the next crawl re-imports it,
        so the download list is pruned on the spot."""
        movie = self.movie([{'url': MP4_URL, 'quality': '1080p'}], video_url=MP4_URL)
        with patch.object(verification, '_probe', return_value=dead()):
            verdict = verification.verify_target(movie)
        movie.refresh_from_db()
        self.assertEqual(verdict['status'], MediaCheck.Status.FAILED)
        self.assertEqual(movie.download_links, [])

    def test_the_stream_link_survives_the_first_gone_verdict(self):
        """Blanking ``video_url`` takes the title offline until a provider yields
        a replacement, so it waits for a second sighting — but the verdict is
        recorded now, which is what makes a second sighting possible."""
        movie = self.movie([{'url': MP4_URL, 'quality': '1080p'}], video_url=MP4_URL)
        with patch.object(verification, '_probe', return_value=dead()):
            verification.verify_target(movie)
        movie.refresh_from_db()
        self.assertEqual(movie.video_url, MP4_URL)
        self.assertEqual(movie.playback_mode, PlaybackMode.NONE)
        self.assertIsNotNone(movie.playback_checked_at)

    def test_a_second_gone_verdict_a_day_later_clears_the_stream_link(self):
        movie = self.movie(
            [{'url': MP4_URL, 'quality': '1080p'}], video_url=MP4_URL,
            playback_mode=PlaybackMode.NONE,
            playback_checked_at=timezone.now() - timedelta(hours=21),
        )
        with patch.object(verification, '_probe', return_value=dead()):
            verification.verify_target(movie)
        movie.refresh_from_db()
        self.assertEqual(movie.video_url, '')

    def test_reimporting_all_day_never_pushes_the_second_opinion_further_away(self):
        """The clock is started by the first sighting and left alone after that.
        Re-stamping it on every import would make the second opinion permanently
        due tomorrow, and the dead link would be served forever."""
        first = timezone.now() - timedelta(hours=19)
        movie = self.movie(
            [{'url': MP4_URL, 'quality': '1080p'}], video_url=MP4_URL,
            playback_mode=PlaybackMode.NONE, playback_checked_at=first,
        )
        with patch.object(verification, '_probe', return_value=dead()):
            verification.verify_target(movie)
        movie.refresh_from_db()
        self.assertEqual(movie.video_url, MP4_URL)
        self.assertEqual(movie.playback_checked_at, first)

    def test_unreachable_source_keeps_every_link(self):
        """The conservative half of the contract: doubt never deletes."""
        movie = self.movie([{'url': MP4_URL, 'quality': '1080p'}], video_url=MP4_URL)
        with patch.object(verification, '_probe', return_value=unknown()):
            verdict = verification.verify_target(movie)
        movie.refresh_from_db()
        self.assertEqual(verdict['status'], MediaCheck.Status.UNKNOWN)
        self.assertEqual(len(movie.download_links), 1)
        self.assertEqual(movie.video_url, MP4_URL)

    def test_subtitles_are_never_probed_as_video(self):
        """``download_links`` also carries .srt/.vtt sidecars; probing them would
        report 'not a video' and delete perfectly good subtitles."""
        movie = self.movie([
            {'url': 'https://cdn.example/film.fa.srt', 'quality': 'sub'},
            {'url': MP4_URL, 'quality': '1080p'},
        ])
        with patch.object(verification, '_probe', return_value=live()) as probe:
            verification.verify_target(movie)
        movie.refresh_from_db()
        probed = [call.args[0] for call in probe.call_args_list]
        self.assertNotIn('https://cdn.example/film.fa.srt', probed)
        self.assertEqual(len(movie.download_links), 2)

    def test_own_storage_key_is_trusted_without_a_probe(self):
        """Our own HLS transcode has no third-party host to interrogate."""
        movie = self.movie(video_url='movies/9001/hls/master.m3u8')
        with patch.object(verification, '_probe') as probe:
            verdict = verification.verify_target(movie)
        probe.assert_not_called()
        self.assertEqual(verdict['status'], MediaCheck.Status.PASSED)
        self.assertTrue(verdict['playable'])

    def test_budget_exhausted_on_dead_mirrors_is_not_a_death_sentence(self):
        """More mirrors than the probe budget: the dead ones go, but the title is
        left unverified rather than condemned on links nobody tested."""
        movie = self.movie([
            {'url': f'https://cdn.example/film.{n}.mp4'}
            for n in range(verification.MAX_PROBES_PER_TARGET + 3)
        ])
        with patch.object(verification, '_probe', side_effect=lambda url, **kw: dead(url)):
            verdict = verification.verify_target(movie)
        movie.refresh_from_db()
        self.assertEqual(verdict['status'], MediaCheck.Status.UNKNOWN)
        self.assertEqual(verdict['reason'], 'partially_probed')
        self.assertEqual(len(movie.download_links), 3)

    def test_title_without_any_source_fails(self):
        movie = self.movie()
        verdict = verification.verify_target(movie)
        self.assertEqual(verdict['status'], MediaCheck.Status.FAILED)
        self.assertEqual(verdict['reason'], 'no_sources')

    def test_first_live_safe_source_stops_the_probing(self):
        movie = self.movie([
            {'url': MP4_URL, 'quality': '1080p'},
            {'url': 'https://cdn.example/film.720p.mp4', 'quality': '720p'},
            {'url': 'https://cdn.example/film.480p.mp4', 'quality': '480p'},
        ])
        with patch.object(verification, '_probe', return_value=live()) as probe:
            verification.verify_target(movie)
        self.assertEqual(probe.call_count, 1)

    def test_verdict_is_stored_once_per_target(self):
        movie = self.movie([{'url': MP4_URL}])
        with patch.object(verification, '_probe', return_value=live()):
            verification.verify_target(movie)
            verification.verify_target(movie)
        record = MediaCheck.objects.get(content_type='movie', object_id=movie.pk, episode_id=0)
        self.assertEqual(MediaCheck.objects.count(), 1)
        self.assertEqual(record.attempts, 2)

    def test_fresh_verdict_is_reused_instead_of_reprobing(self):
        movie = self.movie([{'url': MP4_URL}])
        with patch.object(verification, '_probe', return_value=live()):
            verification.verify_target(movie)
        with patch.object(verification, '_probe') as probe:
            verdict = verification.ensure_verified(movie)
        probe.assert_not_called()
        self.assertTrue(verdict['cached'])

    def test_stale_verdict_is_reprobed(self):
        movie = self.movie([{'url': MP4_URL}])
        with patch.object(verification, '_probe', return_value=live()):
            verification.verify_target(movie)
        MediaCheck.objects.update(
            checked_at=timezone.now() - timedelta(seconds=verification.FRESH_SECONDS + 60),
        )
        with patch.object(verification, '_probe', return_value=live()) as probe:
            verification.ensure_verified(movie)
        probe.assert_called()


class EpisodeVerificationTests(_Base):
    def setUp(self):
        super().setUp()
        self.series = self.series([
            {'url': 'https://cdn.example/Show.S01E01.1080p.mp4', 'quality': '1080p'},
            {'url': 'https://cdn.example/Show.S01E07.1080p.mp4', 'quality': '1080p'},
        ])
        season = Season.objects.create(series=self.series, season_number=1, title='S1')
        self.episode = Episode.objects.create(
            season=season, episode_number=7, title='E7', is_published=True,
        )

    def test_only_this_episode_sources_are_probed(self):
        """A series-level verdict hid broken episodes: one good episode made the
        whole show look playable."""
        with patch.object(verification, '_probe', return_value=live()) as probe:
            verification.verify_target(self.series, episode=self.episode)
        probed = [call.args[0] for call in probe.call_args_list]
        self.assertEqual(probed, ['https://cdn.example/Show.S01E07.1080p.mp4'])

    def test_episode_verdict_is_stored_against_the_episode(self):
        with patch.object(verification, '_probe', return_value=live()):
            verification.verify_target(self.series, episode=self.episode)
        self.assertTrue(
            MediaCheck.objects.filter(
                content_type='series', object_id=self.series.pk, episode_id=self.episode.pk,
            ).exists()
        )

    def test_dead_episode_stream_is_cleared_from_the_episode_row(self):
        """Which row owns the stream link matters: clearing it on the series
        would take every other episode offline too. Set up as a confirmed second
        sighting, since the first one deliberately changes nothing."""
        self.episode.video_url = 'https://cdn.example/Show.S01E07.1080p.mp4'
        self.episode.playback_mode = PlaybackMode.NONE
        self.episode.playback_checked_at = timezone.now() - timedelta(hours=21)
        self.episode.save(update_fields=[
            'video_url', 'playback_mode', 'playback_checked_at',
        ])
        with patch.object(verification, '_probe', return_value=dead()):
            verification.verify_target(self.series, episode=self.episode)
        self.episode.refresh_from_db()
        self.series.refresh_from_db()
        self.assertEqual(self.episode.video_url, '')
        # …and the series keeps the other episode's link.
        self.assertEqual(len(self.series.download_links), 1)


class ScreenLinksTests(_Base):
    """The import-time guard: links are tested before they are ever stored."""

    def test_dead_links_are_dropped_and_live_ones_kept(self):
        movie = self.movie()
        links = [
            {'url': 'https://cdn.example/a.1080p.mp4'},
            {'url': 'https://cdn.example/b.720p.mp4'},
        ]

        def fake(url, **kw):
            return dead(url) if url.endswith('a.1080p.mp4') else live(url)

        with patch.object(verification, '_probe', side_effect=fake):
            kept, dropped = verification.screen_links(movie, links)
        self.assertEqual([item['url'] for item in kept], ['https://cdn.example/b.720p.mp4'])
        self.assertEqual(len(dropped), 1)

    def test_unverifiable_links_are_kept(self):
        movie = self.movie()
        links = [{'url': MP4_URL}]
        with patch.object(verification, '_probe', return_value=unknown()):
            kept, dropped = verification.screen_links(movie, links)
        self.assertEqual(kept, links)
        self.assertEqual(dropped, [])

    def test_one_episode_per_group_is_sampled(self):
        """A 40-link season pack must not cost 40 probes, and the sample must
        spread across episodes instead of exhausting one."""
        series = self.series()
        links = [
            {'url': f'https://cdn.example/Show.S01E{n:02d}.1080p.mp4'}
            for n in range(1, 9)
        ]
        with patch.object(verification, '_probe', return_value=live()) as probe:
            kept, _ = verification.screen_links(series, links)
        self.assertEqual(len(kept), 8)
        self.assertEqual(probe.call_count, 8)  # one per episode, none doubled

    def test_probe_budget_is_capped(self):
        series = self.series()
        links = [
            {'url': f'https://cdn.example/Show.S01E{n:02d}.1080p.mp4'}
            for n in range(1, 40)
        ]
        with patch.object(verification, '_probe', return_value=live()) as probe:
            verification.screen_links(series, links)
        self.assertLessEqual(probe.call_count, verification.MAX_SCREEN_PROBES)

    def test_a_dead_preferred_mirror_falls_through_to_the_next_one(self):
        """The mirror that would have become ``video_url`` is gone, so the batch
        must not be thrown away — the fallback is probed and kept."""
        movie = self.movie()
        links = [{'url': MP4_URL}, {'url': 'https://cdn.example/film.1080p.mkv'}]

        def fake(url, **kw):
            return dead(url) if url.endswith('.mp4') else live(url)

        with patch.object(verification, '_probe', side_effect=fake) as probe:
            kept, dropped = verification.screen_links(movie, links)
        self.assertEqual(probe.call_count, 2)
        self.assertEqual([item['url'] for item in kept], ['https://cdn.example/film.1080p.mkv'])
        self.assertEqual(len(dropped), 1)

    def test_a_live_preferred_mirror_settles_the_group(self):
        """Screening is sampled: once something in the group serves, the rest are
        left alone rather than spending probes to prove a mirror nobody uses."""
        movie = self.movie()
        links = [{'url': MP4_URL}, {'url': 'https://cdn.example/film.1080p.mkv'}]
        with patch.object(verification, '_probe', return_value=live()) as probe:
            kept, dropped = verification.screen_links(movie, links)
        self.assertEqual(probe.call_count, 1)
        self.assertEqual(len(kept), 2)
        self.assertEqual(dropped, [])

    @override_settings(CATALOG_SCREEN_PROVIDER_LINKS=False)
    def test_screening_can_be_switched_off(self):
        movie = self.movie()
        links = [{'url': MP4_URL}]
        with patch.object(verification, '_probe') as probe:
            kept, dropped = verification.screen_links(movie, links)
        probe.assert_not_called()
        self.assertEqual(kept, links)

    def test_import_refuses_a_batch_where_everything_is_gone(self):
        from apps.catalog.provider_import.exceptions import ProviderImportError
        from apps.catalog.provider_import.link_apply import apply_provider_download_links

        movie = self.movie()
        with patch.object(verification, '_probe', return_value=dead()):
            with self.assertRaises(ProviderImportError) as ctx:
                apply_provider_download_links(
                    movie, [{'url': MP4_URL, 'quality': '1080p', 'label': 'فیلم'}],
                )
        self.assertEqual(ctx.exception.code, 'provider_links_dead')


class PublishGateTests(_Base):
    """Nothing reaches a viewer until a real server answered for it."""

    def _complete(self, **kw):
        """A movie whose only possible blocker is the media check."""
        from apps.catalog.models import Actor, Genre, MovieActor

        movie = self.movie(
            original_title='The Film', description='خلاصهٔ کامل داستان فیلم.',
            short_description='خلاصهٔ کوتاه.', release_date=timezone.now().date(),
            release_year=2026, poster_external_url='https://img.example/p.jpg',
            backdrop_external_url='https://img.example/b.jpg', imdb_rating='7.8',
            auto_publish=True, rights_verified=True, **kw,
        )
        actor, _ = Actor.objects.get_or_create(name='بازیگر', defaults={'slug': 'actor'})
        MovieActor.objects.create(movie=movie, actor=actor)
        genre, _ = Genre.objects.get_or_create(slug='drama', defaults={'title': 'درام'})
        movie.genres.add(genre)
        self.assertEqual(
            [code for code in movie.auto_publish_blockers if not code.startswith('media_')],
            [], 'fixture must be complete apart from the media check',
        )
        return movie

    def test_unverified_title_is_blocked(self):
        movie = self._complete(links=[{'url': MP4_URL}])
        self.assertIn('media_unverified', movie.auto_publish_blockers)

    def test_verified_title_is_not_blocked_on_media(self):
        movie = self._complete(links=[{'url': MP4_URL}])
        with patch.object(verification, '_probe', return_value=live()):
            verification.verify_target(movie)
        self.assertEqual(movie.auto_publish_blockers, [])

    def test_dead_title_is_blocked(self):
        """The dead video link is pruned, but a leftover subtitle sidecar still
        counts as "has downloads" — the media verdict is what must block here."""
        movie = self._complete(links=[
            {'url': MP4_URL},
            {'url': 'https://cdn.example/film.fa.srt', 'quality': 'sub'},
        ])
        with patch.object(verification, '_probe', return_value=dead()):
            verification.verify_target(movie)
        self.assertIn('media_sources_dead', movie.auto_publish_blockers)

    def test_title_whose_links_all_vanished_is_blocked(self):
        movie = self._complete(links=[{'url': MP4_URL}])
        with patch.object(verification, '_probe', return_value=dead()):
            verification.verify_target(movie)
        movie.refresh_from_db()
        self.assertIn('missing_playback_links', movie.auto_publish_blockers)
        self.assertFalse(movie.ready_for_auto_publish)

    def test_a_stored_refusal_is_probed_again_at_the_gate(self):
        """A fresh "dead" verdict must not outlive the reason for it."""
        movie = self._complete(links=[{'url': MP4_URL}, {'url': MKV_URL}])
        with patch.object(verification, '_probe', return_value=unknown()):
            verification.verify_target(movie)
        movie.refresh_from_db()
        with patch.object(verification, '_probe', return_value=live()):
            ok, blockers = verification.verify_before_publish(movie)
        self.assertTrue(ok, blockers)

    def test_a_stored_pass_is_reused_at_the_gate(self):
        movie = self._complete(links=[{'url': MP4_URL}])
        with patch.object(verification, '_probe', return_value=live()):
            verification.verify_target(movie)
        with patch.object(verification, '_probe') as probe:
            ok, _ = verification.verify_before_publish(movie)
        self.assertTrue(ok)
        probe.assert_not_called()

    def test_geo_blocked_title_is_not_blocked_on_media(self):
        movie = self._complete(links=[{'url': MKV_URL}])
        with patch.object(verification, '_probe', return_value=unknown(MKV_URL, 'geo_blocked')):
            verification.verify_target(movie)
        self.assertEqual(movie.auto_publish_blockers, [])

    @override_settings(CATALOG_VERIFY_MEDIA_BEFORE_PUBLISH=False)
    def test_gate_can_be_switched_off(self):
        movie = self._complete(links=[{'url': MP4_URL}])
        self.assertNotIn('media_unverified', movie.auto_publish_blockers)

    def test_auto_publish_probes_and_publishes_a_working_title(self):
        from apps.catalog.ingestion import maybe_auto_publish

        movie = self._complete(links=[{'url': MP4_URL}])
        with patch.object(verification, '_probe', return_value=live()):
            published = maybe_auto_publish(movie, enabled=True)
        self.assertTrue(published)
        self.assertTrue(movie.is_published)

    def test_auto_publish_refuses_a_dead_title(self):
        from apps.catalog.ingestion import maybe_auto_publish

        movie = self._complete(links=[{'url': MP4_URL}])
        with patch.object(verification, '_probe', return_value=dead()):
            published = maybe_auto_publish(movie, enabled=True)
        self.assertFalse(published)
        self.assertFalse(movie.is_published)

    def test_auto_publish_waits_when_the_host_cannot_be_reached(self):
        """Unreachable is not broken: the title waits for the next pass instead
        of going live unverified."""
        from apps.catalog.ingestion import maybe_auto_publish

        movie = self._complete(links=[{'url': MP4_URL}])
        with patch.object(verification, '_probe', return_value=unknown()):
            published = maybe_auto_publish(movie, enabled=True)
        self.assertFalse(published)

    def test_top_catalog_publish_is_gated(self):
        from apps.catalog import top_catalog

        movie = self.movie([{'url': MP4_URL, 'quality': '1080p'}])
        with patch.object(verification, '_probe', return_value=dead()):
            self.assertFalse(top_catalog._publish_movie(movie))
        movie.refresh_from_db()
        self.assertFalse(movie.is_published)

    def test_top_catalog_publishes_a_verified_title(self):
        from apps.catalog import top_catalog

        movie = self.movie([{'url': MP4_URL, 'quality': '1080p'}])
        with patch.object(verification, '_probe', return_value=live()):
            self.assertTrue(top_catalog._publish_movie(movie))
        movie.refresh_from_db()
        self.assertTrue(movie.is_published)

    def test_series_publish_is_gated(self):
        from apps.catalog import top_catalog

        series = self.series([{'url': 'https://cdn.example/Show.S01E01.1080p.mp4'}])
        with patch.object(verification, '_probe', return_value=dead()):
            self.assertFalse(top_catalog._publish_series(series))
        series.refresh_from_db()
        self.assertFalse(series.is_published)


class SweepTests(_Base):
    """Published titles decay; the sweep repairs rather than deletes."""

    def test_broken_title_with_links_left_is_recrawled(self):
        movie = self.movie([{'url': MP4_URL}, {'url': MKV_URL}], is_published=True)

        def fake(url, **kw):
            return dead(url) if url == MP4_URL else live(url)

        with patch.object(verification, '_probe', side_effect=fake), \
                patch('apps.catalog.provider_import.signals.enqueue_provider_movie_auto_crawl',
                      return_value=True) as enqueue:
            stats = verification.sweep_published_media(limit=10)
        movie.refresh_from_db()
        # One link died, the other survived → still publishable, no unpublish.
        self.assertTrue(movie.is_published)
        self.assertEqual(stats['unpublished'], 0)
        enqueue.assert_not_called()  # the survivor keeps it serviceable

    def test_title_with_nothing_left_goes_back_to_draft(self):
        movie = self.movie([{'url': MP4_URL}], is_published=True,
                           publication_status=Movie.PublicationStatus.PUBLISHED)
        with patch.object(verification, '_probe', return_value=dead()):
            stats = verification.sweep_published_media(limit=10)
        movie.refresh_from_db()
        self.assertFalse(movie.is_published)
        self.assertEqual(movie.publication_status, Movie.PublicationStatus.DRAFT)
        self.assertEqual(stats['unpublished'], 1)

    def test_unreachable_titles_are_left_published(self):
        """A CDN outage must never empty the catalogue."""
        movie = self.movie([{'url': MP4_URL}], is_published=True)
        with patch.object(verification, '_probe', return_value=unknown()):
            stats = verification.sweep_published_media(limit=10)
        movie.refresh_from_db()
        self.assertTrue(movie.is_published)
        self.assertEqual(stats['unknown'], 1)
        self.assertEqual(stats['unpublished'], 0)

    def test_geo_blocked_titles_keep_their_links_and_stay_published(self):
        movie = self.movie([{'url': MKV_URL}], is_published=True,
                           publication_status=Movie.PublicationStatus.PUBLISHED)
        with patch.object(verification, '_probe', return_value=unknown(MKV_URL, 'geo_blocked')):
            stats = verification.sweep_published_media(limit=10)
        movie.refresh_from_db()
        self.assertTrue(movie.is_published)
        self.assertEqual([link['url'] for link in movie.download_links], [MKV_URL])
        self.assertEqual(stats['passed'], 1)
        self.assertEqual(stats['unpublished'], 0)

    def test_unpublishing_is_capped_per_run(self):
        for index in range(verification.MAX_UNPUBLISH_PER_SWEEP + 4):
            self.movie([{'url': MP4_URL}], is_published=True, slug=f'film-{index}',
                       publication_status=Movie.PublicationStatus.PUBLISHED)
        with patch.object(verification, '_probe', return_value=dead()):
            stats = verification.sweep_published_media(limit=40)
        self.assertEqual(stats['unpublished'], verification.MAX_UNPUBLISH_PER_SWEEP)
        self.assertEqual(
            Movie.objects.filter(is_published=True).count(),
            4,
        )

    def test_freshly_checked_titles_are_skipped(self):
        movie = self.movie([{'url': MP4_URL}], is_published=True)
        with patch.object(verification, '_probe', return_value=live()):
            verification.verify_target(movie)
        with patch.object(verification, '_probe') as probe:
            stats = verification.sweep_published_media(limit=10)
        probe.assert_not_called()
        self.assertEqual(stats['checked'], 0)


class EpisodeScopeTests(TestCase):
    """Which of a season pack's links belong to one episode.

    A series keeps every season's files in one ``download_links`` array, so
    this predicate is the only thing standing between an episode and several
    hundred files that are not it. Scoping on the episode number alone is not
    enough — «قسمت ۱۰» is equally true of S01E10 and S06E10 — and getting it
    wrong did two kinds of damage in production: episodes drowned in candidates
    and could never reach a verdict, and some were handed another season's
    file after their own went dead (Rick and Morty S09E08 served S01E08).
    """

    PACK = 'https://cdn.example/yA3f/Series/Dexter/S01-S09/'

    def episode(self, season_number: int, episode_number: int) -> Episode:
        series = Series.objects.create(title='Dexter', slug=f's{season_number}-{episode_number}')
        season = Season.objects.create(series=series, season_number=season_number)
        return Episode.objects.create(season=season, episode_number=episode_number)

    def belongs(self, season_number, episode_number, item, url=None):
        url = url if url is not None else str(item.get('url') or '')
        return verification._link_belongs_to_episode(
            item, url, self.episode(season_number, episode_number),
        )

    # --- the structured fields the importer already parsed --------------

    def test_stored_season_number_rejects_another_season(self):
        """The regression itself: the row said season 1, we wanted season 6."""
        item = {'url': self.PACK + 'Dexter.S01E10.1080p.Farsi.Sub.mkv',
                'label': 'فصل 1 · قسمت 10', 'season_number': 1, 'episode_number': 10}
        self.assertFalse(self.belongs(6, 10, item))

    def test_stored_fields_that_agree_are_enough(self):
        item = {'url': self.PACK + 'whatever-the-name-is.mkv',
                'season_number': 6, 'episode_number': 10}
        self.assertTrue(self.belongs(6, 10, item))

    def test_stored_episode_number_that_disagrees_rejects(self):
        item = {'url': self.PACK + 'Dexter.S06E10.mkv', 'episode_number': 11}
        self.assertFalse(self.belongs(6, 10, item))

    # --- an sNNeNN / NxNN pair states both numbers at once ---------------

    def test_own_pair_in_the_file_name(self):
        self.assertTrue(self.belongs(6, 10, {'url': self.PACK + 'Dexter.S06E10.1080p.mkv'}))

    def test_another_seasons_pair_is_rejected(self):
        self.assertFalse(self.belongs(6, 10, {'url': self.PACK + 'Dexter.S01E10.720p.mkv'}))

    def test_a_persian_label_cannot_override_the_pair_in_the_url(self):
        item = {'url': self.PACK + 'Dexter.S01E10.480p.mkv', 'label': 'قسمت 10'}
        self.assertFalse(self.belongs(6, 10, item))

    def test_separators_inside_the_pair(self):
        self.assertTrue(self.belongs(6, 10, {'url': self.PACK + 'Dexter.S06.E10.1080p.mkv'}))

    def test_nxnn_pair_form(self):
        self.assertTrue(self.belongs(2, 7, {'url': 'https://cdn.example/Show.2x07.720p.mkv'}))
        self.assertFalse(self.belongs(3, 7, {'url': 'https://cdn.example/Show.2x07.720p.mkv'}))

    def test_a_resolution_is_not_a_season_pair(self):
        """``1920x1080`` must not be read as season 1920, episode 1080."""
        item = {'url': self.PACK + 'Dexter.S06E10.1080p.x264.mkv', 'quality': '1920x1080'}
        self.assertTrue(self.belongs(6, 10, item))

    def test_the_folder_naming_a_season_range_decides_nothing(self):
        """Every URL in this pack sits under ``/S01-S09/``, which means neither."""
        self.assertTrue(self.belongs(6, 10, {'url': self.PACK + 'Dexter.S06E10.mkv'}))

    # --- the same statement in words -------------------------------------

    def test_persian_words_naming_our_season_and_episode(self):
        item = {'url': self.PACK + 'dexter-ep10-dubbed.mkv', 'label': 'فصل 6 · قسمت 10'}
        self.assertTrue(self.belongs(6, 10, item))

    def test_persian_words_naming_another_season(self):
        item = {'url': self.PACK + 'dexter-dubbed.mkv', 'label': 'فصل 1 · قسمت 10'}
        self.assertFalse(self.belongs(6, 10, item))

    def test_persian_digits_read_like_ascii(self):
        item = {'url': self.PACK + 'dexter-dubbed.mkv', 'label': 'فصل ۶ · قسمت ۱۰'}
        self.assertTrue(self.belongs(6, 10, item))

    # --- nothing states a season: the single-season pack ------------------

    def test_episode_number_alone_decides_when_no_season_is_stated(self):
        url = 'https://cdn.example/Chernobyl/Chernobyl.E10.1080p.mkv'
        self.assertTrue(self.belongs(1, 10, {'url': url, 'label': 'قسمت 10'}))

    def test_episode_number_alone_still_has_to_match(self):
        url = 'https://cdn.example/Chernobyl/Chernobyl.E11.1080p.mkv'
        self.assertFalse(self.belongs(1, 10, {'url': url}))

    def test_three_digit_episode_numbers_are_not_truncated(self):
        """One Piece E258 is episode 258, not episode 25 with a stray 8."""
        url = 'https://cdn.example/One.Piece.S01E258.1080p.mp4'
        self.assertTrue(self.belongs(1, 258, {'url': url}))
        self.assertFalse(self.belongs(1, 25, {'url': url}))

    def test_a_zero_padded_episode_number_is_the_same_episode(self):
        """``E035`` is episode 35. Matching the two-digit spelling literally
        made 1,774 correctly-linked hardsub episodes look mislinked."""
        url = 'https://cdn.example/Yali.Capkini.E035.HardSub.540p.mkv'
        self.assertTrue(self.belongs(1, 35, {'url': url}))
        self.assertFalse(self.belongs(1, 36, {'url': url}))

    def test_the_unpadded_and_spaced_spellings_still_match(self):
        episode = self.episode(1, 35)
        for url in ('https://cdn.example/Show.E35.mkv',
                    'https://cdn.example/Show.Ep35.mkv',
                    'https://cdn.example/Show.Ep.35.mkv',
                    'https://cdn.example/Show.E0035.mkv'):
            self.assertTrue(
                verification._link_belongs_to_episode({'url': url}, url, episode), url)

    def test_percent_encoded_separators_do_not_hide_the_pair(self):
        """``%20`` leaves a digit against the ``S``, so every word-boundary
        pattern slid past the pair and the link read as naming nothing."""
        url = 'https://cdn.example/Karen%20Pirie%20S01%20E03%20720p%20WEBRip.mkv'
        self.assertTrue(self.belongs(1, 3, {'url': url}))
        self.assertFalse(self.belongs(2, 3, {'url': url}))


class EpisodeIdentityTests(TestCase):
    """Reading what a link's file name claims, and nothing the importer wrote."""

    def stated(self, url):
        return verification.stated_episode_identity(url)

    def test_it_reads_the_pair_a_link_states(self):
        self.assertEqual(self.stated('https://cdn.example/Show.S02E05.mkv'), (2, 5))
        self.assertEqual(self.stated('https://cdn.example/Show.2x05.mkv'), (2, 5))

    def test_an_episode_with_no_season_leaves_the_season_open(self):
        self.assertEqual(self.stated('https://cdn.example/Show.E05.mkv'), (None, 5))
        self.assertEqual(self.stated('https://cdn.example/Asi-E090.mp4'), (None, 90))

    def test_a_link_that_names_nothing_is_not_a_mistake(self):
        self.assertIsNone(self.stated('https://cdn.example/6f2a91c4b8.mkv'))
        self.assertIsNone(self.stated('https://cdn.example/Show.1080p.WEB-DL.mkv'))

    def test_a_link_that_names_two_episodes_states_neither(self):
        """A pack index is not a claim about any single file."""
        self.assertIsNone(self.stated('https://cdn.example/Show.S01E01-S01E09.mkv'))

    def test_a_zero_is_not_an_episode(self):
        """Two shapes on production, one rule.

        ``S02E0`` is a *truncated* S02E07 — The Good Place, where the
        provider's own file name lost a digit — and ``S01E00`` is Euphoria's
        special, which has no episode row to be right or wrong about. Read
        literally, both offer an "episode 0" for a caller to file a link under
        or repair a row against.
        """
        self.assertIsNone(self.stated('https://cdn.example/The.Good.Place.S02E0.720p.mkv'))
        self.assertIsNone(self.stated('https://cdn.example/Euphoria.S01E00.1080p.mkv'))
        self.assertIsNone(self.stated('https://cdn.example/Show.قسمت 0.mkv'))
        self.assertIsNone(self.stated('https://cdn.example/Show.E0.mkv'))

    def test_only_the_file_name_gets_a_vote(self):
        """Everything the importer wrote is what an audit is checking.

        ``episode_number``, ``season_number`` and ``label`` all come from one
        pass over one provider page, so none of them can testify against the
        others. The label is the easy one to forget: «فندک و شاهزاده خانم» has
        two files labelled «قسمت ۱», which puts every later label one episode
        behind the file it names.
        """
        self.assertEqual(
            verification.stated_episode_identity('https://cdn.example/Show.S01E26.mkv'),
            (1, 26))
        self.assertEqual(
            verification.stated_episode_identity(
                'https://cdn.example/Lighter.and.Princess.2022.EP03.480p.mkv'),
            (None, 3))

    def test_an_unstated_season_cannot_contradict_one(self):
        episode = Episode.objects.create(
            season=Season.objects.create(
                series=Series.objects.create(title='S', slug='identity-match'),
                season_number=6),
            episode_number=10,
        )
        self.assertTrue(verification.episode_identity_matches((None, 10), episode))
        self.assertTrue(verification.episode_identity_matches((6, 10), episode))
        self.assertFalse(verification.episode_identity_matches((1, 10), episode))
        self.assertFalse(verification.episode_identity_matches((None, 11), episode))
        self.assertFalse(verification.episode_identity_matches(None, episode))

    def test_everything_it_answers_the_matcher_also_agrees_with(self):
        """The asymmetry must only point the safe way.

        A stated identity that differs from the row is what the audit treats
        as proof of a mislink, so any text this reads as naming *this* episode
        has to be one the matcher also keeps. The reverse gap is harmless: a
        form the matcher reads and this one does not is merely left out.
        """
        episode = Episode.objects.create(
            season=Season.objects.create(
                series=Series.objects.create(title='S', slug='subset-check'),
                season_number=1),
            episode_number=35,
        )
        for url in ('https://cdn.example/Show.E35.mkv',
                    'https://cdn.example/Show.E035.mkv',
                    'https://cdn.example/Show.S01E35.mkv',
                    'https://cdn.example/Show.1x35.mkv',
                    'https://cdn.example/Show%20S01%20E35%20720p.mkv'):
            self.assertTrue(
                verification.episode_identity_matches(
                    verification.stated_episode_identity(url), episode), url)
            self.assertTrue(
                verification._link_belongs_to_episode({'url': url}, url, episode),
                f'{url} is named as episode 35 but the matcher disowns it')


class RestoreGeoPrunedLinksTests(_Base):
    """Mirrors pruned by the 2 KB misreading come back — but only on a fresh probe."""

    GONE = 'https://cdn.example/film.2160p.mkv'

    def _pruned(self, movie, urls):
        MediaCheck.objects.create(
            content_type='movie', object_id=movie.pk, episode_id=0,
            status=MediaCheck.Status.FAILED, reason='all_sources_dead',
            detail={'probes': [
                {'url': url, 'verdict': 'dead', 'reason': 'html_not_video'} for url in urls
            ]},
            checked_at=timezone.now(),
        )

    def _run(self, *args):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command('restore_geo_pruned_links', *args, stdout=out)
        return out.getvalue()

    def test_geo_blocked_mirror_is_put_back(self):
        movie = self.movie([], slug='drafted')
        self._pruned(movie, [MKV_URL])
        geo = unknown(MKV_URL, 'geo_blocked')
        with patch.object(media_probe, 'probe_url', return_value=geo), \
                patch.object(verification, '_probe', return_value=geo):
            output = self._run('--apply')
        movie.refresh_from_db()
        self.assertIn('restored_titles=1', output)
        self.assertEqual([link['url'] for link in movie.download_links], [MKV_URL])

    def test_really_dead_mirror_stays_gone(self):
        movie = self.movie([], slug='gone')
        self._pruned(movie, [self.GONE])
        with patch.object(media_probe, 'probe_url', return_value=dead(self.GONE, 'html_not_video')):
            output = self._run('--apply')
        movie.refresh_from_db()
        self.assertIn('restorable=0', output)
        self.assertEqual(movie.download_links, [])

    def test_dry_run_changes_nothing(self):
        movie = self.movie([], slug='dry')
        self._pruned(movie, [MKV_URL])
        with patch.object(media_probe, 'probe_url', return_value=unknown(MKV_URL, 'geo_blocked')):
            output = self._run()
        movie.refresh_from_db()
        self.assertIn('RESTORE_DRY_RUN', output)
        self.assertEqual(movie.download_links, [])
