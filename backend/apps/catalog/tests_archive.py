"""Mocked staff archive multipart API tests. No real S3 network calls."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .archive_storage import ArchiveStorageClient, ArchiveStorageError
from .models import Movie, MovieArchiveAsset


ARCHIVE_SETTINGS = {
    'ARCHIVE_S3_ENDPOINT_URL': 'https://s3.example.test',
    'ARCHIVE_S3_ACCESS_KEY_ID': 'test-access-key',
    'ARCHIVE_S3_SECRET_ACCESS_KEY': 'test-secret-key-never-return',
    'ARCHIVE_S3_BUCKET_NAME': 'revayato-archive-test',
    'ARCHIVE_S3_REGION': 'ir-thr-at1',
    'ARCHIVE_S3_SIGNATURE_VERSION': 's3v4',
    'ARCHIVE_S3_ADDRESSING_STYLE': 'path',
    'ARCHIVE_S3_PRIVATE': True,
    'ARCHIVE_PRESIGNED_URL_EXPIRES': 900,
    'ARCHIVE_DOWNLOAD_URL_EXPIRES': 600,
    'ARCHIVE_MULTIPART_CHUNK_SIZE_MB': 64,
    'ARCHIVE_MULTIPART_URL_BATCH_SIZE': 20,
    'ARCHIVE_UPLOAD_CONCURRENCY': 3,
    'ARCHIVE_MAX_UPLOAD_SIZE_GB': 100,
    'ARCHIVE_ALLOWED_EXTENSIONS': ('mkv', 'mp4'),
}


def _secret_leak(payload) -> bool:
    text = str(payload).lower()
    return any(token in text for token in (
        'test-secret-key-never-return',
        'secret_access_key',
        'aws_secret',
        'access_key_id',
    ))


@override_settings(**ARCHIVE_SETTINGS)
class ArchiveApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            email='archive-staff@example.com',
            username='archive-staff',
            password='test-pass-123',
            is_staff=True,
        )
        self.user = User.objects.create_user(
            email='archive-user@example.com',
            username='archive-user',
            password='test-pass-123',
            is_staff=False,
        )
        self.movie = Movie.objects.create(title='Archive Movie', slug='archive-movie')
        self.client = APIClient()
        self.storage = MagicMock(spec=ArchiveStorageClient)
        self.storage.bucket = 'revayato-archive-test'
        self.storage.create_multipart_upload.return_value = 'upload-abc'
        self.storage.generate_presigned_upload_part_url.side_effect = (
            lambda key, upload_id, part_number, expires=None: (
                f'https://s3.example.test/presign/{part_number}?x={upload_id}'
            )
        )
        self.storage.head_object.return_value = {
            'content_length': 128 * 1024 * 1024,
            'etag': 'etag-final',
            'content_type': 'video/mp4',
            'metadata': {},
        }
        self.storage.generate_presigned_download_url.return_value = (
            'https://s3.example.test/download?sig=1'
        )
        self.storage_patch = patch(
            'apps.catalog.archive_api.get_archive_storage',
            return_value=self.storage,
        )
        self.storage_patch.start()
        self.addCleanup(self.storage_patch.stop)

    def _initiate_payload(self, **overrides):
        payload = {
            'movie_id': self.movie.id,
            'original_filename': 'Film Title (2024).mp4',
            'size_bytes': 128 * 1024 * 1024,
            'content_type': 'video/mp4',
        }
        payload.update(overrides)
        return payload

    def _initiate(self, user=None, **overrides):
        if user is not None:
            self.client.force_authenticate(user)
        return self.client.post(
            '/api/admin/archive/uploads/initiate/',
            self._initiate_payload(**overrides),
            format='json',
        )

    def test_initiate_requires_authentication(self):
        response = self._initiate()
        self.assertEqual(response.status_code, 401)

    def test_initiate_requires_staff(self):
        response = self._initiate(user=self.user)
        self.assertEqual(response.status_code, 403)

    def test_staff_can_initiate_mocked_multipart_upload(self):
        response = self._initiate(user=self.staff)
        self.assertEqual(response.status_code, 201)
        self.assertFalse(_secret_leak(response.data))
        asset = MovieArchiveAsset.objects.get(pk=response.data['asset_id'])
        self.assertEqual(asset.bucket, 'revayato-archive-test')
        self.assertEqual(asset.upload_id, 'upload-abc')
        self.assertEqual(asset.status, MovieArchiveAsset.Status.UPLOADING)
        self.assertTrue(asset.object_key.startswith(f'archive/movies/{self.movie.id}/source/{asset.id}/'))
        self.assertTrue(asset.object_key.endswith('.mp4'))
        self.storage.create_multipart_upload.assert_called_once()

    def test_client_cannot_override_bucket_or_object_key(self):
        response = self._initiate(
            user=self.staff,
            bucket='evil-bucket',
            object_key='evil/path/file.mp4',
        )
        self.assertEqual(response.status_code, 201)
        self.assertNotIn('evil-bucket', response.data.get('object_key', ''))
        self.assertNotEqual(response.data.get('object_key'), 'evil/path/file.mp4')
        asset = MovieArchiveAsset.objects.get(pk=response.data['asset_id'])
        self.assertEqual(asset.bucket, 'revayato-archive-test')
        self.assertNotEqual(asset.object_key, 'evil/path/file.mp4')

    def test_invalid_movie_id_rejected(self):
        response = self._initiate(user=self.staff, movie_id=999999)
        self.assertEqual(response.status_code, 400)

    def test_invalid_extension_rejected(self):
        response = self._initiate(
            user=self.staff,
            original_filename='malware.exe',
            content_type='video/mp4',
        )
        self.assertEqual(response.status_code, 400)

    def test_path_traversal_filename_is_sanitized(self):
        response = self._initiate(
            user=self.staff,
            original_filename='../../etc/passwd.mp4',
        )
        self.assertEqual(response.status_code, 201)
        asset = MovieArchiveAsset.objects.get(pk=response.data['asset_id'])
        self.assertNotIn('..', asset.object_key)
        self.assertTrue(asset.safe_filename.endswith('.mp4'))

    def test_excessive_size_rejected(self):
        response = self._initiate(user=self.staff, size_bytes=200 * (1024 ** 3))
        self.assertEqual(response.status_code, 400)

    def test_zero_and_negative_size_rejected(self):
        for size in (0, -1):
            response = self._initiate(user=self.staff, size_bytes=size)
            self.assertEqual(response.status_code, 400)

    def test_presign_parts_requires_staff(self):
        created = self._initiate(user=self.staff)
        asset_id = created.data['asset_id']
        self.client.force_authenticate(self.user)
        response = self.client.post(
            f'/api/admin/archive/uploads/{asset_id}/presign-parts/',
            {'part_numbers': [1]},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_presign_parts_rejects_invalid_part_numbers(self):
        created = self._initiate(user=self.staff)
        asset_id = created.data['asset_id']
        total = created.data['total_parts']
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            f'/api/admin/archive/uploads/{asset_id}/presign-parts/',
            {'part_numbers': [total + 1]},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_presign_parts_respects_batch_size(self):
        created = self._initiate(user=self.staff, size_bytes=64 * 1024 * 1024 * 25)
        asset_id = created.data['asset_id']
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            f'/api/admin/archive/uploads/{asset_id}/presign-parts/',
            {'part_numbers': list(range(1, 22))},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_presign_parts_returns_urls(self):
        created = self._initiate(user=self.staff)
        asset_id = created.data['asset_id']
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            f'/api/admin/archive/uploads/{asset_id}/presign-parts/',
            {'start_part': 1, 'end_part': 2},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['parts']), 2)
        self.assertFalse(_secret_leak(response.data))

    def _parts_for(self, total_parts):
        return [{'part_number': n, 'etag': f'etag-{n}'} for n in range(1, total_parts + 1)]

    def test_complete_requires_staff(self):
        created = self._initiate(user=self.staff)
        asset_id = created.data['asset_id']
        self.client.force_authenticate(self.user)
        response = self.client.post(
            f'/api/admin/archive/uploads/{asset_id}/complete/',
            {'parts': self._parts_for(created.data['total_parts'])},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_complete_rejects_duplicate_parts(self):
        created = self._initiate(user=self.staff)
        asset_id = created.data['asset_id']
        parts = self._parts_for(created.data['total_parts'])
        parts.append(parts[0])
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            f'/api/admin/archive/uploads/{asset_id}/complete/',
            {'parts': parts},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_complete_sorts_parts_and_verifies_head(self):
        created = self._initiate(user=self.staff)
        asset_id = created.data['asset_id']
        total = created.data['total_parts']
        parts = list(reversed(self._parts_for(total)))
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            f'/api/admin/archive/uploads/{asset_id}/complete/',
            {'parts': parts},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'available')
        called_parts = self.storage.complete_multipart_upload.call_args.args[2]
        self.assertEqual([p['part_number'] for p in called_parts], list(range(1, total + 1)))
        self.storage.head_object.assert_called_once()
        asset = MovieArchiveAsset.objects.get(pk=asset_id)
        self.assertEqual(asset.etag, 'etag-final')
        self.assertEqual(asset.actual_size_bytes, 128 * 1024 * 1024)

    def test_head_size_mismatch_marks_failed(self):
        created = self._initiate(user=self.staff)
        asset_id = created.data['asset_id']
        self.storage.head_object.return_value = {
            'content_length': 1,
            'etag': 'bad',
            'content_type': 'video/mp4',
            'metadata': {},
        }
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            f'/api/admin/archive/uploads/{asset_id}/complete/',
            {'parts': self._parts_for(created.data['total_parts'])},
            format='json',
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['status'], 'failed')
        asset = MovieArchiveAsset.objects.get(pk=asset_id)
        self.assertEqual(asset.status, MovieArchiveAsset.Status.FAILED)

    def test_duplicate_complete_is_idempotent(self):
        created = self._initiate(user=self.staff)
        asset_id = created.data['asset_id']
        parts = self._parts_for(created.data['total_parts'])
        self.client.force_authenticate(self.staff)
        first = self.client.post(
            f'/api/admin/archive/uploads/{asset_id}/complete/',
            {'parts': parts},
            format='json',
        )
        second = self.client.post(
            f'/api/admin/archive/uploads/{asset_id}/complete/',
            {'parts': parts},
            format='json',
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data['status'], 'available')
        self.assertEqual(self.storage.complete_multipart_upload.call_count, 1)

    def test_abort_requires_staff_and_calls_storage(self):
        created = self._initiate(user=self.staff)
        asset_id = created.data['asset_id']
        self.client.force_authenticate(self.user)
        denied = self.client.post(f'/api/admin/archive/uploads/{asset_id}/abort/', {}, format='json')
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(self.staff)
        response = self.client.post(f'/api/admin/archive/uploads/{asset_id}/abort/', {}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'aborted')
        self.storage.abort_multipart_upload.assert_called_once()

    def test_download_url_requires_staff_and_available(self):
        created = self._initiate(user=self.staff)
        asset_id = created.data['asset_id']
        self.client.force_authenticate(self.staff)
        not_ready = self.client.post(
            f'/api/admin/archive/assets/{asset_id}/download-url/',
            {},
            format='json',
        )
        self.assertEqual(not_ready.status_code, 409)

        self.client.post(
            f'/api/admin/archive/uploads/{asset_id}/complete/',
            {'parts': self._parts_for(created.data['total_parts'])},
            format='json',
        )
        self.client.force_authenticate(self.user)
        denied = self.client.post(
            f'/api/admin/archive/assets/{asset_id}/download-url/',
            {},
            format='json',
        )
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(self.staff)
        ok = self.client.post(
            f'/api/admin/archive/assets/{asset_id}/download-url/',
            {},
            format='json',
        )
        self.assertEqual(ok.status_code, 200)
        self.assertIn('url', ok.data)
        self.assertIn('expires_in', ok.data)
        self.assertFalse(_secret_leak(ok.data))

    def test_delete_ignores_client_object_key_and_marks_deleted(self):
        created = self._initiate(user=self.staff)
        asset_id = created.data['asset_id']
        self.client.force_authenticate(self.staff)
        self.client.post(
            f'/api/admin/archive/uploads/{asset_id}/complete/',
            {'parts': self._parts_for(created.data['total_parts'])},
            format='json',
        )
        asset = MovieArchiveAsset.objects.get(pk=asset_id)
        real_key = asset.object_key
        response = self.client.post(
            f'/api/admin/archive/assets/{asset_id}/delete/',
            {'object_key': 'attacker/other-key.mp4', 'force': True},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'deleted')
        self.storage.delete_object.assert_called_once_with(real_key)
        self.assertNotEqual(real_key, 'attacker/other-key.mp4')

    def test_status_endpoint_returns_safe_metadata(self):
        created = self._initiate(user=self.staff)
        asset_id = created.data['asset_id']
        self.client.force_authenticate(self.staff)
        response = self.client.get(f'/api/admin/archive/assets/{asset_id}/status/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['asset_id'], asset_id)
        self.assertFalse(_secret_leak(response.data))

    def test_storage_errors_do_not_leak_internal_details(self):
        self.storage.create_multipart_upload.side_effect = ArchiveStorageError(
            'Archive storage operation failed.',
        )
        response = self._initiate(user=self.staff)
        self.assertEqual(response.status_code, 502)
        self.assertFalse(_secret_leak(response.data))
        self.assertNotIn('Traceback', str(response.data))

    def test_unknown_asset_404(self):
        self.client.force_authenticate(self.staff)
        response = self.client.get(f'/api/admin/archive/assets/{uuid4()}/status/')
        self.assertEqual(response.status_code, 404)
