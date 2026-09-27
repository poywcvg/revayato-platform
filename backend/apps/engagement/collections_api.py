"""User-created collections ("کالکشن") + public profiles.

Everything here is real, DB-backed data. A collection is an ordered list that can
mix movies and series (reusing the movie/series content_type + object_id pattern),
owned by a user, with three visibility levels (public / unlisted-by-link / private)
and a share token for unlisted links. Public profiles expose only what the owner's
privacy settings allow.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils.text import slugify

from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from config.public_urls import media_url

from . import selectors
from .models import (
    Like,
    Rating,
    RATEABLE_CONTENT_TYPES,
    UserCollection,
    UserCollectionItem,
    WatchlistItem,
)

User = get_user_model()

# A small, fixed palette so covers look designed rather than random; the index is
# a stable hash of the collection id, so a collection keeps its colour for life.
COLLECTION_ACCENTS = [
    '#7c5cff', '#ff5c8a', '#2dd4bf', '#f59e0b',
    '#38bdf8', '#a3e635', '#fb7185', '#c084fc',
]


def _accent_for(collection: UserCollection) -> str:
    if collection.accent:
        return collection.accent
    return COLLECTION_ACCENTS[(collection.id or 0) % len(COLLECTION_ACCENTS)]


# --------------------------------------------------------------------------- #
#  Serialization helpers
# --------------------------------------------------------------------------- #
def _item_cards(collection: UserCollection, *, limit: int | None = None):
    """Resolve a collection's items into poster cards, preserving order.

    Skips items whose title was deleted from the catalog so a broken row never
    crashes the list; the stored row stays for a later re-resolve.
    """
    qs = collection.items.all()
    if limit is not None:
        qs = qs[:limit]
    cards = []
    for item in qs:
        summary = selectors.resolve_content_summary(item.content_type, item.object_id)
        if not summary:
            continue
        summary = dict(summary)
        summary['note'] = item.note
        summary['position'] = item.position
        summary['added_at'] = item.added_at
        cards.append(summary)
    return cards


def _covers(collection: UserCollection):
    """Up to four poster URLs for the collage cover, in order."""
    covers = []
    for item in collection.items.all()[:6]:
        summary = selectors.resolve_content_summary(item.content_type, item.object_id)
        if summary and summary.get('poster'):
            covers.append(summary['poster'])
        if len(covers) >= 4:
            break
    return covers


def serialize_collection(collection: UserCollection, *, detail=False, viewer=None):
    """Shape a collection for the API. `detail` embeds the full ordered item list."""
    count = getattr(collection, 'item_count', None)
    if count is None:
        count = collection.items.count()
    data = {
        'id': collection.id,
        'slug': collection.slug,
        'title': collection.title,
        'description': collection.description,
        'visibility': collection.visibility,
        'accent': _accent_for(collection),
        'item_count': count,
        'covers': _covers(collection),
        'owner': {
            'username': collection.owner.username,
            'avatar': media_url(getattr(getattr(collection.owner, 'profile', None), 'avatar', None)) or None,
        },
        'share_token': collection.share_token,
        'share_url': f'/c/{collection.share_token}',
        'is_mine': bool(viewer and viewer.is_authenticated and viewer.id == collection.owner_id),
        'created_at': collection.created_at,
        'updated_at': collection.updated_at,
    }
    if detail:
        data['items'] = _item_cards(collection)
    return data


# --------------------------------------------------------------------------- #
#  Input serializers
# --------------------------------------------------------------------------- #
class CollectionWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=120)
    description = serializers.CharField(max_length=2000, required=False, allow_blank=True, default='')
    visibility = serializers.ChoiceField(
        choices=UserCollection.Visibility.choices,
        required=False, default=UserCollection.Visibility.PUBLIC,
    )
    accent = serializers.RegexField(r'^#[0-9a-fA-F]{6}$', required=False, allow_blank=True, default='')

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('عنوان کالکشن نمی‌تواند خالی باشد.')
        return value


class CollectionItemSerializer(serializers.Serializer):
    content_type = serializers.ChoiceField(choices=[c[0] for c in RATEABLE_CONTENT_TYPES])
    object_id = serializers.IntegerField(min_value=1)
    note = serializers.CharField(max_length=280, required=False, allow_blank=True, default='')


class ReorderSerializer(serializers.Serializer):
    order = serializers.ListField(
        child=CollectionItemSerializer(), allow_empty=False, max_length=500,
    )


def _unique_slug(owner, title, *, exclude_pk=None):
    base = slugify(title, allow_unicode=True) or 'collection'
    base = base[:120]
    slug = base
    i = 2
    qs = UserCollection.objects.filter(owner=owner)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    while qs.filter(slug=slug).exists():
        slug = f'{base}-{i}'
        i += 1
    return slug


# --------------------------------------------------------------------------- #
#  Owner CRUD
# --------------------------------------------------------------------------- #
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def collections_root(request):
    """GET: my collections (with covers). POST: create a new collection."""
    if request.method == 'GET':
        qs = (
            UserCollection.objects
            .filter(owner=request.user)
            .annotate(item_count=Count('items'))
            .prefetch_related('items')
        )
        return Response([serialize_collection(c, viewer=request.user) for c in qs])

    serializer = CollectionWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    collection = UserCollection.objects.create(
        owner=request.user,
        title=data['title'],
        description=data.get('description', ''),
        visibility=data.get('visibility', UserCollection.Visibility.PUBLIC),
        accent=data.get('accent', ''),
        slug=_unique_slug(request.user, data['title']),
    )
    return Response(
        serialize_collection(collection, detail=True, viewer=request.user),
        status=status.HTTP_201_CREATED,
    )


def _get_owned(request, slug):
    return UserCollection.objects.filter(owner=request.user, slug=slug).first()


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def collection_detail(request, slug):
    collection = _get_owned(request, slug)
    if not collection:
        return Response({'detail': 'کالکشن پیدا نشد.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(serialize_collection(collection, detail=True, viewer=request.user))

    if request.method == 'DELETE':
        collection.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = CollectionWriteSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    update_fields = []
    if 'title' in data and data['title'] != collection.title:
        collection.title = data['title']
        collection.slug = _unique_slug(request.user, data['title'], exclude_pk=collection.pk)
        update_fields += ['title', 'slug']
    if 'description' in data:
        collection.description = data['description']
        update_fields.append('description')
    if 'visibility' in data:
        collection.visibility = data['visibility']
        update_fields.append('visibility')
    if 'accent' in data:
        collection.accent = data['accent']
        update_fields.append('accent')
    if update_fields:
        update_fields.append('updated_at')
        collection.save(update_fields=update_fields)
    return Response(serialize_collection(collection, detail=True, viewer=request.user))


@api_view(['POST', 'DELETE'])
@permission_classes([IsAuthenticated])
def collection_items(request, slug):
    """POST: add a title (idempotent). DELETE: remove a title."""
    collection = _get_owned(request, slug)
    if not collection:
        return Response({'detail': 'کالکشن پیدا نشد.'}, status=status.HTTP_404_NOT_FOUND)

    serializer = CollectionItemSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    if request.method == 'DELETE':
        deleted, _ = UserCollectionItem.objects.filter(
            collection=collection, content_type=data['content_type'], object_id=data['object_id'],
        ).delete()
        collection.save(update_fields=['updated_at'])
        return Response({'removed': bool(deleted), 'item_count': collection.items.count()})

    # Guard against pointing at a title that does not exist.
    if not selectors.resolve_content_summary(data['content_type'], data['object_id']):
        return Response({'detail': 'این عنوان در کاتالوگ نیست.'}, status=status.HTTP_400_BAD_REQUEST)

    next_pos = (
        UserCollectionItem.objects.filter(collection=collection)
        .aggregate(m=Count('id'))['m'] or 0
    )
    try:
        with transaction.atomic():
            _, created = UserCollectionItem.objects.get_or_create(
                collection=collection,
                content_type=data['content_type'],
                object_id=data['object_id'],
                defaults={'note': data.get('note', ''), 'position': next_pos},
            )
    except IntegrityError:
        created = False
    collection.save(update_fields=['updated_at'])
    return Response(
        {'added': created, 'item_count': collection.items.count()},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def collection_reorder(request, slug):
    collection = _get_owned(request, slug)
    if not collection:
        return Response({'detail': 'کالکشن پیدا نشد.'}, status=status.HTTP_404_NOT_FOUND)
    serializer = ReorderSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    order = serializer.validated_data['order']
    existing = {
        (i.content_type, i.object_id): i
        for i in UserCollectionItem.objects.filter(collection=collection)
    }
    to_update = []
    for pos, ref in enumerate(order):
        item = existing.get((ref['content_type'], ref['object_id']))
        if item and item.position != pos:
            item.position = pos
            to_update.append(item)
    if to_update:
        UserCollectionItem.objects.bulk_update(to_update, ['position'])
        collection.save(update_fields=['updated_at'])
    return Response(serialize_collection(collection, detail=True, viewer=request.user))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def collections_containing(request):
    """Power the «افزودن به کالکشن» control: list my collections and flag which
    already contain the given title so the sheet can render checkmarks."""
    content_type = request.GET.get('content_type')
    object_id = request.GET.get('object_id')
    qs = (
        UserCollection.objects.filter(owner=request.user)
        .annotate(item_count=Count('items'))
    )
    containing = set()
    if content_type and object_id:
        containing = set(
            UserCollectionItem.objects
            .filter(collection__owner=request.user, content_type=content_type, object_id=object_id)
            .values_list('collection_id', flat=True)
        )
    return Response([
        {
            'id': c.id,
            'slug': c.slug,
            'title': c.title,
            'visibility': c.visibility,
            'accent': _accent_for(c),
            'item_count': c.item_count,
            'contains': c.id in containing,
        }
        for c in qs
    ])


# --------------------------------------------------------------------------- #
#  Public reads
# --------------------------------------------------------------------------- #
@api_view(['GET'])
@permission_classes([AllowAny])
def public_collections_containing(request):
    """Discovery: PUBLIC collections (built by any user) that contain a given
    title, to show on a movie/series detail page — "این عنوان در این کالکشن‌هاست".

    Real data only: filters to visibility=public, resolves each collection's
    covers/owner via serialize_collection, and orders the most-populated first
    so the richest lists surface. Bounded so a very popular title can't return
    an unbounded page.
    """
    content_type = request.GET.get('content_type')
    object_id = request.GET.get('object_id')
    if not content_type or not object_id:
        return Response({'detail': 'content_type و object_id لازم است.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        object_id = int(object_id)
    except (TypeError, ValueError):
        return Response({'detail': 'object_id نامعتبر است.'}, status=status.HTTP_400_BAD_REQUEST)

    limit = 12
    try:
        limit = max(1, min(24, int(request.GET.get('limit', limit))))
    except (TypeError, ValueError):
        pass

    collection_ids = list(
        UserCollectionItem.objects
        .filter(
            content_type=content_type,
            object_id=object_id,
            collection__visibility=UserCollection.Visibility.PUBLIC,
        )
        .values_list('collection_id', flat=True)
        .distinct()
    )
    if not collection_ids:
        return Response({'results': [], 'count': 0})

    qs = (
        UserCollection.objects
        .filter(id__in=collection_ids)
        .annotate(item_count=Count('items'))
        .select_related('owner')
        .prefetch_related('items')
        .order_by('-item_count', '-updated_at')
    )
    total = qs.count()
    collections = [serialize_collection(c, viewer=request.user) for c in qs[:limit]]
    return Response({'results': collections, 'count': total})


@api_view(['GET'])
@permission_classes([AllowAny])
def public_collection_by_token(request, token):
    """Open a collection by its share token (works for public + unlisted)."""
    collection = (
        UserCollection.objects
        .filter(share_token=token)
        .exclude(visibility=UserCollection.Visibility.PRIVATE)
        .select_related('owner')
        .prefetch_related('items')
        .first()
    )
    if not collection:
        return Response({'detail': 'کالکشن پیدا نشد.'}, status=status.HTTP_404_NOT_FOUND)
    return Response(serialize_collection(collection, detail=True, viewer=request.user))


@api_view(['GET'])
@permission_classes([AllowAny])
def public_collection(request, username, slug):
    """Open a public collection by owner username + slug."""
    collection = (
        UserCollection.objects
        .filter(owner__username=username, slug=slug)
        .select_related('owner')
        .prefetch_related('items')
        .first()
    )
    if not collection:
        return Response({'detail': 'کالکشن پیدا نشد.'}, status=status.HTTP_404_NOT_FOUND)
    is_owner = request.user.is_authenticated and request.user.id == collection.owner_id
    if collection.visibility != UserCollection.Visibility.PUBLIC and not is_owner:
        # Unlisted/private are not discoverable by slug — only via share token.
        return Response({'detail': 'کالکشن پیدا نشد.'}, status=status.HTTP_404_NOT_FOUND)
    return Response(serialize_collection(collection, detail=True, viewer=request.user))


def _profile_visibility(user):
    privacy = getattr(user, 'privacy_settings', None)
    if not privacy:
        return 'public'
    return privacy.profile_visibility


@api_view(['GET'])
@permission_classes([AllowAny])
def public_profile(request, username):
    """A user's public profile: identity + public collections + honest public stats.

    Respects the owner's privacy settings — a private profile returns only the
    minimal identity card with a `is_private` flag; ratings are hidden unless the
    owner's ratings_visibility is public.
    """
    user = User.objects.filter(username=username, is_active=True).select_related('profile').first()
    if not user:
        return Response({'detail': 'کاربر پیدا نشد.'}, status=status.HTTP_404_NOT_FOUND)

    is_self = request.user.is_authenticated and request.user.id == user.id
    profile = getattr(user, 'profile', None)
    privacy = getattr(user, 'privacy_settings', None)
    identity = {
        'username': user.username,
        'display_name': user.get_short_name(),
        'avatar': media_url(getattr(profile, 'avatar', None)) or None,
        'bio': (getattr(profile, 'bio', '') or '').strip(),
        'is_verified': bool(getattr(user, 'is_verified', False)),
        'member_since': user.date_joined if getattr(user, 'date_joined', None) else user.created_at,
    }

    profile_private = _profile_visibility(user) == 'private' and not is_self
    if profile_private:
        return Response({**identity, 'is_private': True, 'is_self': is_self})

    # Public collections (owner sees all of their own).
    coll_qs = (
        UserCollection.objects.filter(owner=user).annotate(item_count=Count('items')).prefetch_related('items')
    )
    if not is_self:
        coll_qs = coll_qs.filter(visibility=UserCollection.Visibility.PUBLIC)
    collections = [serialize_collection(c, viewer=request.user) for c in coll_qs]

    ratings_public = (not privacy) or privacy.ratings_visibility == 'public' or is_self
    reviews = []
    ratings_count = 0
    if ratings_public:
        ratings_count = Rating.objects.filter(user=user, is_hidden=False).count()
        for r in (
            Rating.objects.filter(user=user, is_hidden=False)
            .exclude(review='').order_by('-created_at')[:12]
        ):
            summary = selectors.resolve_content_summary(r.content_type, r.object_id)
            reviews.append({
                'content_type': r.content_type,
                'object_id': r.object_id,
                'content': summary,
                'score': float(r.score),
                'review': r.review,
                'is_spoiler': r.is_spoiler,
                'created_at': r.created_at,
            })

    stats = {
        'collections': len([c for c in collections]),
        'public_titles': sum(c['item_count'] for c in collections),
        'ratings': ratings_count,
        'likes': Like.objects.filter(user=user).count() if is_self else None,
    }

    return Response({
        **identity,
        'is_private': False,
        'is_self': is_self,
        'stats': stats,
        'collections': collections,
        'reviews': reviews,
    })
