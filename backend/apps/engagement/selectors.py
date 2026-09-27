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
    obj = model.objects.filter(pk=object_id).first()
    if not obj:
        return None
    site_rating = getattr(obj, 'site_rating', None)
    summary = {
        # id + content_type let clients open the right detail page straight from
        # a library card; year + rating make the card render like a real poster
        # tile instead of a bare thumbnail.
        'id': obj.id,
        'content_type': content_type,
        'title': obj.title,
        'slug': obj.slug,
        'poster': media_url(obj.poster) or None,
        'site_rating': float(site_rating) if site_rating is not None else None,
    }
    if content_type == 'series':
        summary['start_year'] = getattr(obj, 'start_year', None)
    else:
        summary['release_year'] = getattr(obj, 'release_year', None)
    return summary


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
    ).exclude(review='').select_related('user', 'admin_reply_by')
    if not include_hidden:
        qs = qs.filter(is_hidden=False)
    # Editor's picks lead, then newest — so a featured review sits at the top
    # with its badge, and the team's answered reviews stay in normal order.
    return qs.order_by('-is_featured', '-created_at')


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


def get_admin_reviews(*, content_type=None, q='', hidden=None, state=None):
    qs = Rating.objects.exclude(review='').select_related('user', 'admin_reply_by')
    if content_type:
        qs = qs.filter(content_type=content_type)
    if hidden is True:
        qs = qs.filter(is_hidden=True)
    elif hidden is False:
        qs = qs.filter(is_hidden=False)
    # `state` is the moderation inbox lens: what still needs a human.
    if state == 'unanswered':
        qs = qs.filter(admin_reply='', is_hidden=False)
    elif state == 'answered':
        qs = qs.exclude(admin_reply='')
    elif state == 'featured':
        qs = qs.filter(is_featured=True)
    if q:
        qs = qs.filter(
            Q(review__icontains=q)
            | Q(user__username__icontains=q)
            | Q(user__email__icontains=q)
        )
    # Featured first, then unanswered reviews rise ahead of already-answered ones.
    return qs.order_by('-is_featured', 'admin_reply', '-created_at')


def get_review_moderation_counts():
    """Headline counts for the review moderation inbox / interaction overview."""
    base = Rating.objects.exclude(review='')
    return {
        'total': base.count(),
        'unanswered': base.filter(admin_reply='', is_hidden=False).count(),
        'answered': base.exclude(admin_reply='').count(),
        'featured': base.filter(is_featured=True).count(),
        'hidden': base.filter(is_hidden=True).count(),
    }


def get_support_inbox_counts():
    """Headline counts for the support inbox / interaction overview."""
    closed = [SupportTicket.Status.CLOSED, SupportTicket.Status.RESOLVED]
    return {
        'unread': SupportTicket.objects.filter(unread_by_staff=True).exclude(status__in=closed).count(),
        'open': SupportTicket.objects.exclude(status__in=closed).count(),
        'total': SupportTicket.objects.count(),
    }
