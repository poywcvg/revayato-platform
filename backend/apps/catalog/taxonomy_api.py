"""Staff-only CRUD endpoints for catalog taxonomy entities.

Genres, countries, actors, directors and tags are referenced throughout the
catalog (movie/series editors, public filters, home rails) but until now could
only be created by TMDB sync — there was no admin write surface. These views
give staff a managed create/edit/delete path behind the same ``IsStaffUser``
guard and ``StaffAdminThrottle`` used everywhere else in the admin API.
"""

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    parser_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.serializers import ModelSerializer
from rest_framework.throttling import UserRateThrottle

from .models import Actor, Country, Director, Genre, Movie, Series, Tag
from .serializers import PublicMediaSerializer


class AdminGenreSerializer(ModelSerializer):
    class Meta:
        model = Genre
        fields = ['id', 'title', 'slug', 'description', 'is_featured']


class AdminCountrySerializer(ModelSerializer):
    class Meta:
        model = Country
        fields = ['id', 'name', 'code']


class AdminTagSerializer(ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug', 'is_featured']


class AdminActorSerializer(PublicMediaSerializer):
    class Meta:
        model = Actor
        fields = [
            'id', 'name', 'original_name', 'slug', 'photo', 'photo_external_url',
            'biography', 'birth_date', 'birth_place', 'is_featured', 'popularity', 'tmdb_id',
        ]


class AdminDirectorSerializer(PublicMediaSerializer):
    class Meta:
        model = Director
        fields = [
            'id', 'name', 'original_name', 'slug', 'photo', 'photo_external_url',
            'biography', 'birth_date', 'birth_place', 'is_featured', 'popularity', 'tmdb_id',
        ]


class IsStaffUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class StaffAdminThrottle(UserRateThrottle):
    rate = '120/minute'


# ---------------------------------------------------------------------------
# Slug helpers — reuse Django's unicode-aware slugify; fall back to a hashed
# value when the source string is entirely non-sluggable (e.g. Persian-only
# titles that slugify to an empty string).
# ---------------------------------------------------------------------------
def _auto_slug(source: str, model) -> str:
    base = slugify(source or '', allow_unicode=True) or slugify(source or '', allow_unicode=False)
    if not base:
        base = f"{model.__name__.lower()}-{abs(hash(source))}"
    slug = base
    n = 1
    while model.objects.filter(slug=slug).exists():
        n += 1
        slug = f"{base}-{n}"
    return slug


# ---------------------------------------------------------------------------
# Generic list/create dispatcher per entity
# ---------------------------------------------------------------------------
_ENTITY_CONFIG = {
    'genres': {
        'model': Genre,
        'serializer': AdminGenreSerializer,
        'search_fields': ['title'],
        'slug_source': 'title',
    },
    'countries': {
        'model': Country,
        'serializer': AdminCountrySerializer,
        'search_fields': ['name', 'code'],
        'slug_source': 'name',
    },
    'tags': {
        'model': Tag,
        'serializer': AdminTagSerializer,
        'search_fields': ['name'],
        'slug_source': 'name',
    },
    'actors': {
        'model': Actor,
        'serializer': AdminActorSerializer,
        'search_fields': ['name', 'original_name'],
        'slug_source': 'name',
        'multipart': True,
    },
    'directors': {
        'model': Director,
        'serializer': AdminDirectorSerializer,
        'search_fields': ['name', 'original_name'],
        'slug_source': 'name',
        'multipart': True,
    },
}


def _paginate(queryset, request, serializer_class, many=True):
    paginator = LimitOffsetPagination()
    paginator.default_limit = 20
    paginator.max_limit = 100
    page = paginator.paginate_queryset(queryset, request)
    if page is not None:
        return paginator.get_paginated_response(serializer_class(page, many=True).data)
    return Response(serializer_class(queryset, many=many).data)


def _build_list_queryset(config, request):
    model = config['model']
    queryset = model.objects.all()
    q = (request.query_params.get('q') or '').strip()
    if q:
        filters = Q()
        for field in config['search_fields']:
            filters |= Q(**{f'{field}__icontains': q})
        queryset = queryset.filter(filters)
    # Not every taxonomy model carries updated_at/created_at; pick a safe default.
    model_fields = {field.name for field in model._meta.get_fields()}
    if 'updated_at' in model_fields:
        default_order = '-updated_at'
    elif 'created_at' in model_fields:
        default_order = '-created_at'
    else:
        default_order = 'pk'
    order = request.query_params.get('ordering') or default_order
    if order in {'name', '-name', 'title', '-title', 'updated_at', '-updated_at', 'created_at', '-created_at', 'popularity', '-popularity'}:
        try:
            queryset = queryset.order_by(order)
        except Exception:  # noqa: BLE001 — field missing on this model, fall back safely
            queryset = queryset.order_by(default_order)
    else:
        queryset = queryset.order_by(default_order)
    return queryset


def _make_list_create(entity):
    config = _ENTITY_CONFIG[entity]

    @api_view(['GET', 'POST'])
    @permission_classes([IsAuthenticated, IsStaffUser])
    @throttle_classes([StaffAdminThrottle])
    @parser_classes([JSONParser, FormParser, MultiPartParser] if config.get('multipart') else [JSONParser])
    def view(request):
        if request.method == 'GET':
            return _paginate(_build_list_queryset(config, request), request, config['serializer'])

        model = config['model']
        payload = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if 'slug' not in payload or not (payload.get('slug') or '').strip():
            source = payload.get(config['slug_source']) or ''
            payload['slug'] = _auto_slug(source, model)
        serializer = config['serializer'](data=payload, context={'request': request})
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(config['serializer'](instance, context={'request': request}).data, status=status.HTTP_201_CREATED)

    view.__name__ = f'admin_{entity}_list_create'
    return view


def _make_detail(entity):
    config = _ENTITY_CONFIG[entity]

    @api_view(['GET', 'PATCH', 'DELETE'])
    @permission_classes([IsAuthenticated, IsStaffUser])
    @throttle_classes([StaffAdminThrottle])
    @parser_classes([JSONParser, FormParser, MultiPartParser] if config.get('multipart') else [JSONParser])
    def view(request, pk):
        model = config['model']
        instance = get_object_or_404(model, pk=pk)
        detail_serializer = config['serializer']

        if request.method == 'GET':
            return Response(detail_serializer(instance, context={'request': request}).data)

        if request.method == 'DELETE':
            # Block deletion while still referenced by published catalog titles so
            # staff don't silently orphan catalog metadata.
            referenced = False
            if entity == 'genres':
                referenced = Movie.objects.filter(genres=instance).exists() or Series.objects.filter(genres=instance).exists()
            elif entity == 'countries':
                referenced = Movie.objects.filter(countries=instance).exists() or Series.objects.filter(countries=instance).exists()
            elif entity == 'tags':
                referenced = Movie.objects.filter(tags=instance).exists() or Series.objects.filter(tags=instance).exists()
            elif entity in {'actors', 'directors'}:
                related_movies = Movie.objects.filter(movie_actors__actor=instance).exists() if entity == 'actors' else Movie.objects.filter(directors=instance).exists()
                related_series = Series.objects.filter(series_actors__actor=instance).exists() if entity == 'actors' else Series.objects.filter(directors=instance).exists()
                referenced = related_movies or related_series
            if referenced:
                return Response(
                    {'detail': 'این مورد هنوز به فیلم یا سریال متصل است و قابل حذف نیست.'},
                    status=status.HTTP_409_CONFLICT,
                )
            instance.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        payload = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if 'slug' in payload and not (payload.get('slug') or '').strip():
            del payload['slug']
        serializer = config['serializer'](instance, data=payload, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        return Response(detail_serializer(updated, context={'request': request}).data)

    view.__name__ = f'admin_{entity}_detail'
    return view


# Build the actual view functions the URLconf imports.
admin_genre_list_create = _make_list_create('genres')
admin_genre_detail = _make_detail('genres')
admin_country_list_create = _make_list_create('countries')
admin_country_detail = _make_detail('countries')
admin_tag_list_create = _make_list_create('tags')
admin_tag_detail = _make_detail('tags')
admin_actor_list_create = _make_list_create('actors')
admin_actor_detail = _make_detail('actors')
admin_director_list_create = _make_list_create('directors')
admin_director_detail = _make_detail('directors')
