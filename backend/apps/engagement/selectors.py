from django.apps import apps
from django.db.models import Avg, Count, Q

from config.public_urls import media_url

from .models import Like, Rating, SupportTicket, WatchlistItem

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


def get_reviews(content_type, object_id, *, include_hidden=False):
    qs = Rating.objects.filter(
        content_type=content_type, object_id=object_id,
    ).exclude(review='').select_related('user')
    if not include_hidden:
        qs = qs.filter(is_hidden=False)
    return qs.order_by('-created_at')


def get_user_watchlist(user, list_type=None):
    queryset = WatchlistItem.objects.filter(user=user)
    if list_type:
        queryset = queryset.filter(list_type=list_type)
    return queryset.order_by('-created_at')


def get_user_likes(user):
    return Like.objects.filter(user=user).order_by('-created_at')


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


def get_user_support_tickets(user):
    return SupportTicket.objects.filter(user=user).prefetch_related('messages')


def get_support_ticket_for_user(user, tracking_code):
    return SupportTicket.objects.filter(
        user=user, tracking_code=tracking_code,
    ).prefetch_related('messages__author').first()


def get_admin_support_tickets(*, status=None, category=None, unread_only=False, q=''):
    qs = SupportTicket.objects.select_related('user').prefetch_related('messages')
    if status:
        qs = qs.filter(status=status)
    if category:
        qs = qs.filter(category=category)
    if unread_only:
        qs = qs.filter(unread_by_staff=True)
    if q:
        qs = qs.filter(
            Q(tracking_code__icontains=q)
            | Q(subject__icontains=q)
            | Q(body__icontains=q)
            | Q(related_title__icontains=q)
            | Q(user__username__icontains=q)
            | Q(user__email__icontains=q)
        )
    return qs.order_by('-unread_by_staff', '-last_message_at')


def get_admin_reviews(*, content_type=None, q='', hidden=None):
    qs = Rating.objects.exclude(review='').select_related('user')
    if content_type:
        qs = qs.filter(content_type=content_type)
    if hidden is True:
        qs = qs.filter(is_hidden=True)
    elif hidden is False:
        qs = qs.filter(is_hidden=False)
    if q:
        qs = qs.filter(
            Q(review__icontains=q)
            | Q(user__username__icontains=q)
            | Q(user__email__icontains=q)
        )
    return qs.order_by('-created_at')
