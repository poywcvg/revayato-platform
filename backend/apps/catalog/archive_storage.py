"""Private S3-compatible client for original movie archive objects.

Uses ARCHIVE_* settings only. Never reuse the public AWS_* media storage config.
Credentials must never be logged or returned to API clients.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class ArchiveStorageError(Exception):
    """Safe, non-secret error for archive object-storage operations."""

    def __init__(self, message='Archive storage operation failed.', *, code='archive_storage_error'):
        super().__init__(message)
        self.code = code


def archive_max_upload_bytes():
    return max(1, int(getattr(settings, 'ARCHIVE_MAX_UPLOAD_SIZE_GB', 100))) * (1024 ** 3)


def archive_chunk_size_bytes():
    return max(5 * 1024 * 1024, int(getattr(settings, 'ARCHIVE_MULTIPART_CHUNK_SIZE_MB', 64)) * 1024 * 1024)


def archive_presign_expires():
    return max(60, min(3600, int(getattr(settings, 'ARCHIVE_PRESIGNED_URL_EXPIRES', 900))))


def archive_download_expires():
    return max(60, min(3600, int(getattr(settings, 'ARCHIVE_DOWNLOAD_URL_EXPIRES', 600))))


def archive_url_batch_size():
    return max(1, min(100, int(getattr(settings, 'ARCHIVE_MULTIPART_URL_BATCH_SIZE', 20))))


def ensure_archive_configured():
    if not getattr(settings, 'ARCHIVE_S3_PRIVATE', True):
        raise ImproperlyConfigured('ARCHIVE_S3_PRIVATE must remain True for original movie archives.')
    bucket = (getattr(settings, 'ARCHIVE_S3_BUCKET_NAME', '') or '').strip()
    endpoint = (getattr(settings, 'ARCHIVE_S3_ENDPOINT_URL', '') or '').strip()
    access_key = getattr(settings, 'ARCHIVE_S3_ACCESS_KEY_ID', '') or ''
    secret_key = getattr(settings, 'ARCHIVE_S3_SECRET_ACCESS_KEY', '') or ''
    if not bucket or not endpoint or not access_key or not secret_key:
        raise ImproperlyConfigured(
            'Private archive storage is not configured. Set ARCHIVE_S3_BUCKET_NAME, '
            'ARCHIVE_S3_ENDPOINT_URL, ARCHIVE_S3_ACCESS_KEY_ID, and ARCHIVE_S3_SECRET_ACCESS_KEY.',
        )
    return {
        'bucket': bucket,
        'endpoint_url': endpoint,
        'access_key': access_key,
        'secret_key': secret_key,
        'region': (getattr(settings, 'ARCHIVE_S3_REGION', '') or 'us-east-1').strip(),
        'signature_version': (getattr(settings, 'ARCHIVE_S3_SIGNATURE_VERSION', 's3v4') or 's3v4').strip(),
        'addressing_style': (getattr(settings, 'ARCHIVE_S3_ADDRESSING_STYLE', 'path') or 'path').strip(),
    }


def get_archive_storage():
    return ArchiveStorageClient()


class ArchiveStorageClient:
    """Thin boto3 wrapper for private archive multipart operations."""

    def __init__(self, client=None, bucket=None):
        if client is not None:
            self._client = client
            self.bucket = bucket or (getattr(settings, 'ARCHIVE_S3_BUCKET_NAME', '') or '').strip()
            if not self.bucket:
                raise ImproperlyConfigured('ARCHIVE_S3_BUCKET_NAME is required.')
            return

        cfg = ensure_archive_configured()
        self.bucket = cfg['bucket']
        connect_timeout = int(getattr(settings, 'ARCHIVE_S3_CONNECT_TIMEOUT', 10))
        read_timeout = int(getattr(settings, 'ARCHIVE_S3_READ_TIMEOUT', 60))
        max_attempts = int(getattr(settings, 'ARCHIVE_S3_MAX_ATTEMPTS', 3))
        self._client = boto3.client(
            's3',
            endpoint_url=cfg['endpoint_url'],
            region_name=cfg['region'],
            aws_access_key_id=cfg['access_key'],
            aws_secret_access_key=cfg['secret_key'],
            config=Config(
                signature_version=cfg['signature_version'],
                s3={'addressing_style': cfg['addressing_style']},
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
                retries={'max_attempts': max_attempts, 'mode': 'standard'},
            ),
        )

    def _wrap(self, exc: Exception) -> ArchiveStorageError:
        error = ArchiveStorageError('Archive storage operation failed.', code='archive_storage_error')
        error.__cause__ = exc
        return error

    def create_multipart_upload(self, object_key, content_type, metadata=None):
        params: dict[str, Any] = {
            'Bucket': self.bucket,
            'Key': object_key,
            'ContentType': content_type,
        }
        if metadata:
            params['Metadata'] = {str(k): str(v) for k, v in metadata.items()}
        try:
            response = self._client.create_multipart_upload(**params)
        except (BotoCoreError, ClientError) as exc:
            raise self._wrap(exc) from exc
        upload_id = response.get('UploadId')
        if not upload_id:
            raise ArchiveStorageError('Multipart upload could not be started.', code='multipart_create_failed')
        return upload_id

    def generate_presigned_upload_part_url(self, object_key, upload_id, part_number, expires=None):
        expires = expires if expires is not None else archive_presign_expires()
        try:
            return self._client.generate_presigned_url(
                ClientMethod='upload_part',
                Params={
                    'Bucket': self.bucket,
                    'Key': object_key,
                    'UploadId': upload_id,
                    'PartNumber': int(part_number),
                },
                ExpiresIn=int(expires),
                HttpMethod='PUT',
            )
        except (BotoCoreError, ClientError) as exc:
            raise self._wrap(exc) from exc

    def upload_part(self, object_key, upload_id, part_number, body):
        """Server-side multipart part upload (Celery streaming transfers)."""
        try:
            response = self._client.upload_part(
                Bucket=self.bucket,
                Key=object_key,
                UploadId=upload_id,
                PartNumber=int(part_number),
                Body=body,
            )
        except (BotoCoreError, ClientError) as exc:
            raise self._wrap(exc) from exc
        etag = (response.get('ETag') or '').strip()
        if not etag:
            raise ArchiveStorageError('Multipart part upload returned no ETag.', code='multipart_part_failed')
        return etag

    def complete_multipart_upload(self, object_key, upload_id, parts):
        formatted_parts = []
        for part in parts:
            etag = str(part['etag']).strip()
            if not etag.startswith('"'):
                etag = f'"{etag}"'
            formatted_parts.append({
                'ETag': etag,
                'PartNumber': int(part['part_number']),
            })
        payload = {'Parts': formatted_parts}
        try:
            return self._client.complete_multipart_upload(
                Bucket=self.bucket,
                Key=object_key,
                UploadId=upload_id,
                MultipartUpload=payload,
            )
        except (BotoCoreError, ClientError) as exc:
            raise self._wrap(exc) from exc

    def abort_multipart_upload(self, object_key, upload_id):
        try:
            self._client.abort_multipart_upload(
                Bucket=self.bucket,
                Key=object_key,
                UploadId=upload_id,
            )
        except (BotoCoreError, ClientError) as exc:
            raise self._wrap(exc) from exc

    def head_object(self, object_key):
        try:
            response = self._client.head_object(Bucket=self.bucket, Key=object_key)
        except (BotoCoreError, ClientError) as exc:
            raise self._wrap(exc) from exc
        return {
            'content_length': response.get('ContentLength'),
            'etag': (response.get('ETag') or '').strip('"'),
            'content_type': response.get('ContentType') or '',
            'metadata': response.get('Metadata') or {},
        }

    def generate_presigned_download_url(self, object_key, filename, expires=None):
        expires = expires if expires is not None else archive_download_expires()
        safe_name = quote(filename or 'archive.bin')
        try:
            return self._client.generate_presigned_url(
                ClientMethod='get_object',
                Params={
                    'Bucket': self.bucket,
                    'Key': object_key,
                    'ResponseContentDisposition': f'attachment; filename="{safe_name}"',
                },
                ExpiresIn=int(expires),
                HttpMethod='GET',
            )
        except (BotoCoreError, ClientError) as exc:
            raise self._wrap(exc) from exc

    def delete_object(self, object_key):
        try:
            self._client.delete_object(Bucket=self.bucket, Key=object_key)
        except (BotoCoreError, ClientError) as exc:
            raise self._wrap(exc) from exc
