"""Database-backed admin dashboard API tests."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import Episode, Movie, Season, Series
from apps.engagement.models import Like, Rating, UserActivityEvent, WatchlistItem

User = get_user_model()


class AdminDashboardApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            email='dashboard-staff@example.com',
            username='dashboard-staff',
            password='test-pass-123',
            is_staff=True,
            is_verified=True,
        )
        self.member = User.objects.create_user(
            email='dashboard-member@example.com',
            username='dashboard-member',
            password='test-pass-123',
        )
        self.movie = Movie.objects.create(
            title='Dashboard Movie',
            slug='dashboard-movie',
            publication_status=Movie.PublicationStatus.PUBLISHED,
            is_published=True,
            is_featured=True,
            media_status='ready',
            view_count=19,
        )
        self.series = Series.objects.create(
            title='Dashboard Series',
            slug='dashboard-series',
            is_published=True,
            view_count=7,
        )
        season = Season.objects.create(
            series=self.series,
            season_number=1,
            title='Season 1',
            is_published=True,
        )
        Episode.objects.create(
            season=season,
            episode_number=1,
            title='Episode 1',
            is_published=True,
            view_count=3,
        )

    def create_event(self, *, action, content_type='movie', object_id=None, user=None, days_ago=0, query=''):
        event = UserActivityEvent.objects.create(
            user=user,
            session_key='dashboard-anonymous-session' if user is None else '',
            content_type=content_type,
            object_id=object_id,
            action=action,
            query=query,
            metadata={'result_count': 0} if query else {},
        )
        created_at = timezone.now() - timedelta(days=days_ago)
        UserActivityEvent.objects.filter(pk=event.pk).update(created_at=created_at)
        event.created_at = created_at
        return event

    def test_non_staff_is_denied(self):
        self.client.force_authenticate(self.member)
        response = self.client.get('/api/admin/dashboard/')
        self.assertEqual(response.status_code, 403)

    def test_dashboard_returns_exact_database_aggregates(self):
        self.create_event(
            action='view_movie',
            object_id=self.movie.pk,
            user=self.member,
            days_ago=1,
        )
        self.create_event(
            action='play',
            object_id=self.movie.pk,
            user=self.member,
            days_ago=1,
        )
        self.create_event(
            action='complete_watch',
            object_id=self.movie.pk,
            user=self.member,
            days_ago=1,
        )
        self.create_event(
            action='search',
            content_type='search',
            user=None,
            days_ago=1,
            query='فیلم بی‌نتیجه',
        )
        self.create_event(
            action='view_movie',
            object_id=self.movie.pk,
            user=self.member,
            days_ago=35,
        )
        Rating.objects.create(
            user=self.member,
            content_type='movie',
            object_id=self.movie.pk,
            score='8.0',
        )
        Like.objects.create(
            user=self.member,
            content_type='movie',
            object_id=self.movie.pk,
        )
        WatchlistItem.objects.create(
            user=self.member,
            content_type='movie',
            object_id=self.movie.pk,
        )

        self.client.force_authenticate(self.staff)
        response = self.client.get('/api/admin/dashboard/', {'days': 30})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(response.data['period']['days'], 30)
        self.assertEqual(response.data['summary']['tracked_views']['current'], 1)
        self.assertEqual(response.data['summary']['tracked_views']['previous'], 1)
        self.assertEqual(response.data['summary']['playback_events']['current'], 1)
        self.assertEqual(response.data['summary']['completed_views']['current'], 1)
        self.assertEqual(response.data['summary']['active_users']['current'], 1)
        self.assertEqual(response.data['summary']['recorded_audience']['current'], 2)
        self.assertEqual(response.data['catalog']['movies']['published'], 1)
        self.assertEqual(response.data['catalog']['movies']['recorded_views'], 19)
        self.assertEqual(response.data['catalog']['series']['recorded_views'], 7)
        self.assertEqual(response.data['catalog']['episodes']['recorded_views'], 3)
        self.assertEqual(response.data['engagement']['ratings_total'], 1)
        self.assertEqual(response.data['engagement']['likes_total'], 1)
        self.assertEqual(response.data['engagement']['watchlist_total'], 1)
        self.assertEqual(response.data['tracking']['events_in_period'], 4)
        self.assertEqual(response.data['tracking']['identified_events_in_period'], 3)
        self.assertEqual(response.data['tracking']['anonymous_events_in_period'], 1)
        self.assertEqual(response.data['tracking']['anonymous_sessions_in_period'], 1)
        self.assertEqual(response.data['trend'][-2]['recorded_audience'], 2)
        self.assertEqual(response.data['top_content'][0]['title'], self.movie.title)
        self.assertEqual(response.data['top_searches'][0]['query'], 'فیلم بی‌نتیجه')
        self.assertEqual(response.data['top_searches'][0]['zero_result_count'], 1)
        self.assertEqual(len(response.data['trend']), 30)
        self.assertEqual(len(response.data['hourly']), 24)
        self.assertIn('view_to_play', response.data['funnel'])
        self.assertEqual(response.data['funnel']['stages'][0]['count'], 1)
        self.assertIn('alerts', response.data['health'])
        self.assertTrue(response.data['watchparty']['available'])
        self.assertGreaterEqual(response.data['summary']['searches']['current'], 1)
        self.assertTrue(any(row['action'] == 'search' for row in response.data['actions']))

    def test_invalid_period_falls_back_to_thirty_days(self):
        self.client.force_authenticate(self.staff)
        response = self.client.get('/api/admin/dashboard/', {'days': '12'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['period']['days'], 30)
