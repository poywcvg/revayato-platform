from django.apps import apps
from django.db.models import Avg, Count

from config.public_urls import media_url

from .models import Like, Rating, WatchlistItem

CONTENT_MODEL_MAP = {
    'movie': ('catalog', 'Movie'),
    'series': ('catalog', 'Series'),
}


def resolve_content_summary(content_type, object_id):
    app_label, model_name = CONTENT_MODEL_MAP[content_type]
    model = apps.get_model(app_label, model_name)
    obj = model.objects.filter(pk=object_id).only('id', 'title', 'slug', 'poster').first()
    if not obj:
        return None
    return {
        'title': obj.title,
        'slug': obj.slug,
        'poster': media_url(obj.poster) or None,
    }


def get_user_rating(user, content_type, object_id):
    if not user or not user.is_authenticated:
        return None
    return Rating.objects.filter(
        user=user, content_type=content_type, object_id=object_id,
    ).first()


def get_rating_summary(content_type, object_id):
    result = Rating.objects.filter(
        content_type=content_type, object_id=object_id,
    ).aggregate(average=Avg('score'), count=Count('id'))
    return {
        'average': round(result['average'], 1) if result['average'] is not None else None,
        'count': result['count'],
    }


def get_reviews(content_type, object_id):
    return Rating.objects.filter(
        content_type=content_type, object_id=object_id,
    ).exclude(review='').select_related('user').order_by('-created_at')


def get_user_watchlist(user, list_type=None):
    queryset = WatchlistItem.objects.filter(user=user)
    if list_type:
        queryset = queryset.filter(list_type=list_type)
    return queryset.order_by('-created_at')


def is_in_watchlist(user, content_type, object_id, list_type):
    if not user or not user.is_authenticated:
        return False
    return WatchlistItem.objects.filter(
        user=user, content_type=content_type, object_id=object_id, list_type=list_type,
    ).exists()


def has_liked(user, content_type, object_id):
    if not user or not user.is_authenticated:
        return False
    return Like.objects.filter(
        user=user, content_type=content_type, object_id=object_id,
    ).exists()


def get_like_count(content_type, object_id):
    return Like.objects.filter(content_type=content_type, object_id=object_id).count()
