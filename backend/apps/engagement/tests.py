from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.models import Movie

from . import selectors, services
from .models import Like, Rating, UserActivityEvent, WatchlistItem

User = get_user_model()


class EngagementServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='tester', email='tester@example.com', password='pass12345',
        )
        self.movie = Movie.objects.create(title='Test Movie', slug='test-movie')

    def test_rate_content_creates_and_updates_site_rating(self):
        rating = services.rate_content(self.user, 'movie', self.movie.pk, score=8)
        self.assertEqual(Rating.objects.count(), 1)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.site_rating, 8)

        services.rate_content(self.user, 'movie', self.movie.pk, score=6)
        self.assertEqual(Rating.objects.count(), 1)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.site_rating, 6)
        self.assertEqual(rating.content_type, 'movie')

    def test_remove_rating_recomputes_site_rating(self):
        services.rate_content(self.user, 'movie', self.movie.pk, score=10)
        removed = services.remove_rating(self.user, 'movie', self.movie.pk)
        self.assertTrue(removed)
        self.movie.refresh_from_db()
        self.assertIsNone(self.movie.site_rating)

    def test_toggle_watchlist_adds_and_removes(self):
        added = services.toggle_watchlist(self.user, 'movie', self.movie.pk, WatchlistItem.ListType.WATCHLIST)
        self.assertTrue(added)
        self.assertEqual(WatchlistItem.objects.count(), 1)

        added_again = services.toggle_watchlist(self.user, 'movie', self.movie.pk, WatchlistItem.ListType.WATCHLIST)
        self.assertFalse(added_again)
        self.assertEqual(WatchlistItem.objects.count(), 0)

    def test_toggle_like_updates_like_count(self):
        liked = services.toggle_like(self.user, 'movie', self.movie.pk)
        self.assertTrue(liked)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.like_count, 1)
        self.assertEqual(Like.objects.count(), 1)

        liked_again = services.toggle_like(self.user, 'movie', self.movie.pk)
        self.assertFalse(liked_again)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.like_count, 0)

    def test_selectors_rating_summary(self):
        other = User.objects.create_user(username='other', email='other@example.com', password='pass12345')
        services.rate_content(self.user, 'movie', self.movie.pk, score=8)
        services.rate_content(other, 'movie', self.movie.pk, score=6)

        summary = selectors.get_rating_summary('movie', self.movie.pk)
        self.assertEqual(summary['count'], 2)
        self.assertEqual(summary['average'], 7)


class PrivacySafeEventApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_accepts_anonymous_first_party_event_without_device_identity(self):
        response = self.client.post(reverse('create_privacy_safe_event'), {
            'event_type': 'search',
            'movie_slug': None,
            'query': 'فیلم اکشن کره‌ای',
            'genre': 'اکشن',
            'progress_percent': None,
            'source_page': '/search',
            'timestamp': '2026-07-15T12:00:00Z',
            'anonymous_session_id': '3d594650-3436-4b58-90c0-36ce1f47f66d',
            'result_count': 4,
        }, format='json', HTTP_USER_AGENT='should-not-be-stored', HTTP_X_PERSONALIZATION_CONSENT='granted')

        self.assertEqual(response.status_code, 201)
        event = UserActivityEvent.objects.get()
        self.assertEqual(event.action, 'search')
        self.assertEqual(event.query, 'فیلم اکشن کره‌ای')
        self.assertIsNone(event.ip_address)
        self.assertEqual(event.user_agent, '')
        self.assertEqual(event.device_type, '')

    def test_rejects_external_source_page(self):
        response = self.client.post(reverse('create_privacy_safe_event'), {
            'event_type': 'search',
            'query': 'درام',
            'source_page': 'https://example.com/search',
        }, format='json', HTTP_X_PERSONALIZATION_CONSENT='granted')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(UserActivityEvent.objects.count(), 0)

    def test_rejects_event_without_explicit_consent_header(self):
        response = self.client.post(reverse('create_privacy_safe_event'), {
            'event_type': 'search',
            'query': 'درام',
            'source_page': '/search',
        }, format='json')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(UserActivityEvent.objects.count(), 0)

    def test_accepts_canonical_title_fields_and_remove_like_without_negative_aliasing(self):
        movie = Movie.objects.create(title='Canonical Movie', slug='canonical-movie')
        response = self.client.post(reverse('create_privacy_safe_event'), {
            'event_type': 'remove_like',
            'title_id': movie.id,
            'title_slug': movie.slug,
            'content_type': 'movie',
            'source_page': f'/movies/{movie.slug}',
            'anonymous_session_id': 'canonical-session-123456',
        }, format='json', HTTP_X_PERSONALIZATION_CONSENT='granted')

        self.assertEqual(response.status_code, 201)
        event = UserActivityEvent.objects.get()
        self.assertEqual(event.object_id, movie.id)
        self.assertEqual(event.action, 'remove_like')
        self.assertEqual(event.metadata['title_slug'], movie.slug)

    def test_accepts_continue_watch_event_used_by_frontend(self):
        response = self.client.post(reverse('create_privacy_safe_event'), {
            'event_type': 'continue_watch',
            'title_id': 42,
            'title_slug': 'resume-title',
            'content_type': 'movie',
            'progress_percent': 48,
            'source_page': '/watch/resume-title',
        }, format='json', HTTP_X_PERSONALIZATION_CONSENT='granted')

        self.assertEqual(response.status_code, 201)
        event = UserActivityEvent.objects.get()
        self.assertEqual(event.action, 'play')
        self.assertEqual(event.progress, 48)

    def test_retried_event_id_is_idempotent(self):
        payload = {
            'event_id': '6f94a72d-685d-45de-b43e-fcc9f2a86c53',
            'event_type': 'recommendation_click',
            'title_id': 7,
            'title_slug': 'recommended-title',
            'content_type': 'movie',
            'source_page': '/',
            'anonymous_session_id': 'idempotent-session-123456',
        }

        first = self.client.post(
            reverse('create_privacy_safe_event'), payload,
            format='json', HTTP_X_PERSONALIZATION_CONSENT='granted',
        )
        second = self.client.post(
            reverse('create_privacy_safe_event'), payload,
            format='json', HTTP_X_PERSONALIZATION_CONSENT='granted',
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(UserActivityEvent.objects.count(), 1)


class ReviewAndSupportApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='reviewer', email='reviewer@example.com', password='pass12345',
        )
        self.staff = User.objects.create_user(
            username='staffer', email='staff@example.com', password='pass12345', is_staff=True,
        )
        self.movie = Movie.objects.create(title='Comment Movie', slug='comment-movie')

    def test_rate_with_review_appears_in_summary(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(reverse('rate_content'), {
            'content_type': 'movie',
            'object_id': self.movie.pk,
            'score': 9,
            'review': 'فیلم فوق‌العاده‌ای بود.',
            'is_spoiler': False,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['review'], 'فیلم فوق‌العاده‌ای بود.')

        summary = self.client.get(reverse('rating_summary'), {
            'content_type': 'movie', 'object_id': self.movie.pk,
        })
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(len(summary.data['reviews']), 1)
        self.assertEqual(summary.data['reviews'][0]['username'], 'reviewer')

    def test_hidden_review_is_excluded_from_public_summary(self):
        rating = services.rate_content(
            self.user, 'movie', self.movie.pk, score=7, review='مخفی شود',
        )
        services.set_rating_hidden(rating, True)
        summary = self.client.get(reverse('rating_summary'), {
            'content_type': 'movie', 'object_id': self.movie.pk,
        })
        self.assertEqual(summary.data['reviews'], [])

    def test_support_ticket_flow_user_to_admin(self):
        self.client.force_authenticate(self.user)
        created = self.client.post(reverse('support_ticket_list_create'), {
            'category': 'content_request',
            'subject': 'درخواست فیلم جدید',
            'body': 'لطفاً فیلم Inception را اضافه کنید.',
            'related_title': 'Inception',
            'related_year': 2010,
        }, format='json')
        self.assertEqual(created.status_code, 201)
        code = created.data['tracking_code']
        self.assertTrue(code.startswith('HS-'))

        self.client.force_authenticate(self.staff)
        inbox = self.client.get(reverse('admin_support_inbox'))
        self.assertEqual(inbox.status_code, 200)
        self.assertGreaterEqual(inbox.data['unread_count'], 1)
        self.assertEqual(inbox.data['results'][0]['tracking_code'], code)

        reply = self.client.post(
            reverse('admin_support_ticket_detail', kwargs={'tracking_code': code}),
            {'body': 'در صف ورود قرار گرفت.'},
            format='json',
        )
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(len(reply.data['messages']), 2)

        self.client.force_authenticate(self.user)
        detail = self.client.get(reverse('support_ticket_detail', kwargs={'tracking_code': code}))
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(any(m['is_staff_reply'] for m in detail.data['messages']))


class WatchStatsApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='watcher', email='watcher@example.com', password='pass12345',
        )
        self.movie = Movie.objects.create(
            title='Long Watch', slug='long-watch', duration_minutes=100, is_published=True,
        )

    def test_requires_auth(self):
        response = self.client.get(reverse('watch_stats'))
        self.assertEqual(response.status_code, 401)

    def test_estimates_minutes_from_progress_and_duration(self):
        UserActivityEvent.objects.create(
            user=self.user,
            content_type='movie',
            object_id=self.movie.pk,
            action='watch_progress',
            progress=50,
        )
        UserActivityEvent.objects.create(
            user=self.user,
            content_type='movie',
            object_id=self.movie.pk,
            action='complete_watch',
            progress=100,
        )
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse('watch_stats'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_minutes'], 100.0)
        self.assertEqual(response.data['titles_completed'], 1)
        self.assertIn('milestone', response.data)
        self.assertIn('equivalents', response.data)
