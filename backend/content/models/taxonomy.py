from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings

from core.models import (
    TimeStampedModel, SlugModel, PublishableModel, SEOMixin,
    MediaMixin, RatingMixin, ViewLikeMixin, ActiveManager
)


class Genre(TimeStampedModel, SlugModel, PublishableModel):
    title = models.CharField(_('Title'), max_length=100, unique=True, db_index=True)
    description = models.TextField(_('Description'), blank=True)
    icon = models.CharField(_('Icon'), max_length=50, blank=True)
    order = models.PositiveIntegerField(_('Order'), default=0)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Genre')
        verbose_name_plural = _('Genres')
        ordering = ['order', 'title']

    def __str__(self):
        return self.title


class Country(TimeStampedModel, SlugModel, PublishableModel):
    name = models.CharField(_('Name'), max_length=100, unique=True, db_index=True)
    code = models.CharField(_('Code'), max_length=3, unique=True)
    flag = models.ImageField(_('Flag'), upload_to='countries/', blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Country')
        verbose_name_plural = _('Countries')
        ordering = ['name']

    def __str__(self):
        return self.name


class Person(TimeStampedModel, SlugModel, PublishableModel, MediaMixin, SEOMixin):
    name = models.CharField(_('Name'), max_length=255, db_index=True)
    bio = models.TextField(_('Bio'), blank=True)
    birth_date = models.DateField(_('Birth Date'), null=True, blank=True)
    birth_place = models.CharField(_('Birth Place'), max_length=255, blank=True)
    death_date = models.DateField(_('Death Date'), null=True, blank=True)
    imdb_id = models.CharField(_('IMDb ID'), max_length=20, blank=True)
    tmdb_id = models.PositiveIntegerField(_('TMDb ID'), null=True, blank=True)
    instagram = models.URLField(_('Instagram'), blank=True)
    twitter = models.URLField(_('Twitter'), blank=True)
    order = models.PositiveIntegerField(_('Order'), default=0)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Person')
        verbose_name_plural = _('People')
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class Actor(Person):
    class Meta(Person.Meta):
        verbose_name = _('Actor')
        verbose_name_plural = _('Actors')


class Director(Person):
    class Meta(Person.Meta):
        verbose_name = _('Director')
        verbose_name_plural = _('Directors')


class Tag(TimeStampedModel, SlugModel, PublishableModel):
    name = models.CharField(_('Name'), max_length=100, unique=True, db_index=True)
    description = models.TextField(_('Description'), blank=True)
    color = models.CharField(_('Color'), max_length=7, default='#E39300')
    is_featured = models.BooleanField(_('Featured'), default=False)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Tag')
        verbose_name_plural = _('Tags')
        ordering = ['name']

    def __str__(self):
        return self.name