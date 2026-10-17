"""Staff-only endpoints for review moderation and the HamSeda support inbox."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.admin_api import IsStaffUser, StaffAdminThrottle

from . import selectors, services
from .models import Rating, SupportTicket
from .serializers import (
    AdminReviewActionSerializer,
    AdminSupportTicketUpdateSerializer,
    RatingSerializer,
    SupportReplySerializer,
    SupportTicketListSerializer,
    SupportTicketSerializer,
)


class AdminInboxPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100


def _review_payload(rating):
    payload = RatingSerializer(rating).data
    payload['content'] = selectors.resolve_content_summary(rating.content_type, rating.object_id)
    return payload


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def admin_reviews_list(request):
    content_type = request.GET.get('content_type') or None
    q = (request.GET.get('q') or '').strip()
    state = request.GET.get('state') or None
    if state not in {'unanswered', 'answered', 'featured'}:
        state = None
    hidden_raw = request.GET.get('hidden')
    hidden = None
    if hidden_raw in {'1', 'true', 'True'}:
        hidden = True
    elif hidden_raw in {'0', 'false', 'False'}:
        hidden = False

    queryset = selectors.get_admin_reviews(content_type=content_type, q=q, hidden=hidden, state=state)
    paginator = AdminInboxPagination()
    page = paginator.paginate_queryset(queryset, request)
    results = [_review_payload(rating) for rating in page]
    response = paginator.get_paginated_response(results)
    response.data['counts'] = selectors.get_review_moderation_counts()
    return response


@api_view(['PATCH'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def admin_review_detail(request, rating_id):
    rating = get_object_or_404(Rating, pk=rating_id)
    serializer = AdminReviewActionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    if 'is_hidden' in data:
        services.set_rating_hidden(rating, data['is_hidden'])
    if 'is_featured' in data:
        services.set_review_featured(rating, data['is_featured'])
    if 'admin_reply' in data:
        services.set_review_admin_reply(rating, author=request.user, body=data['admin_reply'])
    rating.refresh_from_db()
    return Response(_review_payload(rating))


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def admin_interaction_overview(request):
    """Lightweight badge/overview feed for the admin shell: how many reviews are
    waiting on the team and how many support requests are unread."""
    return Response({
        'reviews': selectors.get_review_moderation_counts(),
        'support': selectors.get_support_inbox_counts(),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def admin_support_inbox(request):
    status_filter = request.GET.get('status') or None
    category = request.GET.get('category') or None
    unread_only = request.GET.get('unread') in {'1', 'true', 'True'}
    # Hide finished conversations by default so the panel only shows work to do.
    # Resolved/closed rows are still reachable via the status filter and can be
    # permanently removed with the purge endpoint below.
    hide_resolved = request.GET.get('hide_resolved') in {'1', 'true', 'True'}
    q = (request.GET.get('q') or '').strip()

    queryset = selectors.get_admin_support_tickets(
        status=status_filter,
        category=category,
        unread_only=unread_only,
        q=q,
        hide_resolved=hide_resolved and not status_filter,
    )
    paginator = AdminInboxPagination()
    page = paginator.paginate_queryset(queryset, request)
    unread_count = SupportTicket.objects.filter(unread_by_staff=True).exclude(
        status__in=[SupportTicket.Status.CLOSED, SupportTicket.Status.RESOLVED],
    ).count()
    open_count = SupportTicket.objects.exclude(
        status__in=[SupportTicket.Status.CLOSED, SupportTicket.Status.RESOLVED],
    ).count()
    response = paginator.get_paginated_response(SupportTicketListSerializer(page, many=True).data)
    response.data['unread_count'] = unread_count
    response.data['open_count'] = open_count
    return response


@api_view(['GET', 'PATCH', 'POST', 'DELETE'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def admin_support_ticket_detail(request, tracking_code):
    ticket = get_object_or_404(
        SupportTicket.objects.select_related('user').prefetch_related('messages__author'),
        tracking_code=tracking_code,
    )

    if request.method == 'DELETE':
        # Permanent removal (e.g. a resolved conversation cluttering the panel).
        # Messages cascade; a linked ContentIssueReport keeps its row with the
        # ticket link nulled (SET_NULL) so remediation history is preserved.
        code = ticket.tracking_code
        ticket.delete()
        return Response({'ok': True, 'deleted': code})

    if request.method == 'GET':
        services.mark_ticket_read_by_staff(ticket)
        ticket.refresh_from_db()
        ticket = SupportTicket.objects.select_related('user').prefetch_related(
            'messages__author',
        ).get(pk=ticket.pk)
        payload = SupportTicketSerializer(ticket).data
        payload['staff_note'] = ticket.staff_note
        payload['user_email'] = ticket.user.email
        return Response(payload)

    if request.method == 'POST':
        serializer = SupportReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reply_support_ticket(
            ticket=ticket,
            author=request.user,
            body=serializer.validated_data['body'],
            is_staff_reply=True,
        )
        ticket = SupportTicket.objects.select_related('user').prefetch_related(
            'messages__author',
        ).get(pk=ticket.pk)
        payload = SupportTicketSerializer(ticket).data
        payload['staff_note'] = ticket.staff_note
        payload['user_email'] = ticket.user.email
        return Response(payload)

    serializer = AdminSupportTicketUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    if 'body' in data and data['body']:
        services.reply_support_ticket(
            ticket=ticket,
            author=request.user,
            body=data['body'],
            is_staff_reply=True,
        )
    if 'status' in data or 'staff_note' in data:
        services.set_support_ticket_status(
            ticket=ticket,
            status=data.get('status', ticket.status),
            staff_note=data.get('staff_note'),
        )
    ticket = SupportTicket.objects.select_related('user').prefetch_related(
        'messages__author',
    ).get(pk=ticket.pk)
    payload = SupportTicketSerializer(ticket).data
    payload['staff_note'] = ticket.staff_note
    payload['user_email'] = ticket.user.email
    return Response(payload)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def admin_support_tickets_purge(request):
    """Permanently delete finished conversations (resolved/closed) from the panel.

    Body (all optional): ``{ status, category, older_than_days, limit }``.
    Without ``status`` both ``resolved`` and ``closed`` are removed. ``limit``
    caps a single click (default 200, max 1000) so one press cannot wipe the
    whole history unseen. Returns ``{ ok, deleted }``.
    """
    from datetime import timedelta

    from django.utils import timezone

    data = request.data if isinstance(request.data, dict) else {}
    status_filter = (data.get('status') or '').strip()
    category = (data.get('category') or '').strip() or None
    try:
        older_than_days = int(data.get('older_than_days') or 0)
    except (TypeError, ValueError):
        older_than_days = 0
    try:
        limit = int(data.get('limit') or 200)
    except (TypeError, ValueError):
        limit = 200
    limit = max(1, min(limit, 1000))

    valid_statuses = {choice for choice, _label in SupportTicket.Status.choices}
    if status_filter:
        if status_filter not in valid_statuses:
            return Response(
                {'detail': 'وضعیت نامعتبر است.', 'code': 'invalid_status'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        statuses = [status_filter]
    else:
        statuses = [SupportTicket.Status.RESOLVED, SupportTicket.Status.CLOSED]

    qs = SupportTicket.objects.filter(status__in=statuses)
    if category:
        qs = qs.filter(category=category)
    if older_than_days > 0:
        cutoff = timezone.now() - timedelta(days=older_than_days)
        qs = qs.filter(updated_at__lt=cutoff)
    ids = list(qs.order_by('updated_at').values_list('pk', flat=True)[:limit])
    deleted, _details = SupportTicket.objects.filter(pk__in=ids).delete()
    # ``deleted`` counts cascaded messages too; report back ticket rows only.
    return Response({'ok': True, 'deleted': len(ids)})
