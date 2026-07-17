from django.db import models
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils.text import slugify

from core.models import (
    TimeStampedModel, SlugModel, PublishableModel,
    MediaMixin, RatingMixin, ViewLikeMixin, SoftDeleteModel,
    ActiveManager, SEOModelMixin
)
from config.public_urls import validate_object_key


class Movie(
    TimeStampedModel, SlugModel, PublishableModel,
    MediaMixin, RatingMixin, ViewLikeMixin,
    SEOModelMixin, SoftDeleteModel
):
    STATUS_CHOICES = [
        ('released', _('Released')),
        ('coming_soon', _('Coming Soon')),
        ('in_production', _('In Production')),
        ('cancelled', _('Cancelled')),
    ]

    title = models.CharField(_('Title'), max_length=255, db_index=True)
    original_title = models.CharField(_('Original Title'), max_length=255, blank=True, db_index=True)
    description = models.TextField(_('Description'), blank=True)
    short_description = models.TextField(_('Short Description'), max_length=500, blank=True)
    release_year = models.PositiveIntegerField(_('Release Year'), null=True, blank=True, db_index=True)
    duration_minutes = models.PositiveIntegerField(_('Duration (Minutes)'), null=True, blank=True)
    age_rating = models.CharField(_('Age Rating'), max_length=10, blank=True, db_index=True)
    language = models.CharField(_('Language'), max_length=10, default='fa')
    status = models.CharField(_('Status'), max_length=20, choices=STATUS_CHOICES, default='released', db_index=True)
    quality = models.CharField(_('Quality'), max_length=20, blank=True)
    has_dub = models.BooleanField(_('Has Dub'), default=False, db_index=True)
    has_sub = models.BooleanField(_('Has Sub'), default=False, db_index=True)
    is_featured = models.BooleanField(_('Featured'), default=False, db_index=True)
    is_adult = models.BooleanField(_('Adult Content'), default=False, db_index=True)
    imdb_id = models.CharField(_('IMDb ID'), max_length=20, blank=True)
    tmdb_id = models.PositiveIntegerField(_('TMDb ID'), null=True, blank=True)
    trailer_url = models.CharField(_('Trailer object key'), max_length=500, blank=True, validators=[validate_object_key])
    video_url = models.CharField(_('HLS manifest object key'), max_length=500, blank=True, validators=[validate_object_key])
    keywords = models.JSONField(_('Keywords'), default=list, blank=True)
    awards = models.JSONField(_('Awards'), default=list, blank=True)
    budget = models.BigIntegerField(_('Budget'), null=True, blank=True)
    revenue = models.BigIntegerField(_('Revenue'), null=True, blank=True)

    genres = models.ManyToManyField('content.Genre', verbose_name=_('Genres'), related_name='movies', blank=True)
    countries = models.ManyToManyField('content.Country', verbose_name=_('Countries'), related_name='movies', blank=True)
    tags = models.ManyToManyField('content.Tag', verbose_name=_('Tags'), related_name='movies', blank=True)
    actors = models.ManyToManyField('content.Actor', through='content.MovieActor', verbose_name=_('Actors'), related_name='movies', blank=True)
    directors = models.ManyToManyField('content.Director', through='content.MovieDirector', verbose_name=_('Directors'), related_name='movies', blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Movie')
        verbose_name_plural = _('Movies')
        ordering = ['-release_year', '-created_at']
        indexes = [
            models.Index(fields=['is_published', 'release_year']),
            models.Index(fields=['is_published', 'imdb_rating']),
            models.Index(fields=['is_published', 'view_count']),
            models.Index(fields=['is_published', 'is_featured']),
            models.Index(fields=['slug', 'is_published']),
            models.Index(fields=['status', 'is_published']),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('movie-detail', kwargs={'slug': self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f'{self.title}-{self.release_year or ""}')
        super().save(*args, **kwargs)

    @property
    def year_display(self):
        return str(self.release_year) if self.release_year else _('Unknown')

    @property
    def formatted_duration(self):
        if not self.duration_minutes:
            return _('Unknown')
        hours = self.duration_minutes // 60
        minutes = self.duration_minutes % 60
        if hours:
            return f'{hours}h {minutes}m'
        return f'{minutes}m'
