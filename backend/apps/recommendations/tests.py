from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.models import Genre, Movie
from apps.engagement.models import Like, UserActivityEvent

from .services import get_recommendations_for_user


User = get_user_model()


class RecommendationServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='recommender', email='recommender@example.com', password='pass12345',
        )
        self.action, _created = Genre.objects.update_or_create(
            slug='action', defaults={'title': 'Action'},
        )
        self.drama, _created = Genre.objects.update_or_create(
            slug='drama', defaults={'title': 'Drama'},
        )

    def movie(self, title, slug, genre, rating=7, views=10):
        item = Movie.objects.create(
            title=title,
            slug=slug,
            site_rating=rating,
            view_count=views,
            is_published=True,
        )
        item.genres.add(genre)
        return item

    def test_like_profile_promotes_similar_unseen_content(self):
        source = self.movie('Liked Action', 'liked-action', self.action, rating=7)
        similar = self.movie('Similar Action', 'similar-action', self.action, rating=7)
        self.movie('Popular Drama', 'popular-drama', self.drama, rating=9, views=1000)
        Like.objects.create(user=self.user, content_type='movie', object_id=source.id)

        data = get_recommendations_for_user(self.user, limit=3)

        self.assertTrue(data['personalized'])
        self.assertEqual(data['ranked'][0]['item'], similar)
        self.assertIn('Action', data['ranked'][0]['reason'])

    def test_completed_title_is_demoted_but_its_genre_trains_profile(self):
        completed = self.movie('Completed Action', 'completed-action', self.action, rating=9, views=1000)
        similar = self.movie('Fresh Action', 'fresh-action', self.action, rating=7)
        UserActivityEvent.objects.create(
            user=self.user,
            content_type='movie',
            object_id=completed.id,
            action='complete_watch',
            progress=100,
        )

        data = get_recommendations_for_user(self.user, limit=2)

        self.assertEqual(data['ranked'][0]['item'], similar)
        self.assertEqual(data['ranked'][-1]['item'], completed)


class RecommendationApiTests(TestCase):
    def test_invalid_limit_is_safely_bounded_and_response_is_explainable(self):
        genre, _created = Genre.objects.update_or_create(
            slug='mystery', defaults={'title': 'Mystery'},
        )
        movie = Movie.objects.create(title='Mystery Film', slug='mystery-film', is_published=True)
        movie.genres.add(genre)
        response = APIClient().get(reverse('recommendations'), {'limit': 'invalid'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('confidence', response.data)
        self.assertIn('signals_used', response.data)
        self.assertEqual(response.data['recommendations'][0]['item']['slug'], movie.slug)
        self.assertTrue(response.data['recommendations'][0]['reason'])
