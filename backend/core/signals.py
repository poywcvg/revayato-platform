from django.db.models.signals import post_save, pre_save, m2m_changed
from django.dispatch import receiver
from django.utils.text import slugify
from django.db import models

from core.models import TimeStampedModel, SlugModel
from content.models import Movie, Series, Season, Episode, Genre, Actor, Director


@receiver(pre_save, sender=Movie)
@receiver(pre_save, sender=Series)
def generate_content_slug(sender, instance, **kwargs):
    if not instance.slug:
        base = slugify(instance.title)
        if instance.release_year if hasattr(instance, 'release_year') else instance.start_year:
            year = instance.release_year if hasattr(instance, 'release_year') else instance.start_year
            instance.slug = f'{base}-{year}'
        else:
            instance.slug = base


@receiver(pre_save, sender=Season)
def generate_season_slug(sender, instance, **kwargs):
    if not instance.slug:
        instance.slug = f'{instance.series.slug}-season-{instance.season_number}'


@receiver(pre_save, sender=Episode)
def generate_episode_slug(sender, instance, **kwargs):
    if not instance.slug:
        instance.slug = f'{instance.season.slug}-episode-{instance.episode_number}'


@receiver(pre_save, sender=Genre)
@receiver(pre_save, sender=Actor)
@receiver(pre_save, sender=Director)
def generate_taxonomy_slug(sender, instance, **kwargs):
    if not instance.slug:
        instance.slug = slugify(instance.title if hasattr(instance, 'title') else instance.name)


@receiver(m2m_changed, sender=Movie.genres.through)
@receiver(m2m_changed, sender=Series.genres.through)
def update_genre_counts(sender, instance, action, **kwargs):
    if action in ['post_add', 'post_remove', 'post_clear']:
        genres = instance.genres.all()
        for genre in genres:
            movie_count = genre.movies.filter(is_published=True).count()
            series_count = genre.series_genres.filter(is_published=True).count()
            genre.content_count = movie_count + series_count
            genre.save(update_fields=['content_count'])


@receiver(post_save, sender=Movie)
@receiver(post_save, sender=Series)
def update_content_relations(sender, instance, **kwargs):
    if hasattr(instance, 'genres'):
        for genre in instance.genres.all():
            movie_count = genre.movies.filter(is_published=True).count()
            series_count = genre.series_genres.filter(is_published=True).count()
            genre.content_count = movie_count + series_count
            genre.save(update_fields=['content_count'])


@receiver(post_save, sender=Season)
def update_season_counts(sender, instance, **kwargs):
    instance.update_counts()


@receiver(post_save, sender=Episode)
def update_episode_counts(sender, instance, **kwargs):
    if instance.season:
        instance.season.update_counts()
    if instance.season and instance.season.series:
        series = instance.season.series
        series.total_episodes = series.episodes.filter(is_published=True).count()
        series.total_duration = series.episodes.filter(is_published=True).aggregate(
            total=models.Sum('duration_minutes')
        )['total'] or 0
        series.save(update_fields=['total_episodes', 'total_duration'])