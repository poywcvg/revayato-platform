from django.db import models
from django.db.models import Q, Count, Sum, Avg, F, Case, When, Value, IntegerField
from django.utils import timezone
from datetime import timedelta


class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False, is_published=True)


class ContentManager(ActiveManager):
    def published(self):
        return self.filter(is_published=True, is_deleted=False)

    def featured(self):
        return self.published().filter(is_featured=True)

    def trending(self, days=7, limit=20):
        since = timezone.now() - timedelta(days=days)
        return self.published().filter(
            view_count__gt=0,
            created_at__gte=since
        ).order_by('-view_count')[:limit]

    def popular(self, limit=20):
        return self.published().order_by('-view_count', '-like_count')[:limit]

    def top_rated(self, min_votes=10, limit=20):
        return self.published().filter(vote_count__gte=min_votes).order_by('-imdb_rating', '-vote_count')[:limit]

    def recent(self, days=30, limit=20):
        since = timezone.now() - timedelta(days=days)
        return self.published().filter(created_at__gte=since).order_by('-created_at')[:limit]

    def coming_soon(self, limit=20):
        return self.published().filter(
            status='coming_soon',
            release_year__gte=timezone.now().year
        ).order_by('release_year')[:limit]

    def by_genre(self, genre_slug, limit=20):
        return self.published().filter(genres__slug=genre_slug).order_by('-imdb_rating', '-release_year')[:limit]

    def by_country(self, country_code, limit=20):
        return self.published().filter(countries__code=country_code).order_by('-imdb_rating', '-release_year')[:limit]

    def by_actor(self, actor_slug, limit=20):
        return self.published().filter(actors__slug=actor_slug).order_by('-imdb_rating', '-release_year')[:limit]

    def by_director(self, director_slug, limit=20):
        return self.published().filter(directors__slug=director_slug).order_by('-imdb_rating', '-release_year')[:limit]

    def by_year(self, year, limit=20):
        return self.published().filter(release_year=year).order_by('-imdb_rating', '-view_count')[:limit]

    def by_year_range(self, start_year, end_year, limit=20):
        return self.published().filter(
            release_year__gte=start_year,
            release_year__lte=end_year
        ).order_by('-imdb_rating', '-view_count')[:limit]

    def search(self, query, limit=20):
        return self.published().filter(
            Q(title__icontains=query) |
            Q(original_title__icontains=query) |
            Q(description__icontains=query)
        ).order_by('-imdb_rating', '-view_count')[:limit]

    def with_stats(self):
        return self.annotate(
            total_views=Count('view_count'),
            avg_rating=Avg('imdb_rating'),
        )

    def for_homepage(self):
        return self.published().select_related().prefetch_related(
            'genres', 'countries', 'actors', 'directors'
        )


class MovieManager(ContentManager):
    def released(self):
        return self.published().filter(status='released', release_year__lte=timezone.now().year)

    def now_playing(self):
        return self.released().filter(
            release_year__gte=timezone.now().year - 1
        ).order_by('-release_year', '-imdb_rating')

    def classics(self, year_threshold=1990):
        return self.released().filter(release_year__lte=year_threshold).order_by('-imdb_rating')

    def by_decade(self, decade):
        start = decade
        end = decade + 9
        return self.by_year_range(start, end)


class SeriesManager(ContentManager):
    def ongoing(self):
        return self.published().filter(status='ongoing')

    def completed(self):
        return self.published().filter(status='ended')

    def upcoming(self):
        return self.published().filter(status='upcoming')

    def binge_worthy(self, min_seasons=3):
        return self.published().filter(
            seasons__is_published=True
        ).annotate(
            season_count=Count('seasons', filter=Q(seasons__is_published=True))
        ).filter(season_count__gte=min_seasons).order_by('-imdb_rating')

    def with_episodes(self):
        return self.published().prefetch_related(
            'seasons__episodes'
        ).filter(seasons__is_published=True, seasons__episodes__is_published=True)


class PersonManager(ActiveManager):
    def featured(self):
        return self.published().filter(is_featured=True)

    def popular(self, limit=20):
        return self.published().order_by('-popularity')[:limit]

    def by_type(self, person_type):
        return self.published().filter(person_type=person_type)

    def birthday_today(self):
        today = timezone.now().date()
        return self.published().filter(
            birth_date__month=today.month,
            birth_date__day=today.day
        )

    def search(self, query):
        return self.published().filter(
            Q(name__icontains=query) |
            Q(name_en__icontains=query) |
            Q(known_for__icontains=query)
        )


class GenreManager(ActiveManager):
    def with_content_count(self):
        return self.published().annotate(
            movie_count=Count('movies', filter=Q(movies__is_published=True)),
            series_count=Count('series_genres', filter=Q(series_genres__is_published=True))
        ).filter(Q(movie_count__gt=0) | Q(series_count__gt=0))

    def featured(self):
        return self.with_content_count().filter(is_featured=True)


class WatchProgressManager(ActiveManager):
    def continue_watching(self, user, limit=10):
        return self.filter(
            user=user,
            is_completed=False,
            progress_percent__gt=1,
            progress_percent__lt=90
        ).order_by('-last_watched_at')[:limit]

    def completed(self, user, limit=20):
        return self.filter(
            user=user,
            is_completed=True
        ).order_by('-completed_at')[:limit]

    def in_progress(self, user):
        return self.filter(
            user=user,
            is_completed=False
        ).order_by('-last_watched_at')


class RecommendationManager(ActiveManager):
    def for_user(self, user, algorithm=None, limit=20):
        qs = self.filter(user=user, is_shown=False, is_dismissed=False)
        if algorithm:
            qs = qs.filter(algorithm=algorithm)
        return qs.order_by('-score', 'rank')[:limit]

    def active_for_user(self, user, limit=50):
        return self.filter(
            user=user,
            is_dismissed=False,
            expires_at__gt=timezone.now()
        ).order_by('-score', 'rank')[:limit]


class SimilarityManager(ActiveManager):
    def similar_to(self, content_type, object_id, limit=10):
        return self.filter(
            source_content_type=content_type,
            source_object_id=object_id
        ).order_by('-score')[:limit]