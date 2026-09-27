from unittest.mock import patch

from django.test import TestCase

from apps.catalog.models import Movie, PlaybackSourceGap, Series
from apps.catalog import playback_sources


class CodecFamilyTests(TestCase):
    def test_hevc_tokens(self):
        for blob in ('movie.1080p.x265.mkv', 'Film.HEVC.10bit', 'clip.h265', 'a.DoVi.mp4', 'x.10bit'):
            self.assertEqual(playback_sources.codec_family(blob), 'hevc', blob)

    def test_av1_and_h264_and_unknown(self):
        self.assertEqual(playback_sources.codec_family('movie.av1.webm'), 'av1')
        self.assertEqual(playback_sources.codec_family('movie.x264.mp4'), 'h264')
        self.assertEqual(playback_sources.codec_family('movie.1080p.mp4'), '')


class ClassifyLinkTests(TestCase):
    def test_mkv_container_is_unsafe(self):
        self.assertEqual(playback_sources._classify_link({'url': 'https://cdn/x/movie.1080p.mkv'}), 'unsafe')

    def test_hevc_mp4_is_unsafe(self):
        self.assertEqual(
            playback_sources._classify_link({'url': 'https://cdn/x/movie.1080p.x265.mp4'}), 'unsafe',
        )

    def test_plain_mp4_is_safe(self):
        self.assertEqual(playback_sources._classify_link({'url': 'https://cdn/x/movie.1080p.mp4'}), 'safe')

    def test_hls_key_is_safe(self):
        self.assertEqual(playback_sources._classify_link({'key': 'hls/movie/master.m3u8'}), 'safe')

    def test_subtitle_and_expired_are_skipped(self):
        self.assertEqual(playback_sources._classify_link({'url': 'https://cdn/x/movie.fa.srt'}), 'skip')
        # A real provider expiry is an absolute Unix time — every one of the
        # 6,956 signed links in this catalog is exactly ten digits. A shorter
        # number is a duration or noise, and reading it as "expired in 1970"
        # would condemn links on any provider that publishes one.
        self.assertEqual(
            playback_sources._classify_link({'url': 'https://cdn/x/movie.mp4?expires=1000000000'}),
            'skip',
        )

    def test_the_playback_gate_sees_an_expired_link_the_gate_can_still_repair(self):
        """``ignore_expiry`` asks about the file, not about its access token.

        The gate has to rank a lapsed link to re-crawl it. Dropping it here is
        what left titles with no candidates at all, and no candidates is the
        start of the path that blanks a link.
        """
        expired = {'url': 'https://cdn/x/movie.1080p.mp4?expires=1000000000'}
        self.assertEqual(playback_sources._classify_link(expired), 'skip')
        self.assertEqual(
            playback_sources._classify_link(expired, ignore_expiry=True), 'safe',
        )
        # A dead host is still skipped either way: that is about the file.
        dead = {'url': 'https://cdnhost.lol/x/movie.1080p.mp4'}
        self.assertEqual(
            playback_sources._classify_link(dead, ignore_expiry=True), 'skip',
        )

    def test_signed_url_without_extension_is_not_false_flagged(self):
        # Ambiguous signed URL (no container/codec hint) must count as safe.
        self.assertEqual(playback_sources._classify_link({'url': 'https://cdn/stream/abc123?token=xyz'}), 'safe')


class DiagnoseMovieTests(TestCase):
    def _movie(self, links, **extra):
        return Movie.objects.create(
            title='T', original_title='T', slug=extra.pop('slug', 't-movie'),
            is_published=True, download_links=links, **extra,
        )

    def test_mkv_only_movie_is_unplayable(self):
        movie = self._movie([{'url': 'https://cdn/x/movie.1080p.mkv', 'quality': '1080p'}])
        diag = playback_sources.diagnose(movie)
        self.assertTrue(diag['unplayable'])
        self.assertEqual(diag['reason'], 'mkv_only')

    def test_hevc_only_movie_is_unplayable(self):
        movie = self._movie([{'url': 'https://cdn/x/movie.1080p.x265.mp4', 'quality': '1080p'}], slug='hevc-movie')
        diag = playback_sources.diagnose(movie)
        self.assertTrue(diag['unplayable'])
        self.assertIn('hevc', diag['reason'])

    def test_movie_with_mp4_mirror_is_playable(self):
        movie = self._movie([
            {'url': 'https://cdn/x/movie.1080p.x265.mkv', 'quality': '1080p'},
            {'url': 'https://cdn/x/movie.720p.x264.mp4', 'quality': '720p'},
        ], slug='mixed-movie')
        self.assertFalse(playback_sources.diagnose(movie)['unplayable'])

    def test_movie_with_hls_video_url_is_playable(self):
        movie = self._movie(
            [{'url': 'https://cdn/x/movie.1080p.mkv', 'quality': '1080p'}],
            slug='hls-movie', video_url='hls/movie/master.m3u8',
        )
        self.assertFalse(playback_sources.diagnose(movie)['unplayable'])

    def test_movie_with_no_links_is_not_flagged(self):
        movie = self._movie([], slug='empty-movie')
        self.assertFalse(playback_sources.diagnose(movie)['unplayable'])

    def test_hevc_mp4_video_url_is_not_trusted_as_safe(self):
        # An imported own-stream in an .mp4 container but HEVC-encoded must not
        # count as a browser-safe source (Firefox/Chrome cannot decode it).
        movie = self._movie(
            [{'url': 'https://cdn/x/movie.1080p.x265.mkv', 'quality': '1080p'}],
            slug='hevc-vurl-movie',
            video_url='https://cdn/x/The.Film.2026.1080p.TELESYNC.HEVC.AAC2.mp4',
        )
        self.assertTrue(playback_sources.diagnose(movie)['unplayable'])


class RemediationTests(TestCase):
    def test_scan_records_and_self_heals(self):
        bad = Movie.objects.create(
            title='Bad', original_title='Bad', slug='bad', is_published=True,
            download_links=[{'url': 'https://cdn/x/movie.1080p.mkv', 'quality': '1080p'}],
        )
        stats = playback_sources.scan(order='stale', series=False)
        self.assertEqual(stats['unplayable'], 1)
        gap = PlaybackSourceGap.objects.get(object_id=bad.pk)
        self.assertEqual(gap.status, PlaybackSourceGap.Status.OPEN)

        # A browser-safe mirror appears → next scan resolves the gap.
        bad.download_links = [{'url': 'https://cdn/x/movie.720p.x264.mp4', 'quality': '720p'}]
        bad.save(update_fields=['download_links'])
        stats2 = playback_sources.scan(order='stale', series=False)
        self.assertEqual(stats2['self_healed'], 1)
        gap.refresh_from_db()
        self.assertEqual(gap.status, PlaybackSourceGap.Status.RESOLVED)

    def test_remediate_refreshes_when_provider_adds_mp4(self):
        movie = Movie.objects.create(
            title='Fixable', original_title='Fixable', slug='fixable', is_published=True,
            download_links=[{'url': 'https://cdn/x/movie.1080p.mkv', 'quality': '1080p'}],
        )
        playback_sources.upsert_source_gap(movie, playback_sources.diagnose(movie))

        def fake_recrawl(obj):
            obj.download_links = obj.download_links + [
                {'url': 'https://cdn/x/movie.720p.x264.mp4', 'quality': '720p'},
            ]
            obj.save(update_fields=['download_links'])
            return {'myf2m': ('ok', 1)}

        with patch.object(playback_sources, '_recrawl_all_providers', side_effect=fake_recrawl):
            stats = playback_sources.remediate_open_gaps(fix_limit=5)
        self.assertEqual(stats['refreshed'], 1)
        self.assertEqual(
            PlaybackSourceGap.objects.get(object_id=movie.pk).status,
            PlaybackSourceGap.Status.RESOLVED,
        )

    def test_remediate_marks_unavailable_when_no_mirror(self):
        movie = Movie.objects.create(
            title='Stuck', original_title='Stuck', slug='stuck', is_published=True,
            download_links=[{'url': 'https://cdn/x/movie.1080p.x265.mkv', 'quality': '1080p'}],
        )
        playback_sources.upsert_source_gap(movie, playback_sources.diagnose(movie))

        with patch.object(playback_sources, '_recrawl_all_providers', return_value={'myf2m': ('ok', 0)}):
            stats = playback_sources.remediate_open_gaps(fix_limit=5)
        self.assertEqual(stats['unavailable'], 1)
        self.assertEqual(
            PlaybackSourceGap.objects.get(object_id=movie.pk).status,
            PlaybackSourceGap.Status.UNAVAILABLE,
        )

    def test_resolved_gap_reopens_when_title_regresses(self):
        # A title healed earlier (its browser-safe mirror was a signed URL) whose
        # signature has since expired must re-open — otherwise the remediation
        # pass, which skips RESOLVED rows, never re-crawls it and it stays dark.
        movie = Movie.objects.create(
            title='Expired', original_title='Expired', slug='expired-again', is_published=True,
            download_links=[{'url': 'https://cdn/x/movie.1080p.x265.mkv', 'quality': '1080p'}],
        )
        gap = playback_sources.upsert_source_gap(movie, playback_sources.diagnose(movie))
        playback_sources.resolve_source_gap(movie)
        gap.refresh_from_db()
        self.assertEqual(gap.status, PlaybackSourceGap.Status.RESOLVED)

        # Still browser-unplayable → a fresh scan must flip it back to OPEN.
        stats = playback_sources.scan(order='stale', series=False)
        self.assertEqual(stats['unplayable'], 1)
        gap.refresh_from_db()
        self.assertEqual(gap.status, PlaybackSourceGap.Status.OPEN)
        self.assertIsNone(gap.resolved_at)
