"""Tests for the two import gates that read the actual file.

Everything the catalog knew about a source used to come from its *name*. These
two modules read the bytes instead, and the tests worth having are the ones
that pin the difference:

* :mod:`media_tech` — a filename that says ``.mp4`` and an encode that is HEVC,
  Matroska, or carrying DTS audio no browser decodes;
* :mod:`subtitle_verify` — a subtitle that is English, truncated, an advert, or
  timed against a different framerate than the encode it will play over.

And, in both, the rule that keeps a gate from doing damage of its own: when the
check cannot reach an answer, the outcome is exactly what it was before the
gate existed. Nothing here spawns ffprobe or touches the network.
"""

from __future__ import annotations

import time
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.catalog import media_tech, media_verification as verification, subtitle_verify
from apps.catalog.media_probe import Probe
from apps.catalog.models import MediaCheck, Movie
from apps.catalog.stream_gateway import SourceTech

MP4_URL = 'https://cdn.example/film.1080p.mp4'
MP4_URL_2 = 'https://cdn2.example/film.1080p.web-dl.mp4'


def live(url=MP4_URL):
    return Probe(
        url=url, verdict='live', reason='', status=206,
        content_type='video/mp4', content_length=900_000_000, accept_ranges=True,
    )


def tech(**kw) -> SourceTech:
    base = dict(ok=True, container='mov', video_codec='h264', audio_codec='aac', duration=7200.0)
    base.update(kw)
    return SourceTech(**base)


class ClassifyTechTests(TestCase):
    """What a browser will make of a file, given what it really contains."""

    def test_h264_in_mp4_is_safe(self):
        self.assertEqual(media_tech.classify_tech(tech()), ('safe', ''))

    def test_hevc_behind_an_mp4_name_is_caught(self):
        """The whole point of the module: the name passes, the encode does not."""
        self.assertEqual(
            media_tech.classify_tech(tech(video_codec='hevc')), ('unsafe', 'video_hevc'),
        )

    def test_matroska_behind_an_mp4_name_is_caught(self):
        self.assertEqual(
            media_tech.classify_tech(tech(container='matroska')), ('unsafe', 'container_mkv'),
        )

    def test_webm_is_not_mistaken_for_mkv(self):
        """ffprobe calls both 'matroska'; the codec is what separates them."""
        self.assertEqual(
            media_tech.classify_tech(tech(container='matroska', video_codec='vp9', audio_codec='opus')),
            ('safe', ''),
        )

    def test_dts_audio_is_unsafe(self):
        """Picture plays, sound does not, and the player reports no error."""
        self.assertEqual(
            media_tech.classify_tech(tech(audio_codec='dts')), ('unsafe', 'audio_dts'),
        )

    def test_ac3_audio_is_unsafe(self):
        self.assertEqual(
            media_tech.classify_tech(tech(audio_codec='ac3')), ('unsafe', 'audio_ac3'),
        )

    def test_avi_is_unsafe_whatever_is_inside(self):
        self.assertEqual(
            media_tech.classify_tech(tech(container='avi', audio_codec='mp3')),
            ('unsafe', 'container_avi'),
        )

    def test_missing_audio_stream_is_still_playable(self):
        self.assertEqual(media_tech.classify_tech(tech(audio_codec='')), ('safe', ''))

    def test_failed_probe_is_unknown_not_unsafe(self):
        verdict, reason = media_tech.classify_tech(tech(ok=False, reason='timeout'))
        self.assertEqual((verdict, reason), ('unknown', 'timeout'))

    def test_unrecognised_codec_is_unknown_not_safe(self):
        verdict, _ = media_tech.classify_tech(tech(video_codec='theora'))
        self.assertEqual(verdict, 'unknown')

    def test_manifest_container_is_not_judged(self):
        verdict, _ = media_tech.classify_tech(tech(container='hls'), is_manifest=True)
        self.assertEqual(verdict, 'safe')


@override_settings(CATALOG_VERIFY_CODEC_BEFORE_PUBLISH=True)
class CodecGateTests(TestCase):
    """What the codec truth is allowed to change about a publish verdict."""

    def movie(self, links, **kw):
        return Movie.objects.create(
            title='فیلم', slug=kw.pop('slug', 'film'), download_links=links, **kw,
        )

    def verify(self, movie, tech_result):
        with patch.object(verification, '_probe', return_value=live()), \
             patch.object(media_tech, 'verify_source', return_value=tech_result):
            return verification.verify_target(movie)

    def safe_result(self, **kw):
        row = {
            'verdict': 'safe', 'reason': '', 'container': 'mp4', 'video': 'h264',
            'audio': 'aac', 'duration': 7200.0, 'width': 1920, 'height': 804,
        }
        row.update(kw)
        return row

    def test_confirmed_h264_publishes_as_playable(self):
        movie = self.movie([{'url': MP4_URL, 'quality': '1080p'}])
        verdict = self.verify(movie, self.safe_result())
        self.assertTrue(verdict['playable'])
        self.assertEqual(verdict['status'], MediaCheck.Status.PASSED)

    def test_hevc_behind_an_mp4_name_is_demoted_to_download_only(self):
        """Previously published as playable; Firefox and Chrome showed a black
        frame and the viewer filed the report we then had to chase."""
        movie = self.movie([{'url': MP4_URL, 'quality': '1080p'}])
        verdict = self.verify(movie, self.safe_result(verdict='unsafe', reason='video_hevc', video='hevc'))
        self.assertFalse(verdict['playable'])
        self.assertTrue(verdict['downloadable'])
        self.assertEqual(verdict['reason'], 'download_only')

    def test_demoted_source_is_recorded_as_unsafe_for_the_crawler(self):
        movie = self.movie([{'url': MP4_URL, 'quality': '1080p'}])
        verdict = self.verify(movie, self.safe_result(verdict='unsafe', reason='container_mkv'))
        row = verdict['probes'][0]
        self.assertFalse(row['safe'])
        self.assertEqual(row['tech']['reason'], 'container_mkv')

    def test_unreadable_codec_falls_back_to_the_filename(self):
        """An ffprobe that cannot answer must leave us exactly where we were."""
        movie = self.movie([{'url': MP4_URL, 'quality': '1080p'}])
        verdict = self.verify(movie, {'verdict': 'unknown', 'reason': 'timeout'})
        self.assertTrue(verdict['playable'])

    def test_probe_exception_never_blocks_an_import(self):
        movie = self.movie([{'url': MP4_URL, 'quality': '1080p'}])
        with patch.object(verification, '_probe', return_value=live()), \
             patch.object(media_tech, 'verify_source', side_effect=RuntimeError('boom')):
            verdict = verification.verify_target(movie)
        self.assertTrue(verdict['playable'])

    def test_a_second_mirror_can_still_win(self):
        """One bad encode does not condemn the title — the next mirror is tried."""
        movie = self.movie([
            {'url': MP4_URL, 'quality': '1080p'},
            {'url': MP4_URL_2, 'quality': '1080p'},
        ])
        results = {
            MP4_URL: self.safe_result(verdict='unsafe', reason='video_hevc'),
            MP4_URL_2: self.safe_result(),
        }
        with patch.object(verification, '_probe', side_effect=lambda url, **kw: live(url)), \
             patch.object(media_tech, 'verify_source', side_effect=lambda url, **kw: results[url]):
            verdict = verification.verify_target(movie)
        self.assertTrue(verdict['playable'])

    def test_tech_budget_caps_the_ffprobes(self):
        urls = [f'https://cdn.example/m{i}.mp4' for i in range(5)]
        movie = self.movie([{'url': url, 'quality': '1080p'} for url in urls])
        calls = []

        def spy(url, **kw):
            calls.append(url)
            return self.safe_result(verdict='unsafe', reason='video_hevc')

        with patch.object(verification, '_probe', side_effect=lambda url, **kw: live(url)), \
             patch.object(media_tech, 'verify_source', side_effect=spy):
            verification.verify_target(movie)
        self.assertEqual(len(calls), verification.MAX_TECH_PROBES_PER_TARGET)

    def test_an_expired_sweep_deadline_stops_probing_without_blocking(self):
        """A batch that has used its wall clock falls back to the filename.

        ``probe_tech`` caches only successes, so a host that stalls costs the
        full ffprobe timeout on every sweep. Past the deadline we stop asking —
        and the title stays publishable, exactly as before this check existed.
        """
        movie = self.movie([{'url': MP4_URL, 'quality': '1080p'}])
        with patch.object(verification, '_probe', return_value=live()), \
             patch.object(media_tech, 'verify_source') as probe:
            verdict = verification.verify_target(
                movie, tech_deadline=time.monotonic() - 1,
            )
        probe.assert_not_called()
        self.assertTrue(verdict['playable'])

    def test_a_live_deadline_still_probes(self):
        movie = self.movie([{'url': MP4_URL, 'quality': '1080p'}])
        with patch.object(verification, '_probe', return_value=live()), \
             patch.object(media_tech, 'verify_source',
                          return_value=self.safe_result(verdict='unsafe', reason='video_hevc')):
            verdict = verification.verify_target(
                movie, tech_deadline=time.monotonic() + 600,
            )
        self.assertFalse(verdict['playable'])
        self.assertTrue(verdict['downloadable'])

    @override_settings(CATALOG_VERIFY_CODEC_BEFORE_PUBLISH=False)
    def test_disabled_returns_to_filename_trust(self):
        movie = self.movie([{'url': MP4_URL, 'quality': '1080p'}])
        with patch.object(verification, '_probe', return_value=live()), \
             patch.object(media_tech, 'real_tech') as probe:
            verdict = verification.verify_target(movie)
        probe.assert_not_called()
        self.assertTrue(verdict['playable'])

    def test_measured_runtime_is_stored_for_the_subtitle_gate(self):
        movie = self.movie([{'url': MP4_URL, 'quality': '1080p'}])
        self.verify(movie, self.safe_result(duration=7412.5))
        self.assertEqual(verification.measured_duration(movie), 7412.5)

    def test_runtime_is_zero_when_nothing_was_measured(self):
        movie = self.movie([{'url': MP4_URL, 'quality': '1080p'}])
        self.assertEqual(verification.measured_duration(movie), 0.0)

    def test_runtime_survives_an_encode_no_browser_can_play(self):
        """A Matroska copy is still published, still gets subtitles — and its
        measured runtime is the only thing those subtitles can be synced to.

        Most of the real catalog is exactly this case, so discarding the
        duration here would have left the subtitle sync gate blind on the
        titles that need it most.
        """
        movie = self.movie([{'url': MP4_URL, 'quality': '1080p'}])
        verdict = self.verify(movie, self.safe_result(
            verdict='unsafe', reason='container_mkv', duration=6168.0,
        ))
        self.assertFalse(verdict['playable'])
        self.assertTrue(verdict['downloadable'])
        self.assertEqual(verification.measured_duration(movie), 6168.0)

    def test_a_playable_mirror_wins_the_stored_runtime(self):
        movie = self.movie([
            {'url': MP4_URL, 'quality': '1080p'},
            {'url': MP4_URL_2, 'quality': '1080p'},
        ])
        results = {
            MP4_URL: self.safe_result(verdict='unsafe', reason='container_mkv', duration=6168.0),
            MP4_URL_2: self.safe_result(duration=7412.5),
        }
        with patch.object(verification, '_probe', side_effect=lambda url, **kw: live(url)), \
             patch.object(media_tech, 'verify_source', side_effect=lambda url, **kw: results[url]):
            verification.verify_target(movie)
        self.assertEqual(verification.measured_duration(movie), 7412.5)


def vtt(count, *, end, text='سلام دنیا این یک زیرنویس فارسی است', hold=2.0) -> bytes:
    """A WebVTT document of ``count`` cues, the last ending at ``end`` seconds."""
    step = (end - hold) / max(1, count - 1)

    def stamp(value):
        hours, value = int(value // 3600), value % 3600
        return f'{hours:02d}:{int(value // 60):02d}:{value % 60:06.3f}'

    lines = ['WEBVTT', '']
    for index in range(count):
        start = index * step
        lines += [f'{stamp(start)} --> {stamp(start + hold)}', text, '']
    return '\n'.join(lines).encode('utf-8')


class SubtitleVerifyTests(TestCase):
    """Whether a cue file is a Persian subtitle for *this* encode."""

    def test_a_good_subtitle_passes(self):
        report = subtitle_verify.verify_payload(vtt(400, end=7000.0), duration=7100.0)
        self.assertEqual((report['verdict'], report['reason']), ('passed', ''))

    def test_a_stub_is_not_a_subtitle(self):
        report = subtitle_verify.verify_payload(vtt(5, end=600.0), duration=7100.0)
        self.assertEqual(report['verdict'], 'failed')
        self.assertEqual(report['reason'], 'only_5_cues')

    def test_an_english_file_labelled_persian_is_rejected(self):
        payload = vtt(400, end=7000.0, text='Hello there, this is a subtitle line')
        report = subtitle_verify.verify_payload(payload, duration=7100.0)
        self.assertEqual(report['reason'], 'not_persian')

    def test_english_song_lines_do_not_condemn_a_persian_file(self):
        """Real Persian subtitles carry signs, song titles and credits."""
        mixed = 'او گفت که فردا می‌آید — "Some Song Title" — و رفت'
        report = subtitle_verify.verify_payload(vtt(400, end=7000.0, text=mixed), duration=7100.0)
        self.assertEqual(report['verdict'], 'passed')

    def test_an_advert_dump_is_rejected(self):
        promo = 'برای دانلود فیلم بیشتر به کانال ما بپیوندید @revayatochannel'
        report = subtitle_verify.verify_payload(vtt(400, end=7000.0, text=promo), duration=7100.0)
        self.assertEqual(report['reason'], 'advert_dump')

    def test_a_single_credit_line_is_not_an_advert(self):
        good = vtt(400, end=7000.0).decode('utf-8')
        good += '\n02:00:00.000 --> 02:00:04.000\nمترجم: کانال ما @somebody\n'
        report = subtitle_verify.verify_payload(good.encode('utf-8'), duration=7300.0)
        self.assertEqual(report['verdict'], 'passed')

    def test_a_half_download_is_rejected(self):
        report = subtitle_verify.verify_payload(vtt(400, end=3000.0), duration=7100.0)
        self.assertEqual(report['verdict'], 'failed')
        self.assertTrue(report['reason'].startswith('covers_only_'))

    def test_cues_running_past_the_film_are_rejected(self):
        report = subtitle_verify.verify_payload(vtt(400, end=9000.0), duration=7100.0)
        self.assertEqual(report['verdict'], 'failed')
        self.assertTrue(report['reason'].startswith('overruns_runtime_by_'))

    def test_without_a_measured_runtime_timing_is_not_judged(self):
        report = subtitle_verify.verify_payload(vtt(400, end=7000.0), duration=0.0)
        self.assertEqual((report['verdict'], report['reason']), ('passed', 'sync_unmeasured'))

    def test_empty_file(self):
        self.assertEqual(subtitle_verify.verify_payload(b'')['reason'], 'empty_file')

    @override_settings(CATALOG_VERIFY_SUBTITLES_BEFORE_PUBLISH=False)
    def test_disabled_stores_whatever_arrives(self):
        report = subtitle_verify.verify_payload(vtt(2, end=10.0), duration=7100.0)
        self.assertEqual(report['verdict'], 'unknown')


class FramerateCorrectionTests(TestCase):
    """Rescue a mistimed subtitle — without ever restretching a correct one."""

    RUNTIME = 7200.0

    def test_a_subtitle_overshooting_the_film_is_rescaled(self):
        payload = vtt(500, end=self.RUNTIME * (25.0 / 23.976) * 0.985)
        report = subtitle_verify.verify_payload(payload, duration=self.RUNTIME)
        self.assertEqual((report['verdict'], report['reason']), ('passed', 'fps_corrected'))
        self.assertEqual(report['scale'], round(23.976 / 25.0, 5))

    def test_the_corrected_file_is_what_gets_returned(self):
        payload = vtt(500, end=self.RUNTIME * (25.0 / 23.976) * 0.985)
        report = subtitle_verify.verify_payload(payload, duration=self.RUNTIME)
        self.assertNotEqual(report['payload'], payload)
        spans, _ = subtitle_verify.parse_cues(report['payload'].decode('utf-8'))
        self.assertEqual(len(spans), 500)
        self.assertLessEqual(spans[-1][1], self.RUNTIME)
        self.assertGreaterEqual(spans[-1][1] / self.RUNTIME, subtitle_verify.FIXED_COVERAGE_MIN)

    def test_a_correct_subtitle_is_never_rescaled(self):
        for share in (0.94, 0.95, 0.96, 0.97, 0.98, 0.99, 1.0):
            with self.subTest(share=share):
                self.assertIsNone(
                    subtitle_verify._fit_framerate(self.RUNTIME * share, self.RUNTIME),
                )

    def test_an_early_ending_subtitle_is_left_alone(self):
        """4% early is what a PAL-timed file looks like — and also what a file
        that simply ends before the credits looks like. Unknowable, so untouched:
        stretching a correct subtitle is worse than leaving a slightly early one."""
        self.assertIsNone(
            subtitle_verify._fit_framerate(self.RUNTIME * (23.976 / 25.0), self.RUNTIME),
        )

    def test_a_mistiming_that_is_not_a_framerate_ratio_stays_rejected(self):
        report = subtitle_verify.verify_payload(
            vtt(400, end=self.RUNTIME * 0.40), duration=self.RUNTIME,
        )
        self.assertEqual(report['verdict'], 'failed')

    def test_no_runtime_means_no_rescale(self):
        self.assertIsNone(subtitle_verify._fit_framerate(7000.0, 0.0))


class StoreGateTests(TestCase):
    """The choke point: every subtitle the catalog has ever served went here."""

    def store(self, payload, duration=0.0):
        from apps.catalog import subtitle_extract

        with patch.object(subtitle_extract, 'default_storage') as storage:
            storage.exists.return_value = False
            storage.save.side_effect = lambda key, content: key
            key = subtitle_extract._store_webvtt(payload, filename='x.vtt', duration=duration)
        return key, storage

    def test_a_good_subtitle_is_stored(self):
        key, storage = self.store(vtt(400, end=7000.0), duration=7100.0)
        self.assertEqual(key, 'catalog/subtitles/x.vtt')
        storage.save.assert_called_once()

    def test_a_rejected_subtitle_never_reaches_storage(self):
        key, storage = self.store(vtt(400, end=3000.0), duration=7100.0)
        self.assertEqual(key, '')
        storage.save.assert_not_called()

    def test_the_stored_bytes_are_the_corrected_ones(self):
        payload = vtt(500, end=7200.0 * (25.0 / 23.976) * 0.985)
        key, storage = self.store(payload, duration=7200.0)
        self.assertTrue(key)
        written = storage.save.call_args[0][1].file.read()
        self.assertNotEqual(written, payload)
        spans, _ = subtitle_verify.parse_cues(written.decode('utf-8'))
        self.assertLessEqual(spans[-1][1], 7200.0)
