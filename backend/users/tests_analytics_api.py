"""Tests for /api/analytics/* staff endpoints."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.engagement.models import UserActivityEvent
from apps.watchparty.models import WatchRoom, WatchRoomMember
from users.presence import touch_presence

User = get_user_model()


class AnalyticsApiTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username='analytics-staff',
            email='analytics-staff@example.com',
            password='pass12345',
            is_staff=True,
        )
        self.member = User.objects.create_user(
            username='analytics-member',
            email='analytics-member@example.com',
            password='pass12345',
        )
        UserActivityEvent.objects.create(
            user=self.member,
            action='play',
            content_type='movie',
            object_id=1,
            device_type='mobile',
            progress=40,
        )
        UserActivityEvent.objects.create(
            user=self.member,
            action='complete_watch',
            content_type='movie',
            object_id=1,
            device_type='desktop',
            progress=100,
        )
        UserActivityEvent.objects.create(
            user=self.member,
            action='search',
            content_type='search',
            query='ماتریکس',
            device_type='desktop',
            metadata={'result_count': 3},
        )

    def test_requires_staff(self):
        self.client.force_authenticate(self.member)
        response = self.client.get('/api/analytics/overview/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_overview_envelope(self):
        self.client.force_authenticate(self.staff)
        response = self.client.get('/api/analytics/overview/', {'period': '30d'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertIn('data', body)
        self.assertIn('period', body)
        self.assertIn('generated_at', body)
        self.assertEqual(body['period']['days'], 30)
        self.assertEqual(body['period']['key'], '30d')
        self.assertIn('start', body['period'])
        self.assertIn('end', body['period'])
        self.assertEqual(body.get('source'), 'database')
        kpi_ids = {item['id'] for item in body['data']['kpis']}
        self.assertTrue({'total_users', 'active_users', 'watch_hours'}.issubset(kpi_ids))
        self.assertIn('realtime', body['data'])
        self.assertIn('catalog', body['data'])
        realtime = body['data']['realtime']
        self.assertIn('online_users', realtime)
        self.assertIn('online_guests', realtime)
        self.assertIn('sources', realtime)
        # Must not invent live rooms from stale ACTIVE status alone.
        self.assertGreaterEqual(realtime['online_users'], 0)
        self.assertGreaterEqual(realtime['active_watch_rooms'], 0)

    def test_users_content_engagement(self):
        self.client.force_authenticate(self.staff)
        users = self.client.get('/api/analytics/users/', {'period': '7d', 'granularity': 'daily'})
        self.assertEqual(users.status_code, status.HTTP_200_OK)
        users_body = users.json()['data']
        self.assertIn('registrations', users_body)
        self.assertEqual(users_body['registrations']['granularity'], 'daily')
        self.assertIn('totals', users_body)
        self.assertIn('top_active_users', users_body)

        content = self.client.get('/api/analytics/content/top/', {'period': '30d'})
        self.assertEqual(content.status_code, status.HTTP_200_OK)
        content_body = content.json()['data']
        self.assertIn('top_watched', content_body)
        self.assertIn('heatmap', content_body)
        self.assertIn('catalog', content_body)

        engagement = self.client.get('/api/analytics/engagement/', {'period': '30d'})
        self.assertEqual(engagement.status_code, status.HTTP_200_OK)
        engagement_body = engagement.json()['data']
        self.assertIn('search_terms', engagement_body)
        self.assertIn('completion_by_content', engagement_body)
        self.assertTrue(any(term['term'] == 'ماتریکس' for term in engagement_body['search_terms']))

    def test_realtime_ignores_stale_watch_rooms(self):
        from apps.catalog.models import Movie

        self.client.force_authenticate(self.staff)
        movie = Movie.objects.create(
            title='Analytics Stale Room Movie',
            slug='analytics-stale-room-movie',
            is_published=True,
        )
        room = WatchRoom.objects.create(
            host_user=self.member,
            movie=movie,
            status=WatchRoom.Status.ACTIVE,
            expires_at=timezone.now() - timedelta(hours=2),
        )
        WatchRoomMember.objects.create(
            room=room,
            user=self.member,
            role=WatchRoomMember.Role.HOST,
            is_online=True,
            last_seen_at=timezone.now() - timedelta(days=2),
        )
        touch_presence(user_id=self.staff.pk)
        touch_presence(anonymous_session_id='anon-test-session-01')

        response = self.client.get('/api/analytics/overview/', {'period': '7d'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        realtime = response.json()['data']['realtime']
        self.assertEqual(realtime['active_watch_rooms'], 0)
        self.assertEqual(realtime['live_watch_sessions'], 0)
        # Presence heartbeat + any fresh DB signals; never invented from stale rooms.
        self.assertGreaterEqual(realtime['online_users'], 0)
        self.assertIn('sources', realtime)
        room.refresh_from_db()
        self.assertEqual(room.status, WatchRoom.Status.EXPIRED)

        presence = self.client.post(
            '/api/analytics/presence/',
            {'anonymous_session_id': 'anon-test-session-02'},
            format='json',
        )
        self.assertEqual(presence.status_code, status.HTTP_200_OK)
        self.assertTrue(presence.json().get('ok'))
