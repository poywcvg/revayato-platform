"""Admin panel operations: the reasons they failed, and «جستجوی دوباره و تکمیل»."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.throttling import UserRateThrottle

from . import admin_ops, title_completion
from .admin_api import StaffAdminThrottle, TMDBAdminThrottle
from .models import Movie, MovieSyncAudit, Series


class _StaffCase(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = get_user_model().objects.create_user(
            username='staffer', email='s@example.test', password='x-Pass-12345', is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def desk(self, kind, pk, action, **body):
        return self.client.post(f'/api/admin/catalog/{kind}/{pk}/media/', {'action': action, **body}, format='json')


class ThrottleIsolationTests(TestCase):
    def test_admin_throttles_do_not_share_the_site_user_bucket(self):
        request = APIRequestFactory().get('/')
        request.user = mock.Mock(pk=7, is_authenticated=True)
        site = UserRateThrottle().get_cache_key(request, None)
        desk = StaffAdminThrottle().get_cache_key(request, None)
        tmdb = TMDBAdminThrottle().get_cache_key(request, None)
        self.assertEqual(len({site, desk, tmdb}), 3)


class PartialUpdateTests(_StaffCase):
    def test_toggle_on_row_with_latin_title_succeeds(self):
        movie = Movie.objects.create(title='Film', original_title='Film', slug='film-2020', is_published=True)
        response = self.client.patch(f'/api/admin/movies/{movie.pk}/', {'is_featured': True}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        movie.refresh_from_db()
        self.assertTrue(movie.is_featured)

    def test_publishing_a_latin_title_still_asks_for_persian(self):
        movie = Movie.objects.create(
            title='Film', original_title='Film', slug='film-2021',
            is_published=False, publication_status=Movie.PublicationStatus.DRAFT,
        )
        response = self.client.patch(
            f'/api/admin/movies/{movie.pk}/', {'publication_status': 'published'}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_unrelated_patch_keeps_links_and_flags(self):
        links = [
            {'url': 'https://dl.example/Film.2020.1080p.Farsi.Dubbed.mkv', 'quality': '1080p', 'label': 'دوبله فارسی'},
            {'url': 'https://dl.example/Film.2020.720p.SoftSub.mkv', 'quality': '720p', 'label': 'زیرنویس فارسی'},
        ]
        movie = Movie.objects.create(
            title='فیلم', original_title='Film', slug='film-2022', is_published=True, download_links=links,
        )
        before = Movie.objects.get(pk=movie.pk)
        response = self.client.patch(f'/api/admin/movies/{movie.pk}/', {'is_featured': True}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        movie.refresh_from_db()
        self.assertEqual(movie.download_links, before.download_links)
        self.assertEqual((movie.is_dubbed, movie.has_subtitle), (before.is_dubbed, before.has_subtitle))


class PublishGateTests(_StaffCase):
    def test_publish_verifies_media_inline_instead_of_refusing(self):
        movie = Movie.objects.create(
            title='فیلم', original_title='Film', slug='film-2023',
            is_published=False, publication_status=Movie.PublicationStatus.DRAFT,
        )
        calls = []

        def media(obj, verify=False):
            calls.append(verify)
            return [] if verify else ['media_unverified']

        with mock.patch('apps.catalog.completeness.publish_blockers', return_value=[]), \
                mock.patch('apps.catalog.media_verification.media_publish_blockers', side_effect=media):
            response = self.desk('movie', movie.pk, 'publish')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(calls, [False, True])
        movie.refresh_from_db()
        self.assertTrue(movie.is_published)

    def test_structural_gap_refuses_without_probing(self):
        movie = Movie.objects.create(title='فیلم', original_title='Film', slug='film-2024', is_published=False)
        with mock.patch('apps.catalog.completeness.publish_blockers', return_value=['missing_poster']), \
                mock.patch('apps.catalog.media_verification.media_publish_blockers') as media:
            response = self.desk('movie', movie.pk, 'publish')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['blockers'], ['missing_poster'])
        media.assert_not_called()

    def test_bulk_stops_at_the_time_budget_and_says_so(self):
        movie = Movie.objects.create(title='فیلم', original_title='Film', slug='film-2025', is_published=True)
        with mock.patch.object(admin_ops, 'BULK_TIME_BUDGET', -1):
            response = self.client.post(
                '/api/admin/catalog/bulk/', {'kind': 'movie', 'action': 'unpublish', 'ids': [movie.pk]}, format='json',
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'][0]['error'], 'time_budget')
        movie.refresh_from_db()
        self.assertTrue(movie.is_published)


class CompletionQueueTests(_StaffCase):
    def setUp(self):
        super().setUp()
        self.movie = Movie.objects.create(title='فیلم', original_title='Film', slug='film-2026', is_published=False)

    def test_desk_click_queues_one_run_on_the_admin_lane(self):
        with mock.patch('apps.catalog.tasks.complete_title_task.apply_async') as queued:
            first = self.desk('movie', self.movie.pk, 'complete')
            second = self.desk('movie', self.movie.pk, 'recrawl')
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(queued.call_count, 1)
        self.assertEqual(queued.call_args.kwargs['queue'], title_completion.DESK_QUEUE)
        self.assertEqual(queued.call_args.kwargs['kwargs']['user_id'], self.staff.pk)
        self.assertEqual(first.data['desk']['completion']['state'], 'queued')
        self.assertTrue(second.data['result']['already_running'])

    def test_bulk_goes_to_the_imports_lane(self):
        with mock.patch('apps.catalog.tasks.complete_title_task.apply_async') as queued:
            response = self.client.post(
                '/api/admin/catalog/bulk/', {'kind': 'movie', 'action': 'complete', 'ids': [self.movie.pk]}, format='json',
            )
        self.assertEqual(response.data['succeeded'], 1)
        self.assertEqual(queued.call_args.kwargs['queue'], title_completion.BULK_QUEUE)

    def test_broker_down_clears_state_and_reports(self):
        with mock.patch('apps.catalog.tasks.complete_title_task.apply_async', side_effect=OSError):
            response = self.desk('movie', self.movie.pk, 'complete')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'queue_failed')
        self.assertIsNone(title_completion.completion_state(self.movie))

    def test_subtitle_refresh_uses_the_urgent_lane(self):
        self.movie.is_published = True
        self.movie.save(update_fields=['is_published'])
        with mock.patch('apps.catalog.tasks.enqueue_movie_softsub_urgent') as urgent:
            response = self.desk('movie', self.movie.pk, 'refresh_subtitles')
        self.assertEqual(response.status_code, 200, response.data)
        urgent.assert_called_once()


def _add_links(obj, providers):
    type(obj).objects.filter(pk=obj.pk).update(
        download_links=[{'url': 'https://dl.example/film.2026.1080p.mp4', 'quality': '1080p'}],
    )
    return {name: 'filled' for name in providers}


class CompletionPipelineTests(_StaffCase):
    def setUp(self):
        super().setUp()
        self.movie = Movie.objects.create(
            title='فیلم', original_title='Film', slug='film-2027', tmdb_id=99,
            is_published=False, publication_status=Movie.PublicationStatus.DRAFT,
        )

    def _patches(self, **overrides):
        base = {
            'apps.catalog.admin_ops._resync_tmdb': mock.Mock(return_value={'synced': True}),
            'apps.catalog.title_repair.repair_titles': mock.Mock(return_value={'changed': {}}),
            'apps.catalog.provider_import.source_fill.wanted_providers': mock.Mock(
                return_value=(['myf2m', 'dornatv'], 'missing_cookie'),
            ),
            'apps.catalog.provider_import.source_fill.fill_title': mock.Mock(side_effect=_add_links),
            'apps.catalog.link_sizes.size_title': mock.Mock(return_value={'sized': 1, 'left': 0}),
            'apps.catalog.media_verification.verify_target': mock.Mock(return_value={'status': 'passed'}),
            'apps.catalog.completeness.publish_blockers': mock.Mock(return_value=[]),
            'apps.catalog.media_verification.media_publish_blockers': mock.Mock(return_value=[]),
            'apps.catalog.tasks.enqueue_movie_softsub_urgent': mock.Mock(return_value=True),
        }
        base.update(overrides)
        return [mock.patch(target, new) for target, new in base.items()], base

    def _run(self, **overrides):
        patches, mocks = self._patches(**overrides)
        for patcher in patches:
            patcher.start()
        try:
            state = title_completion.run_completion('movie', self.movie.pk, user_id=self.staff.pk, publish=True)
        finally:
            for patcher in patches:
                patcher.stop()
        return state, mocks

    def test_full_run_fills_publishes_and_queues_subtitles(self):
        state, mocks = self._run()
        steps = {row['key']: row for row in state['steps']}
        self.assertEqual(state['state'], 'done')
        self.assertEqual(state['failed_steps'], [])
        self.assertEqual(steps['sources']['links_after'], 1)
        self.assertIn('kargadan: missing_cookie', steps['sources']['detail'])
        self.assertEqual(steps['publish']['status'], 'ok')
        self.assertEqual(steps['subtitles']['status'], 'ok')
        self.movie.refresh_from_db()
        self.assertTrue(self.movie.is_published)
        mocks['apps.catalog.tasks.enqueue_movie_softsub_urgent'].assert_called_once()
        self.assertTrue(MovieSyncAudit.objects.filter(movie=self.movie, details__reason='complete_title').exists())
        self.assertEqual(title_completion.completion_state(self.movie)['state'], 'done')

    def test_one_failing_step_does_not_stop_the_rest(self):
        state, _ = self._run(**{'apps.catalog.link_sizes.size_title': mock.Mock(side_effect=RuntimeError('host down'))})
        steps = {row['key']: row['status'] for row in state['steps']}
        self.assertEqual(steps['sizes'], 'error')
        self.assertEqual(steps['verify'], 'ok')
        self.assertEqual(steps['publish'], 'ok')
        self.assertEqual(state['failed_steps'], ['sizes'])

    def test_blocked_publish_is_reported_with_its_reasons(self):
        state, _ = self._run(**{
            'apps.catalog.completeness.publish_blockers': mock.Mock(return_value=['missing_poster']),
        })
        publish = next(row for row in state['steps'] if row['key'] == 'publish')
        self.assertEqual(publish['status'], 'blocked')
        self.assertEqual(publish['blockers'], ['missing_poster'])
        subtitles = next(row for row in state['steps'] if row['key'] == 'subtitles')
        self.assertEqual(subtitles['status'], 'skipped')
        self.movie.refresh_from_db()
        self.assertFalse(self.movie.is_published)

    def test_archived_title_is_never_republished(self):
        self.movie.publication_status = Movie.PublicationStatus.ARCHIVED
        self.movie.save(update_fields=['publication_status'])
        state, _ = self._run()
        publish = next(row for row in state['steps'] if row['key'] == 'publish')
        self.assertEqual(publish['status'], 'skipped')
        self.movie.refresh_from_db()
        self.assertFalse(self.movie.is_published)

    def test_series_subtitles_go_to_the_urgent_lane(self):
        series = Series.objects.create(title='سریال', original_title='Show', slug='show-2027', is_published=True)
        patches, _ = self._patches()
        with mock.patch('apps.catalog.tasks.extract_series_softsub_task.apply_async') as queued:
            for patcher in patches:
                patcher.start()
            try:
                state = title_completion.run_completion('series', series.pk, publish=True)
            finally:
                for patcher in patches:
                    patcher.stop()
        self.assertEqual(state['state'], 'done')
        self.assertEqual(queued.call_args.kwargs['queue'], 'softsub-urgent')


class DiscoverJobConstraintTests(_StaffCase):
    """«duplicate key … uniq_active_provider_series_job» on a forced re-search."""

    def setUp(self):
        super().setUp()
        from .provider_import.catalog_lookup import create_catalog_discover_job, ensure_myf2m_provider

        self.create = create_catalog_discover_job
        self.provider = ensure_myf2m_provider()
        self.series = Series.objects.create(title='سریال', original_title='Show', slug='show-2030', is_published=True)

    def _job(self, status):
        from .models import ProviderImportJob

        return ProviderImportJob.objects.create(
            provider=self.provider, target_series=self.series,
            content_type=ProviderImportJob.ContentType.SERIES,
            mode=ProviderImportJob.Mode.DISCOVER_ONLY, status=status,
        )

    def test_forced_research_supersedes_a_job_awaiting_review(self):
        from .models import ProviderImportJob

        old = self._job(ProviderImportJob.Status.AWAITING_REVIEW)
        job = self.create(content_type='series', object_id=self.series.pk, force=True)
        self.assertNotEqual(job.pk, old.pk)
        self.assertFalse(getattr(job, 'reused', False))
        old.refresh_from_db()
        self.assertEqual(old.status, ProviderImportJob.Status.CANCELLED)

    def test_a_job_being_crawled_is_reused_not_duplicated(self):
        from .models import ProviderImportJob

        running = self._job(ProviderImportJob.Status.RUNNING)
        job = self.create(content_type='series', object_id=self.series.pk, force=True)
        self.assertEqual(job.pk, running.pk)
        self.assertTrue(job.reused)

    def test_a_stale_working_job_is_replaced(self):
        from datetime import timedelta

        from django.utils import timezone

        from .models import ProviderImportJob

        stuck = self._job(ProviderImportJob.Status.QUEUED)
        ProviderImportJob.objects.filter(pk=stuck.pk).update(updated_at=timezone.now() - timedelta(hours=2))
        job = self.create(content_type='series', object_id=self.series.pk, force=True)
        self.assertNotEqual(job.pk, stuck.pk)
        stuck.refresh_from_db()
        self.assertEqual(stuck.status, ProviderImportJob.Status.CANCELLED)

    def test_staff_endpoint_and_desk_do_not_queue_a_reused_job(self):
        from .models import ProviderImportJob

        self._job(ProviderImportJob.Status.RUNNING)
        with mock.patch('apps.catalog.provider_import.api._queue_job') as queued:
            response = self.client.post(
                f'/api/admin/catalog/series/{self.series.pk}/provider-discover/', {'force': True}, format='json',
            )
            desk = self.desk('series', self.series.pk, 'discover', force=True)
        queued.assert_not_called()
        self.assertEqual(desk.status_code, 200, desk.data)
        self.assertTrue(desk.data['result']['already_running'])
        self.assertEqual(response.status_code, 202, response.data)
