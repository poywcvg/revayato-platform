"""Tests for the one fact that took most of this catalog off the air.

Almost every provider link here is time-limited: ``…?md5=<token>&expires=<unix>``,
and the token lapses in about thirteen hours. Two things followed from that, and
both are pinned here.

**A lapsed token must not read as a dead film.** The CDN answers ``410 Gone``,
which :mod:`media_probe` counts as definitive — so the sweep condemned 4,119 of
the first 6,387 movies it looked at, and ``none`` is the one verdict allowed to
blank a link. The film was on the origin the whole time; only the token had
run out.

**And something has to re-sign it.** The scheduled refresh managed 240 titles an
hour against 26,644 rows that lapse twice a day, which is not a rate problem
that can be tuned away — so the refresh now happens when a viewer actually asks
to watch, which is the only moment that reliably identifies a link that needs to
be valid right now.
"""

import threading
import time
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.catalog import media_probe, playback_gate as gate, playback_resolve
from apps.catalog.media_probe import Probe
from apps.catalog.models import Episode, Movie, PlaybackMode, Season, Series

FRESH = 'https://s8.cdn.example/Film.2026.1080p.x264.mp4?md5=abc&expires=%d'
LAPSED = 'https://s8.cdn.example/Film.2026.1080p.x264.mp4?md5=abc&expires=%d'
PLAIN = 'https://cdn.example/Film.2026.1080p.x264.mp4'


def fresh_url(seconds=86_400):
    return FRESH % int(time.time() + seconds)


def lapsed_url(seconds=86_400):
    return LAPSED % int(time.time() - seconds)


class SignatureExpiryTests(TestCase):
    """Reading the token. A false positive here makes a good link unplayable."""

    def test_a_url_without_a_token_never_expires(self):
        self.assertIsNone(media_probe.signature_expiry(PLAIN))
        self.assertFalse(media_probe.signature_expired(PLAIN))

    def test_a_future_token_is_not_expired_and_a_past_one_is(self):
        self.assertFalse(media_probe.signature_expired(fresh_url()))
        self.assertTrue(media_probe.signature_expired(lapsed_url()))

    def test_a_millisecond_token_is_not_read_as_the_year_58000(self):
        """Both units appear in the wild, and the difference is a factor of 1000.

        Read as seconds, a millisecond timestamp is a link valid for nine
        thousand years — every lapsed link on that provider would look healthy.
        """
        past_ms = int((time.time() - 86_400) * 1000)
        self.assertTrue(media_probe.signature_expired(f'{PLAIN}?expires={past_ms}'))
        future_ms = int((time.time() + 86_400) * 1000)
        self.assertFalse(media_probe.signature_expired(f'{PLAIN}?expires={future_ms}'))

    def test_a_token_about_to_lapse_counts_as_lapsed(self):
        """A probe begun inside the last seconds of validity is answered after it.

        Handing such a URL to a player fails mid-buffer, which reads to a viewer
        as the film breaking rather than as a link that needed refreshing.
        """
        edge = f'{PLAIN}?expires={int(time.time() + 30)}'
        self.assertTrue(media_probe.signature_expired(edge))
        self.assertFalse(media_probe.signature_expired(edge, skew=0))

    def test_a_number_that_is_not_an_expiry_is_ignored(self):
        """Only the parameters providers actually use. Guessing costs good links."""
        self.assertFalse(media_probe.signature_expired(f'{PLAIN}?size=1200000000'))
        self.assertFalse(media_probe.signature_expired(f'{PLAIN}?start=1000000000'))


class ProbeShortCircuitTests(TestCase):
    """What the probe does with a lapsed token: nothing, on purpose."""

    def test_a_lapsed_url_is_never_requested(self):
        """The answer would describe the token, not the film.

        And the answer it would get — ``410`` — is the one status that counts as
        proof the film is gone.
        """
        with patch('apps.catalog.media_probe._confirm') as confirmed:
            probe = media_probe.probe_url(lapsed_url(), use_cache=False)
        confirmed.assert_not_called()
        self.assertEqual(probe.verdict, 'unknown')
        self.assertEqual(probe.reason, 'signature_expired')
        self.assertFalse(probe.dead)

    def test_a_fresh_url_is_still_probed_normally(self):
        url = fresh_url()
        with patch('apps.catalog.media_probe._confirm',
                   return_value=Probe(url=url, verdict='live', status=206)) as confirmed:
            probe = media_probe.probe_url(url, use_cache=False)
        confirmed.assert_called_once()
        self.assertTrue(probe.live)


class GateExpiryTests(TestCase):
    """The gate's two jobs around expiry: prefer fresh, and never condemn."""

    def setUp(self):
        cache.clear()

    def test_a_fresh_mirror_outranks_a_lapsed_one(self):
        """Ranking decides what gets probed first, and a lapsed link cannot win.

        The lapsed URL here is the better-named file — 1080p against 480p — so
        without the expiry demotion the filename heuristic would put it first
        and the title would be judged on a token instead of on a film.
        """
        links = [
            {'url': lapsed_url(), 'quality': '1080p'},
            {'url': 'https://cdn.example/Film.2026.480p.x264.mp4', 'quality': '480p'},
        ]
        ranked = gate.rank_candidates(links)
        self.assertEqual(ranked[0]['quality'], '480p')

    def test_a_lapsed_link_is_ranked_but_not_dropped(self):
        """A title whose every token has lapsed still needs a link to re-crawl from.

        Dropping them would leave ``rank_candidates`` empty, which reads
        downstream as ``no_candidates`` — the beginning of the deletion path,
        for a title whose only problem is that it needs re-signing.
        """
        ranked = gate.rank_candidates([{'url': lapsed_url(), 'quality': '1080p'}])
        self.assertEqual(len(ranked), 1)

    def test_a_title_whose_tokens_lapsed_is_never_judged_gone(self):
        """``none`` is the only verdict that may blank a link. Expiry must not reach it."""
        links = [{'url': lapsed_url(), 'quality': '1080p'},
                 {'url': lapsed_url(2), 'quality': '720p'}]
        choice = gate.choose_playback_link(links, use_cache=False)
        self.assertNotEqual(choice.mode, gate.MODE_NONE)
        self.assertEqual(choice.reason, 'signature_expired')

    def test_a_genuinely_dead_unsigned_link_is_still_judged_gone(self):
        """The fix must not make the gate unable to condemn anything at all."""
        with patch('apps.catalog.media_probe.probe_url',
                   side_effect=lambda url, **kw: Probe(url=url, verdict='dead', reason='http_404')):
            choice = gate.choose_playback_link([{'url': PLAIN}], use_cache=False)
        self.assertEqual(choice.mode, gate.MODE_NONE)


class ResolveTests(TestCase):
    """Re-signing at play time."""

    def setUp(self):
        cache.clear()
        # Inline, not threaded: the crawl thread opens its own DB connection,
        # which cannot see the transaction this TestCase is holding open. The
        # hand-off that the thread exists for is tested separately below.
        threaded = patch.object(playback_resolve, 'THREADED', False)
        threaded.start()
        self.addCleanup(threaded.stop)
        self.movie = Movie.objects.create(
            title='فیلم', slug='film', is_published=True,
            download_links=[{'url': lapsed_url(), 'quality': '1080p'}],
            video_url=lapsed_url(),
        )

    def test_a_fresh_link_costs_nothing(self):
        """The overwhelmingly common case. It must not touch a provider or a lock."""
        self.movie.video_url = fresh_url()
        self.movie.save(update_fields=['video_url'])
        with patch('apps.catalog.playback_refresh._crawl_one') as crawl:
            result = playback_resolve.resolve_playback(self.movie)
        crawl.assert_not_called()
        self.assertEqual(result.reason, 'fresh')
        self.assertFalse(result.refreshed)
        self.assertFalse(result.stale)

    def test_a_lapsed_link_is_re_crawled_and_written_back(self):
        replacement = fresh_url()

        def crawl(slug, obj, **kw):
            Movie.objects.filter(pk=obj.pk).update(
                download_links=[{'url': replacement, 'quality': '1080p'}],
            )
            return {'imported_count': 1}

        with patch('apps.catalog.playback_refresh._crawl_one', side_effect=crawl), \
             patch('apps.catalog.provider_import.multi_provider_crawl.catalog_link_providers',
                   return_value=['myf2m']), \
             patch('apps.catalog.media_probe.probe_url',
                   side_effect=lambda url, **kw: Probe(
                       url=url, verdict='live', status=206, accept_ranges=True,
                       content_type='video/mp4', content_length=900_000_000)), \
             patch('apps.catalog.media_tech.verify_source',
                   return_value={'verdict': 'safe', 'container': 'mp4', 'video': 'h264'}):
            result = playback_resolve.resolve_playback(self.movie)

        self.assertTrue(result.refreshed)
        self.assertEqual(result.url, replacement)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.video_url, replacement)
        self.assertEqual(self.movie.playback_mode, PlaybackMode.DIRECT)

    def test_a_crawl_that_finds_nothing_returns_the_stale_url_not_an_error(self):
        """Failing closed here shows a viewer nothing at all.

        A lapsed link that probably will not play is still better than refusing
        to try — some CDNs honour a spent token, and the client already knows
        how to report a failure.
        """
        original = self.movie.video_url
        with patch('apps.catalog.playback_refresh._crawl_one',
                   side_effect=RuntimeError('provider down')), \
             patch('apps.catalog.provider_import.multi_provider_crawl.catalog_link_providers',
                   return_value=['myf2m']):
            result = playback_resolve.resolve_playback(self.movie)
        self.assertEqual(result.url, original)
        self.assertTrue(result.stale)
        self.assertEqual(result.reason, 'provider_unavailable')

    def test_a_title_that_could_not_be_refreshed_is_not_crawled_again_at_once(self):
        """A popular broken title must not become a crawl loop against a provider."""
        with patch('apps.catalog.playback_refresh._crawl_one',
                   side_effect=RuntimeError('provider down')), \
             patch('apps.catalog.provider_import.multi_provider_crawl.catalog_link_providers',
                   return_value=['myf2m']):
            playback_resolve.resolve_playback(self.movie)
            with patch('apps.catalog.playback_refresh._crawl_one') as second:
                result = playback_resolve.resolve_playback(self.movie)
        second.assert_not_called()
        self.assertEqual(result.reason, 'cooldown')

    def test_allow_refresh_false_answers_without_crawling(self):
        with patch('apps.catalog.playback_refresh._crawl_one') as crawl:
            result = playback_resolve.resolve_playback(self.movie, allow_refresh=False)
        crawl.assert_not_called()
        self.assertEqual(result.reason, 'expired')
        self.assertTrue(result.stale)

    def test_a_second_viewer_waits_for_the_first_ones_crawl(self):
        """A season's episodes share one provider page, so twenty viewers are one crawl."""
        key = playback_resolve._LOCK_PREFIX + playback_resolve._key(self.movie)
        cache.set(key, 'running', 30)
        replacement = fresh_url()
        Movie.objects.filter(pk=self.movie.pk).update(video_url=replacement)
        with patch('apps.catalog.playback_refresh._crawl_one') as crawl, \
             patch.object(playback_resolve, 'WAIT_FOR_HOLDER_SECONDS', 0.5):
            result = playback_resolve.resolve_playback(self.movie)
        crawl.assert_not_called()
        self.assertEqual(result.url, replacement)
        self.assertTrue(result.refreshed)

    def test_an_episode_is_locked_on_its_series_not_on_itself(self):
        """One season, one ``download_links`` list, one provider page: one crawl."""
        series = Series.objects.create(title='سریال', slug='serial', is_published=True)
        season = Season.objects.create(series=series, season_number=1)
        one = Episode.objects.create(season=season, episode_number=1, is_published=True)
        two = Episode.objects.create(season=season, episode_number=2, is_published=True)
        self.assertEqual(
            playback_resolve._key(series, one), playback_resolve._key(series, two),
        )


class StreamOpenResignTests(TestCase):
    """The gateway must not spend a process rediscovering a lapsed token."""

    def test_only_the_query_string_may_change(self):
        from apps.catalog.stream_api import _same_file

        self.assertTrue(_same_file(f'{PLAIN}?md5=a&expires=1', f'{PLAIN}?md5=b&expires=2'))
        self.assertFalse(_same_file(PLAIN, 'https://other.example/Film.2026.1080p.x264.mp4'))
        self.assertFalse(_same_file(PLAIN, 'https://cdn.example/Other.2026.1080p.x264.mp4'))

    def test_a_fresh_url_is_passed_straight_through(self):
        from apps.catalog.stream_api import _resigned

        url = fresh_url()
        with patch('apps.catalog.playback_resolve.resolve_playback') as resolve:
            self.assertEqual(_resigned('movie', 1, url), url)
        resolve.assert_not_called()


class DeadlineHandoffTests(TestCase):
    """A slow crawl must cost the viewer the budget, and not one second more."""

    def setUp(self):
        cache.clear()
        self.movie = Movie.objects.create(
            title='کند', slug='kond', is_published=True,
            download_links=[{'url': lapsed_url(), 'quality': '1080p'}],
            video_url=lapsed_url(),
        )

    def test_a_crawl_slower_than_the_budget_still_answers_on_time(self):
        """The viewer gets the stale URL at the deadline, not whenever the crawl ends."""
        started = threading.Event()

        def slow(*args, **kwargs):
            started.set()
            time.sleep(3.0)

        with patch.object(playback_resolve, 'DEADLINE_SECONDS', 0.3), \
                patch('apps.catalog.playback_refresh._crawl_one', side_effect=slow):
            began = time.monotonic()
            result = playback_resolve.resolve_playback(self.movie)
            waited = time.monotonic() - began

        self.assertTrue(started.wait(2.0), 'the crawl never actually started')
        self.assertLess(waited, 2.0, 'the viewer waited for the whole crawl')
        self.assertEqual(result.reason, 'refresh_in_progress')
        self.assertTrue(result.stale)
        # Stale, but still playable-ish: never an empty URL.
        self.assertTrue(result.url)

    def test_a_handed_off_crawl_is_not_raced_by_the_next_viewer(self):
        """The lock travels with the thread, so viewer two waits instead of re-crawling."""
        calls = []

        def slow(slug, *args, **kwargs):
            calls.append(slug)
            time.sleep(2.0)

        with patch.object(playback_resolve, 'DEADLINE_SECONDS', 0.3), \
                patch.object(playback_resolve, 'WAIT_FOR_HOLDER_SECONDS', 0.5), \
                patch('apps.catalog.playback_refresh._crawl_one', side_effect=slow):
            playback_resolve.resolve_playback(self.movie)
            first = len(calls)
            second = playback_resolve.resolve_playback(self.movie)

        self.assertEqual(len(calls), first, 'a second crawl started on a locked title')
        self.assertTrue(second.stale)
