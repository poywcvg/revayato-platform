"""Staff-only TMDB search / preview / import / sync endpoints."""

import re
import unicodedata

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from .bulk_sync import (
    ActiveCatalogSyncError, catalog_sync_payload, fail_catalog_sync,
    request_catalog_sync_cancel, start_catalog_sync,
)
from .ingestion import load_media_manifest, localize_tmdb_genres, upsert_tmdb_movie, upsert_tmdb_series
from .imdb import enrich_imdb_rating
from .importer_config import get_importer_settings
from .models import CatalogImporterSettings, CatalogSyncRun, Movie, MovieSyncAudit, Series
from .serializers import AdminMovieSerializer, AdminSeriesSerializer, CatalogImporterSettingsSerializer
from .tmdb import TMDBError, configured_tmdb_client


class IsStaffUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class StaffAdminThrottle(UserRateThrottle):
    rate = '120/minute'


class TMDBAdminThrottle(UserRateThrottle):
    rate = '30/minute'


def _add_imdb_rating_to_preview(preview):
    importer = get_importer_settings()
    payload = {
        'vote_average': preview.get('vote_average'),
        'vote_count': preview.get('vote_count'),
        'imdb_rating': preview.get('imdb_rating'),
    }
    enrich_imdb_rating(payload, enabled=bool(importer.fetch_imdb_ratings))
    preview['imdb_rating'] = payload.get('imdb_rating')
    preview['imdb_votes'] = payload.get('imdb_votes')
    preview['imdb_rating_source'] = payload.get('imdb_rating_source')
    return preview


def _client_or_error():
    try:
        return configured_tmdb_client(), None
    except ImproperlyConfigured as exc:
        return None, Response(
            {'detail': str(exc), 'code': 'tmdb_not_configured'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def _bool_flag(value, default=False):
    if value is None:
        return default
    return str(value).lower() in {'1', 'true', 'yes', 'on'}


def _bounded_int(value, default, minimum, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(maximum, max(minimum, parsed))


def _normalize_title(value):
    value = unicodedata.normalize('NFKC', str(value or '')).casefold().replace('\u200c', ' ')
    return re.sub(r'[\W_]+', '', value, flags=re.UNICODE)


def _safe_language(value):
    value = (value or '').strip()
    if not value:
        return None
    if not re.fullmatch(r'[a-z]{2,3}(?:-[A-Z]{2})?', value):
        raise ValueError('Invalid TMDB language code.')
    return value


def _media_manifest_or_error():
    try:
        return load_media_manifest(getattr(settings, 'CATALOG_MEDIA_MANIFEST', '')), None
    except (OSError, ValueError, ValidationError):
        return None, Response(
            {'detail': 'The configured media manifest could not be loaded.', 'code': 'media_manifest_invalid'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def _duplicates(details, *, exclude_pk=None):
    queryset = Movie.objects.all()
    if exclude_pk:
        queryset = queryset.exclude(pk=exclude_pk)
    tmdb_id = details.get('id') or details.get('tmdb_id')
    imdb_id = ((details.get('external_ids') or {}).get('imdb_id') or details.get('imdb_id') or '').strip()
    release_year = str(details.get('release_date') or '')[:4]
    title = (details.get('title') or details.get('original_title') or '').strip()
    slug_base = slugify(title, allow_unicode=True) if title else ''
    query = Q()
    if tmdb_id:
        query |= Q(tmdb_id=tmdb_id)
    if imdb_id:
        query |= Q(imdb_id=imdb_id)
    if title and release_year.isdigit():
        query |= Q(title__iexact=title, release_year=int(release_year))
        query |= Q(release_year=int(release_year))
    if slug_base:
        query |= Q(slug=slug_base)
        if tmdb_id:
            query |= Q(slug=f'{slug_base}-{tmdb_id}')
    if not query.children:
        return []

    normalized_title = _normalize_title(title)
    candidates = {}
    for movie in queryset.filter(query).only(
        'id', 'title', 'slug', 'tmdb_id', 'imdb_id', 'release_year', 'publication_status',
    )[:250]:
        identifier_match = bool(
            (tmdb_id and movie.tmdb_id == int(tmdb_id))
            or (imdb_id and movie.imdb_id == imdb_id)
            or (slug_base and movie.slug in {slug_base, f'{slug_base}-{tmdb_id}'})
        )
        title_year_match = bool(
            normalized_title
            and release_year.isdigit()
            and movie.release_year == int(release_year)
            and _normalize_title(movie.title) == normalized_title
        )
        if identifier_match or title_year_match:
            candidates[movie.pk] = movie
    return [
        {
            'id': movie.id, 'title': movie.title, 'slug': movie.slug,
            'tmdb_id': movie.tmdb_id, 'imdb_id': movie.imdb_id,
            'release_year': movie.release_year, 'publication_status': movie.publication_status,
        }
        for movie in list(candidates.values())[:10]
    ]


def _audit(request, action, *, movie=None, tmdb_id=None, overwrite=False, dry_run=False, changed=None, skipped=None, details=None):
    return MovieSyncAudit.objects.create(
        movie=movie,
        actor=request.user,
        action=action,
        tmdb_id=tmdb_id,
        overwrite=overwrite,
        dry_run=dry_run,
        changed_fields=changed or [],
        skipped_fields=skipped or [],
        details=details or {},
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([TMDBAdminThrottle])
def tmdb_search(request):
    client, error = _client_or_error()
    if error:
        return error
    query = (request.GET.get('query') or request.GET.get('q') or '').strip()
    page = request.GET.get('page', 1)
    try:
        language = _safe_language(request.GET.get('language'))
        payload = client.search_movies(query, page=page, language=language)
    except (TypeError, ValueError):
        return Response({'detail': 'Page or language is invalid.', 'retryable': False}, status=status.HTTP_400_BAD_REQUEST)
    except TMDBError as exc:
        return Response(
            {'detail': str(exc), 'retryable': exc.retryable},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    results = []
    tmdb_ids = [item.get('id') for item in payload.get('results') or [] if item.get('id')]
    existing = {
        movie.tmdb_id: {'id': movie.id, 'slug': movie.slug, 'title': movie.title}
        for movie in Movie.objects.filter(tmdb_id__in=tmdb_ids).only('id', 'slug', 'title', 'tmdb_id')
    }
    for item in payload.get('results') or []:
        tmdb_id = item.get('id')
        results.append({
            'tmdb_id': tmdb_id,
            'title': item.get('title') or item.get('original_title'),
            'original_title': item.get('original_title'),
            'overview': item.get('overview') or '',
            'release_date': item.get('release_date') or '',
            'original_language': item.get('original_language') or '',
            'vote_average': item.get('vote_average'),
            'popularity': item.get('popularity'),
            'poster_path': item.get('poster_path'),
            'poster_url': client.image_url(item.get('poster_path'), 'w185'),
            'backdrop_url': client.image_url(item.get('backdrop_path'), 'w780'),
            'already_imported': tmdb_id in existing,
            'local_movie': existing.get(tmdb_id),
        })
    return Response({
        'query': query,
        'page': payload.get('page', 1),
        'total_pages': payload.get('total_pages', 0),
        'total_results': payload.get('total_results', 0),
        'proxy': client.uses_proxy,
        'results': results,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([TMDBAdminThrottle])
def tmdb_movie_preview(request, tmdb_id):
    client, error = _client_or_error()
    if error:
        return error
    try:
        preview = client.preview_movie(tmdb_id)
    except TMDBError as exc:
        return Response(
            {'detail': str(exc), 'retryable': exc.retryable},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    _add_imdb_rating_to_preview(preview)
    preview['genres'] = localize_tmdb_genres(preview.get('genres') or [])
    local = Movie.objects.filter(tmdb_id=preview['tmdb_id']).only('id', 'slug', 'title', 'is_published').first()
    preview['already_imported'] = bool(local)
    preview['local_movie'] = (
        {'id': local.id, 'slug': local.slug, 'title': local.title, 'is_published': local.is_published}
        if local else None
    )
    preview['proxy'] = client.uses_proxy
    preview['duplicates'] = _duplicates({'id': preview['tmdb_id'], **preview})
    return Response(preview)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([TMDBAdminThrottle])
def tmdb_series_preview(request, tmdb_id):
    client, error = _client_or_error()
    if error:
        return error
    try:
        preview = client.preview_tv(tmdb_id)
    except TMDBError as exc:
        return Response(
            {'detail': str(exc), 'retryable': exc.retryable},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    _add_imdb_rating_to_preview(preview)
    preview['genres'] = localize_tmdb_genres(preview.get('genres') or [])
    local = Series.objects.filter(tmdb_id=preview['tmdb_id']).only(
        'id', 'slug', 'title', 'is_published',
    ).first()
    local_item = (
        {'id': local.id, 'slug': local.slug, 'title': local.title, 'is_published': local.is_published}
        if local else None
    )
    preview['already_imported'] = bool(local)
    preview['local_item'] = local_item
    preview['local_movie'] = local_item
    preview['proxy'] = client.uses_proxy
    preview['duplicates'] = []
    return Response(preview)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([TMDBAdminThrottle])
def tmdb_movie_import(request, tmdb_id):
    client, error = _client_or_error()
    if error:
        return error
    overwrite_manual = _bool_flag(request.data.get('overwrite_manual', request.data.get('overwrite')), False)
    dry_run = _bool_flag(request.data.get('dry_run'), False)
    publish = _bool_flag(request.data.get('publish'), False)
    try:
        details = client.movie_details(tmdb_id)
    except TMDBError as exc:
        return Response(
            {'detail': str(exc), 'retryable': exc.retryable},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    from django.conf import settings as dj_settings
    from apps.catalog.iranian import is_iranian_tmdb_details
    if getattr(dj_settings, 'CATALOG_EXCLUDE_IRANIAN', True) and is_iranian_tmdb_details(details):
        return Response(
            {
                'code': 'iranian_excluded',
                'detail': 'فیلم‌های ایرانی در کاتالوگ نگهداری نمی‌شوند (خزنده فقط هالیوود از myf2m).',
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    duplicates = _duplicates(details)
    exact = next((item for item in duplicates if item['tmdb_id'] == int(tmdb_id)), None)
    link_movie_id = request.data.get('link_movie_id')
    if link_movie_id not in (None, ''):
        try:
            link_movie_id = int(link_movie_id)
        except (TypeError, ValueError):
            return Response(
                {'code': 'invalid_link_movie', 'detail': 'link_movie_id must be a positive integer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if link_movie_id <= 0:
            return Response(
                {'code': 'invalid_link_movie', 'detail': 'link_movie_id must be a positive integer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
    else:
        link_movie_id = None
    if exact and link_movie_id and link_movie_id != exact['id']:
        return Response(
            {'code': 'tmdb_id_conflict', 'detail': 'This TMDb ID is already linked to another movie.', 'duplicates': duplicates},
            status=status.HTTP_409_CONFLICT,
        )
    if duplicates and not exact and not dry_run and not link_movie_id:
        return Response(
            {'code': 'duplicate_candidate', 'detail': 'Possible duplicate found. Confirm linking before import.', 'duplicates': duplicates},
            status=status.HTTP_409_CONFLICT,
        )
    manifest, manifest_error = _media_manifest_or_error()
    if manifest_error:
        return manifest_error
    try:
        with transaction.atomic():
            if link_movie_id and not dry_run:
                linked = get_object_or_404(Movie.objects.select_for_update(), pk=link_movie_id)
                if linked.tmdb_id and linked.tmdb_id != int(tmdb_id):
                    return Response(
                        {'code': 'tmdb_id_conflict', 'detail': 'Selected movie is linked to another TMDb ID.'},
                        status=status.HTTP_409_CONFLICT,
                    )
                linked.tmdb_id = int(tmdb_id)
                linked.save(update_fields=['tmdb_id', 'updated_at'])
            movie, created, published, skipped = upsert_tmdb_movie(
                details,
                media_entry=manifest.get(str(int(tmdb_id))),
                auto_publish=False,
                overwrite_manual=overwrite_manual,
                dry_run=dry_run,
            )
    except IntegrityError:
        return Response(
            {'detail': 'The movie conflicts with an existing unique identifier.', 'code': 'duplicate_conflict'},
            status=status.HTTP_409_CONFLICT,
        )
    except ValidationError as exc:
        return Response(
            {'detail': 'TMDB metadata did not pass catalog validation.', 'code': 'tmdb_validation_error', 'errors': getattr(exc, 'message_dict', None) or exc.messages},
            status=status.HTTP_400_BAD_REQUEST,
        )
    payload = {
        'dry_run': dry_run,
        'created': created,
        'published': published,
        'skipped_manual_fields': skipped,
        'overwrite_manual': overwrite_manual,
        'tmdb_id': int(tmdb_id),
        'duplicates': duplicates,
    }
    if dry_run:
        payload['preview'] = {
            'title': movie.title,
            'slug': movie.slug,
            'overview': movie.description[:300],
            'release_date': movie.release_date.isoformat() if movie.release_date else None,
            'runtime': movie.duration_minutes,
        }
        _audit(request, MovieSyncAudit.Action.IMPORT, movie=movie if movie.pk else None, tmdb_id=tmdb_id, overwrite=overwrite_manual, dry_run=True, changed=getattr(movie, '_tmdb_changed_fields', []), skipped=skipped)
        return Response(payload)
    if publish and movie.ready_for_auto_publish:
        movie.publication_status = Movie.PublicationStatus.PUBLISHED
        movie.is_published = True
        movie.save(update_fields=['publication_status', 'is_published', 'updated_at'])
        payload['published'] = True
        if not (movie.download_links or []):
            from apps.catalog.provider_import.signals import enqueue_provider_movie_auto_crawl
            enqueue_provider_movie_auto_crawl(movie.pk, replace=True, reason='tmdb_import_publish')
    elif publish:
        payload['publication_blockers'] = movie.auto_publish_blockers
    _audit(request, MovieSyncAudit.Action.IMPORT, movie=movie, tmdb_id=tmdb_id, overwrite=overwrite_manual, changed=getattr(movie, '_tmdb_changed_fields', []), skipped=skipped)
    payload['movie'] = AdminMovieSerializer(movie, context={'request': request}).data
    return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([TMDBAdminThrottle])
def tmdb_series_import(request, tmdb_id):
    client, error = _client_or_error()
    if error:
        return error
    dry_run = _bool_flag(request.data.get('dry_run'), False)
    publish = _bool_flag(request.data.get('publish'), False)
    try:
        details = client.tv_details(tmdb_id)
        from django.conf import settings as dj_settings
        from apps.catalog.iranian import is_iranian_tmdb_details
        if getattr(dj_settings, 'CATALOG_EXCLUDE_IRANIAN', True) and is_iranian_tmdb_details(details):
            return Response(
                {
                    'code': 'iranian_excluded',
                    'detail': 'سریال‌های ایرانی در کاتالوگ نگهداری نمی‌شوند (خزنده فقط هالیوود از myf2m).',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        series, created = upsert_tmdb_series(details, dry_run=dry_run)
    except TMDBError as exc:
        return Response(
            {'detail': str(exc), 'retryable': exc.retryable},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except IntegrityError:
        return Response(
            {'detail': 'The series conflicts with an existing unique identifier.', 'code': 'duplicate_conflict'},
            status=status.HTTP_409_CONFLICT,
        )
    except ValidationError as exc:
        return Response(
            {
                'detail': 'TMDB metadata did not pass catalog validation.',
                'code': 'tmdb_validation_error',
                'errors': getattr(exc, 'message_dict', None) or exc.messages,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    payload = {
        'content_type': 'series',
        'dry_run': dry_run,
        'created': created,
        'published': False,
        'skipped_manual_fields': [],
        'tmdb_id': int(tmdb_id),
    }
    if dry_run:
        payload['preview'] = {
            'title': series.title,
            'slug': series.slug,
            'overview': series.description[:300],
            'release_date': (details.get('first_air_date') or None),
            'runtime': next(iter(details.get('episode_run_time') or []), None),
        }
        return Response(payload)
    if publish and not dry_run:
        series.is_published = True
        series.save(update_fields=['is_published', 'updated_at'])
        payload['published'] = True
        if not (getattr(series, 'download_links', None) or []):
            from apps.catalog.provider_import.signals import enqueue_provider_series_auto_crawl
            enqueue_provider_series_auto_crawl(series.pk, replace=True, reason='tmdb_series_import_publish')
    payload['series'] = {
        'id': series.id,
        'title': series.title,
        'slug': series.slug,
        'tmdb_id': series.tmdb_id,
        'is_published': series.is_published,
        'poster_url': series.poster_external_url or None,
        'season_count': (
            series.seasons.filter(is_published=True, episodes__is_published=True)
            .exclude(episodes__video_url='')
            .distinct()
            .count()
            or int((series.source_metadata or {}).get('number_of_seasons') or 0)
        ),
    }
    return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([TMDBAdminThrottle])
def movie_sync_tmdb(request, movie_id):
    client, error = _client_or_error()
    if error:
        return error
    movie = get_object_or_404(Movie, pk=movie_id)
    if not movie.tmdb_id:
        return Response(
            {'detail': 'Movie has no tmdb_id.', 'code': 'missing_tmdb_id'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    overwrite_manual = _bool_flag(request.data.get('overwrite_manual', request.data.get('overwrite')), False)
    dry_run = _bool_flag(request.data.get('dry_run'), False)
    try:
        details = client.movie_details(movie.tmdb_id)
    except TMDBError as exc:
        return Response(
            {'detail': str(exc), 'retryable': exc.retryable},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    manifest, manifest_error = _media_manifest_or_error()
    if manifest_error:
        return manifest_error
    try:
        synced, created, published, skipped = upsert_tmdb_movie(
            details,
            media_entry=manifest.get(str(movie.tmdb_id)),
            auto_publish=False,
            overwrite_manual=overwrite_manual,
            dry_run=dry_run,
        )
    except ValidationError as exc:
        return Response(
            {'detail': 'TMDB metadata did not pass catalog validation.', 'code': 'tmdb_validation_error', 'errors': getattr(exc, 'message_dict', None) or exc.messages},
            status=status.HTTP_400_BAD_REQUEST,
        )
    payload = {
        'dry_run': dry_run,
        'created': created,
        'published': published,
        'skipped_manual_fields': skipped,
        'overwrite_manual': overwrite_manual,
        'tmdb_id': movie.tmdb_id,
        'metadata_gaps': getattr(synced, '_metadata_gaps', None) or synced.metadata_structure_gaps,
    }
    if dry_run:
        payload['preview'] = {
            'title': synced.title,
            'slug': synced.slug,
            'overview': synced.description[:300],
        }
        _audit(request, MovieSyncAudit.Action.SYNC, movie=movie, tmdb_id=movie.tmdb_id, overwrite=overwrite_manual, dry_run=True, changed=getattr(synced, '_tmdb_changed_fields', []), skipped=skipped)
        return Response(payload)
    _audit(request, MovieSyncAudit.Action.SYNC, movie=synced, tmdb_id=movie.tmdb_id, overwrite=overwrite_manual, changed=getattr(synced, '_tmdb_changed_fields', []), skipped=skipped)
    payload['movie'] = AdminMovieSerializer(synced, context={'request': request}).data
    return Response(payload)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([TMDBAdminThrottle])
def series_sync_tmdb(request, series_id):
    """Sync a series with TMDB metadata (staff only).

    Mirrors ``movie_sync_tmdb`` for series. dry-run returns a preview without
    touching the database; a real run refreshes metadata and credits.
    """
    client, error = _client_or_error()
    if error:
        return error
    series = get_object_or_404(Series, pk=series_id)
    if not series.tmdb_id:
        return Response(
            {'detail': 'Series has no tmdb_id.', 'code': 'missing_tmdb_id'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    dry_run = _bool_flag(request.data.get('dry_run'), False)
    try:
        details = client.tv_details(series.tmdb_id)
    except TMDBError as exc:
        return Response(
            {'detail': str(exc), 'retryable': exc.retryable},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    try:
        synced, created = upsert_tmdb_series(details, dry_run=dry_run)
    except ValidationError as exc:
        return Response(
            {'detail': 'TMDB metadata did not pass catalog validation.', 'code': 'tmdb_validation_error', 'errors': getattr(exc, 'message_dict', None) or exc.messages},
            status=status.HTTP_400_BAD_REQUEST,
        )
    payload = {
        'dry_run': dry_run,
        'created': created,
        'tmdb_id': series.tmdb_id,
        'metadata_gaps': getattr(synced, '_metadata_gaps', None) or synced.metadata_structure_gaps,
    }
    if dry_run:
        payload['preview'] = {
            'title': synced.title,
            'slug': synced.slug,
            'overview': synced.description[:300],
        }
        return Response(payload)
    _audit(request, MovieSyncAudit.Action.SYNC, tmdb_id=series.tmdb_id, overwrite=False, changed=getattr(synced, '_tmdb_changed_fields', []))
    payload['series'] = AdminSeriesSerializer(synced, context={'request': request}).data
    return Response(payload)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def admin_movie_list_create(request):
    if request.method == 'POST':
        serializer = AdminMovieSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        movie = serializer.save()
        _audit(request, MovieSyncAudit.Action.MANUAL_CREATE, movie=movie, tmdb_id=movie.tmdb_id, changed=getattr(movie, '_manual_changed_fields', []))
        return Response(AdminMovieSerializer(movie, context={'request': request}).data, status=status.HTTP_201_CREATED)

    queryset = Movie.objects.prefetch_related('genres', 'countries').order_by('-updated_at')
    query = (request.query_params.get('q') or '').strip()
    publication = (request.query_params.get('status') or '').strip()
    catalog_type = (request.query_params.get('type') or '').strip()
    source = (request.query_params.get('source') or '').strip()
    genre = (request.query_params.get('genre') or '').strip()
    year = (request.query_params.get('year') or '').strip()
    ordering = request.query_params.get('ordering') or '-updated_at'
    allowed_ordering = {
        'title', '-title', 'release_date', '-release_date', 'release_year', '-release_year',
        'created_at', '-created_at', 'updated_at', '-updated_at',
        'imdb_rating', '-imdb_rating', 'rating_average', '-rating_average', 'popularity', '-popularity',
    }
    if query:
        search_query = Q(title__icontains=query) | Q(original_title__icontains=query) | Q(imdb_id__icontains=query)
        if query.isdigit():
            search_query |= Q(tmdb_id=int(query))
        queryset = queryset.filter(search_query)
    if publication in Movie.PublicationStatus.values:
        queryset = queryset.filter(publication_status=publication)
    if catalog_type in Movie.CatalogType.values:
        queryset = queryset.filter(catalog_type=catalog_type)
    if source in {'manual', 'tmdb'}:
        queryset = queryset.filter(metadata_source=source)
    if genre:
        queryset = queryset.filter(genres__slug=genre)
    if year.isdigit() and 1888 <= int(year) <= 2100:
        queryset = queryset.filter(release_year=int(year))
    queryset = queryset.order_by(ordering if ordering in allowed_ordering else '-updated_at').distinct()
    paginator = LimitOffsetPagination()
    paginator.default_limit = 20
    paginator.max_limit = 100
    page = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response(AdminMovieSerializer(page, many=True, context={'request': request}).data)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def admin_movie_detail(request, movie_id):
    movie = get_object_or_404(
        Movie.objects.prefetch_related(
            'genres',
            'countries',
            'directors',
            'movie_actors__actor',
        ),
        pk=movie_id,
    )
    if request.method == 'GET':
        return Response(AdminMovieSerializer(movie, context={'request': request}).data)
    if request.method == 'DELETE':
        movie.publication_status = Movie.PublicationStatus.ARCHIVED
        movie.is_published = False
        movie.save(update_fields=['publication_status', 'is_published', 'updated_at'])
        _audit(request, MovieSyncAudit.Action.ARCHIVE, movie=movie, tmdb_id=movie.tmdb_id)
        return Response({'id': movie.id, 'publication_status': movie.publication_status, 'archived': True})

    serializer = AdminMovieSerializer(movie, data=request.data, partial=True, context={'request': request})
    serializer.is_valid(raise_exception=True)
    movie = serializer.save()
    changed_fields = getattr(movie, '_manual_changed_fields', [])
    _audit(request, MovieSyncAudit.Action.MANUAL_UPDATE, movie=movie, tmdb_id=movie.tmdb_id, changed=changed_fields, details={'fields': changed_fields})
    return Response(AdminMovieSerializer(movie, context={'request': request}).data)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def admin_series_list_create(request):
    if request.method == 'POST':
        serializer = AdminSeriesSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        series = serializer.save()
        return Response(AdminSeriesSerializer(series, context={'request': request}).data, status=status.HTTP_201_CREATED)

    queryset = Series.objects.prefetch_related('genres', 'countries', 'directors', 'series_actors__actor').order_by('-updated_at')
    query = (request.query_params.get('q') or '').strip()
    published = (request.query_params.get('status') or '').strip()
    source = (request.query_params.get('source') or '').strip()
    genre = (request.query_params.get('genre') or '').strip()
    year = (request.query_params.get('year') or '').strip()
    ordering = request.query_params.get('ordering') or '-updated_at'
    allowed_ordering = {
        'title', '-title', 'start_year', '-start_year',
        'created_at', '-created_at', 'updated_at', '-updated_at',
        'imdb_rating', '-imdb_rating', 'rating_average', '-rating_average', 'popularity', '-popularity',
    }
    if query:
        search_query = Q(title__icontains=query) | Q(original_title__icontains=query) | Q(imdb_id__icontains=query)
        if query.isdigit():
            search_query |= Q(tmdb_id=int(query))
        queryset = queryset.filter(search_query)
    if published == 'published':
        queryset = queryset.filter(is_published=True)
    elif published == 'draft':
        queryset = queryset.filter(is_published=False)
    if source in {'manual', 'tmdb'}:
        queryset = queryset.filter(metadata_source=source)
    if genre:
        queryset = queryset.filter(genres__slug=genre)
    if year.isdigit() and 1888 <= int(year) <= 2100:
        queryset = queryset.filter(start_year=int(year))
    queryset = queryset.order_by(ordering if ordering in allowed_ordering else '-updated_at').distinct()
    paginator = LimitOffsetPagination()
    paginator.default_limit = 20
    paginator.max_limit = 100
    page = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response(AdminSeriesSerializer(page, many=True, context={'request': request}).data)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def admin_series_detail(request, series_id):
    series = get_object_or_404(
        Series.objects.prefetch_related(
            'genres',
            'countries',
            'directors',
            'series_actors__actor',
        ),
        pk=series_id,
    )
    if request.method == 'GET':
        return Response(AdminSeriesSerializer(series, context={'request': request}).data)
    if request.method == 'DELETE':
        series.is_published = False
        series.save(update_fields=['is_published', 'updated_at'])
        return Response({'id': series.id, 'is_published': False, 'archived': True})

    serializer = AdminSeriesSerializer(series, data=request.data, partial=True, context={'request': request})
    serializer.is_valid(raise_exception=True)
    series = serializer.save()
    return Response(AdminSeriesSerializer(series, context={'request': request}).data)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def catalog_sync_run_list_create(request):
    if request.method == 'GET':
        limit = _bounded_int(request.query_params.get('limit'), 10, 1, 50)
        runs = CatalogSyncRun.objects.select_related('requested_by').order_by('-started_at')[:limit]
        return Response({'results': [catalog_sync_payload(run) for run in runs]})

    client, error = _client_or_error()
    if error:
        return error
    del client  # Configuration validation only; the credential remains worker-side.
    mode = str(request.data.get('mode') or CatalogSyncRun.Mode.INCREMENTAL)
    if mode not in CatalogSyncRun.Mode.values:
        return Response(
            {'detail': 'mode must be daily, trending, incremental, or full.', 'code': 'invalid_sync_mode'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if mode == CatalogSyncRun.Mode.FULL and not _bool_flag(request.data.get('confirm_full')):
        return Response(
            {
                'detail': 'Full import requires explicit confirmation.',
                'code': 'full_sync_confirmation_required',
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    parameters = {}
    importer = CatalogImporterSettings.get_solo()
    if mode in {CatalogSyncRun.Mode.DAILY, CatalogSyncRun.Mode.INCREMENTAL}:
        parameters = {
            'lookback_days': _bounded_int(
                request.data.get('lookback_days'),
                importer.daily_lookback_days,
                1,
                14,
            ),
            'lookahead_days': _bounded_int(
                request.data.get('lookahead_days'),
                importer.daily_lookahead_days,
                0,
                90,
            ),
            'max_pages': _bounded_int(
                request.data.get('max_pages'),
                importer.daily_max_pages,
                1,
                500,
            ),
        }
    elif mode == CatalogSyncRun.Mode.TRENDING:
        window = str(request.data.get('window') or importer.trending_window)
        parameters = {
            'window': window if window in {'day', 'week'} else importer.trending_window,
            'max_pages': _bounded_int(
                request.data.get('max_pages'), importer.trending_max_pages, 1, 20,
            ),
        }
    try:
        run = start_catalog_sync(
            requested_by=request.user,
            mode=mode,
            parameters=parameters,
        )
    except ActiveCatalogSyncError as exc:
        active = CatalogSyncRun.objects.select_related('requested_by').get(pk=exc.run.pk)
        return Response(
            {
                'detail': 'A catalog sync is already active.',
                'code': 'catalog_sync_already_active',
                'run': catalog_sync_payload(active),
            },
            status=status.HTTP_409_CONFLICT,
        )

    try:
        from .tasks import stage_catalog_sync_task
        task = stage_catalog_sync_task.delay(run.pk)
        run.task_id = task.id
        run.save(update_fields=['task_id', 'updated_at'])
    except Exception:
        run = fail_catalog_sync(run.pk, 'The catalog worker could not enqueue the sync job.')
        return Response(
            {
                'detail': 'Catalog worker is unavailable.',
                'code': 'catalog_worker_unavailable',
                'run': catalog_sync_payload(run),
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    run = CatalogSyncRun.objects.select_related('requested_by').get(pk=run.pk)
    return Response(catalog_sync_payload(run), status=status.HTTP_202_ACCEPTED)


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def catalog_importer_settings(request):
    importer = CatalogImporterSettings.get_solo()
    if request.method == 'GET':
        return Response(CatalogImporterSettingsSerializer(importer).data)
    serializer = CatalogImporterSettingsSerializer(importer, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    importer = serializer.save(updated_by=request.user)
    return Response(CatalogImporterSettingsSerializer(importer).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def catalog_sync_run_detail(request, run_id):
    run = get_object_or_404(
        CatalogSyncRun.objects.select_related('requested_by'),
        pk=run_id,
    )
    return Response(catalog_sync_payload(run))


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def catalog_sync_run_cancel(request, run_id):
    get_object_or_404(CatalogSyncRun, pk=run_id)
    run = request_catalog_sync_cancel(run_id)
    run = CatalogSyncRun.objects.select_related('requested_by').get(pk=run.pk)
    return Response(catalog_sync_payload(run))
