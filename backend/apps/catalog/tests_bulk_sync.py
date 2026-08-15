from types import SimpleNamespace
from unittest.mock import patch
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .bulk_sync import (
    ActiveCatalogSyncError,
    process_catalog_sync_batch,
    request_catalog_sync_cancel,
    stage_catalog_sync,
    start_catalog_sync,
)
from .models import CatalogSyncCandidate, CatalogSyncRun, Movie
from .tests_ingestion import MOVIE_DETAILS
from .tasks import catalog_sync_watchdog_task


class FakeBulkTMDBClient:
    def iter_movie_export(self, _export_date):
        yield {'id': 9001, 'adult': False, 'video': False, 'popularity': 20}
        yield {'id': 9001, 'adult': False, 'video': False, 'popularity': 20}
        yield {'id': 9002, 'adult': True, 'video': False, 'popularity': 30}

    def changed_movies(self, **_kwargs):
        return iter([{'id': 9001, 'adult': False}])

    def discover_movies(self, **_kwargs):
        return iter([{'id': 9001, 'adult': False}])

    def movie_details(self, movie_id):
        assert movie_id == 9001
        return MOVIE_DETAILS


@override_settings(
    CATALOG_AUTO_PUBLISH=False,
    CATALOG_MEDIA_MANIFEST='',
    CATALOG_SYNC_ITEMS_PER_SECOND=15,
)
class CatalogBulkSyncServiceTests(TestCase):
    def test_full_run_is_staged_idempotently_and_imported_as_draft(self):
        run = start_catalog_sync(mode=CatalogSyncRun.Mode.FULL)

        staged = stage_catalog_sync(run.pk, client=FakeBulkTMDBClient())
        self.assertTrue(staged['ready'])
        self.assertEqual(CatalogSyncCandidate.objects.filter(run=run).count(), 1)

        result = process_catalog_sync_batch(
            run.pk,
            client=FakeBulkTMDBClient(),
            manifest={},
            batch_size=10,
        )

        self.assertFalse(result['has_more'])
        run.refresh_from_db()
        movie = Movie.objects.get(tmdb_id=9001)
        self.assertEqual(run.status, CatalogSyncRun.Status.SUCCEEDED)
        self.assertEqual(run.total_count, 1)
        self.assertEqual(run.processed_count, 1)
        self.assertEqual(run.created_count, 1)
        self.assertFalse(movie.is_published)
        self.assertEqual(CatalogSyncCandidate.objects.filter(run=run).count(), 0)

    def test_incremental_run_unions_changed_and_discovered_ids(self):
        run = start_catalog_sync(mode=CatalogSyncRun.Mode.INCREMENTAL)
        staged = stage_catalog_sync(run.pk, client=FakeBulkTMDBClient())

        self.assertEqual(staged['total'], 1)
        self.assertEqual(CatalogSyncCandidate.objects.filter(run=run).count(), 1)

    def test_incremental_run_includes_stale_local_tmdb_rows(self):
        Movie.objects.create(title='Stale cached movie', slug='stale-cached', tmdb_id=8123)
        run = start_catalog_sync(mode=CatalogSyncRun.Mode.INCREMENTAL)

        staged = stage_catalog_sync(run.pk, client=FakeBulkTMDBClient())

        self.assertEqual(staged['total'], 2)
        self.assertTrue(CatalogSyncCandidate.objects.filter(run=run, tmdb_id=8123).exists())

    def test_only_one_active_tmdb_run_is_allowed(self):
        first = start_catalog_sync(mode=CatalogSyncRun.Mode.FULL)

        with self.assertRaises(ActiveCatalogSyncError) as context:
            start_catalog_sync(mode=CatalogSyncRun.Mode.INCREMENTAL)

        self.assertEqual(context.exception.run.pk, first.pk)

    def test_queued_run_can_be_cancelled_before_worker_starts(self):
        run = start_catalog_sync(mode=CatalogSyncRun.Mode.FULL)

        cancelled = request_catalog_sync_cancel(run.pk)
        staged = stage_catalog_sync(run.pk, client=FakeBulkTMDBClient())

        self.assertEqual(cancelled.status, CatalogSyncRun.Status.CANCELLED)
        self.assertTrue(staged['cancelled'])
        self.assertEqual(CatalogSyncCandidate.objects.count(), 0)

    @override_settings(CATALOG_SYNC_STALE_HEARTBEAT_MINUTES=15)
    def test_watchdog_requeues_stale_import_from_persisted_candidates(self):
        run = start_catalog_sync(mode=CatalogSyncRun.Mode.FULL)
        CatalogSyncRun.objects.filter(pk=run.pk).update(
            status=CatalogSyncRun.Status.RUNNING,
            phase='importing',
            heartbeat_at=timezone.now() - timedelta(minutes=20),
        )
        CatalogSyncCandidate.objects.create(run=run, tmdb_id=9001)

        with patch(
            'apps.catalog.tasks.process_catalog_sync_batch_task.delay',
            return_value=SimpleNamespace(id='recovered-task'),
        ):
            result = catalog_sync_watchdog_task.run()

        run.refresh_from_db()
        self.assertEqual(result['recovered'], [run.pk])
        self.assertEqual(run.task_id, 'recovered-task')
        self.assertEqual(run.phase, 'import_retry')

    def test_watchdog_finishes_abandoned_cancellation_and_cleans_queue(self):
        run = start_catalog_sync(mode=CatalogSyncRun.Mode.FULL)
        CatalogSyncRun.objects.filter(pk=run.pk).update(
            status=CatalogSyncRun.Status.CANCELLING,
            phase='cancelling',
            heartbeat_at=timezone.now() - timedelta(minutes=10),
        )
        CatalogSyncCandidate.objects.create(run=run, tmdb_id=9001)

        result = catalog_sync_watchdog_task.run()

        run.refresh_from_db()
        self.assertEqual(result['cancelled'], [run.pk])
        self.assertEqual(run.status, CatalogSyncRun.Status.CANCELLED)
        self.assertEqual(CatalogSyncCandidate.objects.filter(run=run).count(), 0)


@override_settings(
    TMDB_BASE_URL='https://api.themoviedb.org/3',
    TMDB_READ_ACCESS_TOKEN='test-token',
)
class CatalogBulkSyncApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            email='bulk-staff@example.com',
            username='bulk-staff',
            password='test-pass-123',
            is_staff=True,
        )
        self.user = User.objects.create_user(
            email='bulk-user@example.com',
            username='bulk-user',
            password='test-pass-123',
            is_staff=False,
        )
        self.client = APIClient()

    def test_start_requires_staff(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            '/api/admin/catalog-sync/runs/',
            {'mode': 'incremental'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_full_start_requires_explicit_confirmation(self):
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            '/api/admin/catalog-sync/runs/',
            {'mode': 'full'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'full_sync_confirmation_required')

    def test_staff_can_start_poll_and_cancel_a_run(self):
        self.client.force_authenticate(self.staff)
        with patch(
            'apps.catalog.tasks.stage_catalog_sync_task.delay',
            return_value=SimpleNamespace(id='test-task-id'),
        ):
            started = self.client.post(
                '/api/admin/catalog-sync/runs/',
                {'mode': 'full', 'confirm_full': True},
                format='json',
            )
        self.assertEqual(started.status_code, 202)
        run_id = started.data['id']

        detail = self.client.get(f'/api/admin/catalog-sync/runs/{run_id}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['mode'], 'full')
        self.assertTrue(detail.data['is_active'])

        cancelled = self.client.post(
            f'/api/admin/catalog-sync/runs/{run_id}/cancel/',
            {},
            format='json',
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.data['status'], 'cancelled')
