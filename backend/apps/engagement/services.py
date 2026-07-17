from django.apps import apps
from django.db.models import Avg
from django.shortcuts import get_object_or_404

from . import selectors
from .models import Like, Rating, WatchlistItem

CONTENT_MODEL_MAP = {
    'movie': ('catalog', 'Movie'),
    'series': ('catalog', 'Series'),
}


def _get_content_object(content_type, object_id):
    app_label, model_name = CONTENT_MODEL_MAP[content_type]
    model = apps.get_model(app_label, model_name)
    return get_object_or_404(model, pk=object_id)


def _refresh_site_rating(content_type, object_id):
    obj = _get_content_object(content_type, object_id)
    average = Rating.objects.filter(
        content_type=content_type, object_id=object_id,
    ).aggregate(avg=Avg('score'))['avg']
    obj.site_rating = round(average, 1) if average is not None else None
    obj.save(update_fields=['site_rating'])


def rate_content(user, content_type, object_id, score, review='', is_spoiler=False):
    _get_content_object(content_type, object_id)
    rating, _created = Rating.objects.update_or_create(
        user=user, content_type=content_type, object_id=object_id,
        defaults={'score': score, 'review': review, 'is_spoiler': is_spoiler},
    )
    _refresh_site_rating(content_type, object_id)
    return rating


def remove_rating(user, content_type, object_id):
    deleted, _ = Rating.objects.filter(
        user=user, content_type=content_type, object_id=object_id,
    ).delete()
    if deleted:
        _refresh_site_rating(content_type, object_id)
    return deleted > 0


def toggle_watchlist(user, content_type, object_id, list_type):
    _get_content_object(content_type, object_id)
    existing = WatchlistItem.objects.filter(
        user=user, content_type=content_type, object_id=object_id, list_type=list_type,
    ).first()
    if existing:
        existing.delete()
        return False
    WatchlistItem.objects.create(
        user=user, content_type=content_type, object_id=object_id, list_type=list_type,
    )
    return True


def toggle_like(user, content_type, object_id):
    obj = _get_content_object(content_type, object_id)
    existing = Like.objects.filter(
        user=user, content_type=content_type, object_id=object_id,
    ).first()
    if existing:
        existing.delete()
        liked = False
    else:
        Like.objects.create(user=user, content_type=content_type, object_id=object_id)
        liked = True

    obj.like_count = selectors.get_like_count(content_type, object_id)
    obj.save(update_fields=['like_count'])
    return liked
