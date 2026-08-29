import math
import time
from collections import deque

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.db import transaction
from django.utils import timezone

from .models import WatchRoom, WatchRoomMember, WatchRoomMessage, WatchRoomPlaybackState
from .serializers import ChatMessageInputSerializer, WatchRoomMessageSerializer
from .services import (
    allowed_stream_urls,
    ephemeral_playback_payload,
    expire_room_if_needed,
    member_payload,
    playback_payload,
    room_payload,
    room_queryset,
    user_can_access_room_content,
)


class WatchPartyConsumer(AsyncJsonWebsocketConsumer):
    CHAT_LIMIT = (5, 10)
    PLAYBACK_LIMIT = (36, 6)
    SYNC_PERSIST_SECONDS = 8
    SYNC_PERSIST_POSITION_DELTA = 0.75

    async def connect(self):
        self.user = self.scope.get('user')
        self.invite_code = self.scope['url_route']['kwargs']['invite_code']
        self.group_name = f'watchparty.{self.invite_code}'
        self._rate_windows = {'chat': deque(), 'playback': deque(), 'latency': deque()}
        self._connected = False

        if not self.user or not self.user.is_authenticated:
            await self.close(code=4401)
            return

        state, close_code = await self._connect_state()
        if not state:
            await self.close(code=close_code)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept(subprotocol=self.scope.get('watchparty_subprotocol'))
        self._connected = True
        await self.send_json(state)
        await self.send_json({
            'type': 'playback.state',
            'playback_state': state['playback_state'],
        })
        await self.channel_layer.group_send(self.group_name, {
            'type': 'watchparty.event',
            'payload': {'type': 'member.joined', 'member': state['current_member']},
        })

    async def disconnect(self, close_code):
        if not getattr(self, '_connected', False):
            return
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        member = await self._mark_offline()
        if member:
            await self.channel_layer.group_send(self.group_name, {
                'type': 'watchparty.event',
                'payload': {'type': 'member.left', 'member': member},
            })
        self._connected = False

    async def receive_json(self, content, **kwargs):
        event_type = content.get('type')
        if event_type == 'room.join':
            state = await self._room_state()
            if state:
                await self.send_json(state)
            else:
                await self._error('room_unavailable', 'This watch party is no longer available.')
            return
        if event_type == 'room.leave':
            await self.close(code=1000)
            return
        if event_type == 'heartbeat':
            if not await self._heartbeat():
                await self.close(code=4403)
            return
        if event_type == 'latency.ping':
            await self._handle_latency_ping(content)
            return
        if event_type == 'chat.message':
            await self._handle_chat(content)
            return
        if event_type in {'playback.play', 'playback.pause', 'playback.seek', 'playback.sync'}:
            await self._handle_playback(event_type, content)
            return
        if event_type == 'playback.sync.request':
            playback = await self._current_playback()
            if playback:
                await self.send_json({
                    'type': 'playback.sync.response',
                    'playback_state': playback,
                })
                # Persisted sync snapshots are deliberately throttled. Also ask
                # the connected host for its exact in-memory player state so a
                # late join/reconnect does not visibly jump to an older position.
                await self.channel_layer.group_send(self.group_name, {
                    'type': 'watchparty.event',
                    'payload': {'type': 'playback.sync.requested'},
                    'sender_channel': self.channel_name,
                })
            else:
                await self._error('room_unavailable', 'This watch party is no longer available.')
            return
        await self._error('unsupported_event', 'Unsupported watch-party event.')

    async def _handle_chat(self, content):
        if not self._allow('chat', *self.CHAT_LIMIT):
            await self._error('rate_limited', 'Please wait before sending another message.')
            return
        message, error = await self._create_message(content.get('message'))
        if error:
            await self._error(error[0], error[1])
            return
        await self.channel_layer.group_send(self.group_name, {
            'type': 'watchparty.event',
            'payload': {'type': 'chat.message', 'message': message},
        })

    async def _handle_playback(self, event_type, content):
        if not self._allow('playback', *self.PLAYBACK_LIMIT):
            await self._error('rate_limited', 'Playback updates are arriving too quickly.')
            return
        playback, error = await self._update_playback(event_type, content)
        if error:
            await self._error(error[0], error[1])
            return
        await self.channel_layer.group_send(self.group_name, {
            'type': 'watchparty.event',
            'payload': {'type': event_type, 'playback_state': playback},
            'sender_channel': self.channel_name,
        })

    async def _handle_latency_ping(self, content):
        if not self._allow('latency', 10, 10):
            return
        try:
            client_time_ms = float(content.get('client_time_ms'))
        except (TypeError, ValueError):
            return
        if not math.isfinite(client_time_ms):
            return
        await self.send_json({
            'type': 'latency.pong',
            'client_time_ms': int(client_time_ms),
            'server_time_ms': int(time.time() * 1000),
        })

    async def watchparty_event(self, event):
        if event.get('sender_channel') == self.channel_name:
            return
        await self.send_json(event['payload'])
        if event.get('close'):
            await self.close(code=4000)

    async def _error(self, code, message):
        await self.send_json({'type': 'error', 'code': code, 'message': message})

    def _allow(self, bucket, limit, window_seconds):
        now = time.monotonic()
        timestamps = self._rate_windows[bucket]
        while timestamps and now - timestamps[0] >= window_seconds:
            timestamps.popleft()
        if len(timestamps) >= limit:
            return False
        timestamps.append(now)
        return True

    @database_sync_to_async
    def _connect_state(self):
        try:
            room = room_queryset().get(invite_code=self.invite_code)
        except WatchRoom.DoesNotExist:
            return None, 4404
        expire_room_if_needed(room)
        if not room.is_joinable:
            return None, 4409
        if not user_can_access_room_content(self.user, room):
            return None, 4403
        member = next((item for item in room.members.all() if item.user_id == self.user.pk), None)
        if not member:
            return None, 4403
        member.is_online = True
        member.last_seen_at = timezone.now()
        member.save(update_fields=['is_online', 'last_seen_at'])
        state = self._serialize_room_state(room, member)
        return state, None

    @database_sync_to_async
    def _room_state(self):
        try:
            room = room_queryset().get(invite_code=self.invite_code)
        except WatchRoom.DoesNotExist:
            return None
        expire_room_if_needed(room)
        if not room.is_joinable or not user_can_access_room_content(self.user, room):
            return None
        member = next((item for item in room.members.all() if item.user_id == self.user.pk), None)
        if not member:
            return None
        return self._serialize_room_state(room, member)

    def _serialize_room_state(self, room, current_member):
        state, _created = WatchRoomPlaybackState.objects.get_or_create(room=room)
        messages = list(
            room.messages.filter(is_deleted=False).select_related('user').order_by('-created_at')[:50]
        )
        messages.reverse()
        members = list(
            WatchRoomMember.objects.filter(room=room).select_related('user').order_by('role', 'joined_at')
        )
        return {
            'type': 'room.state',
            'room': room_payload(room, self.user),
            'members': [member_payload(item) for item in members],
            'messages': WatchRoomMessageSerializer(messages, many=True).data,
            'playback_state': playback_payload(state),
            'current_member': member_payload(current_member),
        }

    @database_sync_to_async
    def _mark_offline(self):
        try:
            member = WatchRoomMember.objects.select_related('user').get(
                room__invite_code=self.invite_code,
                user=self.user,
            )
        except WatchRoomMember.DoesNotExist:
            return None
        member.is_online = False
        member.last_seen_at = timezone.now()
        member.save(update_fields=['is_online', 'last_seen_at'])
        return member_payload(member)

    @database_sync_to_async
    def _heartbeat(self):
        updated = WatchRoomMember.objects.filter(
            room__invite_code=self.invite_code,
            room__status=WatchRoom.Status.ACTIVE,
            room__expires_at__gt=timezone.now(),
            user=self.user,
        ).update(last_seen_at=timezone.now(), is_online=True)
        return bool(updated)

    @database_sync_to_async
    def _create_message(self, raw_message):
        serializer = ChatMessageInputSerializer(data={'message': raw_message})
        if not serializer.is_valid():
            first_error = next(iter(serializer.errors.values()))[0]
            return None, ('invalid_message', str(first_error))
        try:
            room = WatchRoom.objects.get(invite_code=self.invite_code)
        except WatchRoom.DoesNotExist:
            return None, ('room_unavailable', 'This watch party no longer exists.')
        expire_room_if_needed(room)
        if not room.is_joinable:
            return None, ('room_inactive', 'This watch party is no longer active.')
        if not WatchRoomMember.objects.filter(room=room, user=self.user).exists():
            return None, ('not_a_member', 'Join the room before sending messages.')
        message = WatchRoomMessage.objects.create(
            room=room,
            user=self.user,
            message=serializer.validated_data['message'],
        )
        message.user = self.user
        return WatchRoomMessageSerializer(message).data, None

    @database_sync_to_async
    def _current_playback(self):
        try:
            room = WatchRoom.objects.get(invite_code=self.invite_code)
        except WatchRoom.DoesNotExist:
            return None
        expire_room_if_needed(room)
        if not room.is_joinable:
            return None
        if not WatchRoomMember.objects.filter(room=room, user=self.user).exists():
            return None
        state, _created = WatchRoomPlaybackState.objects.get_or_create(room=room)
        return playback_payload(state)

    @database_sync_to_async
    def _update_playback(self, event_type, content):
        try:
            position = float(content.get('position_seconds', 0))
            duration = float(content.get('duration_seconds', 0))
            rate = float(content.get('playback_rate', 1))
        except (TypeError, ValueError):
            return None, ('invalid_playback', 'Playback values must be numeric.')
        if not all(math.isfinite(value) for value in (position, duration, rate)):
            return None, ('invalid_playback', 'Playback values must be finite.')
        if position < 0 or position > 86400 or duration < 0 or duration > 86400:
            return None, ('invalid_playback', 'Playback position or duration is out of range.')
        if rate < 0.25 or rate > 4:
            return None, ('invalid_playback', 'Playback rate is out of range.')
        if duration > 0:
            position = min(position, duration)

        requested_stream = str(content.get('stream_url') or '').strip()[:2000]

        with transaction.atomic():
            try:
                room = WatchRoom.objects.select_for_update().get(invite_code=self.invite_code)
            except WatchRoom.DoesNotExist:
                return None, ('room_unavailable', 'This watch party no longer exists.')
            expire_room_if_needed(room)
            if not room.is_joinable:
                return None, ('room_inactive', 'This watch party is no longer active.')
            if room.host_user_id != self.user.pk:
                return None, ('host_only', 'Only the host can control playback.')
            current, _created = WatchRoomPlaybackState.objects.select_for_update().get_or_create(room=room)
            if event_type == 'playback.play':
                is_playing = True
            elif event_type == 'playback.pause':
                is_playing = False
            else:
                is_playing = bool(content.get('is_playing', current.is_playing))

            allowed = allowed_stream_urls(room)
            stream_url = None
            if requested_stream:
                if requested_stream not in allowed:
                    return None, ('invalid_stream', 'Stream URL is not allowed for this room.')
                stream_url = requested_stream
            else:
                primary = (room_payload(room).get('content') or {}).get('video_url') or ''
                stream_url = primary if primary in allowed else None

            age = (timezone.now() - current.updated_at).total_seconds() if current.updated_at else 999
            significant = (
                event_type != 'playback.sync'
                or current.is_playing != is_playing
                or abs(current.position_seconds - position) >= self.SYNC_PERSIST_POSITION_DELTA
                or abs(current.playback_rate - rate) >= 0.01
                or (duration > 0 and abs(current.duration_seconds - duration) >= 1)
                or bool(requested_stream)
                or age >= self.SYNC_PERSIST_SECONDS
            )
            if significant:
                current.is_playing = is_playing
                current.position_seconds = position
                current.duration_seconds = duration
                current.playback_rate = rate
                current.updated_by = self.user
                current.save(update_fields=[
                    'is_playing', 'position_seconds', 'duration_seconds',
                    'playback_rate', 'updated_by', 'updated_at',
                ])
                return playback_payload(current, stream_url=stream_url), None

            return ephemeral_playback_payload(
                user=self.user,
                is_playing=is_playing,
                position_seconds=position,
                duration_seconds=duration or current.duration_seconds,
                playback_rate=rate,
                stream_url=stream_url,
            ), None
