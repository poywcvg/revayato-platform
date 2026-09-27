"""Two unbounded-growth defects found on production 2026-09-24.

1. The bulk SoftSub lane had 154,481 queued tasks covering only 5,618 distinct
   titles — 96.4% duplicates. The per-title enqueue lock expires after two hours,
   which bounds duplicates per *two hours*, not per *queue*: once consumption is
   slower than that, every lock expires before its task is popped and the same
   title is admitted again, forever. A depth ceiling is what actually bounds it.

2. A provider import job whose worker died stayed RUNNING with no task behind it,
   and ``catalog_import_start`` answers 409 ``job_active`` for any provider with a
   non-terminal job — so one dead worker wedged the admin importer permanently.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.catalog.models import ProviderImportJob
from apps.catalog.provider_import.service import (
    create_import_job,
    ensure_avasarami_provider,
    reap_stale_import_jobs,
)
from apps.catalog.tasks import (
    enqueue_movie_softsub,
    enqueue_series_softsub,
    softsub_queue_saturated,
)


def _depth(value):
    """Patch the broker depth probe to report ``value``."""
    return patch('apps.catalog.tasks.softsub_queue_depth', return_value=value)


@override_settings(CATALOG_SOFTSUB_QUEUE_MAX_DEPTH=5000)
class SoftsubQueueBackpressureTests(TestCase):
    def test_saturated_only_at_or_above_the_ceiling(self):
        with _depth(4999):
            self.assertFalse(softsub_queue_saturated())
        with _depth(5000):
            self.assertTrue(softsub_queue_saturated())
        with _depth(154481):
            self.assertTrue(softsub_queue_saturated())

    def test_unreadable_depth_admits_the_task(self):
        """A broker introspection failure must not become a work stoppage."""
        with _depth(-1):
            self.assertFalse(softsub_queue_saturated())

    @override_settings(CATALOG_SOFTSUB_QUEUE_MAX_DEPTH=0)
    def test_zero_disables_the_ceiling(self):
        with _depth(999999):
            self.assertFalse(softsub_queue_saturated())

    def test_producers_skip_while_saturated_and_resume_after(self):
        with _depth(154481), patch('apps.catalog.tasks.extract_movie_softsub_task.delay') as movie, \
                patch('apps.catalog.tasks.extract_series_softsub_task.delay') as series:
            self.assertFalse(enqueue_movie_softsub(4810))
            self.assertFalse(enqueue_series_softsub(1940))
            movie.assert_not_called()
            series.assert_not_called()

        with _depth(12), patch('apps.catalog.tasks.extract_movie_softsub_task.delay') as movie, \
                patch('apps.catalog.tasks.extract_series_softsub_task.delay') as series:
            self.assertTrue(enqueue_movie_softsub(4810))
            self.assertTrue(enqueue_series_softsub(1940))
            movie.assert_called_once()
            series.assert_called_once()

    def test_saturation_does_not_burn_the_per_title_lock(self):
        """A title skipped for back-pressure must stay eligible for the next pass."""
        with _depth(154481), patch('apps.catalog.tasks.extract_movie_softsub_task.delay'):
            self.assertFalse(enqueue_movie_softsub(777))
        with _depth(10), patch('apps.catalog.tasks.extract_movie_softsub_task.delay') as movie:
            self.assertTrue(enqueue_movie_softsub(777))
            movie.assert_called_once()


class StaleImportJobReaperTests(TestCase):
    def setUp(self):
        self.provider = ensure_avasarami_provider()
        self.staff = get_user_model().objects.create_user(
            username='reaper-staff', password='x', is_staff=True,
        )

    def _job(self, status, *, age_minutes):
        job = create_import_job(
            provider=self.provider, user=self.staff,
            content_type='movies', mode='discover_only', params={'limit': 1},
        )
        job.status = status
        job.processed_items = 417
        job.save(update_fields=['status', 'processed_items'])
        # auto_now on updated_at means the stale timestamp has to be forced.
        ProviderImportJob.objects.filter(pk=job.pk).update(
            updated_at=timezone.now() - timedelta(minutes=age_minutes),
        )
        return job

    @override_settings(CATALOG_IMPORT_JOB_STALE_MINUTES=60)
    def test_abandoned_running_job_is_failed_and_releases_the_provider(self):
        job = self._job(ProviderImportJob.Status.RUNNING, age_minutes=234)
        result = reap_stale_import_jobs()
        self.assertEqual(result['reaped'], 1)
        job.refresh_from_db()
        self.assertEqual(job.status, ProviderImportJob.Status.FAILED)
        self.assertIsNotNone(job.finished_at)
        self.assertIn('417', job.error_message)
        self.assertFalse(
            ProviderImportJob.objects.filter(
                provider=self.provider,
                status__in=[
                    ProviderImportJob.Status.QUEUED,
                    ProviderImportJob.Status.RUNNING,
                    ProviderImportJob.Status.CANCEL_REQUESTED,
                ],
            ).exists(),
            'a reaped job must no longer trip the 409 job_active guard',
        )

    @override_settings(CATALOG_IMPORT_JOB_STALE_MINUTES=60)
    def test_a_job_that_is_still_making_progress_is_left_alone(self):
        job = self._job(ProviderImportJob.Status.RUNNING, age_minutes=5)
        self.assertEqual(reap_stale_import_jobs()['reaped'], 0)
        job.refresh_from_db()
        self.assertEqual(job.status, ProviderImportJob.Status.RUNNING)

    @override_settings(CATALOG_IMPORT_JOB_STALE_MINUTES=60)
    def test_terminal_jobs_are_never_touched(self):
        for status in (
            ProviderImportJob.Status.COMPLETED,
            ProviderImportJob.Status.FAILED,
            ProviderImportJob.Status.CANCELLED,
            ProviderImportJob.Status.AWAITING_REVIEW,
        ):
            job = self._job(status, age_minutes=10000)
            self.assertEqual(reap_stale_import_jobs()['reaped'], 0, status)
            job.refresh_from_db()
            self.assertEqual(job.status, status)

    @override_settings(CATALOG_IMPORT_JOB_STALE_MINUTES=60)
    def test_every_non_terminal_state_is_reapable(self):
        for status in (
            ProviderImportJob.Status.QUEUED,
            ProviderImportJob.Status.VALIDATING,
            ProviderImportJob.Status.SEARCHING,
            ProviderImportJob.Status.RUNNING,
            ProviderImportJob.Status.TRANSFERRING,
            ProviderImportJob.Status.CANCEL_REQUESTED,
        ):
            job = self._job(status, age_minutes=120)
            self.assertEqual(reap_stale_import_jobs()['reaped'], 1, status)
            job.refresh_from_db()
            self.assertEqual(job.status, ProviderImportJob.Status.FAILED)
