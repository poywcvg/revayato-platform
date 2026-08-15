import secrets
import string

from django.apps import apps
from django.db import transaction
from django.db.models import Avg
from django.shortcuts import get_object_or_404
from django.utils import timezone

from . import selectors
from .models import Like, Rating, SupportMessage, SupportTicket, WatchlistItem

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


def rate_content(user, content_type, object_id, score, review=None, is_spoiler=None):
    _get_content_object(content_type, object_id)
    defaults = {'score': score}
    if review is not None:
        defaults['review'] = review
    if is_spoiler is not None:
        defaults['is_spoiler'] = is_spoiler
    rating, _created = Rating.objects.update_or_create(
        user=user, content_type=content_type, object_id=object_id,
        defaults=defaults,
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


def _generate_tracking_code():
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(12):
        code = 'HS-' + ''.join(secrets.choice(alphabet) for _ in range(6))
        if not SupportTicket.objects.filter(tracking_code=code).exists():
            return code
    raise RuntimeError('Could not allocate a unique support tracking code.')


@transaction.atomic
def create_support_ticket(
    *,
    user,
    category,
    subject,
    body,
    related_title='',
    related_year=None,
    related_url='',
):
    ticket = SupportTicket.objects.create(
        user=user,
        tracking_code=_generate_tracking_code(),
        category=category,
        subject=subject.strip(),
        body=body.strip(),
        related_title=(related_title or '').strip(),
        related_year=related_year,
        related_url=(related_url or '').strip(),
        unread_by_staff=True,
        unread_by_user=False,
        last_message_at=timezone.now(),
    )
    SupportMessage.objects.create(
        ticket=ticket,
        author=user,
        is_staff_reply=False,
        body=body.strip(),
    )
    return ticket


@transaction.atomic
def reply_support_ticket(*, ticket, author, body, is_staff_reply):
    message = SupportMessage.objects.create(
        ticket=ticket,
        author=author,
        is_staff_reply=is_staff_reply,
        body=body.strip(),
    )
    now = timezone.now()
    ticket.last_message_at = now
    if is_staff_reply:
        ticket.unread_by_user = True
        ticket.unread_by_staff = False
        if ticket.status in {SupportTicket.Status.OPEN, SupportTicket.Status.IN_PROGRESS}:
            ticket.status = SupportTicket.Status.WAITING_USER
    else:
        ticket.unread_by_staff = True
        ticket.unread_by_user = False
        if ticket.status in {
            SupportTicket.Status.WAITING_USER,
            SupportTicket.Status.RESOLVED,
        }:
            ticket.status = SupportTicket.Status.OPEN
    ticket.save(update_fields=[
        'last_message_at', 'unread_by_user', 'unread_by_staff', 'status', 'updated_at',
    ])
    return message


def set_support_ticket_status(*, ticket, status, staff_note=None):
    ticket.status = status
    update_fields = ['status', 'updated_at']
    if staff_note is not None:
        ticket.staff_note = staff_note
        update_fields.append('staff_note')
    if status in {SupportTicket.Status.RESOLVED, SupportTicket.Status.CLOSED}:
        ticket.unread_by_staff = False
        update_fields.append('unread_by_staff')
    ticket.save(update_fields=update_fields)
    return ticket


def mark_ticket_read_by_user(ticket):
    if ticket.unread_by_user:
        ticket.unread_by_user = False
        ticket.save(update_fields=['unread_by_user', 'updated_at'])
    return ticket


def mark_ticket_read_by_staff(ticket):
    if ticket.unread_by_staff:
        ticket.unread_by_staff = False
        ticket.save(update_fields=['unread_by_staff', 'updated_at'])
    return ticket


def set_rating_hidden(rating, is_hidden):
    rating.is_hidden = bool(is_hidden)
    rating.save(update_fields=['is_hidden', 'updated_at'])
    return rating
