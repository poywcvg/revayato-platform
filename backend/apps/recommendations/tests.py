from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.models import Actor, Director, Genre, Movie, MovieActor, Series
from apps.engagement.models import Like, UserActivityEvent, WatchlistItem

from .services import get_recommendations_for_user, normalize_preferences, _similar_content


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

    def movie(self, title, slug, genre, rating=7, views=10, **extra):
        item = Movie.objects.create(
            title=title,
            slug=slug,
            site_rating=rating,
            view_count=views,
            is_published=True,
            **extra,
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
            metadata={'event_type': 'complete_watch'},
        )

        data = get_recommendations_for_user(self.user, limit=2)

        self.assertEqual(data['ranked'][0]['item'], similar)
        self.assertEqual(data['ranked'][-1]['item'], completed)

    def test_favorite_genre_preference_overrides_popularity(self):
        popular = self.movie('Mega Drama', 'mega-drama', self.drama, rating=9, views=5000, is_featured=True)
        niche = self.movie('Quiet Action', 'quiet-action', self.action, rating=6, views=5)

        data = get_recommendations_for_user(
            self.user,
            limit=2,
            preferences={'favorite_genres': ['action']},
        )

        self.assertEqual(data['ranked'][0]['item'], niche)
        self.assertNotEqual(data['ranked'][0]['item'], popular)
        self.assertIn('علاقه', data['ranked'][0]['reason'])

    def test_progress_demotes_in_progress_title(self):
        watching = self.movie('Halfway Action', 'halfway-action', self.action, rating=9, views=800)
        fresh = self.movie('Fresh Action Two', 'fresh-action-two', self.action, rating=7, views=20)
        UserActivityEvent.objects.create(
            user=self.user,
            content_type='movie',
            object_id=watching.id,
            action='watch_progress',
            progress=70,
            metadata={'event_type': 'watch_progress'},
        )
        UserActivityEvent.objects.create(
            user=self.user,
            content_type='movie',
            object_id=fresh.id,
            action='view_movie',
            metadata={'event_type': 'view_movie'},
        )

        data = get_recommendations_for_user(self.user, limit=2)
        ranked_ids = [entry['item'].id for entry in data['ranked']]
        self.assertLess(ranked_ids.index(fresh.id), ranked_ids.index(watching.id))

    def test_shared_cast_boosts_similarity_reason(self):
        actor = Actor.objects.create(name='Keanu Reeves')
        source = self.movie('Matrix-like', 'matrix-like', self.action, rating=8)
        twin = self.movie('John-like', 'john-like', self.action, rating=7)
        other = self.movie('No Cast Drama', 'no-cast-drama', self.drama, rating=9, views=2000)
        MovieActor.objects.create(movie=source, actor=actor, order=0)
        MovieActor.objects.create(movie=twin, actor=actor, order=0)
        Like.objects.create(user=self.user, content_type='movie', object_id=source.id)

        data = get_recommendations_for_user(self.user, limit=3)
        top = data['ranked'][0]
        self.assertEqual(top['item'], twin)
        self.assertTrue('Keanu' in top['reason'] or 'Action' in top['reason'] or 'حال' in top['reason'])
        self.assertNotEqual(top['item'], other)

    def test_recommendation_click_metadata_is_stronger_than_generic_view(self):
        clicked = self.movie('Clicked Action', 'clicked-action', self.action, rating=6, views=10)
        viewed = self.movie('Only Viewed Drama', 'only-viewed-drama', self.drama, rating=8, views=40)
        target = self.movie('Sibling Action', 'sibling-action', self.action, rating=7, views=12)
        UserActivityEvent.objects.create(
            user=self.user,
            content_type='movie',
            object_id=clicked.id,
            action='click_search_result',
            metadata={'event_type': 'recommendation_click'},
        )
        UserActivityEvent.objects.create(
            user=self.user,
            content_type='movie',
            object_id=viewed.id,
            action='view_movie',
            metadata={'event_type': 'view_movie'},
        )

        data = get_recommendations_for_user(self.user, limit=3)
        self.assertEqual(data['ranked'][0]['item'], target)

    def test_normalize_preferences_accepts_csv(self):
        prefs = normalize_preferences({
            'favorite_genres': 'action,drama',
            'playback_preference': 'dubbed',
            'content_sensitivity': 'reduced',
        })
        self.assertEqual(prefs['favorite_genres'], ['action', 'drama'])
        self.assertEqual(prefs['playback_preference'], 'dubbed')
        self.assertEqual(prefs['content_sensitivity'], 'reduced')

    def test_behavior_infers_taste_without_explicit_preferences(self):
        liked = self.movie('Watched Action', 'watched-action', self.action, rating=8)
        similar = self.movie('Sibling Action', 'sibling-action', self.action, rating=7)
        self.movie('Random Drama', 'random-drama', self.drama, rating=9, views=8000, is_featured=True)
        UserActivityEvent.objects.create(
            user=self.user,
            content_type='movie',
            object_id=liked.id,
            action='watch_progress',
            progress=80,
            metadata={'event_type': 'watch_progress'},
        )
        UserActivityEvent.objects.create(
            user=self.user,
            content_type='movie',
            object_id=liked.id,
            action='complete_watch',
            progress=100,
            metadata={'event_type': 'complete_watch'},
        )

        data = get_recommendations_for_user(self.user, limit=3)

        self.assertTrue(data['personalized'])
        self.assertIn('taste_summary', data)
        self.assertEqual(data['ranked'][0]['item'], similar)
        self.assertTrue(
            any(g['slug'] == 'action' for g in data['taste_summary']['top_genres'])
            or 'Action' in data['ranked'][0]['reason']
            or 'تماشا' in data['ranked'][0]['reason']
        )


class RecommendationApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='api-recommender', email='api-recommender@example.com', password='pass12345',
        )

    def test_anonymous_user_cannot_receive_recommendations(self):
        response = APIClient().get(reverse('recommendations'))

        self.assertEqual(response.status_code, 401)

    def test_invalid_limit_is_safely_bounded_and_response_is_explainable(self):
        genre, _created = Genre.objects.update_or_create(
            slug='mystery', defaults={'title': 'Mystery'},
        )
        movie = Movie.objects.create(title='Mystery Film', slug='mystery-film', is_published=True)
        movie.genres.add(genre)
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get(reverse('recommendations'), {'limit': 'invalid'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('confidence', response.data)
        self.assertIn('signals_used', response.data)
        self.assertEqual(response.data['recommendations'][0]['item']['slug'], movie.slug)
        self.assertTrue(response.data['recommendations'][0]['reason'])

    def test_favorite_genres_query_param_shapes_results(self):
        action, _ = Genre.objects.update_or_create(slug='action', defaults={'title': 'Action'})
        drama, _ = Genre.objects.update_or_create(slug='drama', defaults={'title': 'Drama'})
        action_movie = Movie.objects.create(title='Action Hit', slug='action-hit', is_published=True, view_count=5)
        drama_movie = Movie.objects.create(
            title='Drama Hit', slug='drama-hit', is_published=True, view_count=900, is_featured=True,
        )
        action_movie.genres.add(action)
        drama_movie.genres.add(drama)

        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get(reverse('recommendations'), {
            'limit': 2,
            'favorite_genres': 'action',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['recommendations'][0]['item']['slug'], 'action-hit')


class SimilarContentTests(TestCase):
    """``_similar_content`` must surface director/cast/genre ties, not just genre."""

    def setUp(self):
        self.action, _ = Genre.objects.update_or_create(slug='action', defaults={'title': 'Action'})
        self.drama, _ = Genre.objects.update_or_create(slug='drama', defaults={'title': 'Drama'})
        self.nolan = Director.objects.create(name='Christopher Nolan', slug='christopher-nolan')
        self.bardem = Actor.objects.create(name='Javier Bardem', slug='javier-bardem')

    def _movie(self, title, slug, genre, director=None, actor=None, views=10):
        item = Movie.objects.create(
            title=title, slug=slug, is_published=True, view_count=views,
        )
        item.genres.add(genre)
        if director:
            item.directors.add(director)
        if actor:
            MovieActor.objects.create(movie=item, actor=actor, order=0)
        return item

    def test_self_is_excluded(self):
        source = self._movie('Source', 'source', self.action, views=999)
        similar = self._movie('Other', 'other', self.action)
        self.assertNotIn(source, _similar_content(source))

    def test_director_tie_breaks_same_genre(self):
        source = self._movie('Nolan A', 'nolan-a', self.action, director=self.nolan, views=100)
        same_director = self._movie('Nolan B', 'nolan-b', self.action, director=self.nolan, views=50)
        genre_only = self._movie('Action B', 'action-b', self.action, views=999)

        results = _similar_content(source, limit=2)
        self.assertEqual(results[0], same_director)
        self.assertEqual(results[1], genre_only)

    def test_cast_tie_counts(self):
        source = self._movie('Bardem A', 'bardem-a', self.action, actor=self.bardem, views=100)
        same_cast = self._movie('Bardem B', 'bardem-b', self.action, actor=self.bardem, views=50)
        unrelated = self._movie('Action C', 'action-c', self.action, views=999)

        results = _similar_content(source, limit=2)
        self.assertEqual(results[0], same_cast)

    def test_different_content_type_is_excluded(self):
        source = self._movie('Film', 'film', self.action, views=100)
        series = Series.objects.create(title='Show', slug='show', start_year=2026, is_published=True, view_count=999)
        series.genres.add(self.action)

        results = _similar_content(source)
        self.assertNotIn(series, results)
