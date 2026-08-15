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
    AdminRatingHideSerializer,
    AdminSupportTicketUpdateSerializer,
    RatingSerializer,
    SupportReplySerializer,
    SupportTicketListSerializer,
    SupportTicketSerializer,
)


class AdminInboxPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def admin_reviews_list(request):
    content_type = request.GET.get('content_type') or None
    q = (request.GET.get('q') or '').strip()
    hidden_raw = request.GET.get('hidden')
    hidden = None
    if hidden_raw in {'1', 'true', 'True'}:
        hidden = True
    elif hidden_raw in {'0', 'false', 'False'}:
        hidden = False

    queryset = selectors.get_admin_reviews(content_type=content_type, q=q, hidden=hidden)
    paginator = AdminInboxPagination()
    page = paginator.paginate_queryset(queryset, request)
    results = []
    for rating in page:
        payload = RatingSerializer(rating).data
        content = selectors.resolve_content_summary(rating.content_type, rating.object_id)
        payload['content'] = content
        results.append(payload)
    return paginator.get_paginated_response(results)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def admin_review_detail(request, rating_id):
    rating = get_object_or_404(Rating, pk=rating_id)
    serializer = AdminRatingHideSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    services.set_rating_hidden(rating, serializer.validated_data['is_hidden'])
    payload = RatingSerializer(rating).data
    payload['content'] = selectors.resolve_content_summary(rating.content_type, rating.object_id)
    return Response(payload)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def admin_support_inbox(request):
    status_filter = request.GET.get('status') or None
    category = request.GET.get('category') or None
    unread_only = request.GET.get('unread') in {'1', 'true', 'True'}
    q = (request.GET.get('q') or '').strip()

    queryset = selectors.get_admin_support_tickets(
        status=status_filter,
        category=category,
        unread_only=unread_only,
        q=q,
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


@api_view(['GET', 'PATCH', 'POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def admin_support_ticket_detail(request, tracking_code):
    ticket = get_object_or_404(
        SupportTicket.objects.select_related('user').prefetch_related('messages__author'),
        tracking_code=tracking_code,
    )

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
