from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from django.utils import timezone
from datetime import timedelta

from . import selectors, services
from .models import CommunityMessage
from .serializers import (
    CommunityMessageCreateSerializer, CommunityMessageSerializer,
    LikeToggleInputSerializer, RateContentInputSerializer, RatingSerializer,
    PrivacySafeEventInputSerializer, SupportReplySerializer, SupportTicketCreateSerializer,
    SupportTicketListSerializer, SupportTicketSerializer, UserActivityEventSerializer,
    WatchlistItemSerializer, WatchlistToggleInputSerializer,
)


@api_view(['POST'])
@permission_classes([AllowAny])
def create_event(request):
    serializer = UserActivityEventSerializer(data=request.data)
    if serializer.is_valid():
        event = serializer.save(
            user=request.user if request.user.is_authenticated else None,
        )
        return Response(
            UserActivityEventSerializer(event).data,
            status=status.HTTP_201_CREATED,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def create_privacy_safe_event(request):
    """Accept only consented first-party signals; never derive device/network identity."""
    if request.headers.get('X-Personalization-Consent') != 'granted':
        return Response(
            {'detail': 'Explicit personalization consent is required.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    serializer = PrivacySafeEventInputSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    event = serializer.save(
        user=request.user if request.user.is_authenticated else None,
    )
    return Response({
        'id': event.id,
        'event_type': serializer.validated_data['event_type'],
        'accepted': True,
        'created_at': event.created_at,
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
def rating_summary(request):
    content_type = request.GET.get('content_type')
    object_id = request.GET.get('object_id')
    if not content_type or not object_id:
        return Response({'detail': 'content_type and object_id are required'}, status=status.HTTP_400_BAD_REQUEST)

    summary = selectors.get_rating_summary(content_type, object_id)
    my_rating = selectors.get_user_rating(request.user, content_type, object_id)
    summary['my_rating'] = RatingSerializer(my_rating).data if my_rating else None
    summary['reviews'] = RatingSerializer(
        selectors.get_reviews(content_type, object_id)[:40],
        many=True,
    ).data
    return Response(summary)


@api_view(['POST', 'DELETE'])
@permission_classes([IsAuthenticated])
def rate_content(request):
    if request.method == 'DELETE':
        input_serializer = LikeToggleInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data
        services.remove_rating(request.user, data['content_type'], data['object_id'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    input_serializer = RateContentInputSerializer(data=request.data)
    input_serializer.is_valid(raise_exception=True)
    data = input_serializer.validated_data
    rating = services.rate_content(
        user=request.user,
        content_type=data['content_type'],
        object_id=data['object_id'],
        score=data['score'],
        review=data['review'] if 'review' in data else None,
        is_spoiler=data['is_spoiler'] if 'is_spoiler' in data else None,
    )
    return Response(RatingSerializer(rating).data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def watchlist_list(request):
    list_type = request.GET.get('list_type')
    queryset = selectors.get_user_watchlist(request.user, list_type=list_type)
    return Response(WatchlistItemSerializer(queryset, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def watchlist_toggle(request):
    input_serializer = WatchlistToggleInputSerializer(data=request.data)
    input_serializer.is_valid(raise_exception=True)
    data = input_serializer.validated_data
    added = services.toggle_watchlist(
        user=request.user,
        content_type=data['content_type'],
        object_id=data['object_id'],
        list_type=data['list_type'],
    )
    return Response({'added': added})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def likes_list(request):
    likes = selectors.get_user_likes(request.user)
    return Response([
        {
            'content_type': like.content_type,
            'object_id': like.object_id,
            # Embed the poster/title/slug so the library's «پسندیده‌ها» tab can
            # render cards. Without this, clients only knew *what* was liked, not
            # how to show it, so the favorites tab always came up empty.
            'content': selectors.resolve_content_summary(like.content_type, like.object_id),
            'created_at': like.created_at,
        }
        for like in likes
    ])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def watch_stats(request):
    """Lifetime + weekly watch-time story for the signed-in profile."""
    from .watch_stats import build_watch_stats

    return Response(build_watch_stats(request.user))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def like_toggle(request):
    input_serializer = LikeToggleInputSerializer(data=request.data)
    input_serializer.is_valid(raise_exception=True)
    data = input_serializer.validated_data
    liked = services.toggle_like(
        user=request.user,
        content_type=data['content_type'],
        object_id=data['object_id'],
    )
    return Response({'liked': liked})


@api_view(['GET', 'POST'])
def community_messages(request):
    """Site-wide lounge: anyone can read, only signed-in users can post.

    Lightweight by design: flat list, 30 newest, no threads. Rate-limited to
    one message per 5 seconds per user to keep it calm without moderation UI.
    Reads are cached for a few seconds: every open lounge polls, and without
    this each poll paid a full ORM + serialize round-trip on a busy host.
    """
    from django.core.cache import cache

    list_cache_key = 'community:messages:v1'
    list_cache_ttl = 15
    if request.method == 'GET':
        cached = cache.get(list_cache_key)
        if cached is not None:
            return Response({'messages': cached})
        messages = (
            CommunityMessage.objects
            .filter(is_hidden=False)
            .select_related('user')
            .order_by('-created_at')[:30]
        )
        # Chronological for rendering.
        data = CommunityMessageSerializer(reversed(list(messages)), many=True).data
        cache.set(list_cache_key, data, timeout=list_cache_ttl)
        return Response({'messages': data})

    if not request.user.is_authenticated:
        return Response({'detail': 'برای گفتگو وارد حساب شو.'}, status=status.HTTP_401_UNAUTHORIZED)
    serializer = CommunityMessageCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    cutoff = timezone.now() - timedelta(seconds=5)
    if CommunityMessage.objects.filter(user=request.user, created_at__gte=cutoff).exists():
        return Response({'detail': 'کمی صبر کن بعد دوباره بفرست.'}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    message = CommunityMessage.objects.create(
        user=request.user,
        body=serializer.validated_data['body'],
    )
    cache.delete(list_cache_key)
    return Response(CommunityMessageSerializer(message).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def support_ticket_list_create(request):
    if request.method == 'GET':
        tickets = selectors.get_user_support_tickets(request.user)
        return Response(SupportTicketListSerializer(tickets, many=True).data)

    serializer = SupportTicketCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    ticket = services.create_support_ticket(
        user=request.user,
        category=data['category'],
        subject=data['subject'],
        body=data['body'],
        related_title=data.get('related_title', ''),
        related_year=data.get('related_year'),
        related_url=data.get('related_url', ''),
    )
    return Response(SupportTicketSerializer(ticket).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def support_ticket_detail(request, tracking_code):
    ticket = selectors.get_support_ticket_for_user(request.user, tracking_code)
    if not ticket:
        return Response({'detail': 'پیام پیدا نشد.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        services.mark_ticket_read_by_user(ticket)
        ticket = selectors.get_support_ticket_for_user(request.user, tracking_code)
        return Response(SupportTicketSerializer(ticket).data)

    if ticket.status == ticket.Status.CLOSED:
        return Response({'detail': 'این گفتگو بسته شده است.'}, status=status.HTTP_400_BAD_REQUEST)

    serializer = SupportReplySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    services.reply_support_ticket(
        ticket=ticket,
        author=request.user,
        body=serializer.validated_data['body'],
        is_staff_reply=False,
    )
    ticket = selectors.get_support_ticket_for_user(request.user, tracking_code)
    return Response(SupportTicketSerializer(ticket).data)
