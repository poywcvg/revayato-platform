import logging
import re

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import WatchRoom, WatchRoomMember, WatchRoomPlaybackState
from .serializers import (
    WatchRoomCreateSerializer,
    WatchRoomMessageSerializer,
    WatchRoomSerializer,
)
from .services import expire_room_if_needed, room_queryset, user_can_access_room_content
from .throttles import WatchPartyCreateThrottle, WatchPartyJoinThrottle


INVITE_CODE_PATTERN = re.compile(r'^[A-Za-z0-9_-]{20,32}$')
logger = logging.getLogger(__name__)


def _room_or_404(invite_code, *, for_update=False):
    if not INVITE_CODE_PATTERN.fullmatch(invite_code):
        return get_object_or_404(WatchRoom, pk=-1)
    queryset = room_queryset()
    if for_update:
        queryset = queryset.select_for_update()
    return get_object_or_404(queryset, invite_code=invite_code)


def _room_response(room, request, response_status=status.HTTP_200_OK):
    room = room_queryset().get(pk=room.pk)
    return Response(
        WatchRoomSerializer(room, context={'request': request}).data,
        status=response_status,
    )


def _inactive_response(room):
    return Response(
        {'detail': f'This watch party is {room.status}.', 'status': room.status},
        status=status.HTTP_410_GONE,
    )


def _broadcast(invite_code, payload, *, close=False):
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    try:
        async_to_sync(channel_layer.group_send)(
            f'watchparty.{invite_code}',
            {'type': 'watchparty.event', 'payload': payload, 'close': close},
        )
    except Exception:
        logger.exception('Unable to broadcast watch-party event for room %s.', invite_code)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([WatchPartyCreateThrottle])
def create_room(request):
    serializer = WatchRoomCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    content = serializer.validated_data['content_object']

    with transaction.atomic():
        room_kwargs = {
            'host_user': request.user,
            'expires_at': serializer.expiry(),
        }
        room_kwargs[serializer.validated_data['content_type']] = content
        room = WatchRoom.objects.create(**room_kwargs)
        WatchRoomMember.objects.create(
            room=room,
            user=request.user,
            role=WatchRoomMember.Role.HOST,
            last_seen_at=timezone.now(),
        )
        WatchRoomPlaybackState.objects.create(
            room=room,
            duration_seconds=(content.duration_minutes or 0) * 60,
            updated_by=request.user,
        )

    return _room_response(room, request, status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_room(request, invite_code):
    room = expire_room_if_needed(_room_or_404(invite_code))
    if not user_can_access_room_content(request.user, room):
        return Response({'detail': 'You cannot access this content.'}, status=status.HTTP_403_FORBIDDEN)
    return _room_response(room, request)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([WatchPartyJoinThrottle])
def join_room(request, invite_code):
    with transaction.atomic():
        room = expire_room_if_needed(_room_or_404(invite_code, for_update=True))
        if not room.is_joinable:
            return _inactive_response(room)
        if not user_can_access_room_content(request.user, room):
            return Response({'detail': 'You cannot access this content.'}, status=status.HTTP_403_FORBIDDEN)

        membership = WatchRoomMember.objects.filter(room=room, user=request.user).first()
        if not membership and room.members.count() >= getattr(settings, 'WATCH_PARTY_MAX_MEMBERS', 20):
            return Response({'detail': 'This watch party is full.'}, status=status.HTTP_409_CONFLICT)
        if membership:
            membership.last_seen_at = timezone.now()
            membership.save(update_fields=['last_seen_at'])
        else:
            WatchRoomMember.objects.create(
                room=room,
                user=request.user,
                role=(
                    WatchRoomMember.Role.HOST
                    if room.host_user_id == request.user.pk
                    else WatchRoomMember.Role.MEMBER
                ),
                last_seen_at=timezone.now(),
            )

    return _room_response(room, request)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def leave_room(request, invite_code):
    room = expire_room_if_needed(_room_or_404(invite_code))
    membership = WatchRoomMember.objects.filter(room=room, user=request.user).first()
    if not membership:
        return Response(status=status.HTTP_204_NO_CONTENT)
    if room.host_user_id == request.user.pk and room.status == WatchRoom.Status.ACTIVE:
        return Response(
            {'detail': 'The host must end the room instead of leaving it.'},
            status=status.HTTP_409_CONFLICT,
        )
    membership.delete()
    _broadcast(invite_code, {'type': 'member.left', 'user_id': request.user.pk})
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def recent_messages(request, invite_code):
    room = expire_room_if_needed(_room_or_404(invite_code))
    if not WatchRoomMember.objects.filter(room=room, user=request.user).exists():
        return Response({'detail': 'Join the room before reading messages.'}, status=status.HTTP_403_FORBIDDEN)
    try:
        limit = min(max(int(request.query_params.get('limit', 50)), 1), 100)
    except (TypeError, ValueError):
        limit = 50
    messages = list(
        room.messages.filter(is_deleted=False).select_related('user').order_by('-created_at')[:limit]
    )
    messages.reverse()
    return Response(WatchRoomMessageSerializer(messages, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def end_room(request, invite_code):
    with transaction.atomic():
        room = _room_or_404(invite_code, for_update=True)
        if room.host_user_id != request.user.pk:
            return Response({'detail': 'Only the host can end this room.'}, status=status.HTTP_403_FORBIDDEN)
        expire_room_if_needed(room)
        if room.status == WatchRoom.Status.ACTIVE:
            room.status = WatchRoom.Status.ENDED
            room.save(update_fields=['status'])
        room.members.filter(is_online=True).update(is_online=False, last_seen_at=timezone.now())

    _broadcast(
        invite_code,
        {'type': 'room.state', 'room': {'invite_code': room.invite_code, 'status': room.status}},
        close=True,
    )
    return _room_response(room, request)
