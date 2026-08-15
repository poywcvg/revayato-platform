"""Provider import framework and Avasarami connector tests."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.catalog.archive_storage import ArchiveStorageClient
from apps.catalog.models import Movie, MovieArchiveAsset, ProviderImportJob, ProviderSource
from apps.catalog.provider_import.avasarami import AvasaramiConnector, CAPTCHA_MESSAGE
from apps.catalog.provider_import.base import ProviderDownloadCandidate, ProviderMovie, sanitize_payload
from apps.catalog.provider_import.downloader import transfer_movie_candidate
from apps.catalog.provider_import.matcher import match_movie
from apps.catalog.provider_import.service import (
    create_import_job,
    ensure_avasarami_provider,
    run_provider_import_job,
)


ARCHIVE_SETTINGS = {
    'ARCHIVE_S3_ENDPOINT_URL': 'https://s3.example.test',
    'ARCHIVE_S3_ACCESS_KEY_ID': 'test-access-key',
    'ARCHIVE_S3_SECRET_ACCESS_KEY': 'test-secret-key-never-return',
    'ARCHIVE_S3_BUCKET_NAME': 'revayato-archive-test',
    'ARCHIVE_S3_REGION': 'ir-thr-at1',
    'ARCHIVE_S3_SIGNATURE_VERSION': 's3v4',
    'ARCHIVE_S3_ADDRESSING_STYLE': 'path',
    'ARCHIVE_S3_PRIVATE': True,
    'ARCHIVE_MULTIPART_CHUNK_SIZE_MB': 5,
    'ARCHIVE_MAX_UPLOAD_SIZE_GB': 100,
}

PROVIDER_SETTINGS = {
    **ARCHIVE_SETTINGS,
    'AVASARAMI_BASE_URL': 'https://avasarami.top',
    'AVASARAMI_LOGIN_URL': 'https://avasarami.top/sign-in/',
    'AVASARAMI_MOVIES_URL': 'https://avasarami.top/movies/',
    'AVASARAMI_SERIES_URL': 'https://avasarami.top/series/',
    'AVASARAMI_AUTH_TYPE': '',
    'AVASARAMI_USERNAME': '',
    'AVASARAMI_PASSWORD': '',
    'AVASARAMI_API_TOKEN': '',
    'AVASARAMI_COOKIE': '',
    'AVASARAMI_TIMEOUT_SECONDS': 5,
    'AVASARAMI_RATE_LIMIT_PER_MINUTE': 120,
    'AVASARAMI_VERIFY_SSL': True,
}


def _secret_leak(payload) -> bool:
    text = str(payload)
    return any(token in text for token in (
        'super-secret-token',
        'session-cookie-value',
        'test-secret-key-never-return',
        'https://cdn.provider.test/secret-download',
    ))


@override_settings(**PROVIDER_SETTINGS)
class ProviderImportApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            email='provider-staff@example.com',
            username='provider-staff',
            password='test-pass-123',
            is_staff=True,
        )
        self.user = User.objects.create_user(
            email='provider-user@example.com',
            username='provider-user',
            password='test-pass-123',
            is_staff=False,
        )
        self.client = APIClient()
        self.provider = ensure_avasarami_provider()

    def test_staff_can_list_sources(self):
        self.client.force_authenticate(self.staff)
        response = self.client.get('/api/admin/provider-sources/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item['slug'] == 'avasarami' for item in response.data['results']))
        self.assertFalse(_secret_leak(response.data))

    def test_non_staff_denied(self):
        self.client.force_authenticate(self.user)
        response = self.client.get('/api/admin/provider-sources/')
        self.assertEqual(response.status_code, 403)

    @override_settings(AVASARAMI_API_TOKEN='super-secret-token', AVASARAMI_AUTH_TYPE='bearer_token')
    def test_secrets_not_exposed_on_validate(self):
        self.client.force_authenticate(self.staff)
        with patch.object(AvasaramiConnector, '_request', return_value=(200, 'ok', {})):
            response = self.client.post(f'/api/admin/provider-sources/{self.provider.id}/validate/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['ok'])
        self.assertTrue(response.data['secrets']['api_token_configured'])
        self.assertNotIn('super-secret-token', str(response.data))

    def test_captcha_detection_requires_interactive(self):
        self.client.force_authenticate(self.staff)
        provider = self.provider
        provider.auth_type = 'username_password'
        provider.save(update_fields=['auth_type'])
        html = '<form><div class="g-recaptcha" data-sitekey="abc"></div></form>'
        with patch.object(AvasaramiConnector, '_request', return_value=(200, html, {})):
            with override_settings(AVASARAMI_USERNAME='u', AVASARAMI_PASSWORD='p', AVASARAMI_AUTH_TYPE='username_password'):
                response = self.client.post(f'/api/admin/provider-sources/{provider.id}/validate/')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.data['requires_interactive_verification'])
        self.assertIn('CAPTCHA', response.data['message'])

    @override_settings(AVASARAMI_API_TOKEN='super-secret-token', AVASARAMI_AUTH_TYPE='bearer_token')
    def test_validate_bearer_success(self):
        self.client.force_authenticate(self.staff)
        with patch.object(AvasaramiConnector, '_request', return_value=(200, 'ok', {})):
            response = self.client.post(f'/api/admin/provider-sources/{self.provider.id}/validate/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['ok'])

    @override_settings(AVASARAMI_COOKIE='session-cookie-value', AVASARAMI_AUTH_TYPE='cookie_session')
    def test_validate_cookie_success(self):
        self.client.force_authenticate(self.staff)
        with patch.object(AvasaramiConnector, '_request', return_value=(200, '<html>movies</html>', {})):
            response = self.client.post(f'/api/admin/provider-sources/{self.provider.id}/validate/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['ok'])
        self.assertNotIn('session-cookie-value', str(response.data))

    @patch('apps.catalog.provider_import.tasks.run_provider_import_job_task')
    @override_settings(AVASARAMI_API_TOKEN='super-secret-token', AVASARAMI_AUTH_TYPE='bearer_token')
    def test_discover_job_created(self, task):
        task.delay.return_value = MagicMock(id='task-1')
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            f'/api/admin/provider-sources/{self.provider.id}/discover/',
            {'content_type': 'movies', 'mode': 'discover_only', 'limit': 10, 'dry_run': True},
            format='json',
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data['mode'], 'discover_only')
        self.assertTrue(ProviderImportJob.objects.filter(pk=response.data['id']).exists())

    @patch('apps.catalog.provider_import.tasks.run_provider_import_job_task')
    @override_settings(AVASARAMI_API_TOKEN='super-secret-token', AVASARAMI_AUTH_TYPE='bearer_token')
    def test_import_job_created(self, task):
        task.delay.return_value = MagicMock(id='task-2')
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            f'/api/admin/provider-sources/{self.provider.id}/import/',
            {
                'content_type': 'both',
                'mode': 'import_missing_files',
                'limit': 5,
                'overwrite': False,
                'quality_preference': ['1080p', '720p'],
                'dry_run': False,
            },
            format='json',
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data['mode'], 'import_missing_files')

    def test_cancel_request_stops_job(self):
        self.client.force_authenticate(self.staff)
        job = create_import_job(
            provider=self.provider,
            user=self.staff,
            content_type='movies',
            mode='discover_only',
            params={'limit': 1},
        )
        job.status = ProviderImportJob.Status.RUNNING
        job.save(update_fields=['status'])
        response = self.client.post(f'/api/admin/provider-import/jobs/{job.id}/cancel/')
        self.assertEqual(response.status_code, 200)
        job.refresh_from_db()
        self.assertTrue(job.cancel_requested)
        self.assertEqual(job.status, ProviderImportJob.Status.CANCEL_REQUESTED)

    def test_logs_sanitized_and_download_url_not_serialized(self):
        self.client.force_authenticate(self.staff)
        job = create_import_job(
            provider=self.provider,
            user=self.staff,
            content_type='movies',
            mode='discover_only',
            params={'limit': 1},
        )
        from apps.catalog.provider_import.service import append_log
        append_log(job, 'info', 'safe message', {
            'token': 'super-secret-token',
            'download_url': 'https://cdn.provider.test/secret-download',
            'title': 'ok',
        })
        response = self.client.get(f'/api/admin/provider-import/jobs/{job.id}/logs/')
        self.assertEqual(response.status_code, 200)
        context = response.data['results'][0]['context']
        self.assertEqual(context.get('title'), 'ok')
        self.assertNotIn('token', context)
        self.assertNotIn('download_url', context)
        candidate = ProviderDownloadCandidate(
            provider_item_id='1',
            content_type='movie',
            url_or_reference='https://cdn.provider.test/secret-download',
        )
        public = candidate.public_dict()
        self.assertNotIn('url_or_reference', public)
        self.assertNotIn('secret-download', str(public))


@override_settings(**PROVIDER_SETTINGS)
class ProviderMatcherAndTransferTests(TestCase):
    def setUp(self):
        self.movie = Movie.objects.create(
            title='Matched Film',
            original_title='Matched Film',
            slug='matched-film',
            tmdb_id=4242,
            imdb_id='tt4242424',
            release_year=2020,
        )
        self.provider = ensure_avasarami_provider()

    def test_match_by_tmdb_id(self):
        movie, reason = match_movie(tmdb_id=4242, title='Other', year=1999)
        self.assertEqual(movie.id, self.movie.id)
        self.assertEqual(reason, 'tmdb_id')

    def test_match_by_imdb_id(self):
        movie, reason = match_movie(imdb_id='tt4242424')
        self.assertEqual(movie.id, self.movie.id)
        self.assertEqual(reason, 'imdb_id')

    def test_match_by_title_year(self):
        movie, reason = match_movie(title='Matched Film', year=2020)
        self.assertEqual(movie.id, self.movie.id)
        self.assertEqual(reason, 'title_year')

    def test_no_overwrite_unless_true(self):
        MovieArchiveAsset.objects.create(
            movie=self.movie,
            bucket='revayato-archive-test',
            object_key=f'archive/movies/{self.movie.id}/source/{uuid4()}/a.mp4',
            original_filename='a.mp4',
            safe_filename='a.mp4',
            file_extension='mp4',
            content_type='video/mp4',
            size_bytes=10,
            part_size_bytes=5 * 1024 * 1024,
            total_parts=1,
            status=MovieArchiveAsset.Status.AVAILABLE,
        )
        connector = MagicMock()
        candidate = ProviderDownloadCandidate(
            provider_item_id='x',
            content_type='movie',
            filename='a.mp4',
            size_bytes=10,
            url_or_reference='https://cdn.provider.test/secret-download',
        )
        from apps.catalog.provider_import.exceptions import ProviderImportError
        with self.assertRaises(ProviderImportError):
            transfer_movie_candidate(
                connector=connector,
                candidate=candidate,
                movie=self.movie,
                overwrite=False,
            )

    def test_streaming_transfer_creates_asset_and_abort_on_failure(self):
        storage = MagicMock(spec=ArchiveStorageClient)
        storage.bucket = 'revayato-archive-test'
        storage.create_multipart_upload.return_value = 'upload-xyz'
        storage.upload_part.return_value = '"etag-1"'
        storage.head_object.return_value = {
            'content_length': 11,
            'etag': 'final',
            'content_type': 'video/mp4',
            'metadata': {},
        }

        connector = MagicMock()
        connector.slug = 'avasarami'
        connector.open_download_stream.return_value = iter([b'hello ', b'world'])

        candidate = ProviderDownloadCandidate(
            provider_item_id='x',
            content_type='movie',
            filename='film.mp4',
            size_bytes=11,
            content_type_header='video/mp4',
            url_or_reference='https://cdn.provider.test/secret-download',
        )

        with patch('apps.catalog.provider_import.downloader.get_archive_storage', return_value=storage):
            result = transfer_movie_candidate(
                connector=connector,
                candidate=candidate,
                movie=self.movie,
                overwrite=True,
            )
        self.assertEqual(result.asset.status, MovieArchiveAsset.Status.AVAILABLE)
        self.assertTrue(result.asset.sha256)
        self.assertIn('/source/provider/avasarami/', result.asset.object_key)
        storage.complete_multipart_upload.assert_called_once()

        # Failure path aborts multipart.
        storage2 = MagicMock(spec=ArchiveStorageClient)
        storage2.bucket = 'revayato-archive-test'
        storage2.create_multipart_upload.return_value = 'upload-fail'
        storage2.upload_part.side_effect = Exception('boom')
        connector2 = MagicMock()
        connector2.slug = 'avasarami'
        connector2.open_download_stream.return_value = iter([b'data'])
        with patch('apps.catalog.provider_import.downloader.get_archive_storage', return_value=storage2):
            with self.assertRaises(Exception):
                transfer_movie_candidate(
                    connector=connector2,
                    candidate=candidate,
                    movie=self.movie,
                    overwrite=True,
                )
        storage2.abort_multipart_upload.assert_called()

    @override_settings(AVASARAMI_API_TOKEN='super-secret-token', AVASARAMI_AUTH_TYPE='bearer_token')
    def test_job_runs_discover_with_mocked_list(self):
        User = get_user_model()
        staff = User.objects.create_user(
            email='job-staff@example.com', username='job-staff', password='x', is_staff=True,
        )
        job = create_import_job(
            provider=self.provider,
            user=staff,
            content_type='movies',
            mode='discover_only',
            params={'limit': 10, 'dry_run': True},
        )
        movie = ProviderMovie(
            provider_item_id='p1',
            title='Matched Film',
            year=2020,
            tmdb_id=4242,
            raw_payload={'title': 'Matched Film', 'download_url': 'https://cdn.provider.test/secret-download'},
        )
        with patch.object(AvasaramiConnector, 'authenticate', return_value=MagicMock(
            ok=True, message='ok', auth_type='bearer_token', requires_interactive_verification=False,
        )):
            with patch.object(AvasaramiConnector, 'list_movies', return_value=[movie]):
                result = run_provider_import_job(str(job.id))
        self.assertEqual(result['status'], 'completed')
        job.refresh_from_db()
        item = job.items.get()
        self.assertEqual(item.status, 'matched')
        self.assertEqual(item.matched_movie_id, self.movie.id)
        self.assertNotIn('download_url', item.raw_payload)

    def test_sanitize_payload_strips_secrets(self):
        cleaned = sanitize_payload({
            'title': 'x',
            'password': 'p',
            'cookie': 'c',
            'download_url': 'https://cdn.provider.test/secret-download',
        })
        self.assertEqual(cleaned, {'title': 'x'})

    def test_captcha_message_constant(self):
        self.assertIn('CAPTCHA', CAPTCHA_MESSAGE)
        self.assertIn('official API', CAPTCHA_MESSAGE)
