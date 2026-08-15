"""Staff-only private movie archive multipart upload APIs.

Browser uploads go directly to object storage via short-lived presigned URLs.
Django never receives original movie file bytes on these endpoints.
"""

from __future__ import annotations

import math
import re
from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .admin_api import IsStaffUser, StaffAdminThrottle
from .archive_storage import (
    ArchiveStorageError,
    archive_chunk_size_bytes,
    archive_download_expires,
    archive_max_upload_bytes,
    archive_presign_expires,
    archive_url_batch_size,
    get_archive_storage,
)
from .models import Movie, MovieArchiveAsset

S3_MAX_PARTS = 10000

ALLOWED_CONTENT_TYPES = {
    'mp4': {'video/mp4'},
    'mkv': {'video/x-matroska', 'video/mkv'},
}

UPLOAD_ACTIVE_STATUSES = {
    MovieArchiveAsset.Status.MULTIPART_CREATED,
    MovieArchiveAsset.Status.UPLOADING,
}

COMPLETABLE_STATUSES = {
    MovieArchiveAsset.Status.MULTIPART_CREATED,
    MovieArchiveAsset.Status.UPLOADING,
}

ABORTABLE_STATUSES = {
    MovieArchiveAsset.Status.PENDING,
    MovieArchiveAsset.Status.MULTIPART_CREATED,
    MovieArchiveAsset.Status.UPLOADING,
    MovieArchiveAsset.Status.FAILED,
}

DELETABLE_STATUSES = {
    MovieArchiveAsset.Status.AVAILABLE,
    MovieArchiveAsset.Status.FAILED,
    MovieArchiveAsset.Status.ABORTED,
}


def _storage_or_error():
    try:
        return get_archive_storage(), None
    except ImproperlyConfigured as exc:
        return None, Response(
            {'detail': str(exc), 'code': 'archive_not_configured'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def _storage_failure(exc: ArchiveStorageError):
    return Response(
        {'detail': str(exc), 'code': getattr(exc, 'code', 'archive_storage_error')},
        status=status.HTTP_502_BAD_GATEWAY,
    )


def sanitize_archive_filename(filename: str) -> tuple[str, str, str]:
    """Return (original_basename, safe_filename, extension)."""
    raw = PurePosixPath(str(filename or '').replace('\\', '/')).name.strip()
    if not raw or raw in {'.', '..'}:
        raise serializers.ValidationError({'original_filename': 'A valid filename is required.'})
    if '\x00' in raw:
        raise serializers.ValidationError({'original_filename': 'Filename contains invalid characters.'})

    stem = PurePosixPath(raw).stem
    extension = PurePosixPath(raw).suffix.lower().lstrip('.')
    if not extension:
        raise serializers.ValidationError({'original_filename': 'Filename must include an extension.'})

    safe_stem = re.sub(r'[^A-Za-z0-9._-]+', '_', stem).strip('._-')
    if not safe_stem:
        safe_stem = 'movie'
    safe_stem = safe_stem[:180]
    safe_filename = f'{safe_stem}.{extension}'
    return raw[:255], safe_filename, extension


def calculate_multipart_plan(size_bytes: int) -> tuple[int, int]:
    part_size = archive_chunk_size_bytes()
    total_parts = max(1, math.ceil(size_bytes / part_size))
    if total_parts > S3_MAX_PARTS:
        part_size = math.ceil(size_bytes / S3_MAX_PARTS)
        # Align upward to 1 MiB for cleaner multipart boundaries.
        part_size = max(5 * 1024 * 1024, int(math.ceil(part_size / (1024 * 1024)) * 1024 * 1024))
        total_parts = max(1, math.ceil(size_bytes / part_size))
    if total_parts > S3_MAX_PARTS:
        raise serializers.ValidationError({
            'size_bytes': f'File requires more than {S3_MAX_PARTS} multipart parts.',
        })
    return part_size, total_parts


def build_object_key(movie_id, asset_id, safe_filename: str) -> str:
    return f'archive/movies/{movie_id}/source/{asset_id}/{safe_filename}'


def asset_status_payload(asset: MovieArchiveAsset) -> dict:
    return {
        'asset_id': str(asset.id),
        'movie_id': asset.movie_id,
        'original_filename': asset.original_filename,
        'safe_filename': asset.safe_filename,
        'file_extension': asset.file_extension,
        'content_type': asset.content_type,
        'size_bytes': asset.size_bytes,
        'actual_size_bytes': asset.actual_size_bytes,
        'etag': asset.etag or None,
        'part_size_bytes': asset.part_size_bytes,
        'total_parts': asset.total_parts,
        'status': asset.status,
        'failure_reason': asset.failure_reason or None,
        'object_key': asset.object_key,
        'created_at': asset.created_at,
        'updated_at': asset.updated_at,
        'completed_at': asset.completed_at,
        'aborted_at': asset.aborted_at,
        'deleted_at': asset.deleted_at,
    }


class ArchiveInitiateSerializer(serializers.Serializer):
    movie_id = serializers.IntegerField(min_value=1)
    original_filename = serializers.CharField(max_length=255)
    size_bytes = serializers.IntegerField()
    content_type = serializers.CharField(max_length=100)

    def validate_size_bytes(self, value):
        if value <= 0:
            raise serializers.ValidationError('size_bytes must be greater than zero.')
        max_bytes = archive_max_upload_bytes()
        if value > max_bytes:
            raise serializers.ValidationError(
                f'size_bytes exceeds the maximum of {max_bytes} bytes.',
            )
        return value

    def validate(self, attrs):
        original, safe_filename, extension = sanitize_archive_filename(attrs['original_filename'])
        allowed = tuple(getattr(settings, 'ARCHIVE_ALLOWED_EXTENSIONS', ('mkv', 'mp4')))
        if extension not in allowed:
            raise serializers.ValidationError({
                'original_filename': f'Extension must be one of: {", ".join(allowed)}.',
            })

        content_type = (attrs.get('content_type') or '').strip().lower()
        allowed_types = ALLOWED_CONTENT_TYPES.get(extension, set())
        if content_type not in allowed_types:
            raise serializers.ValidationError({
                'content_type': f'content_type must be one of: {", ".join(sorted(allowed_types))}.',
            })

        if not Movie.objects.filter(pk=attrs['movie_id']).exists():
            raise serializers.ValidationError({'movie_id': 'Movie not found.'})

        part_size, total_parts = calculate_multipart_plan(attrs['size_bytes'])
        attrs['original_filename'] = original
        attrs['safe_filename'] = safe_filename
        attrs['file_extension'] = extension
        attrs['content_type'] = content_type
        attrs['part_size_bytes'] = part_size
        attrs['total_parts'] = total_parts
        return attrs


class ArchivePresignPartsSerializer(serializers.Serializer):
    part_numbers = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=False,
    )
    start_part = serializers.IntegerField(min_value=1, required=False)
    end_part = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        asset: MovieArchiveAsset = self.context['asset']
        part_numbers = attrs.get('part_numbers')
        start_part = attrs.get('start_part')
        end_part = attrs.get('end_part')

        if part_numbers is None:
            if start_part is None or end_part is None:
                raise serializers.ValidationError(
                    'Provide part_numbers or both start_part and end_part.',
                )
            if end_part < start_part:
                raise serializers.ValidationError({'end_part': 'end_part must be >= start_part.'})
            part_numbers = list(range(start_part, end_part + 1))

        batch_limit = archive_url_batch_size()
        if len(part_numbers) > batch_limit:
            raise serializers.ValidationError({
                'part_numbers': f'At most {batch_limit} part URLs may be requested at once.',
            })

        unique = []
        seen = set()
        for number in part_numbers:
            if number in seen:
                continue
            if number > asset.total_parts:
                raise serializers.ValidationError({
                    'part_numbers': f'part_number {number} exceeds total_parts ({asset.total_parts}).',
                })
            seen.add(number)
            unique.append(number)
        attrs['part_numbers'] = unique
        return attrs


class ArchiveCompletePartSerializer(serializers.Serializer):
    part_number = serializers.IntegerField(min_value=1)
    etag = serializers.CharField(max_length=255)

    def validate_etag(self, value):
        value = (value or '').strip().strip('"')
        if not value:
            raise serializers.ValidationError('ETag is required.')
        return value


class ArchiveCompleteSerializer(serializers.Serializer):
    parts = ArchiveCompletePartSerializer(many=True, allow_empty=False)

    def validate_parts(self, parts):
        asset: MovieArchiveAsset = self.context['asset']
        numbers = [part['part_number'] for part in parts]
        if len(numbers) != len(set(numbers)):
            raise serializers.ValidationError('Duplicate part_number values are not allowed.')
        expected = set(range(1, asset.total_parts + 1))
        provided = set(numbers)
        if provided != expected:
            missing = sorted(expected - provided)
            extra = sorted(provided - expected)
            detail = []
            if missing:
                detail.append(f'missing parts: {missing[:20]}')
            if extra:
                detail.append(f'unexpected parts: {extra[:20]}')
            raise serializers.ValidationError('; '.join(detail) or 'Invalid part list.')
        return sorted(parts, key=lambda item: item['part_number'])


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def archive_upload_initiate(request):
    storage, error = _storage_or_error()
    if error:
        return error

    serializer = ArchiveInitiateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    movie = Movie.objects.get(pk=data['movie_id'])

    asset = MovieArchiveAsset(
        movie=movie,
        bucket=storage.bucket,
        original_filename=data['original_filename'],
        safe_filename=data['safe_filename'],
        file_extension=data['file_extension'],
        content_type=data['content_type'],
        size_bytes=data['size_bytes'],
        part_size_bytes=data['part_size_bytes'],
        total_parts=data['total_parts'],
        status=MovieArchiveAsset.Status.PENDING,
        created_by=request.user,
        uploaded_by=request.user,
    )
    asset.object_key = build_object_key(movie.id, asset.id, asset.safe_filename)
    try:
        upload_id = storage.create_multipart_upload(
            asset.object_key,
            asset.content_type,
            metadata={
                'movie-id': str(movie.id),
                'asset-id': str(asset.id),
            },
        )
    except ArchiveStorageError as exc:
        return _storage_failure(exc)

    asset.upload_id = upload_id
    asset.status = MovieArchiveAsset.Status.UPLOADING
    asset.save()

    expires = archive_presign_expires()
    return Response(
        {
            'asset_id': str(asset.id),
            'movie_id': movie.id,
            'object_key': asset.object_key,
            'upload_id': asset.upload_id,
            'content_type': asset.content_type,
            'size_bytes': asset.size_bytes,
            'part_size_bytes': asset.part_size_bytes,
            'total_parts': asset.total_parts,
            'status': asset.status,
            'presigned_url_expires': expires,
            'presign_batch_size': archive_url_batch_size(),
            'upload_concurrency_hint': int(getattr(settings, 'ARCHIVE_UPLOAD_CONCURRENCY', 3)),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def archive_upload_presign_parts(request, asset_id):
    storage, error = _storage_or_error()
    if error:
        return error

    asset = get_object_or_404(MovieArchiveAsset, pk=asset_id)
    if asset.status not in UPLOAD_ACTIVE_STATUSES:
        return Response(
            {'detail': 'Upload is not active for this asset.', 'code': 'upload_not_active'},
            status=status.HTTP_409_CONFLICT,
        )
    if not asset.upload_id:
        return Response(
            {'detail': 'Multipart upload is missing.', 'code': 'upload_id_missing'},
            status=status.HTTP_409_CONFLICT,
        )

    serializer = ArchivePresignPartsSerializer(data=request.data, context={'asset': asset})
    serializer.is_valid(raise_exception=True)
    expires = archive_presign_expires()
    urls = []
    try:
        for part_number in serializer.validated_data['part_numbers']:
            url = storage.generate_presigned_upload_part_url(
                asset.object_key,
                asset.upload_id,
                part_number,
                expires=expires,
            )
            urls.append({'part_number': part_number, 'url': url, 'expires_in': expires})
    except ArchiveStorageError as exc:
        return _storage_failure(exc)

    if asset.status == MovieArchiveAsset.Status.MULTIPART_CREATED:
        asset.status = MovieArchiveAsset.Status.UPLOADING
        asset.save(update_fields=['status', 'updated_at'])

    return Response({'asset_id': str(asset.id), 'parts': urls})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def archive_upload_complete(request, asset_id):
    storage, error = _storage_or_error()
    if error:
        return error

    asset = get_object_or_404(MovieArchiveAsset, pk=asset_id)
    if asset.status == MovieArchiveAsset.Status.AVAILABLE:
        return Response(asset_status_payload(asset))
    if asset.status not in COMPLETABLE_STATUSES:
        return Response(
            {'detail': 'Asset cannot be completed in its current state.', 'code': 'invalid_status'},
            status=status.HTTP_409_CONFLICT,
        )
    if not asset.upload_id:
        return Response(
            {'detail': 'Multipart upload is missing.', 'code': 'upload_id_missing'},
            status=status.HTTP_409_CONFLICT,
        )

    serializer = ArchiveCompleteSerializer(data=request.data, context={'asset': asset})
    serializer.is_valid(raise_exception=True)
    parts = serializer.validated_data['parts']

    asset.status = MovieArchiveAsset.Status.VERIFYING
    asset.failure_reason = ''
    asset.save(update_fields=['status', 'failure_reason', 'updated_at'])

    try:
        storage.complete_multipart_upload(asset.object_key, asset.upload_id, parts)
        head = storage.head_object(asset.object_key)
    except ArchiveStorageError as exc:
        asset.status = MovieArchiveAsset.Status.FAILED
        asset.failure_reason = 'Upload completion or verification failed.'
        asset.save(update_fields=['status', 'failure_reason', 'updated_at'])
        return _storage_failure(exc)

    actual_size = head.get('content_length')
    if actual_size != asset.size_bytes:
        asset.status = MovieArchiveAsset.Status.FAILED
        asset.actual_size_bytes = actual_size
        asset.etag = head.get('etag') or ''
        asset.failure_reason = 'Uploaded object size does not match the expected size.'
        asset.save(update_fields=[
            'status', 'actual_size_bytes', 'etag', 'failure_reason', 'updated_at',
        ])
        return Response(asset_status_payload(asset), status=status.HTTP_409_CONFLICT)

    asset.actual_size_bytes = actual_size
    asset.etag = head.get('etag') or ''
    asset.status = MovieArchiveAsset.Status.AVAILABLE
    asset.completed_at = timezone.now()
    asset.failure_reason = ''
    asset.save(update_fields=[
        'actual_size_bytes', 'etag', 'status', 'completed_at', 'failure_reason', 'updated_at',
    ])
    return Response(asset_status_payload(asset))


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def archive_upload_abort(request, asset_id):
    storage, error = _storage_or_error()
    if error:
        return error

    asset = get_object_or_404(MovieArchiveAsset, pk=asset_id)
    if asset.status in {
        MovieArchiveAsset.Status.ABORTED,
        MovieArchiveAsset.Status.DELETED,
        MovieArchiveAsset.Status.DELETION_PENDING,
    }:
        return Response(asset_status_payload(asset))
    if asset.status == MovieArchiveAsset.Status.AVAILABLE:
        return Response(
            {'detail': 'Completed uploads cannot be aborted; delete instead.', 'code': 'already_available'},
            status=status.HTTP_409_CONFLICT,
        )
    if asset.status not in ABORTABLE_STATUSES | {MovieArchiveAsset.Status.VERIFYING}:
        return Response(
            {'detail': 'Asset cannot be aborted in its current state.', 'code': 'invalid_status'},
            status=status.HTTP_409_CONFLICT,
        )

    if asset.upload_id and asset.status != MovieArchiveAsset.Status.AVAILABLE:
        try:
            storage.abort_multipart_upload(asset.object_key, asset.upload_id)
        except ArchiveStorageError as exc:
            return _storage_failure(exc)

    asset.status = MovieArchiveAsset.Status.ABORTED
    asset.aborted_at = timezone.now()
    asset.failure_reason = asset.failure_reason or 'Upload aborted by staff.'
    asset.save(update_fields=['status', 'aborted_at', 'failure_reason', 'updated_at'])
    return Response(asset_status_payload(asset))


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def archive_asset_status(request, asset_id):
    asset = get_object_or_404(MovieArchiveAsset, pk=asset_id)
    return Response(asset_status_payload(asset))


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def archive_asset_download_url(request, asset_id):
    storage, error = _storage_or_error()
    if error:
        return error

    asset = get_object_or_404(MovieArchiveAsset, pk=asset_id)
    if asset.status != MovieArchiveAsset.Status.AVAILABLE or asset.deleted_at:
        return Response(
            {'detail': 'Download is only available for completed archive assets.', 'code': 'not_available'},
            status=status.HTTP_409_CONFLICT,
        )

    expires = archive_download_expires()
    try:
        url = storage.generate_presigned_download_url(
            asset.object_key,
            asset.safe_filename,
            expires=expires,
        )
    except ArchiveStorageError as exc:
        return _storage_failure(exc)

    return Response({
        'asset_id': str(asset.id),
        'url': url,
        'expires_in': expires,
    })


@api_view(['DELETE', 'POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def archive_asset_delete(request, asset_id):
    storage, error = _storage_or_error()
    if error:
        return error

    asset = get_object_or_404(MovieArchiveAsset, pk=asset_id)
    if asset.status == MovieArchiveAsset.Status.DELETED:
        return Response(asset_status_payload(asset))

    force = str((request.data or {}).get('force', False)).lower() in {'1', 'true', 'yes', 'on'}
    if asset.status not in DELETABLE_STATUSES and not force:
        return Response(
            {
                'detail': 'Only available, failed, or aborted assets can be deleted unless force=true.',
                'code': 'invalid_status',
            },
            status=status.HTTP_409_CONFLICT,
        )

    was_completed = asset.status == MovieArchiveAsset.Status.AVAILABLE or bool(asset.completed_at)
    upload_id = asset.upload_id
    object_key = asset.object_key

    asset.status = MovieArchiveAsset.Status.DELETION_PENDING
    asset.save(update_fields=['status', 'updated_at'])

    try:
        if upload_id and not was_completed:
            try:
                storage.abort_multipart_upload(object_key, upload_id)
            except ArchiveStorageError:
                pass
        storage.delete_object(object_key)
    except ArchiveStorageError as exc:
        asset.status = MovieArchiveAsset.Status.FAILED
        asset.failure_reason = 'Object deletion failed.'
        asset.save(update_fields=['status', 'failure_reason', 'updated_at'])
        return _storage_failure(exc)

    asset.status = MovieArchiveAsset.Status.DELETED
    asset.deleted_at = timezone.now()
    asset.save(update_fields=['status', 'deleted_at', 'updated_at'])
    return Response(asset_status_payload(asset))
