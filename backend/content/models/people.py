from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify

from core.models import TimeStampedModel, SlugModel, PublishableModel, MediaMixin, ActiveManager






class Actor(TimeStampedModel, SlugModel, PublishableModel, MediaMixin):
    name = models.CharField(_('Name'), max_length=255, db_index=True)
    name_en = models.CharField(_('English Name'), max_length=255, blank=True, db_index=True)
    biography = models.TextField(_('Biography'), blank=True)
    birth_date = models.DateField(_('Birth Date'), null=True, blank=True)
    birth_place = models.CharField(_('Birth Place'), max_length=255, blank=True)
    death_date = models.DateField(_('Death Date'), null=True, blank=True)
    height = models.PositiveIntegerField(_('Height (cm)'), null=True, blank=True)
    imdb_id = models.CharField(_('IMDb ID'), max_length=20, blank=True)
    tmdb_id = models.PositiveIntegerField(_('TMDb ID'), null=True, blank=True)
    instagram = models.URLField(_('Instagram'), blank=True)
    twitter = models.URLField(_('Twitter/X'), blank=True)
    known_for = models.TextField(_('Known For'), blank=True)
    is_featured = models.BooleanField(_('Featured'), default=False)
    popularity = models.DecimalField(_('Popularity'), max_digits=10, decimal_places=3, default=0)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Actor')
        verbose_name_plural = _('Actors')
        ordering = ['-popularity', 'name']
        indexes = [
            models.Index(fields=['is_published', '-popularity']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name_en or self.name)
        super().save(*args, **kwargs)

    @property
    def age(self):
        if self.birth_date:
            from datetime import date
            today = date.today()
            if self.death_date:
                today = self.death_date
            return today.year - self.birth_date.year - (
                (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
            )
        return None


class Director(TimeStampedModel, SlugModel, PublishableModel, MediaMixin):
    name = models.CharField(_('Name'), max_length=255, db_index=True)
    name_en = models.CharField(_('English Name'), max_length=255, blank=True, db_index=True)
    biography = models.TextField(_('Biography'), blank=True)
    birth_date = models.DateField(_('Birth Date'), null=True, blank=True)
    birth_place = models.CharField(_('Birth Place'), max_length=255, blank=True)
    death_date = models.DateField(_('Death Date'), null=True, blank=True)
    imdb_id = models.CharField(_('IMDb ID'), max_length=20, blank=True)
    tmdb_id = models.PositiveIntegerField(_('TMDb ID'), null=True, blank=True)
    is_featured = models.BooleanField(_('Featured'), default=False)
    popularity = models.DecimalField(_('Popularity'), max_digits=10, decimal_places=3, default=0)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Director')
        verbose_name_plural = _('Directors')
        ordering = ['-popularity', 'name']
        indexes = [
            models.Index(fields=['is_published', '-popularity']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name_en or self.name)
        super().save(*args, **kwargs)



class Person(TimeStampedModel, SlugModel, PublishableModel, MediaMixin):
    PERSON_TYPES = [
        ('actor', _('Actor')),
        ('director', _('Director')),
        ('writer', _('Writer')),
        ('producer', _('Producer')),
        ('composer', _('Composer')),
        ('cinematographer', _('Cinematographer')),
        ('editor', _('Editor')),
    ]

    name = models.CharField(_('Name'), max_length=255, db_index=True)
    name_en = models.CharField(_('English Name'), max_length=255, blank=True, db_index=True)
    person_type = models.CharField(_('Type'), max_length=20, choices=PERSON_TYPES, default='actor', db_index=True)
    biography = models.TextField(_('Biography'), blank=True)
    birth_date = models.DateField(_('Birth Date'), null=True, blank=True)
    birth_place = models.CharField(_('Birth Place'), max_length=255, blank=True)
    death_date = models.DateField(_('Death Date'), null=True, blank=True)
    imdb_id = models.CharField(_('IMDb ID'), max_length=20, blank=True)
    tmdb_id = models.PositiveIntegerField(_('TMDb ID'), null=True, blank=True)
    known_for = models.TextField(_('Known For'), blank=True)
    popularity = models.DecimalField(_('Popularity'), max_digits=10, decimal_places=3, default=0)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Person')
        verbose_name_plural = _('People')
        ordering = ['-popularity', 'name']
        indexes = [
            models.Index(fields=['person_type', 'is_published', '-popularity']),
        ]

    def __str__(self):
        return f'{self.name} ({self.get_person_type_display()})'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name_en or self.name)
        super().save(*args, **kwargs)