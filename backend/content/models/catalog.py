from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify

from core.models import (
    TimeStampedModel, SlugModel, PublishableModel, MediaMixin,
    RatingMixin, ViewLikeMixin, SoftDeleteModel, ActiveManager,
    SEOModelMixin,
)


class Genre(TimeStampedModel, SlugModel, PublishableModel, MediaMixin, SEOModelMixin, SoftDeleteModel):
    title = models.CharField(_('Title'), max_length=100, unique=True, db_index=True)
    description = models.TextField(_('Description'), blank=True)
    order = models.PositiveIntegerField(_('Order'), default=0, db_index=True)
    is_featured = models.BooleanField(_('Featured'), default=False, db_index=True)
    tmdb_id = models.PositiveIntegerField(_('TMDb ID'), null=True, blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Genre')
        verbose_name_plural = _('Genres')
        ordering = ['order', 'title']
        indexes = [
            models.Index(fields=['is_published', 'order']),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('genre-detail', kwargs={'slug': self.slug})


class Country(TimeStampedModel, SlugModel, PublishableModel, MediaMixin, SoftDeleteModel):
    name = models.CharField(_('Name'), max_length=100, unique=True, db_index=True)
    code = models.CharField(_('Code'), max_length=3, unique=True)
    flag = models.ImageField(_('Flag'), upload_to='countries/', blank=True, null=True)
    is_featured = models.BooleanField(_('Featured'), default=False, db_index=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Country')
        verbose_name_plural = _('Countries')
        ordering = ['name']

    def __str__(self):
        return self.name


class Tag(TimeStampedModel, SlugModel, PublishableModel, SoftDeleteModel):
    name = models.CharField(_('Name'), max_length=100, unique=True, db_index=True)
    description = models.TextField(_('Description'), blank=True)
    is_featured = models.BooleanField(_('Featured'), default=False, db_index=True)
    color = models.CharField(_('Color'), max_length=7, default='#E39300')

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Tag')
        verbose_name_plural = _('Tags')
        ordering = ['name']

    def __str__(self):
        return self.name


class MovieActor(TimeStampedModel):
    movie = models.ForeignKey('content.Movie', on_delete=models.CASCADE, related_name='movie_actors')
    actor = models.ForeignKey('content.Actor', on_delete=models.CASCADE, related_name='actor_movies')
    role = models.CharField(_('Role'), max_length=255)
    order = models.PositiveIntegerField(_('Order'), default=0)
    is_lead = models.BooleanField(_('Lead Role'), default=False)
    is_cameo = models.BooleanField(_('Cameo'), default=False)

    class Meta:
        verbose_name = _('Movie Actor')
        verbose_name_plural = _('Movie Actors')
        ordering = ['order', 'id']
        unique_together = ['movie', 'actor']

    def __str__(self):
        return f'{self.movie} - {self.actor} as {self.role}'


class MovieDirector(TimeStampedModel):
    movie = models.ForeignKey('content.Movie', on_delete=models.CASCADE, related_name='movie_directors')
    director = models.ForeignKey('content.Director', on_delete=models.CASCADE, related_name='director_movies')
    order = models.PositiveIntegerField(_('Order'), default=0)

    class Meta:
        verbose_name = _('Movie Director')
        verbose_name_plural = _('Movie Directors')
        ordering = ['order', 'id']
        unique_together = ['movie', 'director']

    def __str__(self):
        return f'{self.movie} - {self.director}'