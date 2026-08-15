"""Stream provider downloads into private ArvanCloud archive storage."""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from pathlib import PurePosixPath

from django.utils import timezone

from apps.catalog.archive_storage import (
    ArchiveStorageError,
    archive_chunk_size_bytes,
    get_archive_storage,
)
from apps.catalog.models import MovieArchiveAsset

from .base import ProviderDownloadCandidate
from .exceptions import JobCancelled, ProviderImportError


def sanitize_provider_filename(filename: str) -> tuple[str, str, str]:
    raw = PurePosixPath(str(filename or '').replace('\\', '/')).name.strip() or 'archive.bin'
    stem = PurePosixPath(raw).stem or 'archive'
    extension = PurePosixPath(raw).suffix.lower().lstrip('.') or 'bin'
    safe_stem = re.sub(r'[^A-Za-z0-9._-]+', '_', stem).strip('._-') or 'archive'
    safe_filename = f'{safe_stem[:180]}.{extension}'
    return raw[:255], safe_filename, extension


def build_provider_movie_object_key(movie_id, asset_id, safe_filename: str, provider_slug='avasarami') -> str:
    return (
        f'archive/movies/{movie_id}/source/provider/{provider_slug}/'
        f'{asset_id}/{safe_filename}'
    )


def build_provider_episode_object_key(
    series_id, episode_id, asset_id, safe_filename: str, provider_slug='avasarami',
) -> str:
    return (
        f'archive/series/{series_id}/episodes/{episode_id}/source/provider/'
        f'{provider_slug}/{asset_id}/{safe_filename}'
    )


class StreamingTransferResult:
    def __init__(self, *, asset, bytes_transferred, sha256):
        self.asset = asset
        self.bytes_transferred = bytes_transferred
        self.sha256 = sha256


def transfer_movie_candidate(
    *,
    connector,
    candidate: ProviderDownloadCandidate,
    movie,
    user=None,
    overwrite=False,
    should_cancel=None,
    on_progress=None,
    dry_run=False,
) -> StreamingTransferResult | None:
    """Stream an authorized provider candidate into MovieArchiveAsset.

    Never logs candidate.url_or_reference.
    """
    if movie.archive_assets.filter(status=MovieArchiveAsset.Status.AVAILABLE).exists() and not overwrite:
        raise ProviderImportError(
            'Movie already has an available archive asset. Pass overwrite=true to replace.',
            code='archive_exists',
        )

    if dry_run:
        return None

    original_filename, safe_filename, extension = sanitize_provider_filename(
        candidate.filename or f'{movie.slug or movie.id}.bin',
    )
    content_type = candidate.content_type_header or 'application/octet-stream'
    size_bytes = int(candidate.size_bytes or 0)
    part_size = archive_chunk_size_bytes()
    # Unknown size: plan for large streaming; adjust as bytes arrive.
    total_parts = max(1, (size_bytes // part_size) + 1) if size_bytes else 1

    asset_id = uuid.uuid4()
    object_key = build_provider_movie_object_key(
        movie.id, asset_id, safe_filename, getattr(connector, 'slug', 'avasarami'),
    )
    storage = get_archive_storage()
    upload_id = None
    parts = []
    digest = hashlib.sha256()
    transferred = 0
    part_number = 1
    buffer = bytearray()

    asset = MovieArchiveAsset.objects.create(
        id=asset_id,
        movie=movie,
        storage_provider='arvan_s3',
        bucket=storage.bucket,
        object_key=object_key,
        original_filename=original_filename,
        safe_filename=safe_filename,
        file_extension=extension[:16],
        content_type=content_type[:100],
        size_bytes=max(size_bytes, 1),
        part_size_bytes=part_size,
        total_parts=total_parts,
        status=MovieArchiveAsset.Status.PENDING,
        created_by=user,
        uploaded_by=user,
    )

    try:
        upload_id = storage.create_multipart_upload(
            object_key,
            content_type,
            metadata={
                'provider': getattr(connector, 'slug', 'avasarami'),
                'movie_id': str(movie.id),
            },
        )
        asset.upload_id = upload_id
        asset.status = MovieArchiveAsset.Status.UPLOADING
        asset.save(update_fields=['upload_id', 'status', 'updated_at'])

        for chunk in connector.open_download_stream(candidate):
            if should_cancel and should_cancel():
                raise JobCancelled('Provider import job was cancelled.')
            if not chunk:
                continue
            digest.update(chunk)
            buffer.extend(chunk)
            transferred += len(chunk)
            if on_progress:
                on_progress(transferred)
            while len(buffer) >= part_size:
                body = bytes(buffer[:part_size])
                del buffer[:part_size]
                etag = _upload_part_with_retry(storage, object_key, upload_id, part_number, body)
                parts.append({'etag': etag, 'part_number': part_number})
                part_number += 1

        if buffer:
            etag = _upload_part_with_retry(storage, object_key, upload_id, part_number, bytes(buffer))
            parts.append({'etag': etag, 'part_number': part_number})
            part_number += 1

        if not parts:
            raise ProviderImportError('Download stream produced no data.', code='empty_download')

        storage.complete_multipart_upload(object_key, upload_id, parts)
        head = storage.head_object(object_key)
        sha = digest.hexdigest()
        asset.status = MovieArchiveAsset.Status.AVAILABLE
        asset.actual_size_bytes = head.get('content_length') or transferred
        asset.size_bytes = asset.actual_size_bytes or transferred or 1
        asset.etag = head.get('etag') or ''
        asset.sha256 = sha
        asset.total_parts = len(parts)
        asset.upload_id = ''
        asset.completed_at = timezone.now()
        asset.failure_reason = ''
        asset.save()
        return StreamingTransferResult(asset=asset, bytes_transferred=transferred, sha256=sha)
    except Exception as exc:
        asset.status = (
            MovieArchiveAsset.Status.ABORTED
            if isinstance(exc, JobCancelled)
            else MovieArchiveAsset.Status.FAILED
        )
        asset.failure_reason = str(exc)[:500]
        asset.aborted_at = timezone.now()
        asset.save(update_fields=['status', 'failure_reason', 'aborted_at', 'updated_at'])
        if upload_id:
            try:
                storage.abort_multipart_upload(object_key, upload_id)
            except ArchiveStorageError:
                pass
        raise


def _upload_part_with_retry(storage, object_key, upload_id, part_number, body, attempts=4):
    delay = 1.0
    last_exc = None
    for _ in range(attempts):
        try:
            return storage.upload_part(object_key, upload_id, part_number, body)
        except ArchiveStorageError as exc:
            last_exc = exc
            time.sleep(delay)
            delay = min(30.0, delay * 2)
    raise last_exc or ArchiveStorageError('Multipart part upload failed.')
