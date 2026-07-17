from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from config.public_urls import validate_object_key, validate_subtitle_tracks

class ContentFormat(models.TextChoices):
    LIVE_ACTION = 'live_action', _('Live Action')
    ANIMATION = 'animation', _('Animation')
    SHORT = 'short', _('Short')


class MediaStatus(models.TextChoices):
    MISSING = 'missing', _('Media missing')
    READY = 'ready', _('Media ready')
    ERROR = 'error', _('Media error')


class CatalogSyncRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = 'running', _('Running')
        SUCCEEDED = 'succeeded', _('Succeeded')
        FAILED = 'failed', _('Failed')

    provider = models.CharField(_('Provider'), max_length=40, default='tmdb')
    status = models.CharField(_('Status'), max_length=20, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    discovered_count = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    published_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['-started_at']
        verbose_name = _('Catalog sync run')
        verbose_name_plural = _('Catalog sync runs')

    def __str__(self):
        return f'{self.provider} · {self.started_at:%Y-%m-%d %H:%M} · {self.status}'


class Genre(models.Model):
    title = models.CharField(_('Title'), max_length=100, unique=True, db_index=True)
    slug = models.SlugField(_('Slug'), max_length=120, unique=True, allow_unicode=True)
    description = models.TextField(_('Description'), blank=True)
    is_featured = models.BooleanField(_('Featured'), default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Genre')
        verbose_name_plural = _('Genres')
        ordering = ['title']

    def __str__(self):
        return self.title


class Actor(models.Model):
    name = models.CharField(_('Name'), max_length=255, db_index=True)
    slug = models.SlugField(_('Slug'), max_length=280, unique=True, allow_unicode=True)
    photo = models.ImageField(_('Photo'), upload_to='catalog/actors/', null=True, blank=True)
    biography = models.TextField(_('Biography'), blank=True)
    birth_date = models.DateField(_('Birth Date'), null=True, blank=True, db_index=True)
    birth_place = models.CharField(_('Birth Place'), max_length=255, blank=True)
    is_featured = models.BooleanField(_('Featured'), default=False)
    popularity = models.FloatField(_('Popularity'), default=0.0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Actor')
        verbose_name_plural = _('Actors')
        ordering = ['name']
        indexes = [
            models.Index(fields=['-popularity', 'name']),
        ]

    def __str__(self):
        return self.name


class Director(models.Model):
    name = models.CharField(_('Name'), max_length=255, db_index=True)
    slug = models.SlugField(_('Slug'), max_length=280, unique=True, allow_unicode=True)
    photo = models.ImageField(_('Photo'), upload_to='catalog/directors/', null=True, blank=True)
    biography = models.TextField(_('Biography'), blank=True)
    birth_date = models.DateField(_('Birth Date'), null=True, blank=True, db_index=True)
    birth_place = models.CharField(_('Birth Place'), max_length=255, blank=True)
    is_featured = models.BooleanField(_('Featured'), default=False)
    popularity = models.FloatField(_('Popularity'), default=0.0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Director')
        verbose_name_plural = _('Directors')
        ordering = ['name']
        indexes = [
            models.Index(fields=['-popularity', 'name']),
        ]

    def __str__(self):
        return self.name


class Country(models.Model):
    name = models.CharField(_('Name'), max_length=100, unique=True, db_index=True)
    code = models.CharField(_('Code'), max_length=2, unique=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Country')
        verbose_name_plural = _('Countries')
        ordering = ['name']

    def __str__(self):
        return self.name


class Tag(models.Model):
    name = models.CharField(_('Name'), max_length=100, unique=True, db_index=True)
    slug = models.SlugField(_('Slug'), max_length=120, unique=True, allow_unicode=True)
    is_featured = models.BooleanField(_('Featured'), default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Tag')
        verbose_name_plural = _('Tags')
        ordering = ['name']

    def __str__(self):
        return self.name


class Movie(models.Model):
    title = models.CharField(_('Title'), max_length=255, db_index=True)
    original_title = models.CharField(_('Original Title'), max_length=255, blank=True)
    slug = models.SlugField(_('Slug'), max_length=280, unique=True, allow_unicode=True)
    short_description = models.CharField(_('Short Description'), max_length=500, blank=True)
    description = models.TextField(_('Description'), blank=True)
    release_year = models.PositiveIntegerField(_('Release Year'), null=True, blank=True, db_index=True)
    release_date = models.DateField(_('Release Date'), null=True, blank=True, db_index=True)
    duration_minutes = models.PositiveIntegerField(_('Duration (Minutes)'), null=True, blank=True)

    genres = models.ManyToManyField(Genre, verbose_name=_('Genres'), related_name='movies', blank=True)
    actors = models.ManyToManyField(Actor, verbose_name=_('Actors'), related_name='movies', blank=True, through='MovieActor')
    directors = models.ManyToManyField(Director, verbose_name=_('Directors'), related_name='movies', blank=True)
    countries = models.ManyToManyField(Country, verbose_name=_('Countries'), related_name='movies', blank=True)
    tags = models.ManyToManyField(Tag, verbose_name=_('Tags'), related_name='movies', blank=True)

    poster = models.ImageField(_('Poster'), upload_to='catalog/movies/posters/', null=True, blank=True)
    backdrop = models.ImageField(_('Backdrop'), upload_to='catalog/movies/backdrops/', null=True, blank=True)
    trailer_url = models.CharField(_('Trailer object key'), max_length=500, blank=True, validators=[validate_object_key])
    video_url = models.CharField(_('HLS manifest object key'), max_length=500, blank=True, validators=[validate_object_key])
    download_key = models.CharField(_('Download object key'), max_length=500, blank=True, validators=[validate_object_key])
    subtitle_tracks = models.JSONField(_('Subtitle tracks'), default=list, blank=True, validators=[validate_subtitle_tracks])
    media_status = models.CharField(_('Media status'), max_length=20, choices=MediaStatus.choices, default=MediaStatus.MISSING, db_index=True)
    rights_verified = models.BooleanField(_('Rights verified'), default=False, db_index=True)
    auto_publish = models.BooleanField(_('Auto publish when ready'), default=False, db_index=True)
    scheduled_publish_at = models.DateTimeField(_('Scheduled publish time'), null=True, blank=True, db_index=True)
    metadata_source = models.CharField(_('Metadata source'), max_length=40, default='manual', blank=True)
    metadata_synced_at = models.DateTimeField(_('Metadata synced at'), null=True, blank=True)
    source_metadata = models.JSONField(_('Source metadata'), default=dict, blank=True)

    imdb_rating = models.DecimalField(
        _('IMDb Rating'), max_digits=3, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
    )
    site_rating = models.DecimalField(
        _('Site Rating'), max_digits=3, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
    )
    age_rating = models.CharField(_('Age Rating'), max_length=20, blank=True, db_index=True)
    language = models.CharField(_('Language'), max_length=100, blank=True)
    content_format = models.CharField(
        _('Content Format'), max_length=20, choices=ContentFormat.choices,
        default=ContentFormat.LIVE_ACTION, db_index=True,
    )
    is_dubbed = models.BooleanField(_('Dubbed'), default=False, db_index=True)
    has_subtitle = models.BooleanField(_('Has Subtitle'), default=False, db_index=True)
    is_uncensored = models.BooleanField(_('Uncensored'), default=False, db_index=True)
    content_warnings = models.JSONField(_('Content Warnings'), default=list, blank=True)

    imdb_id = models.CharField(_('IMDb ID'), max_length=20, blank=True, null=True, unique=True)
    tmdb_id = models.PositiveIntegerField(_('TMDb ID'), blank=True, null=True, unique=True)

    meta_title = models.CharField(_('SEO Title'), max_length=255, blank=True)
    meta_description = models.CharField(_('SEO Description'), max_length=500, blank=True)

    is_published = models.BooleanField(_('Published'), default=False, db_index=True)
    is_featured = models.BooleanField(_('Featured'), default=False, db_index=True)

    view_count = models.PositiveBigIntegerField(_('View Count'), default=0)
    like_count = models.PositiveBigIntegerField(_('Like Count'), default=0)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Movie')
        verbose_name_plural = _('Movies')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-release_year', 'is_published']),
            models.Index(fields=['is_published', '-view_count']),
            models.Index(fields=['slug', 'is_published']),
        ]

    def __str__(self):
        return self.title

    @property
    def seo_title(self):
        return self.meta_title or self.title

    @property
    def seo_description(self):
        return self.meta_description or self.short_description or self.description[:160]

    @property
    def auto_publish_blockers(self):
        blockers = []
        if not self.rights_verified:
            blockers.append('rights_not_verified')
        if self.media_status != MediaStatus.READY:
            blockers.append('media_not_ready')
        if not self.video_url:
            blockers.append('missing_hls')
        if not self.poster:
            blockers.append('missing_poster')
        if not self.backdrop:
            blockers.append('missing_backdrop')
        if not self.description:
            blockers.append('missing_description')
        if not self.release_date:
            blockers.append('missing_release_date')
        if not self.duration_minutes:
            blockers.append('missing_duration')
        if self.pk and not self.genres.exists():
            blockers.append('missing_genres')
        if self.pk and not self.directors.exists():
            blockers.append('missing_director')
        return blockers

    @property
    def ready_for_auto_publish(self):
        return not self.auto_publish_blockers


class MovieActor(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='movie_actors')
    actor = models.ForeignKey(Actor, on_delete=models.CASCADE, related_name='movie_roles')
    role = models.CharField(_('Role'), max_length=255, blank=True)
    order = models.PositiveIntegerField(_('Order'), default=0)
    is_lead = models.BooleanField(_('Lead Role'), default=False)

    class Meta:
        verbose_name = _('Movie Actor')
        verbose_name_plural = _('Movie Actors')
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(fields=['movie', 'actor'], name='uq_movie_actor'),
        ]

    def __str__(self):
        return f'{self.actor.name} in {self.movie.title}'


class Series(models.Model):
    class Status(models.TextChoices):
        ONGOING = 'ongoing', _('Ongoing')
        ENDED = 'ended', _('Ended')
        UPCOMING = 'upcoming', _('Upcoming')
        CANCELLED = 'cancelled', _('Cancelled')
        ON_HOLD = 'on_hold', _('On Hold')

    title = models.CharField(_('Title'), max_length=255, db_index=True)
    original_title = models.CharField(_('Original Title'), max_length=255, blank=True)
    slug = models.SlugField(_('Slug'), max_length=280, unique=True, allow_unicode=True)
    short_description = models.CharField(_('Short Description'), max_length=500, blank=True)
    description = models.TextField(_('Description'), blank=True)
    start_year = models.PositiveIntegerField(_('Start Year'), null=True, blank=True, db_index=True)
    end_year = models.PositiveIntegerField(_('End Year'), null=True, blank=True)

    genres = models.ManyToManyField(Genre, verbose_name=_('Genres'), related_name='series', blank=True)
    actors = models.ManyToManyField(Actor, verbose_name=_('Actors'), related_name='series', blank=True, through='SeriesActor')
    directors = models.ManyToManyField(Director, verbose_name=_('Directors'), related_name='series', blank=True)
    countries = models.ManyToManyField(Country, verbose_name=_('Countries'), related_name='series', blank=True)
    tags = models.ManyToManyField(Tag, verbose_name=_('Tags'), related_name='series', blank=True)

    poster = models.ImageField(_('Poster'), upload_to='catalog/series/posters/', null=True, blank=True)
    backdrop = models.ImageField(_('Backdrop'), upload_to='catalog/series/backdrops/', null=True, blank=True)
    trailer_url = models.CharField(_('Trailer object key'), max_length=500, blank=True, validators=[validate_object_key])

    imdb_rating = models.DecimalField(
        _('IMDb Rating'), max_digits=3, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
    )
    site_rating = models.DecimalField(
        _('Site Rating'), max_digits=3, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
    )
    age_rating = models.CharField(_('Age Rating'), max_length=20, blank=True, db_index=True)
    language = models.CharField(_('Language'), max_length=100, blank=True)
    content_format = models.CharField(
        _('Content Format'), max_length=20, choices=ContentFormat.choices,
        default=ContentFormat.LIVE_ACTION, db_index=True,
    )
    is_dubbed = models.BooleanField(_('Dubbed'), default=False, db_index=True)
    has_subtitle = models.BooleanField(_('Has Subtitle'), default=False, db_index=True)
    is_uncensored = models.BooleanField(_('Uncensored'), default=False, db_index=True)
    content_warnings = models.JSONField(_('Content Warnings'), default=list, blank=True)

    status = models.CharField(_('Status'), max_length=20, choices=Status.choices, default=Status.ONGOING, db_index=True)
    is_published = models.BooleanField(_('Published'), default=False, db_index=True)
    is_featured = models.BooleanField(_('Featured'), default=False, db_index=True)

    view_count = models.PositiveBigIntegerField(_('View Count'), default=0)
    like_count = models.PositiveBigIntegerField(_('Like Count'), default=0)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Series')
        verbose_name_plural = _('Series')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-start_year', 'is_published']),
            models.Index(fields=['is_published', '-view_count']),
            models.Index(fields=['slug', 'is_published']),
            models.Index(fields=['status', 'is_published']),
        ]

    def __str__(self):
        return self.title


class SeriesActor(models.Model):
    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name='series_actors')
    actor = models.ForeignKey(Actor, on_delete=models.CASCADE, related_name='series_roles')
    role = models.CharField(_('Role'), max_length=255, blank=True)
    order = models.PositiveIntegerField(_('Order'), default=0)
    is_lead = models.BooleanField(_('Lead Role'), default=False)

    class Meta:
        verbose_name = _('Series Actor')
        verbose_name_plural = _('Series Actors')
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(fields=['series', 'actor'], name='uq_series_actor'),
        ]

    def __str__(self):
        return f'{self.actor.name} in {self.series.title}'


class Season(models.Model):
    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name='seasons', verbose_name=_('Series'))
    season_number = models.PositiveIntegerField(_('Season Number'), db_index=True)
    title = models.CharField(_('Title'), max_length=255, blank=True)
    description = models.TextField(_('Description'), blank=True)
    release_year = models.PositiveIntegerField(_('Release Year'), null=True, blank=True)
    poster = models.ImageField(_('Poster'), upload_to='catalog/seasons/posters/', null=True, blank=True)
    episode_count = models.PositiveIntegerField(_('Episode Count'), default=0)
    air_date = models.DateField(_('Air Date'), null=True, blank=True)
    is_published = models.BooleanField(_('Published'), default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Season')
        verbose_name_plural = _('Seasons')
        ordering = ['series', 'season_number']
        constraints = [
            models.UniqueConstraint(fields=['series', 'season_number'], name='uq_series_season'),
        ]
        indexes = [
            models.Index(fields=['series', 'season_number']),
            models.Index(fields=['series', 'is_published']),
        ]

    def __str__(self):
        return f'{self.series.title} - Season {self.season_number}'


class Episode(models.Model):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='episodes', verbose_name=_('Season'))
    episode_number = models.PositiveIntegerField(_('Episode Number'), db_index=True)
    title = models.CharField(_('Title'), max_length=255)
    description = models.TextField(_('Description'), blank=True)
    duration_minutes = models.PositiveIntegerField(_('Duration (Minutes)'), null=True, blank=True)

    poster = models.ImageField(_('Poster'), upload_to='catalog/episodes/posters/', null=True, blank=True)
    video_url = models.CharField(_('HLS manifest object key'), max_length=500, blank=True, validators=[validate_object_key])
    trailer_url = models.CharField(_('Trailer object key'), max_length=500, blank=True, validators=[validate_object_key])
    download_key = models.CharField(_('Download object key'), max_length=500, blank=True, validators=[validate_object_key])
    subtitle_tracks = models.JSONField(_('Subtitle tracks'), default=list, blank=True, validators=[validate_subtitle_tracks])
    air_date = models.DateField(_('Air Date'), null=True, blank=True, db_index=True)

    is_published = models.BooleanField(_('Published'), default=False, db_index=True)
    view_count = models.PositiveBigIntegerField(_('View Count'), default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Episode')
        verbose_name_plural = _('Episodes')
        ordering = ['season', 'episode_number']
        constraints = [
            models.UniqueConstraint(fields=['season', 'episode_number'], name='uq_season_episode'),
        ]
        indexes = [
            models.Index(fields=['season', 'episode_number']),
            models.Index(fields=['season', 'is_published']),
            models.Index(fields=['air_date', 'is_published']),
        ]

    def __str__(self):
        return f'{self.season.series.title} S{self.season.season_number}E{self.episode_number} - {self.title}'
