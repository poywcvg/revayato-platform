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


class Series(
    TimeStampedModel, SlugModel, PublishableModel,
    MediaMixin, RatingMixin, ViewLikeMixin,
    SEOModelMixin, SoftDeleteModel
):
    STATUS_CHOICES = [
        ('ongoing', _('Ongoing')),
        ('ended', _('Ended')),
        ('upcoming', _('Upcoming')),
        ('cancelled', _('Cancelled')),
        ('on_hold', _('On Hold')),
    ]

    title = models.CharField(_('Title'), max_length=255, db_index=True)
    original_title = models.CharField(_('Original Title'), max_length=255, blank=True, db_index=True)
    description = models.TextField(_('Description'), blank=True)
    short_description = models.TextField(_('Short Description'), max_length=500, blank=True)
    start_year = models.PositiveIntegerField(_('Start Year'), null=True, blank=True, db_index=True)
    end_year = models.PositiveIntegerField(_('End Year'), null=True, blank=True)
    age_rating = models.CharField(_('Age Rating'), max_length=10, blank=True, db_index=True)
    language = models.CharField(_('Language'), max_length=10, default='fa')
    status = models.CharField(_('Status'), max_length=20, choices=STATUS_CHOICES, default='ongoing', db_index=True)
    quality = models.CharField(_('Quality'), max_length=20, blank=True)
    has_dub = models.BooleanField(_('Has Dub'), default=False, db_index=True)
    has_sub = models.BooleanField(_('Has Sub'), default=False, db_index=True)
    is_featured = models.BooleanField(_('Featured'), default=False, db_index=True)
    is_adult = models.BooleanField(_('Adult Content'), default=False, db_index=True)
    imdb_id = models.CharField(_('IMDb ID'), max_length=20, blank=True)
    tmdb_id = models.PositiveIntegerField(_('TMDb ID'), null=True, blank=True)
    trailer_url = models.CharField(_('Trailer object key'), max_length=500, blank=True, validators=[validate_object_key])
    keywords = models.JSONField(_('Keywords'), default=list, blank=True)
    awards = models.JSONField(_('Awards'), default=list, blank=True)

    genres = models.ManyToManyField('content.Genre', verbose_name=_('Genres'), related_name='series_genres', blank=True)
    countries = models.ManyToManyField('content.Country', verbose_name=_('Countries'), related_name='series_countries', blank=True)
    tags = models.ManyToManyField('content.Tag', verbose_name=_('Tags'), related_name='series_tags', blank=True)
    actors = models.ManyToManyField('content.Actor', through='content.SeriesActor', verbose_name=_('Actors'), related_name='series', blank=True)
    directors = models.ManyToManyField('content.Director', through='content.SeriesDirector', verbose_name=_('Directors'), related_name='series', blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Series')
        verbose_name_plural = _('Series')
        ordering = ['-start_year', '-created_at']
        indexes = [
            models.Index(fields=['is_published', 'start_year']),
            models.Index(fields=['is_published', 'imdb_rating']),
            models.Index(fields=['is_published', 'view_count']),
            models.Index(fields=['is_published', 'is_featured']),
            models.Index(fields=['slug', 'is_published']),
            models.Index(fields=['status', 'is_published']),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('series-detail', kwargs={'slug': self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f'{self.title}-{self.start_year or ""}')
        super().save(*args, **kwargs)

    @property
    def year_display(self):
        if self.start_year and self.end_year:
            return f'{self.start_year}-{self.end_year}'
        elif self.start_year:
            return f'{self.start_year}-'
        return _('Unknown')

    @property
    def total_seasons(self):
        return self.seasons.filter(is_published=True).count()

    @property
    def total_episodes(self):
        return self.episodes.filter(is_published=True).count()


class SeriesActor(TimeStampedModel):
    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name='series_actors')
    actor = models.ForeignKey('content.Actor', on_delete=models.CASCADE, related_name='actor_series')
    role = models.CharField(_('Role'), max_length=255)
    order = models.PositiveIntegerField(_('Order'), default=0)
    is_lead = models.BooleanField(_('Lead Role'), default=False)

    class Meta:
        verbose_name = _('Series Actor')
        verbose_name_plural = _('Series Actors')
        ordering = ['order', 'id']
        unique_together = ['series', 'actor']

    def __str__(self):
        return f'{self.series} - {self.actor} as {self.role}'


class SeriesDirector(TimeStampedModel):
    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name='series_directors')
    director = models.ForeignKey('content.Director', on_delete=models.CASCADE, related_name='director_series')
    order = models.PositiveIntegerField(_('Order'), default=0)

    class Meta:
        verbose_name = _('Series Director')
        verbose_name_plural = _('Series Directors')
        ordering = ['order', 'id']
        unique_together = ['series', 'director']

    def __str__(self):
        return f'{self.series} - {self.director}'


class Season(
    TimeStampedModel, SlugModel, PublishableModel,
    MediaMixin, SoftDeleteModel
):
    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name='seasons', verbose_name=_('Series'))
    title = models.CharField(_('Title'), max_length=255)
    season_number = models.PositiveIntegerField(_('Season Number'), db_index=True)
    description = models.TextField(_('Description'), blank=True)
    release_year = models.PositiveIntegerField(_('Release Year'), null=True, blank=True)
    poster = models.ImageField(_('Poster'), upload_to='seasons/', blank=True, null=True)
    episode_count = models.PositiveIntegerField(_('Episode Count'), default=0)
    total_duration = models.PositiveIntegerField(_('Total Duration (Minutes)'), default=0)
    air_date = models.DateField(_('Air Date'), null=True, blank=True)

    class Meta:
        verbose_name = _('Season')
        verbose_name_plural = _('Seasons')
        ordering = ['season_number']
        unique_together = ['series', 'season_number']
        indexes = [
            models.Index(fields=['series', 'season_number']),
            models.Index(fields=['series', 'is_published']),
        ]

    def __str__(self):
        return f'{self.series} - Season {self.season_number}'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = f'{self.series.slug}-season-{self.season_number}'
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('season-detail', kwargs={'series_slug': self.series.slug, 'season_number': self.season_number})

    def update_counts(self):
        self.episode_count = self.episodes.filter(is_published=True).count()
        self.total_duration = self.episodes.filter(is_published=True).aggregate(
            total=models.Sum('duration_minutes')
        )['total'] or 0
        self.save(update_fields=['episode_count', 'total_duration'])


class Episode(
    TimeStampedModel, SlugModel, PublishableModel,
    MediaMixin, RatingMixin, ViewLikeMixin, SoftDeleteModel
):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='episodes', verbose_name=_('Season'))
    title = models.CharField(_('Title'), max_length=255)
    episode_number = models.PositiveIntegerField(_('Episode Number'), db_index=True)
    description = models.TextField(_('Description'), blank=True)
    duration_minutes = models.PositiveIntegerField(_('Duration (Minutes)'), null=True, blank=True)
    video_url = models.CharField(_('HLS manifest object key'), max_length=500, blank=True, validators=[validate_object_key])
    poster = models.ImageField(_('Poster'), upload_to='episodes/', blank=True, null=True)
    air_date = models.DateField(_('Air Date'), null=True, blank=True, db_index=True)
    is_filler = models.BooleanField(_('Filler Episode'), default=False)
    trailer_url = models.CharField(_('Trailer object key'), max_length=500, blank=True, validators=[validate_object_key])

    class Meta:
        verbose_name = _('Episode')
        verbose_name_plural = _('Episodes')
        ordering = ['episode_number']
        unique_together = ['season', 'episode_number']
        indexes = [
            models.Index(fields=['season', 'episode_number']),
            models.Index(fields=['season', 'is_published']),
            models.Index(fields=['air_date', 'is_published']),
        ]

    def __str__(self):
        return f'{self.season} - Episode {self.episode_number}: {self.title}'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = f'{self.season.slug}-episode-{self.episode_number}'
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('episode-detail', kwargs={
            'series_slug': self.season.series.slug,
            'season_number': self.season.season_number,
            'episode_number': self.episode_number
        })

    def get_next_episode(self):
        return Episode.objects.filter(
            season=self.season,
            episode_number__gt=self.episode_number,
            is_published=True
        ).order_by('episode_number').first()

    def get_prev_episode(self):
        return Episode.objects.filter(
            season=self.season,
            episode_number__lt=self.episode_number,
            is_published=True
        ).order_by('-episode_number').first()
