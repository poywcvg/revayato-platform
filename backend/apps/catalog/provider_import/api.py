"""Staff-only provider import admin APIs."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.catalog.admin_api import IsStaffUser, StaffAdminThrottle
from apps.catalog.models import (
    ProviderCredential,
    ProviderImportJob,
    ProviderSource,
)

from .catalog_lookup import (
    approve_match_candidate,
    crawl_myf2m_downloads_for_movie,
    crawl_myf2m_downloads_for_series,
    create_catalog_discover_job,
    ensure_myf2m_provider,
)
from .exceptions import InteractiveVerificationRequired, ProviderCaptchaRequired, ProviderImportError
from .registry import get_connector
from .dornatv_sync import ensure_dornatv_provider
from .serializers import (
    ApproveMatchSerializer,
    CatalogDiscoverRequestSerializer,
    DiscoverImportRequestSerializer,
    ProviderImportItemSerializer,
    ProviderImportJobSerializer,
    ProviderImportLogSerializer,
    ProviderSourceSerializer,
    ProviderSourceWriteSerializer,
)
from .service import (
    append_log,
    create_import_job,
    ensure_avasarami_provider,
    secret_flags_for_provider,
)


def _default_crawl_movie():
    from apps.catalog.provider_import.multi_provider_crawl import crawl_catalog_downloads_for_movie
    return crawl_catalog_downloads_for_movie


def _default_crawl_series():
    from apps.catalog.provider_import.multi_provider_crawl import crawl_catalog_downloads_for_series
    return crawl_catalog_downloads_for_series


def _queue_job(job):
    from apps.catalog.provider_import import tasks as provider_tasks

    async_result = provider_tasks.run_provider_import_job_task.delay(str(job.id))
    ProviderImportJob.objects.filter(pk=job.pk).update(task_id=async_result.id)
    job.task_id = async_result.id
    return job


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def provider_source_list_create(request):
    ensure_avasarami_provider()
    ensure_myf2m_provider()
    ensure_dornatv_provider()
    if request.method == 'GET':
        qs = ProviderSource.objects.select_related('credential').order_by('name')
        return Response({'results': ProviderSourceSerializer(qs, many=True).data})

    serializer = ProviderSourceWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    # Only allow creating non-avasarami custom sources via API; Avasarami is seeded.
    slug = (request.data.get('slug') or serializer.validated_data.get('name', '')).strip().lower()
    slug = slug.replace(' ', '-')[:120] or 'provider'
    if ProviderSource.objects.filter(slug=slug).exists():
        return Response({'detail': 'Provider slug already exists.'}, status=status.HTTP_400_BAD_REQUEST)
    provider = serializer.save(slug=slug)
    ProviderCredential.objects.get_or_create(
        provider=provider,
        defaults={'secret_mode': ProviderCredential.SecretMode.ENV, 'env_prefix': slug.upper()},
    )
    return Response(
        ProviderSourceSerializer(provider).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def provider_source_detail(request, provider_id):
    provider = get_object_or_404(
        ProviderSource.objects.select_related('credential'), pk=provider_id,
    )
    if request.method == 'GET':
        return Response(ProviderSourceSerializer(provider).data)

    serializer = ProviderSourceWriteSerializer(provider, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    provider.refresh_from_db()
    return Response(ProviderSourceSerializer(provider).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def provider_source_validate(request, provider_id):
    provider = get_object_or_404(
        ProviderSource.objects.select_related('credential'), pk=provider_id,
    )
    try:
        connector = get_connector(provider)
        result = connector.validate_credentials()
    except ProviderImportError as exc:
        return Response(
            {
                'ok': False,
                'message': str(exc),
                'requires_interactive_verification': isinstance(exc, ProviderCaptchaRequired),
                'auth_type': provider.auth_type,
                'secrets': secret_flags_for_provider(provider),
                'code': getattr(exc, 'code', 'provider_import_error'),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    cred, _ = ProviderCredential.objects.get_or_create(provider=provider)
    if result.requires_interactive_verification:
        cred.status = ProviderCredential.Status.NEEDS_INTERACTIVE
    elif result.ok:
        cred.status = ProviderCredential.Status.VALID
    else:
        cred.status = ProviderCredential.Status.INVALID
    cred.last_validated_at = timezone.now()
    cred.last_validation_message = result.message[:500]
    cred.save(update_fields=[
        'status', 'last_validated_at', 'last_validation_message', 'updated_at',
    ])

    payload = {
        **result.to_dict(),
        'secrets': secret_flags_for_provider(provider),
        'credential_status': cred.status,
    }
    http_status = status.HTTP_200_OK if result.ok else status.HTTP_400_BAD_REQUEST
    return Response(payload, status=http_status)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def provider_source_discover(request, provider_id):
    return _start_job(request, provider_id, default_mode=ProviderImportJob.Mode.DISCOVER_ONLY)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def provider_source_import(request, provider_id):
    return _start_job(request, provider_id, default_mode=ProviderImportJob.Mode.IMPORT_MISSING_FILES)


def _start_job(request, provider_id, *, default_mode):
    provider = get_object_or_404(ProviderSource, pk=provider_id, is_active=True)
    data = {**request.data}
    data.setdefault('mode', default_mode)
    serializer = DiscoverImportRequestSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    params = {
        'limit': serializer.validated_data['limit'],
        'dry_run': serializer.validated_data['dry_run'],
        'overwrite': serializer.validated_data['overwrite'],
        'quality_preference': serializer.validated_data.get('quality_preference') or [],
    }
    active = ProviderImportJob.objects.filter(
        provider=provider,
        status__in=[
            ProviderImportJob.Status.QUEUED,
            ProviderImportJob.Status.RUNNING,
            ProviderImportJob.Status.CANCEL_REQUESTED,
        ],
    ).exists()
    if active:
        return Response(
            {'detail': 'An active import job already exists for this provider.', 'code': 'job_active'},
            status=status.HTTP_409_CONFLICT,
        )

    job = create_import_job(
        provider=provider,
        user=request.user,
        content_type=serializer.validated_data['content_type'],
        mode=serializer.validated_data['mode'],
        params=params,
    )
    append_log(job, 'info', 'Job queued by staff.')
    try:
        _queue_job(job)
    except Exception:
        job.status = ProviderImportJob.Status.FAILED
        job.error_message = 'Could not queue Celery task.'
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])
        return Response(
            {'detail': job.error_message, 'code': 'queue_failed'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    job.refresh_from_db()
    return Response(ProviderImportJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def provider_import_job_list(request):
    qs = ProviderImportJob.objects.select_related('provider').order_by('-created_at')[:50]
    return Response({'results': ProviderImportJobSerializer(qs, many=True).data})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def provider_import_job_detail(request, job_id):
    job = get_object_or_404(ProviderImportJob.objects.select_related('provider'), pk=job_id)
    return Response(ProviderImportJobSerializer(job).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def provider_import_job_cancel(request, job_id):
    job = get_object_or_404(ProviderImportJob, pk=job_id)
    if not job.is_active:
        return Response(
            {'detail': 'Job is not active.', 'code': 'job_not_active'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    job.cancel_requested = True
    job.status = ProviderImportJob.Status.CANCEL_REQUESTED
    job.save(update_fields=['cancel_requested', 'status', 'updated_at'])
    append_log(job, 'warning', 'Cancel requested by staff.')
    return Response(ProviderImportJobSerializer(job).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def provider_import_job_items(request, job_id):
    job = get_object_or_404(ProviderImportJob, pk=job_id)
    items = job.items.order_by('id')[:500]
    return Response({'results': ProviderImportItemSerializer(items, many=True).data})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def provider_import_job_logs(request, job_id):
    job = get_object_or_404(ProviderImportJob, pk=job_id)
    logs = job.logs.order_by('-created_at')[:200]
    return Response({'results': ProviderImportLogSerializer(logs, many=True).data})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def movie_provider_discover(request, movie_id):
    from apps.catalog.models import Movie

    get_object_or_404(Movie, pk=movie_id)
    serializer = CatalogDiscoverRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    job = create_catalog_discover_job(
        content_type='movie',
        object_id=movie_id,
        user=request.user,
        force=serializer.validated_data['force'],
        trigger=ProviderImportJob.Trigger.MANUAL,
        mode=serializer.validated_data['mode'],
    )
    append_log(job, 'info', 'Catalog movie discover queued by staff.')
    try:
        _queue_job(job)
    except Exception:
        job.status = ProviderImportJob.Status.FAILED
        job.error_message = 'Could not queue Celery task.'
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])
        return Response(
            {'detail': job.error_message, 'code': 'queue_failed'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    job.refresh_from_db()
    return Response(ProviderImportJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def series_provider_discover(request, series_id):
    from apps.catalog.models import Series

    get_object_or_404(Series, pk=series_id)
    serializer = CatalogDiscoverRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    job = create_catalog_discover_job(
        content_type='series',
        object_id=series_id,
        user=request.user,
        force=serializer.validated_data['force'],
        trigger=ProviderImportJob.Trigger.MANUAL,
        mode=serializer.validated_data['mode'],
    )
    append_log(job, 'info', 'Catalog series discover queued by staff.')
    try:
        _queue_job(job)
    except Exception:
        job.status = ProviderImportJob.Status.FAILED
        job.error_message = 'Could not queue Celery task.'
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])
        return Response(
            {'detail': job.error_message, 'code': 'queue_failed'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    job.refresh_from_db()
    return Response(ProviderImportJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def provider_import_job_approve_match(request, job_id):
    job = get_object_or_404(ProviderImportJob, pk=job_id)
    serializer = ApproveMatchSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    item = approve_match_candidate(
        job=job,
        candidate_id=serializer.validated_data['candidate_id'],
        user=request.user,
    )
    return Response(ProviderImportItemSerializer(item).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def movie_provider_crawl_downloads(request, movie_id):
    """Crawl provider movie page download box and store links on the movie."""
    from apps.catalog.models import Movie
    from apps.catalog.serializers import AdminMovieSerializer

    movie = get_object_or_404(Movie, pk=movie_id)
    page_url = str(request.data.get('page_url') or request.data.get('url') or '').strip()
    provider_item_id = str(request.data.get('provider_item_id') or '').strip()
    replace = str(request.data.get('replace', 'true')).lower() not in {'0', 'false', 'no'}
    try:
        result = _default_crawl_movie()(
            movie=movie,
            page_url=page_url,
            provider_item_id=provider_item_id,
            replace=replace,
            user=request.user,
        )
    except (InteractiveVerificationRequired, ProviderCaptchaRequired) as exc:
        return Response(
            {
                'detail': str(exc),
                'code': getattr(exc, 'code', 'interactive_verification_required'),
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    except ProviderImportError as exc:
        return Response(
            {
                'detail': str(exc),
                'code': getattr(exc, 'code', 'provider_import_error'),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    movie.refresh_from_db()
    return Response({
        **result,
        'movie': AdminMovieSerializer(movie, context={'request': request}).data,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def series_provider_crawl_downloads(request, series_id):
    """Crawl provider series page download box and store links on the series."""
    from apps.catalog.models import Series
    from apps.catalog.serializers import AdminSeriesSerializer

    series = get_object_or_404(Series, pk=series_id)
    page_url = str(request.data.get('page_url') or request.data.get('url') or '').strip()
    provider_item_id = str(request.data.get('provider_item_id') or '').strip()
    replace = str(request.data.get('replace', 'true')).lower() not in {'0', 'false', 'no'}
    try:
        result = _default_crawl_series()(
            series=series,
            page_url=page_url,
            provider_item_id=provider_item_id,
            replace=replace,
            user=request.user,
        )
    except (InteractiveVerificationRequired, ProviderCaptchaRequired) as exc:
        return Response(
            {
                'detail': str(exc),
                'code': getattr(exc, 'code', 'interactive_verification_required'),
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    except ProviderImportError as exc:
        return Response(
            {
                'detail': str(exc),
                'code': getattr(exc, 'code', 'provider_import_error'),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    series.refresh_from_db()
    return Response({
        **result,
        'series': AdminSeriesSerializer(series, context={'request': request}).data,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def provider_import_job_import_selected(request, job_id):
    """File transfer remains disabled; use crawl-downloads for Film2Media links."""
    get_object_or_404(ProviderImportJob, pk=job_id)
    return Response(
        {
            'detail': (
                'Media file transfer is not enabled. '
                'Use POST /api/admin/catalog/movies/{id}/provider-crawl-downloads/ '
                'or POST /api/admin/catalog/series/{id}/provider-crawl-downloads/ '
                'to pull Film2Media page download links into the catalog title.'
            ),
            'code': 'provider_file_transfer_disabled',
        },
        status=status.HTTP_501_NOT_IMPLEMENTED,
    )


# Alias for candidates listing (same payload as items).
provider_import_job_candidates = provider_import_job_items
