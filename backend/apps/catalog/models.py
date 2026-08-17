import uuid
from pathlib import Path

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from config.public_urls import (
    validate_download_links, validate_object_key, validate_subtitle_tracks,
)


def _safe_movie_image_path(directory, filename):
    """Keep user supplied filenames out of storage object keys."""
    extension = Path(filename or '').suffix.lower()
    if extension not in {'.jpg', '.jpeg', '.png', '.webp'}:
        extension = '.img'
    return f'catalog/movies/{directory}/{uuid.uuid4().hex}{extension}'


def movie_poster_upload_path(instance, filename):
    return _safe_movie_image_path('posters', filename)


def movie_backdrop_upload_path(instance, filename):
    return _safe_movie_image_path('backdrops', filename)

class ContentFormat(models.TextChoices):
    LIVE_ACTION = 'live_action', _('Live Action')
    ANIMATION = 'animation', _('Animation')
    SHORT = 'short', _('Short')


class MediaStatus(models.TextChoices):
    MISSING = 'missing', _('Media missing')
    PROCESSING = 'processing', _('Media processing')
    READY = 'ready', _('Media ready')
    ERROR = 'error', _('Media error')
    FAILED = 'failed', _('Media failed')


class CatalogSyncRun(models.Model):
    class Mode(models.TextChoices):
        INCREMENTAL = 'incremental', _('Incremental')
        DAILY = 'daily', _('Daily releases')
        TRENDING = 'trending', _('Trending')
        FULL = 'full', _('Full catalog')

    class Status(models.TextChoices):
        QUEUED = 'queued', _('Queued')
        RUNNING = 'running', _('Running')
        CANCELLING = 'cancelling', _('Cancelling')
        CANCELLED = 'cancelled', _('Cancelled')
        SUCCEEDED = 'succeeded', _('Succeeded')
        FAILED = 'failed', _('Failed')

    provider = models.CharField(_('Provider'), max_length=40, default='tmdb')
    mode = models.CharField(_('Mode'), max_length=20, choices=Mode.choices, default=Mode.INCREMENTAL)
    status = models.CharField(_('Status'), max_length=20, choices=Status.choices, default=Status.QUEUED)
    phase = models.CharField(_('Phase'), max_length=40, default='queued')
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='catalog_sync_runs',
    )
    task_id = models.CharField(_('Celery task ID'), max_length=255, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    cancel_requested_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    discovered_count = models.PositiveIntegerField(default=0)
    total_count = models.PositiveIntegerField(default=0)
    processed_count = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    published_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    current_tmdb_id = models.PositiveIntegerField(null=True, blank=True)
    errors = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['-started_at']
        verbose_name = _('Catalog sync run')
        verbose_name_plural = _('Catalog sync runs')
        constraints = [
            models.UniqueConstraint(
                fields=['provider'],
                condition=models.Q(status__in=['queued', 'running', 'cancelling']),
                name='catalog_one_active_sync_per_provider',
            ),
        ]

    def __str__(self):
        return f'{self.provider} · {self.started_at:%Y-%m-%d %H:%M} · {self.status}'

    @property
    def is_active(self):
        return self.status in {
            self.Status.QUEUED,
            self.Status.RUNNING,
            self.Status.CANCELLING,
        }


class CatalogImporterSettings(models.Model):
    """Editable, non-secret settings used by manual and scheduled imports."""

    class AutomaticMode(models.TextChoices):
        DAILY = 'daily', _('Daily releases')
        TRENDING = 'trending', _('Trending')

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    language = models.CharField(_('TMDb language'), max_length=10, default='fa-IR')
    fallback_language = models.CharField(_('Fallback language'), max_length=10, default='en-US')
    region = models.CharField(_('TMDb region'), max_length=2, default='IR', blank=True)
    daily_lookback_days = models.PositiveSmallIntegerField(
        _('Daily lookback days'), default=2,
        validators=[MinValueValidator(1), MaxValueValidator(14)],
    )
    daily_lookahead_days = models.PositiveSmallIntegerField(
        _('Daily lookahead days'), default=7,
        validators=[MinValueValidator(0), MaxValueValidator(90)],
    )
    daily_max_pages = models.PositiveSmallIntegerField(
        _('Daily maximum pages'), default=5,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
    )
    trending_window = models.CharField(
        _('Trending window'), max_length=8,
        choices=[('day', _('Day')), ('week', _('Week'))], default='day',
    )
    trending_max_pages = models.PositiveSmallIntegerField(
        _('Trending maximum pages'), default=3,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
    )
    import_people_images = models.BooleanField(_('Import cast and director images'), default=True)
    cast_import_limit = models.PositiveSmallIntegerField(
        _('Cast import limit'),
        default=15,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
        help_text=_('Maximum number of cast members imported per title (1–50).'),
    )
    fetch_imdb_ratings = models.BooleanField(_('Fetch IMDb ratings'), default=True)
    feature_trending = models.BooleanField(_('Feature trending imports'), default=True)
    auto_publish = models.BooleanField(_('Publish complete imported metadata'), default=False)
    automation_enabled = models.BooleanField(_('Enable scheduled imports'), default=False)
    automation_mode = models.CharField(
        _('Scheduled import mode'), max_length=12,
        choices=AutomaticMode.choices, default=AutomaticMode.DAILY,
    )
    automation_interval_hours = models.PositiveSmallIntegerField(
        _('Scheduled interval (hours)'), default=24,
        validators=[MinValueValidator(1), MaxValueValidator(168)],
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='catalog_importer_settings_updates',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Catalog importer settings')
        verbose_name_plural = _('Catalog importer settings')

    def save(self, *args, **kwargs):
        self.pk = 1
        self.region = (self.region or '').strip().upper()
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        defaults = {
            'language': getattr(settings, 'TMDB_LANGUAGE', 'fa-IR'),
            'fallback_language': getattr(settings, 'TMDB_FALLBACK_LANGUAGE', 'en-US'),
            'region': getattr(settings, 'TMDB_REGION', 'IR'),
            'daily_lookback_days': getattr(settings, 'CATALOG_SYNC_LOOKBACK_DAYS', 2),
            'daily_lookahead_days': getattr(settings, 'CATALOG_SYNC_LOOKAHEAD_DAYS', 7),
            'daily_max_pages': min(100, getattr(settings, 'CATALOG_SYNC_MAX_PAGES', 5)),
            'automation_enabled': getattr(settings, 'CATALOG_SYNC_ENABLED', False),
            'auto_publish': getattr(settings, 'CATALOG_AUTO_PUBLISH', False),
        }
        instance, _ = cls.objects.get_or_create(pk=1, defaults=defaults)
        return instance

    def __str__(self):
        return str(_('TMDb importer settings'))


class CatalogSyncCandidate(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        SUCCEEDED = 'succeeded', _('Succeeded')
        SKIPPED = 'skipped', _('Skipped')
        FAILED = 'failed', _('Failed')

    run = models.ForeignKey(
        CatalogSyncRun,
        on_delete=models.CASCADE,
        related_name='candidates',
    )
    tmdb_id = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    popularity = models.FloatField(default=0.0)
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(
                fields=['run', 'tmdb_id'],
                name='catalog_unique_sync_candidate',
            ),
        ]
        indexes = [
            models.Index(fields=['run', 'status', 'id'], name='catalog_sync_work_idx'),
        ]

    def __str__(self):
        return f'run={self.run_id} tmdb={self.tmdb_id} · {self.status}'


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
    tmdb_id = models.PositiveIntegerField(_('TMDb ID'), null=True, blank=True, unique=True)
    name = models.CharField(_('Name'), max_length=255, db_index=True)
    original_name = models.CharField(_('Original name'), max_length=255, blank=True, db_index=True)
    slug = models.SlugField(_('Slug'), max_length=280, unique=True, allow_unicode=True)
    photo = models.ImageField(_('Photo'), upload_to='catalog/actors/', null=True, blank=True)
    biography = models.TextField(_('Biography'), blank=True)
    birth_date = models.DateField(_('Birth Date'), null=True, blank=True, db_index=True)
    birth_place = models.CharField(_('Birth Place'), max_length=255, blank=True)
    is_featured = models.BooleanField(_('Featured'), default=False)
    popularity = models.FloatField(_('Popularity'), default=0.0, db_index=True)
    profile_path = models.CharField(_('TMDb profile path'), max_length=255, blank=True)
    photo_external_url = models.URLField(_('External photo URL'), max_length=500, blank=True)

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
    tmdb_id = models.PositiveIntegerField(_('TMDb ID'), null=True, blank=True, unique=True)
    name = models.CharField(_('Name'), max_length=255, db_index=True)
    original_name = models.CharField(_('Original name'), max_length=255, blank=True, db_index=True)
    slug = models.SlugField(_('Slug'), max_length=280, unique=True, allow_unicode=True)
    photo = models.ImageField(_('Photo'), upload_to='catalog/directors/', null=True, blank=True)
    biography = models.TextField(_('Biography'), blank=True)
    birth_date = models.DateField(_('Birth Date'), null=True, blank=True, db_index=True)
    birth_place = models.CharField(_('Birth Place'), max_length=255, blank=True)
    is_featured = models.BooleanField(_('Featured'), default=False)
    popularity = models.FloatField(_('Popularity'), default=0.0, db_index=True)
    profile_path = models.CharField(_('TMDb profile path'), max_length=255, blank=True)
    photo_external_url = models.URLField(_('External photo URL'), max_length=500, blank=True)

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
    class PublicationStatus(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        PUBLISHED = 'published', _('Published')
        ARCHIVED = 'archived', _('Archived')

    class CatalogType(models.TextChoices):
        MOVIE = 'movie', _('Movie')
        DOCUMENTARY = 'documentary', _('Documentary')
        SHORT = 'short', _('Short')

    title = models.CharField(_('Persian Title'), max_length=255, db_index=True)
    original_title = models.CharField(_('English Title'), max_length=255, blank=True)
    slug = models.SlugField(_('Slug'), max_length=280, unique=True, allow_unicode=True)
    short_description = models.CharField(_('Short Description'), max_length=500, blank=True)
    description = models.TextField(_('Description'), blank=True)
    release_year = models.PositiveIntegerField(_('Release Year'), null=True, blank=True, db_index=True)
    release_date = models.DateField(_('Release Date'), null=True, blank=True, db_index=True)
    duration_minutes = models.PositiveIntegerField(_('Duration (Minutes)'), null=True, blank=True)
    catalog_type = models.CharField(_('Catalog type'), max_length=20, choices=CatalogType.choices, default=CatalogType.MOVIE, db_index=True)
    publication_status = models.CharField(_('Publication status'), max_length=20, choices=PublicationStatus.choices, default=PublicationStatus.DRAFT, db_index=True)

    genres = models.ManyToManyField(Genre, verbose_name=_('Genres'), related_name='movies', blank=True)
    actors = models.ManyToManyField(Actor, verbose_name=_('Actors'), related_name='movies', blank=True, through='MovieActor')
    directors = models.ManyToManyField(Director, verbose_name=_('Directors'), related_name='movies', blank=True)
    countries = models.ManyToManyField(Country, verbose_name=_('Countries'), related_name='movies', blank=True)
    tags = models.ManyToManyField(Tag, verbose_name=_('Tags'), related_name='movies', blank=True)

    poster = models.ImageField(_('Poster'), upload_to=movie_poster_upload_path, null=True, blank=True)
    backdrop = models.ImageField(_('Backdrop'), upload_to=movie_backdrop_upload_path, null=True, blank=True)
    trailer_url = models.CharField(_('Trailer object key'), max_length=500, blank=True, validators=[validate_object_key])
    video_url = models.CharField(_('HLS manifest object key'), max_length=500, blank=True, validators=[validate_object_key])
    download_key = models.CharField(_('Download object key'), max_length=500, blank=True, validators=[validate_object_key])
    download_links = models.JSONField(
        _('Download links'), default=list, blank=True, validators=[validate_download_links],
    )
    subtitle_tracks = models.JSONField(_('Subtitle tracks'), default=list, blank=True, validators=[validate_subtitle_tracks])
    media_status = models.CharField(_('Media status'), max_length=20, choices=MediaStatus.choices, default=MediaStatus.MISSING, db_index=True)
    rights_verified = models.BooleanField(_('Rights verified'), default=False, db_index=True)
    auto_publish = models.BooleanField(_('Auto publish when ready'), default=False, db_index=True)
    scheduled_publish_at = models.DateTimeField(_('Scheduled publish time'), null=True, blank=True, db_index=True)
    metadata_source = models.CharField(_('Metadata source'), max_length=40, default='manual', blank=True)
    metadata_synced_at = models.DateTimeField(_('Metadata synced at'), null=True, blank=True)
    source_metadata = models.JSONField(_('Source metadata'), default=dict, blank=True)
    manual_override_fields = models.JSONField(_('Manually edited fields'), default=list, blank=True)
    last_tmdb_sync_at = models.DateTimeField(_('Last TMDb sync'), null=True, blank=True)
    poster_path = models.CharField(_('TMDb poster path'), max_length=255, blank=True)
    backdrop_path = models.CharField(_('TMDb backdrop path'), max_length=255, blank=True)
    poster_external_url = models.URLField(_('External poster URL'), max_length=500, blank=True)
    backdrop_external_url = models.URLField(_('External backdrop URL'), max_length=500, blank=True)
    trailer_external_url = models.URLField(_('External trailer URL'), max_length=500, blank=True)
    quality = models.CharField(_('Quality'), max_length=80, blank=True)
    spoken_languages = models.JSONField(_('Spoken languages'), default=list, blank=True)
    production_companies = models.JSONField(_('Production companies'), default=list, blank=True)
    crew_metadata = models.JSONField(_('Crew metadata'), default=list, blank=True)
    writers = models.JSONField(_('Writers'), default=list, blank=True)

    imdb_rating = models.DecimalField(
        _('IMDb Rating'), max_digits=3, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
    )
    imdb_rank = models.PositiveSmallIntegerField(
        _('IMDb Top 250 rank'),
        null=True,
        blank=True,
        db_index=True,
        help_text=_('1–250 when this title is on the IMDb Top 250 chart; null otherwise.'),
    )
    site_rating = models.DecimalField(
        _('Site Rating'), max_digits=3, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
    )
    age_rating = models.CharField(_('Age Rating'), max_length=20, blank=True, db_index=True)
    language = models.CharField(_('Language'), max_length=100, blank=True)
    original_language = models.CharField(_('Original language'), max_length=20, blank=True, db_index=True)
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
    rating_average = models.DecimalField(
        _('TMDb rating average'), max_digits=3, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
    )
    vote_count = models.PositiveBigIntegerField(_('TMDb vote count'), default=0)
    popularity = models.FloatField(_('TMDb popularity'), default=0.0, db_index=True)

    meta_title = models.CharField(_('SEO Title'), max_length=255, blank=True)
    meta_description = models.CharField(_('SEO Description'), max_length=500, blank=True)
    seo_keywords = models.JSONField(_('SEO keywords'), default=list, blank=True)

    is_published = models.BooleanField(_('Published'), default=False, db_index=True)
    is_featured = models.BooleanField(_('Featured'), default=False, db_index=True)
    is_recommended = models.BooleanField(_('Recommended'), default=False, db_index=True)

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
            models.Index(
                fields=['is_published', '-view_count', '-like_count', '-popularity'],
                name='catalog_mov_pub_pop_idx',
            ),
            models.Index(
                fields=['is_published', '-created_at', '-id'],
                name='catalog_mov_pub_new_idx',
            ),
            models.Index(
                fields=['is_published', 'id'],
                name='catalog_mov_pub_dl_idx',
                condition=(
                    models.Q(download_links__isnull=False)
                    & ~models.Q(download_links=[])
                ) | (
                    models.Q(download_key__isnull=False)
                    & ~models.Q(download_key='')
                ),
            ),
            models.Index(fields=['is_published', '-updated_at']),
            models.Index(fields=['slug', 'is_published']),
            models.Index(fields=['publication_status', '-updated_at']),
            models.Index(fields=['catalog_type', 'publication_status']),
            models.Index(fields=['is_published', 'imdb_rank']),
        ]

    def __str__(self):
        return self.title

    @property
    def seo_title(self):
        return self.meta_title or self.title

    @property
    def has_downloads(self):
        flag = getattr(self, '_has_downloads_flag', None)
        if flag is not None:
            return bool(flag)
        if any(
            isinstance(item, dict) and (item.get('url') or item.get('key'))
            for item in (self.download_links or [])
        ):
            return True
        return bool(self.download_key)

    @property
    def download_qualities(self):
        qualities = []
        for item in (self.download_links or []):
            if not isinstance(item, dict):
                continue
            if not (item.get('url') or item.get('key')):
                continue
            quality = str(item.get('quality') or item.get('label') or '').strip()
            if quality and quality not in qualities:
                qualities.append(quality)
        if not qualities and self.quality:
            qualities.append(self.quality)
        return qualities[:24]

    @property
    def seo_description(self):
        base = self.meta_description or self.short_description or (self.description or '')[:160]
        if self.meta_description:
            return base
        if not self.pk:
            return base
        extras = []
        cast_names = list(
            self.movie_actors.select_related('actor')
            .order_by('order')
            .values_list('actor__name', flat=True)[:6]
        )
        if cast_names:
            extras.append(f'بازیگران: {"، ".join(cast_names)}')
        qualities = self.download_qualities
        if qualities:
            extras.append(f'دانلود: {"، ".join(qualities)}')
        if not extras:
            return base
        combined = f'{base} {" ".join(extras)}'.strip()
        return combined[:500]

    @property
    def effective_seo_keywords(self):
        keywords = []
        for item in (self.seo_keywords or []):
            value = str(item or '').strip()
            if value and value not in keywords:
                keywords.append(value)
        for name in (self.title, self.original_title):
            value = str(name or '').strip()
            if value and value not in keywords:
                keywords.append(value)
        if self.has_downloads:
            for token in ('دانلود', 'دانلود فیلم'):
                if token not in keywords:
                    keywords.append(token)
        for quality in self.download_qualities:
            if quality not in keywords:
                keywords.append(quality)
        if self.pk:
            for name in self.movie_actors.select_related('actor').order_by('order').values_list('actor__name', flat=True)[:8]:
                if name and name not in keywords:
                    keywords.append(name)
            for title in self.genres.values_list('title', flat=True)[:8]:
                if title and title not in keywords:
                    keywords.append(title)
        return keywords[:24]

    @property
    def duration_text(self):
        return f'{self.duration_minutes} min' if self.duration_minutes else ''

    @property
    def auto_publish_blockers(self):
        blockers = []
        if not self.description:
            blockers.append('missing_description')
        if not self.release_date:
            blockers.append('missing_release_date')
        if not self.poster and not self.poster_external_url and not self.poster_path:
            blockers.append('missing_poster')
        # Never auto-publish titles without download/playback URLs.
        if not self.has_downloads and not (self.video_url or '').strip():
            blockers.append('missing_playback_links')
        return blockers

    @property
    def ready_for_auto_publish(self):
        return not self.auto_publish_blockers

    def save(self, *args, **kwargs):
        # Keep public dub/subtitle badges honest with download_links + subtitle_tracks.
        from apps.catalog.subtitle_extract import apply_availability_flags

        changed = apply_availability_flags(self, self.download_links or [])
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and changed:
            kwargs['update_fields'] = list({*update_fields, *changed, 'updated_at'})
        super().save(*args, **kwargs)


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


class MovieSyncAudit(models.Model):
    class Action(models.TextChoices):
        IMPORT = 'import', _('Import')
        SYNC = 'sync', _('Sync')
        MANUAL_CREATE = 'manual_create', _('Manual create')
        MANUAL_UPDATE = 'manual_update', _('Manual update')
        ARCHIVE = 'archive', _('Archive')

    movie = models.ForeignKey(Movie, on_delete=models.SET_NULL, null=True, blank=True, related_name='sync_audits')
    actor = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='catalog_sync_audits')
    action = models.CharField(max_length=30, choices=Action.choices, db_index=True)
    tmdb_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    overwrite = models.BooleanField(default=False)
    dry_run = models.BooleanField(default=False)
    changed_fields = models.JSONField(default=list, blank=True)
    skipped_fields = models.JSONField(default=list, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['movie', '-created_at'])]

    def __str__(self):
        return f'{self.action} movie={self.movie_id} tmdb={self.tmdb_id}'


class Series(models.Model):
    class Status(models.TextChoices):
        ONGOING = 'ongoing', _('Ongoing')
        ENDED = 'ended', _('Ended')
        UPCOMING = 'upcoming', _('Upcoming')
        CANCELLED = 'cancelled', _('Cancelled')
        ON_HOLD = 'on_hold', _('On Hold')

    title = models.CharField(_('Persian Title'), max_length=255, db_index=True)
    original_title = models.CharField(_('English Title'), max_length=255, blank=True)
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
    poster_external_url = models.URLField(_('External poster URL'), max_length=500, blank=True)
    backdrop_external_url = models.URLField(_('External backdrop URL'), max_length=500, blank=True)
    trailer_external_url = models.URLField(_('External trailer URL'), max_length=500, blank=True)

    imdb_rating = models.DecimalField(
        _('IMDb Rating'), max_digits=3, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
    )
    imdb_rank = models.PositiveSmallIntegerField(
        _('IMDb Top 250 rank'),
        null=True,
        blank=True,
        db_index=True,
        help_text=_('1–250 when this title is on the IMDb Top 250 TV chart; null otherwise.'),
    )
    site_rating = models.DecimalField(
        _('Site Rating'), max_digits=3, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
    )
    age_rating = models.CharField(_('Age Rating'), max_length=20, blank=True, db_index=True)
    language = models.CharField(_('Language'), max_length=100, blank=True)
    original_language = models.CharField(_('Original language'), max_length=20, blank=True, db_index=True)
    content_format = models.CharField(
        _('Content Format'), max_length=20, choices=ContentFormat.choices,
        default=ContentFormat.LIVE_ACTION, db_index=True,
    )
    is_dubbed = models.BooleanField(_('Dubbed'), default=False, db_index=True)
    has_subtitle = models.BooleanField(_('Has Subtitle'), default=False, db_index=True)
    is_uncensored = models.BooleanField(_('Uncensored'), default=False, db_index=True)
    content_warnings = models.JSONField(_('Content Warnings'), default=list, blank=True)

    status = models.CharField(_('Status'), max_length=20, choices=Status.choices, default=Status.ONGOING, db_index=True)
    imdb_id = models.CharField(_('IMDb ID'), max_length=20, blank=True, null=True, unique=True)
    tmdb_id = models.PositiveIntegerField(_('TMDb ID'), blank=True, null=True, unique=True)
    rating_average = models.DecimalField(
        _('TMDb rating average'), max_digits=3, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
    )
    vote_count = models.PositiveBigIntegerField(_('TMDb vote count'), default=0)
    popularity = models.FloatField(_('TMDb popularity'), default=0.0, db_index=True)
    metadata_source = models.CharField(_('Metadata source'), max_length=40, default='manual', blank=True)
    metadata_synced_at = models.DateTimeField(_('Metadata synced at'), null=True, blank=True)
    last_tmdb_sync_at = models.DateTimeField(_('Last TMDb sync'), null=True, blank=True)
    source_metadata = models.JSONField(_('Source metadata'), default=dict, blank=True)
    download_links = models.JSONField(
        _('Download links'), default=list, blank=True, validators=[validate_download_links],
    )
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
            models.Index(
                fields=['is_published', '-view_count', '-like_count', '-popularity'],
                name='catalog_ser_pub_pop_idx',
            ),
            models.Index(
                fields=['is_published', '-created_at', '-id'],
                name='catalog_ser_pub_new_idx',
            ),
            models.Index(
                fields=['is_published', 'id'],
                name='catalog_ser_pub_dl_idx',
                condition=(
                    models.Q(download_links__isnull=False)
                    & ~models.Q(download_links=[])
                ),
            ),
            models.Index(fields=['is_published', '-updated_at']),
            models.Index(fields=['slug', 'is_published']),
            models.Index(fields=['status', 'is_published']),
            models.Index(fields=['is_published', 'imdb_rank']),
        ]

    def __str__(self):
        return self.title

    @property
    def has_downloads(self):
        flag = getattr(self, '_has_downloads_flag', None)
        if flag is not None:
            return bool(flag)
        return any(
            isinstance(item, dict) and (item.get('url') or item.get('key'))
            for item in (self.download_links or [])
        )

    @property
    def download_qualities(self):
        qualities = []
        for item in (self.download_links or []):
            if not isinstance(item, dict):
                continue
            if not (item.get('url') or item.get('key')):
                continue
            quality = str(item.get('quality') or item.get('label') or '').strip()
            if quality and quality not in qualities:
                qualities.append(quality)
        return qualities[:24]

    def save(self, *args, **kwargs):
        from apps.catalog.subtitle_extract import apply_availability_flags

        changed = apply_availability_flags(self, self.download_links or [])
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and changed:
            kwargs['update_fields'] = list({*update_fields, *changed, 'updated_at'})
        super().save(*args, **kwargs)


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
    tmdb_id = models.PositiveIntegerField(_('TMDb ID'), null=True, blank=True, unique=True)
    season_number = models.PositiveIntegerField(_('Season Number'), db_index=True)
    title = models.CharField(_('Title'), max_length=255, blank=True)
    description = models.TextField(_('Description'), blank=True)
    release_year = models.PositiveIntegerField(_('Release Year'), null=True, blank=True)
    poster = models.ImageField(_('Poster'), upload_to='catalog/seasons/posters/', null=True, blank=True)
    poster_external_url = models.URLField(_('External poster URL'), max_length=500, blank=True)
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


class MovieArchiveAsset(models.Model):
    """Private original movie file archived in S3-compatible object storage.

    Distinct from Movie.video_url / download_key, which hold public CDN/HLS keys.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        MULTIPART_CREATED = 'multipart_created', _('Multipart created')
        UPLOADING = 'uploading', _('Uploading')
        VERIFYING = 'verifying', _('Verifying')
        AVAILABLE = 'available', _('Available')
        FAILED = 'failed', _('Failed')
        ABORTED = 'aborted', _('Aborted')
        DELETION_PENDING = 'deletion_pending', _('Deletion pending')
        DELETED = 'deleted', _('Deleted')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='archive_assets')
    storage_provider = models.CharField(_('Storage provider'), max_length=40, default='arvan_s3')
    bucket = models.CharField(_('Bucket'), max_length=255)
    object_key = models.CharField(_('Object key'), max_length=1024, unique=True)
    original_filename = models.CharField(_('Original filename'), max_length=255)
    safe_filename = models.CharField(_('Safe filename'), max_length=255)
    file_extension = models.CharField(_('File extension'), max_length=16)
    content_type = models.CharField(_('Content type'), max_length=100)
    size_bytes = models.PositiveBigIntegerField(_('Expected size (bytes)'))
    actual_size_bytes = models.PositiveBigIntegerField(_('Actual size (bytes)'), null=True, blank=True)
    etag = models.CharField(_('ETag'), max_length=255, blank=True)
    sha256 = models.CharField(_('SHA-256'), max_length=64, blank=True)
    upload_id = models.CharField(_('Multipart upload ID'), max_length=255, blank=True)
    part_size_bytes = models.PositiveBigIntegerField(_('Part size (bytes)'))
    total_parts = models.PositiveIntegerField(_('Total parts'))
    status = models.CharField(
        _('Status'), max_length=32, choices=Status.choices, default=Status.PENDING, db_index=True,
    )
    failure_reason = models.CharField(_('Failure reason'), max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_archive_assets',
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='uploaded_archive_assets',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    aborted_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('Movie archive asset')
        verbose_name_plural = _('Movie archive assets')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['movie', 'status']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f'{self.movie_id} · {self.safe_filename} · {self.status}'


class ProviderSource(models.Model):
    class ProviderType(models.TextChoices):
        API = 'api', _('API')
        FEED = 'feed', _('Feed')
        COOKIE_SESSION = 'cookie_session', _('Cookie session')
        SESSION_LOGIN = 'session_login', _('Session login')
        STATIC_LINKS = 'static_links', _('Static links')
        CUSTOM = 'custom', _('Custom')

    class AuthType(models.TextChoices):
        NONE = 'none', _('None')
        API_KEY = 'api_key', _('API key')
        BEARER_TOKEN = 'bearer_token', _('Bearer token')
        USERNAME_PASSWORD = 'username_password', _('Username / password')
        COOKIE_SESSION = 'cookie_session', _('Cookie session')
        FEED = 'feed', _('Feed')

    name = models.CharField(_('Name'), max_length=120)
    slug = models.SlugField(_('Slug'), max_length=120, unique=True)
    provider_type = models.CharField(
        _('Provider type'), max_length=32, choices=ProviderType.choices, default=ProviderType.CUSTOM,
    )
    base_url = models.URLField(_('Base URL'), max_length=500, blank=True)
    auth_type = models.CharField(
        _('Auth type'), max_length=32, choices=AuthType.choices, default=AuthType.NONE,
    )
    is_active = models.BooleanField(_('Active'), default=True, db_index=True)
    rate_limit_per_minute = models.PositiveIntegerField(_('Rate limit / minute'), default=30)
    timeout_seconds = models.PositiveIntegerField(_('Timeout (seconds)'), default=30)
    verify_ssl = models.BooleanField(_('Verify SSL'), default=True)
    config = models.JSONField(_('Non-secret config'), default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = _('Provider source')
        verbose_name_plural = _('Provider sources')

    def __str__(self):
        return self.name


class ProviderCredential(models.Model):
    class SecretMode(models.TextChoices):
        ENV = 'env', _('Environment variables')
        ENCRYPTED = 'encrypted', _('Encrypted vault')

    class Status(models.TextChoices):
        UNKNOWN = 'unknown', _('Unknown')
        CONFIGURED = 'configured', _('Configured')
        VALID = 'valid', _('Valid')
        INVALID = 'invalid', _('Invalid')
        NEEDS_INTERACTIVE = 'needs_interactive', _('Needs interactive verification')

    provider = models.OneToOneField(
        ProviderSource, on_delete=models.CASCADE, related_name='credential',
    )
    secret_mode = models.CharField(
        _('Secret mode'), max_length=20, choices=SecretMode.choices, default=SecretMode.ENV,
    )
    env_prefix = models.CharField(_('Env prefix'), max_length=40, default='AVASARAMI')
    status = models.CharField(
        _('Status'), max_length=32, choices=Status.choices, default=Status.UNKNOWN, db_index=True,
    )
    last_validated_at = models.DateTimeField(null=True, blank=True)
    last_validation_message = models.CharField(max_length=500, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Provider credential')
        verbose_name_plural = _('Provider credentials')

    def __str__(self):
        return f'{self.provider.slug} · {self.status}'


class ProviderImportJob(models.Model):
    class ContentType(models.TextChoices):
        MOVIES = 'movies', _('Movies')
        SERIES = 'series', _('Series')
        BOTH = 'both', _('Both')
        MOVIE = 'movie', _('Movie')

    class Status(models.TextChoices):
        QUEUED = 'queued', _('Queued')
        VALIDATING = 'validating', _('Validating')
        SEARCHING = 'searching', _('Searching')
        AWAITING_REVIEW = 'awaiting_review', _('Awaiting review')
        RUNNING = 'running', _('Running')
        TRANSFERRING = 'transferring', _('Transferring')
        CANCEL_REQUESTED = 'cancel_requested', _('Cancel requested')
        COMPLETED = 'completed', _('Completed')
        PARTIALLY_COMPLETED = 'partially_completed', _('Partially completed')
        BLOCKED = 'blocked', _('Blocked')
        FAILED = 'failed', _('Failed')
        CANCELLED = 'cancelled', _('Cancelled')

    class Mode(models.TextChoices):
        DISCOVER_ONLY = 'discover_only', _('Discover only')
        IMPORT_MISSING_FILES = 'import_missing_files', _('Import missing files')
        IMPORT_SELECTED = 'import_selected', _('Import selected')
        IMPORT_MISSING = 'import_missing', _('Import missing')
        SYNC_ALL = 'sync_all', _('Sync all')

    class Trigger(models.TextChoices):
        MANUAL = 'manual', _('Manual')
        MOVIE_CREATED = 'movie_created', _('Movie created')
        MOVIE_UPDATED = 'movie_updated', _('Movie updated')
        SERIES_CREATED = 'series_created', _('Series created')
        SERIES_UPDATED = 'series_updated', _('Series updated')
        SCHEDULED_RETRY = 'scheduled_retry', _('Scheduled retry')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(ProviderSource, on_delete=models.CASCADE, related_name='import_jobs')
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='provider_import_jobs',
    )
    trigger = models.CharField(
        max_length=32, choices=Trigger.choices, default=Trigger.MANUAL, db_index=True,
    )
    target_movie = models.ForeignKey(
        'Movie', null=True, blank=True, on_delete=models.CASCADE, related_name='provider_import_jobs',
    )
    target_series = models.ForeignKey(
        'Series', null=True, blank=True, on_delete=models.CASCADE, related_name='provider_import_jobs',
    )
    content_type = models.CharField(
        _('Content type'), max_length=16, choices=ContentType.choices, default=ContentType.MOVIES,
    )
    status = models.CharField(
        _('Status'), max_length=32, choices=Status.choices, default=Status.QUEUED, db_index=True,
    )
    mode = models.CharField(_('Mode'), max_length=32, choices=Mode.choices, default=Mode.DISCOVER_ONLY)
    params = models.JSONField(default=dict, blank=True)
    total_items = models.PositiveIntegerField(default=0)
    processed_items = models.PositiveIntegerField(default=0)
    matched_items = models.PositiveIntegerField(default=0)
    imported_files = models.PositiveIntegerField(default=0)
    skipped_items = models.PositiveIntegerField(default=0)
    failed_items = models.PositiveIntegerField(default=0)
    current_item_label = models.CharField(max_length=255, blank=True)
    cancel_requested = models.BooleanField(default=False)
    checkpoint = models.JSONField(default=dict, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    sanitized_error_code = models.CharField(max_length=64, blank=True)
    task_id = models.CharField(max_length=255, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Provider import job')
        verbose_name_plural = _('Provider import jobs')
        indexes = [
            models.Index(fields=['provider', 'status']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['target_movie', 'status']),
            models.Index(fields=['target_series', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['provider', 'target_movie', 'mode'],
                condition=models.Q(
                    status__in=['queued', 'validating', 'searching', 'awaiting_review', 'running', 'transferring', 'cancel_requested'],
                    target_movie__isnull=False,
                ),
                name='uniq_active_provider_movie_job',
            ),
            models.UniqueConstraint(
                fields=['provider', 'target_series', 'mode'],
                condition=models.Q(
                    status__in=['queued', 'validating', 'searching', 'awaiting_review', 'running', 'transferring', 'cancel_requested'],
                    target_series__isnull=False,
                ),
                name='uniq_active_provider_series_job',
            ),
        ]

    def __str__(self):
        return f'{self.provider.slug} · {self.mode} · {self.status}'

    @property
    def is_active(self):
        return self.status in {
            self.Status.QUEUED,
            self.Status.VALIDATING,
            self.Status.SEARCHING,
            self.Status.AWAITING_REVIEW,
            self.Status.RUNNING,
            self.Status.TRANSFERRING,
            self.Status.CANCEL_REQUESTED,
        }


class ProviderImportItem(models.Model):
    class ContentType(models.TextChoices):
        MOVIE = 'movie', _('Movie')
        SERIES = 'series', _('Series')
        EPISODE = 'episode', _('Episode')

    class Status(models.TextChoices):
        DISCOVERED = 'discovered', _('Discovered')
        MATCHED = 'matched', _('Matched')
        AWAITING_APPROVAL = 'awaiting_approval', _('Awaiting approval')
        APPROVED = 'approved', _('Approved')
        SKIPPED = 'skipped', _('Skipped')
        DOWNLOADING = 'downloading', _('Downloading')
        UPLOADED = 'uploaded', _('Uploaded')
        FAILED = 'failed', _('Failed')

    job = models.ForeignKey(ProviderImportJob, on_delete=models.CASCADE, related_name='items')
    provider_item_id = models.CharField(max_length=255, db_index=True)
    content_type = models.CharField(max_length=16, choices=ContentType.choices, default=ContentType.MOVIE)
    title = models.CharField(max_length=255, blank=True)
    original_title = models.CharField(max_length=255, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    season_number = models.PositiveIntegerField(null=True, blank=True)
    episode_number = models.PositiveIntegerField(null=True, blank=True)
    tmdb_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    imdb_id = models.CharField(max_length=20, blank=True, db_index=True)
    match_score = models.FloatField(default=0)
    match_reasons = models.JSONField(default=list, blank=True)
    selected = models.BooleanField(default=False)
    manually_approved = models.BooleanField(default=False)
    matched_movie = models.ForeignKey(
        Movie, null=True, blank=True, on_delete=models.SET_NULL, related_name='provider_import_items',
    )
    matched_series = models.ForeignKey(
        Series, null=True, blank=True, on_delete=models.SET_NULL, related_name='provider_import_items',
    )
    matched_episode = models.ForeignKey(
        Episode, null=True, blank=True, on_delete=models.SET_NULL, related_name='provider_import_items',
    )
    selected_candidate = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DISCOVERED, db_index=True,
    )
    status_message = models.CharField(max_length=500, blank=True)
    archive_asset = models.ForeignKey(
        MovieArchiveAsset, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='provider_import_items',
    )
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']
        verbose_name = _('Provider import item')
        verbose_name_plural = _('Provider import items')
        indexes = [
            models.Index(fields=['job', 'status']),
            models.Index(fields=['job', 'provider_item_id']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['job', 'provider_item_id', 'content_type'],
                name='uniq_provider_item_per_job',
            ),
        ]

    def __str__(self):
        return f'{self.provider_item_id} · {self.status}'


class ProviderImportLog(models.Model):
    class Level(models.TextChoices):
        DEBUG = 'debug', _('Debug')
        INFO = 'info', _('Info')
        WARNING = 'warning', _('Warning')
        ERROR = 'error', _('Error')

    job = models.ForeignKey(ProviderImportJob, on_delete=models.CASCADE, related_name='logs')
    level = models.CharField(max_length=16, choices=Level.choices, default=Level.INFO, db_index=True)
    event_code = models.CharField(max_length=64, blank=True, db_index=True)
    message = models.CharField(max_length=500)
    context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Provider import log')
        verbose_name_plural = _('Provider import logs')

    def __str__(self):
        return f'{self.level}: {self.message[:60]}'


class PlaybackSubtitleGap(models.Model):
    """Playback report: online player opened without toggleable SoftSub cues."""

    class ContentType(models.TextChoices):
        MOVIE = 'movie', _('Movie')
        SERIES = 'series', _('Series')

    class Status(models.TextChoices):
        OPEN = 'open', _('Open')
        QUEUED = 'queued', _('Queued')
        RESOLVED = 'resolved', _('Resolved')
        UNAVAILABLE = 'unavailable', _('Unavailable')

    content_type = models.CharField(max_length=16, choices=ContentType.choices, db_index=True)
    object_id = models.PositiveIntegerField(db_index=True)
    episode_id = models.PositiveIntegerField(default=0, db_index=True)
    slug = models.SlugField(max_length=255, blank=True)
    title = models.CharField(max_length=300, blank=True)
    playback_version = models.CharField(max_length=32, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True,
    )
    report_count = models.PositiveIntegerField(default=1)
    last_result = models.CharField(max_length=64, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = _('Playback subtitle gap')
        verbose_name_plural = _('Playback subtitle gaps')
        indexes = [
            models.Index(fields=['content_type', 'object_id', 'status']),
            models.Index(fields=['status', '-updated_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['content_type', 'object_id', 'episode_id'],
                name='uniq_playback_subtitle_gap_target',
            ),
        ]

    def __str__(self):
        return f'{self.content_type}:{self.object_id} · {self.status}'
