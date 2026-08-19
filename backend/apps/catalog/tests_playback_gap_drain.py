"""Tests for the periodic drain of stale viewer-reported playback subtitle gaps."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from unittest.mock import patch

from apps.catalog.models import Movie, PlaybackSubtitleGap
from apps.catalog.tasks import drain_playback_subtitle_gaps

@override_settings(
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class DrainPlaybackSubtitleGapsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.movie = Movie.objects.create(
            title='Drain Movie',
            original_title='Drain Movie',
            slug='drain-movie-test',
            imdb_id='tt0111161',
            is_published=True,
            download_links=[{
                'url': 'https://cdn.example/Original/movie.720p.mkv',
                'label': 'نسخه اصلی · 720p',
                'quality': '720p',
            }],
            subtitle_tracks=[],
        )

    def _stale_gap(self, **overrides):
        gap = PlaybackSubtitleGap.objects.create(
            content_type='movie',
            object_id=self.movie.pk,
            episode_id=0,
            slug=self.movie.slug,
            title=self.movie.title,
            **overrides,
        )
        # auto_now would pin updated_at to now; force it stale for the drain.
        PlaybackSubtitleGap.objects.filter(pk=gap.pk).update(
            updated_at=timezone.now() - timedelta(hours=2),
        )
        gap.refresh_from_db()
        return gap

    def test_drain_enqueues_stale_open_gap_once(self):
        gap = self._stale_gap(status=PlaybackSubtitleGap.Status.OPEN)
        with patch(
            'apps.catalog.tasks.enqueue_movie_softsub_urgent',
            return_value=True,
        ) as enqueue:
            stats = drain_playback_subtitle_gaps(max_batch=10, min_age_seconds=600)

        self.assertEqual(stats['processed'], 1)
        self.assertEqual(stats['re_enqueued'], 1)
        enqueue.assert_called_once()
        self.assertEqual(enqueue.call_args.args, (self.movie.pk,))
        self.assertTrue(enqueue.call_args.kwargs.get('force'))
        gap.refresh_from_db()
        self.assertEqual(gap.status, PlaybackSubtitleGap.Status.QUEUED)
        self.assertEqual(gap.last_result, 'drain_re_enqueued')
        self.assertEqual((gap.meta or {}).get('drain_count'), 1)

    def test_drain_respects_queue_lock(self):
        gap = self._stale_gap(status=PlaybackSubtitleGap.Status.OPEN)
        # Simulate an in-flight worker holding the urgent queue lock (enqueue pre-empts,
        # so the drain treats a False return as "someone else owns this gap").
        with patch(
            'apps.catalog.tasks.enqueue_movie_softsub_urgent',
            return_value=False,
        ) as enqueue:
            stats = drain_playback_subtitle_gaps(max_batch=10, min_age_seconds=600)

        self.assertEqual(stats['processed'], 1)
        self.assertEqual(stats['skipped'], 1)
        self.assertEqual(stats['re_enqueued'], 0)
        enqueue.assert_called_once()
        gap.refresh_from_db()
        # No re-enqueue means the row is untouched (no drain_count bump, no status change).
        self.assertEqual(gap.status, PlaybackSubtitleGap.Status.OPEN)
        self.assertIsNone((gap.meta or {}).get('drain_count'))

    def test_drain_respects_attempt_cap(self):
        gap = self._stale_gap(
            status=PlaybackSubtitleGap.Status.OPEN,
            meta={'drain_count': 3},
        )
        with patch(
            'apps.catalog.tasks.enqueue_movie_softsub_urgent',
            return_value=True,
        ) as enqueue:
            stats = drain_playback_subtitle_gaps(
                max_batch=10, min_age_seconds=600, max_attempts=3,
            )

        self.assertEqual(stats['skipped'], 1)
        enqueue.assert_not_called()
        gap.refresh_from_db()
        self.assertEqual((gap.meta or {}).get('drain_count'), 4)

    def test_drain_resolves_when_tracks_present(self):
        gap = self._stale_gap(status=PlaybackSubtitleGap.Status.QUEUED)
        self.movie.subtitle_tracks = [{
            'id': 'fa-1',
            'language': 'fa',
            'label': 'فارسی',
            'key': 'catalog/subtitles/landed.vtt',
        }]
        self.movie.save(update_fields=['subtitle_tracks'])

        with patch(
            'apps.catalog.tasks.enqueue_movie_softsub_urgent',
            return_value=True,
        ) as enqueue:
            stats = drain_playback_subtitle_gaps(max_batch=10, min_age_seconds=600)

        self.assertEqual(stats['resolved'], 1)
        enqueue.assert_not_called()
        gap.refresh_from_db()
        self.assertEqual(gap.status, PlaybackSubtitleGap.Status.RESOLVED)
        self.assertIsNotNone(gap.resolved_at)

    def test_drain_skips_fresh_gaps(self):
        gap = PlaybackSubtitleGap.objects.create(
            content_type='movie',
            object_id=self.movie.pk,
            episode_id=0,
            slug=self.movie.slug,
            title=self.movie.title,
            status=PlaybackSubtitleGap.Status.OPEN,
        )  # updated_at = now → not stale.
        with patch(
            'apps.catalog.tasks.enqueue_movie_softsub_urgent',
            return_value=True,
        ) as enqueue:
            stats = drain_playback_subtitle_gaps(max_batch=10, min_age_seconds=600)

        self.assertEqual(stats['processed'], 0)
        enqueue.assert_not_called()

    def test_drain_uses_per_row_lock(self):
        gap = self._stale_gap(status=PlaybackSubtitleGap.Status.OPEN)
        # A concurrent beat already claimed this row.
        self.assertTrue(cache.add(f'catalog:gap-drain:{gap.pk}', 'draining', timeout=600))
        with patch(
            'apps.catalog.tasks.enqueue_movie_softsub_urgent',
            return_value=True,
        ) as enqueue:
            stats = drain_playback_subtitle_gaps(max_batch=10, min_age_seconds=600)

        self.assertEqual(stats['processed'], 1)
        self.assertEqual(stats['skipped'], 1)
        enqueue.assert_not_called()

    def test_drain_dry_run_never_mutates(self):
        gap = self._stale_gap(status=PlaybackSubtitleGap.Status.OPEN)
        with patch(
            'apps.catalog.tasks.enqueue_movie_softsub_urgent',
            return_value=True,
        ) as enqueue:
            stats = drain_playback_subtitle_gaps(
                max_batch=10, min_age_seconds=600, dry_run=True,
            )

        self.assertEqual(stats['processed'], 1)
        self.assertEqual(stats['re_enqueued'], 1)
        enqueue.assert_not_called()
        gap.refresh_from_db()
        self.assertEqual(gap.status, PlaybackSubtitleGap.Status.OPEN)
        self.assertIsNone((gap.meta or {}).get('drain_count'))
