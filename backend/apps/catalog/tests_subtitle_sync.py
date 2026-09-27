"""Tests for the self-healing subtitle timing system (crowd consensus + FPS)."""

import tempfile

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.catalog.models import Movie, SubtitleSyncVote
from apps.catalog.subtitle_contract import subtitle_sync_signature
from apps.catalog.subtitle_sync import (
    MIN_APPLY_SECONDS,
    compute_consensus_offset,
    detect_fps_from_release,
    fps_rescale_factor,
    next_version_key,
    promote_pending_offsets,
    prune_stale_votes,
    shift_and_scale_webvtt,
)

SAMPLE_VTT = (
    'WEBVTT\n\n'
    '1\n00:00:10.000 --> 00:00:12.000\nHello\n\n'
    '2\n00:01:00.500 --> 00:01:02.500\nWorld\n'
)


class WebVttRewriteTests(TestCase):
    def test_shift_moves_only_cue_lines(self):
        out = shift_and_scale_webvtt(SAMPLE_VTT, shift=2.0)
        self.assertIn('00:00:12.000 --> 00:00:14.000', out)
        self.assertIn('00:01:02.500 --> 00:01:04.500', out)
        # Non-timestamp lines untouched.
        self.assertIn('Hello', out)
        self.assertTrue(out.startswith('WEBVTT'))

    def test_scale_stretches_cues(self):
        out = shift_and_scale_webvtt(SAMPLE_VTT, scale=25.0 / 23.976)
        # 10s * (25/23.976) ≈ 10.427s
        self.assertIn('00:00:10.427', out)

    def test_noop_returns_input_unchanged(self):
        self.assertEqual(shift_and_scale_webvtt(SAMPLE_VTT), SAMPLE_VTT)

    def test_negative_shift_never_goes_below_zero(self):
        out = shift_and_scale_webvtt(SAMPLE_VTT, shift=-30.0)
        self.assertIn('00:00:00.000', out)


class FpsDetectionTests(TestCase):
    def test_explicit_fps_tag(self):
        self.assertEqual(detect_fps_from_release('Movie.1080p.25fps.BluRay'), 25.0)

    def test_pal_marker(self):
        self.assertEqual(detect_fps_from_release('Movie.PAL.DVDRip'), 25.0)

    def test_ambiguous_returns_none(self):
        self.assertIsNone(detect_fps_from_release('Movie.1080p.WEB-DL'))
        self.assertIsNone(detect_fps_from_release(''))

    def test_rescale_factor(self):
        self.assertEqual(fps_rescale_factor(25.0, 23.976), 25.0 / 23.976)
        self.assertEqual(fps_rescale_factor(None, 23.976), 1.0)
        self.assertEqual(fps_rescale_factor(24.0, 24.0), 1.0)


class ConsensusTests(TestCase):
    def test_tight_cluster_agrees(self):
        self.assertEqual(compute_consensus_offset([2.0, 2.1, 1.9, 2.0]), 2.0)

    def test_too_few_samples(self):
        self.assertIsNone(compute_consensus_offset([2.0, 2.0]))

    def test_split_field_no_consensus(self):
        # Two clusters, neither a majority within tolerance of the median.
        self.assertIsNone(compute_consensus_offset([0.0, 0.1, 5.0, 5.1]))

    def test_outliers_ignored_when_majority_agrees(self):
        self.assertAlmostEqual(
            compute_consensus_offset([3.0, 3.0, 3.1, 2.9, 20.0]), 3.0, places=1,
        )


class VersionKeyTests(TestCase):
    def test_first_and_next_versions(self):
        self.assertEqual(next_version_key('catalog/subtitles/x.vtt'), 'catalog/subtitles/x.s1.vtt')
        self.assertEqual(next_version_key('catalog/subtitles/x.s1.vtt'), 'catalog/subtitles/x.s2.vtt')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PromoteOffsetsTests(TestCase):
    def setUp(self):
        self.key = 'catalog/subtitles/promote-test-fa.vtt'
        if default_storage.exists(self.key):
            default_storage.delete(self.key)
        self.saved_key = default_storage.save(self.key, ContentFile(SAMPLE_VTT.encode('utf-8')))
        self.movie = Movie.objects.create(
            title='Promote Test',
            original_title='Promote Test',
            slug='promote-test',
            is_published=True,
            subtitle_tracks=[{
                'id': 'fa-subzone-1',
                'label': 'فارسی',
                'language': 'fa',
                'key': self.saved_key,
                'default': True,
            }],
        )
        self.sig = subtitle_sync_signature(self.saved_key)

    def _vote(self, voter, offset):
        SubtitleSyncVote.objects.create(
            content_type='movie', object_id=self.movie.pk, episode_id=0,
            track_id='fa-subzone-1', sig=self.sig, voter_key=voter, offset=offset,
        )

    def test_consensus_bakes_shift_and_clears_votes(self):
        for i, offset in enumerate([2.0, 2.0, 2.1, 1.9]):
            self._vote(f'v{i}', offset)
        summary = promote_pending_offsets()
        self.assertEqual(summary['baked'], 1)
        self.assertEqual(SubtitleSyncVote.objects.count(), 0)

        self.movie.refresh_from_db()
        track = self.movie.subtitle_tracks[0]
        # File re-versioned and cues shifted earlier by ~2s (10s -> 8s).
        self.assertNotEqual(track['key'], self.saved_key)
        text = default_storage.open(track['key']).read().decode('utf-8')
        self.assertIn('00:00:08.000', text)
        # Removed 2s of lateness, tracked cumulatively.
        self.assertAlmostEqual(track['sync_offset'], 2.0, places=1)

    def test_agreement_on_zero_resolves_without_rebake(self):
        for i in range(4):
            self._vote(f'v{i}', 0.05)
        summary = promote_pending_offsets()
        self.assertEqual(summary['resolved'], 1)
        self.assertEqual(SubtitleSyncVote.objects.count(), 0)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.subtitle_tracks[0]['key'], self.saved_key)

    def test_stale_signature_votes_pruned(self):
        for i in range(4):
            SubtitleSyncVote.objects.create(
                content_type='movie', object_id=self.movie.pk, episode_id=0,
                track_id='fa-subzone-1', sig='deadbeef', voter_key=f'v{i}', offset=3.0,
            )
        summary = promote_pending_offsets()
        self.assertEqual(summary['stale'], 1)
        self.assertEqual(SubtitleSyncVote.objects.count(), 0)

    def test_min_apply_guard(self):
        self.assertLess(0.2, MIN_APPLY_SECONDS)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ReportEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.movie = Movie.objects.create(
            title='Report Test', original_title='Report Test',
            slug='report-test', is_published=True, subtitle_tracks=[],
        )

    def test_valid_vote_stored_and_upserts(self):
        payload = {
            'content_type': 'movie', 'object_id': self.movie.pk,
            'track_id': 'fa-subzone-1', 'sig': 'abc123', 'offset': 2.5,
        }
        r1 = self.client.post('/api/catalog/subtitle-sync/report/', payload, format='json')
        self.assertEqual(r1.status_code, 200)
        self.assertTrue(r1.data['ok'])
        self.assertEqual(SubtitleSyncVote.objects.count(), 1)

        # Same viewer refines: upsert, not a second row.
        payload['offset'] = 3.0
        r2 = self.client.post('/api/catalog/subtitle-sync/report/', payload, format='json')
        self.assertTrue(r2.data['ok'])
        self.assertEqual(SubtitleSyncVote.objects.count(), 1)
        self.assertEqual(SubtitleSyncVote.objects.first().offset, 3.0)

    def test_invalid_payload_rejected(self):
        r = self.client.post(
            '/api/catalog/subtitle-sync/report/',
            {'content_type': 'bogus', 'object_id': 0, 'track_id': '', 'sig': '', 'offset': 999},
            format='json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data['ok'])
        self.assertEqual(SubtitleSyncVote.objects.count(), 0)

    def test_out_of_range_offset_rejected(self):
        r = self.client.post(
            '/api/catalog/subtitle-sync/report/',
            {'content_type': 'movie', 'object_id': self.movie.pk,
             'track_id': 'fa', 'sig': 'x', 'offset': 500},
            format='json',
        )
        self.assertFalse(r.data['ok'])


class PruneTests(TestCase):
    def test_prune_returns_count(self):
        self.assertEqual(prune_stale_votes(), 0)
