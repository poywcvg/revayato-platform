from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models

from activity.models import UserActivity, UserWatchlist, UserRating
from content.models import Movie, Series, Genre, Actor, Director
from users.models import UserTasteProfile


@receiver(post_save, sender=UserActivity)
def update_taste_profile(sender, instance, created, **kwargs):
    if not created or not instance.user:
        return

    profile, _ = UserTasteProfile.objects.get_or_create(user=instance.user)
    action_scores = {
        'view_movie': 1, 'view_series': 1, 'view_episode': 1,
        'play': 5, 'complete_watch': 12, 'like': 10,
        'rate': 15, 'add_to_watchlist': 8, 'trailer_watch': 3,
    }
    score = action_scores.get(instance.action, 0)
    if score <= 0:
        return

    if instance.content_type:
        model = instance.content_type.model_class()
        if not model:
            return

        content_obj = instance.content_object
        if not content_obj:
            return

        # Update genre preferences
        if hasattr(content_obj, 'genres'):
            for genre in content_obj.genres.all():
                current = profile.genres.get(str(genre.id), 0)
                profile.genres[str(genre.id)] = min(current + score, 100)

        # Update actor preferences
        if hasattr(content_obj, 'actors'):
            for actor in content_obj.actors.all():
                current = profile.actors.get(str(actor.id), 0)
                profile.actors[str(actor.id)] = min(current + score, 100)

        # Update director preferences
        if hasattr(content_obj, 'directors'):
            for director in content_obj.directors.all():
                current = profile.directors.get(str(director.id), 0)
                profile.directors[str(director.id)] = min(current + score, 100)

        # Update country preferences
        if hasattr(content_obj, 'countries'):
            for country in content_obj.countries.all():
                current = profile.countries.get(str(country.id), 0)
                profile.countries[str(country.id)] = min(current + score, 100)

        # Update content type preferences
        ctype = 'movie' if model == Movie else 'series' if model == Series else 'unknown'
        current = profile.content_types.get(ctype, 0)
        profile.content_types[ctype] = min(current + score, 100)

        # Update year range preferences
        if hasattr(content_obj, 'release_year') and content_obj.release_year:
            year = content_obj.release_year
            decade = f'{(year // 10) * 10}-{(year // 10) * 10 + 9}'
            current = profile.year_ranges.get(decade, 0)
            profile.year_ranges[decade] = min(current + score, 100)

        profile.data_points += 1
        profile.version += 1
        profile.save(update_fields=['genres', 'actors', 'directors', 'countries', 'content_types', 'year_ranges', 'data_points', 'version', 'last_updated'])