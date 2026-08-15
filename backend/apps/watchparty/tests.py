from datetime import timedelta

from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.catalog.models import Episode, Movie, Season, Series
from users.models import User

from .auth import JwtAuthMiddleware, SUBPROTOCOL_PREFIX
from .models import WatchRoom, WatchRoomMember, WatchRoomMessage, WatchRoomPlaybackState
from .routing import websocket_urlpatterns


IN_MEMORY_CHANNELS = {
    'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
}


def make_user(label):
    return User.objects.create_user(
        email=f'{label}@example.com',
        username=label,
        password='test-pass-123',
    )


def make_movie(**kwargs):
    defaults = {
        'title': 'Watch Party Movie',
        'slug': 'watch-party-movie',
        'is_published': True,
        'duration_minutes': 120,
        'video_url': 'movies/watch-party/hls/master.m3u8',
    }
    defaults.update(kwargs)
    return Movie.objects.create(**defaults)


def make_episode(**kwargs):
    series_kwargs = kwargs.pop('series_kwargs', {})
    season_kwargs = kwargs.pop('season_kwargs', {})
    series_defaults = {
        'title': 'Watch Party Series',
        'slug': 'watch-party-series',
        'is_published': True,
        'download_links': [],
    }
    series_defaults.update(series_kwargs)
    series = Series.objects.create(**series_defaults)
    season_defaults = {
        'series': series,
        'season_number': 1,
        'title': 'فصل ۱',
        'is_published': True,
    }
    season_defaults.update(season_kwargs)
    season = Season.objects.create(**season_defaults)
    episode_defaults = {
        'season': season,
        'episode_number': 1,
        'title': 'قسمت ۱',
        'is_published': True,
        'video_url': '',
    }
    episode_defaults.update(kwargs)
    return Episode.objects.create(**episode_defaults)


class WatchRoomModelTests(TestCase):
    def setUp(self):
        self.host = make_user('host')
        self.movie = make_movie()

    def test_room_requires_exactly_one_content_reference(self):
        room = WatchRoom.objects.create(host_user=self.host, movie=self.movie)
        self.assertTrue(room.is_joinable)
        self.assertGreaterEqual(len(room.invite_code), 20)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WatchRoom.objects.create(host_user=self.host)

    def test_room_allows_only_one_host_membership(self):
        second_user = make_user('second')
        room = WatchRoom.objects.create(host_user=self.host, movie=self.movie)
        WatchRoomMember.objects.create(room=room, user=self.host, role=WatchRoomMember.Role.HOST)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WatchRoomMember.objects.create(
                    room=room,
                    user=second_user,
                    role=WatchRoomMember.Role.HOST,
                )

    def test_content_payload_uses_download_links_when_video_url_missing(self):
        movie = make_movie(
            slug='watch-party-movie-download-links',
            video_url='',
            download_links=[{
                'label': '1080p',
                'quality': '1080p',
                'url': 'https://cdn.example.com/movie-1080.mp4',
            }],
        )
        room = WatchRoom.objects.create(host_user=self.host, movie=movie)
        from .services import content_payload
        payload = content_payload(room)
        self.assertEqual(payload['video_url'], 'https://cdn.example.com/movie-1080.mp4')
        self.assertEqual(len(payload['stream_links']), 1)

    def test_content_payload_preserves_absolute_episode_cdn_urls(self):
        absolute = (
            'https://cdn.example.com/yA3f/Series/Demo/S01E01.1080p.Farsi.Dubbed.mkv'
        )
        episode = make_episode(
            video_url=absolute,
            series_kwargs={
                'slug': 'watch-party-series-absolute-url',
                'download_links': [{
                    'label': '720p',
                    'quality': '720p',
                    'kind': 'dubbed',
                    'season_number': 1,
                    'episode_number': 1,
                    'url': 'https://cdn.example.com/yA3f/Series/Demo/S01E01.720p.Farsi.Dubbed.mkv',
                }, {
                    'label': '1080p',
                    'quality': '1080p',
                    'kind': 'dubbed',
                    'season_number': 1,
                    'episode_number': 1,
                    'url': absolute,
                }, {
                    'label': 'other-ep',
                    'quality': '1080p',
                    'kind': 'dubbed',
                    'season_number': 1,
                    'episode_number': 2,
                    'url': 'https://cdn.example.com/yA3f/Series/Demo/S01E02.1080p.mkv',
                }],
            },
        )
        room = WatchRoom.objects.create(host_user=self.host, episode=episode)
        from .services import content_payload
        payload = content_payload(room)
        urls = [link['url'] for link in payload['stream_links']]
        self.assertEqual(payload['type'], 'episode')
        self.assertIn(absolute, urls)
        self.assertIn(
            'https://cdn.example.com/yA3f/Series/Demo/S01E01.720p.Farsi.Dubbed.mkv',
            urls,
        )
        self.assertNotIn(
            'https://cdn.example.com/yA3f/Series/Demo/S01E02.1080p.mkv',
            urls,
        )
        self.assertFalse(any('revayato.com/media/' in url for url in urls))
        self.assertEqual(len(payload['stream_links']), 2)


@override_settings(CHANNEL_LAYERS=IN_MEMORY_CHANNELS)
class WatchRoomApiTests(TestCase):
    def setUp(self):
        self.host = make_user('api-host')
        self.member = make_user('api-member')
        self.movie = make_movie(slug='api-watch-party-movie')
        self.client = APIClient()

    def create_room(self):
        self.client.force_authenticate(self.host)
        return self.client.post('/api/watch-party/rooms/', {
            'content_type': 'movie',
            'content_id': self.movie.pk,
        }, format='json')

    def test_authentication_is_required_to_create_and_join(self):
        response = self.client.post('/api/watch-party/rooms/', {
            'content_type': 'movie',
            'content_id': self.movie.pk,
        }, format='json')
        self.assertEqual(response.status_code, 401)

        created = self.create_room()
        self.client.force_authenticate(user=None)
        joined = self.client.post(
            f"/api/watch-party/rooms/{created.json()['invite_code']}/join/",
            format='json',
        )
        self.assertEqual(joined.status_code, 401)

    def test_host_can_create_and_member_can_join(self):
        created = self.create_room()
        self.assertEqual(created.status_code, 201)
        code = created.json()['invite_code']
        room = WatchRoom.objects.get(invite_code=code)
        self.assertEqual(room.host_user, self.host)
        self.assertTrue(room.members.filter(user=self.host, role='host').exists())
        self.assertTrue(hasattr(room, 'playback_state'))

        self.client.force_authenticate(self.member)
        joined = self.client.post(f'/api/watch-party/rooms/{code}/join/', format='json')
        self.assertEqual(joined.status_code, 200)
        self.assertTrue(joined.json()['is_member'])
        self.assertTrue(room.members.filter(user=self.member, role='member').exists())

    def test_draft_content_cannot_create_a_room(self):
        draft = make_movie(title='Draft', slug='draft-party', is_published=False)
        self.client.force_authenticate(self.host)
        response = self.client.post('/api/watch-party/rooms/', {
            'content_type': 'movie',
            'content_id': draft.pk,
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_non_host_cannot_end_room(self):
        created = self.create_room()
        code = created.json()['invite_code']
        self.client.force_authenticate(self.member)
        self.client.post(f'/api/watch-party/rooms/{code}/join/', format='json')
        response = self.client.post(f'/api/watch-party/rooms/{code}/end/', format='json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(WatchRoom.objects.get(invite_code=code).status, WatchRoom.Status.ACTIVE)

    def test_ended_and_expired_rooms_reject_join(self):
        created = self.create_room()
        room = WatchRoom.objects.get(invite_code=created.json()['invite_code'])
        room.status = WatchRoom.Status.ENDED
        room.save(update_fields=['status'])
        self.client.force_authenticate(self.member)
        ended = self.client.post(f'/api/watch-party/rooms/{room.invite_code}/join/', format='json')
        self.assertEqual(ended.status_code, 410)

        room.status = WatchRoom.Status.ACTIVE
        room.expires_at = timezone.now() - timedelta(seconds=1)
        room.save(update_fields=['status', 'expires_at'])
        expired = self.client.post(f'/api/watch-party/rooms/{room.invite_code}/join/', format='json')
        self.assertEqual(expired.status_code, 410)
        room.refresh_from_db()
        self.assertEqual(room.status, WatchRoom.Status.EXPIRED)


@override_settings(CHANNEL_LAYERS=IN_MEMORY_CHANNELS)
class WatchPartyWebSocketTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.host = make_user('socket-host')
        self.member = make_user('socket-member')
        self.movie = make_movie(slug='socket-watch-party-movie')
        self.room = WatchRoom.objects.create(host_user=self.host, movie=self.movie)
        WatchRoomMember.objects.create(
            room=self.room,
            user=self.host,
            role=WatchRoomMember.Role.HOST,
        )
        WatchRoomMember.objects.create(room=self.room, user=self.member)
        WatchRoomPlaybackState.objects.create(room=self.room, duration_seconds=7200)
        self.application = JwtAuthMiddleware(URLRouter(websocket_urlpatterns))

    def communicator(self, user):
        protocol = f'{SUBPROTOCOL_PREFIX}{AccessToken.for_user(user)}'
        return WebsocketCommunicator(
            self.application,
            f'/ws/watch-party/{self.room.invite_code}/',
            subprotocols=[protocol],
        )

    async def receive_type(self, communicator, expected_type, attempts=8):
        for _index in range(attempts):
            response = await communicator.receive_json_from(timeout=2)
            if response.get('type') == expected_type:
                return response
        self.fail(f'Did not receive event type {expected_type!r}.')

    async def test_chat_playback_permissions_and_late_join_state(self):
        host_socket = self.communicator(self.host)
        connected, _protocol = await host_socket.connect()
        self.assertTrue(connected)
        initial = await self.receive_type(host_socket, 'room.state')
        self.assertEqual(initial['playback_state']['position_seconds'], 0)

        member_socket = self.communicator(self.member)
        connected, _protocol = await member_socket.connect()
        self.assertTrue(connected)
        await self.receive_type(member_socket, 'room.state')

        await member_socket.send_json_to({
            'type': 'playback.play',
            'position_seconds': 10,
            'duration_seconds': 7200,
            'playback_rate': 1,
        })
        rejected = await self.receive_type(member_socket, 'error')
        self.assertEqual(rejected['code'], 'host_only')

        await host_socket.send_json_to({
            'type': 'playback.play',
            'position_seconds': 42,
            'duration_seconds': 7200,
            'playback_rate': 1,
        })
        playback_event = await self.receive_type(member_socket, 'playback.play')
        self.assertEqual(playback_event['playback_state']['position_seconds'], 42)
        self.assertIn('server_time_ms', playback_event['playback_state'])

        await host_socket.send_json_to({
            'type': 'playback.sync',
            'is_playing': True,
            'position_seconds': 47,
            'duration_seconds': 7200,
            'playback_rate': 1,
        })
        sync_event = await self.receive_type(member_socket, 'playback.sync')
        self.assertEqual(sync_event['playback_state']['position_seconds'], 47)
        self.assertIn('server_time_ms', sync_event['playback_state'])

        # Tiny heartbeat sync should still broadcast live position without lagging members.
        await host_socket.send_json_to({
            'type': 'playback.sync',
            'is_playing': True,
            'position_seconds': 47.2,
            'duration_seconds': 7200,
            'playback_rate': 1,
        })
        heartbeat = await self.receive_type(member_socket, 'playback.sync')
        self.assertAlmostEqual(heartbeat['playback_state']['position_seconds'], 47.2, places=1)

        await host_socket.send_json_to({
            'type': 'latency.ping',
            'client_time_ms': 123456,
        })
        pong = await self.receive_type(host_socket, 'latency.pong')
        self.assertEqual(pong['client_time_ms'], 123456)
        self.assertIsInstance(pong['server_time_ms'], int)

        await member_socket.send_json_to({'type': 'chat.message', 'message': '<b>Hello</b>'})
        chat_event = await self.receive_type(host_socket, 'chat.message')
        self.assertEqual(chat_event['message']['message'], 'Hello')
        message_count = await database_sync_to_async(WatchRoomMessage.objects.count)()
        self.assertEqual(message_count, 1)

        await member_socket.disconnect()
        reconnect = self.communicator(self.member)
        connected, _protocol = await reconnect.connect()
        self.assertTrue(connected)
        late_state = await self.receive_type(reconnect, 'room.state')
        self.assertTrue(late_state['playback_state']['is_playing'])
        self.assertEqual(late_state['playback_state']['position_seconds'], 47)

        await reconnect.disconnect()
        await host_socket.disconnect()

    async def test_unauthenticated_socket_is_rejected(self):
        communicator = WebsocketCommunicator(
            self.application,
            f'/ws/watch-party/{self.room.invite_code}/',
        )
        connected, close_code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)
