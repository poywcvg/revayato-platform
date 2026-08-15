from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .ingestion import upsert_tmdb_movie
from .models import (
    Actor, CatalogImporterSettings, CatalogSyncCandidate, CatalogSyncRun, Country, Director, Episode, Genre, Movie,
    MovieActor, MovieSyncAudit, PlaybackSubtitleGap, Season, Series, SeriesActor, Tag,
)
from .tmdb import TMDBError, configured_tmdb_client


class MovieActorInline(admin.TabularInline):
    model = MovieActor
    extra = 1
    autocomplete_fields = ['actor']


class SeriesActorInline(admin.TabularInline):
    model = SeriesActor
    extra = 1
    autocomplete_fields = ['actor']


class SeasonInline(admin.TabularInline):
    model = Season
    extra = 0


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ['title', 'slug', 'is_featured']
    list_filter = ['is_featured']
    search_fields = ['title', 'slug']
    prepopulated_fields = {'slug': ('title',)}


@admin.register(CatalogSyncRun)
class CatalogSyncRunAdmin(admin.ModelAdmin):
    list_display = (
        'provider', 'mode', 'status', 'phase', 'started_at', 'processed_count',
        'total_count', 'created_count', 'updated_count', 'published_count', 'error_count',
    )
    list_filter = ('provider', 'mode', 'status', 'phase')
    readonly_fields = [
        field.name for field in CatalogSyncRun._meta.fields
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CatalogSyncCandidate)
class CatalogSyncCandidateAdmin(admin.ModelAdmin):
    list_display = ['run', 'tmdb_id', 'status', 'attempts', 'updated_at']
    list_filter = ['status']
    search_fields = ['tmdb_id', 'run__id']
    readonly_fields = [field.name for field in CatalogSyncCandidate._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CatalogImporterSettings)
class CatalogImporterSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        (_('Localization'), {'fields': ('language', 'fallback_language', 'region')}),
        (_('Daily releases'), {'fields': ('daily_lookback_days', 'daily_lookahead_days', 'daily_max_pages')}),
        (_('Trending'), {'fields': ('trending_window', 'trending_max_pages', 'feature_trending')}),
        (_('Metadata'), {'fields': ('import_people_images', 'cast_import_limit', 'fetch_imdb_ratings', 'auto_publish')}),
        (_('Automation'), {'fields': ('automation_enabled', 'automation_mode', 'automation_interval_hours')}),
        (_('Audit'), {'fields': ('updated_by', 'updated_at'), 'classes': ('collapse',)}),
    )
    readonly_fields = ('updated_by', 'updated_at')

    def has_add_permission(self, request):
        return not CatalogImporterSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(MovieSyncAudit)
class MovieSyncAuditAdmin(admin.ModelAdmin):
    list_display = ['action', 'movie', 'tmdb_id', 'actor', 'overwrite', 'dry_run', 'created_at']
    list_filter = ['action', 'overwrite', 'dry_run']
    search_fields = ['movie__title', 'tmdb_id', 'actor__email']
    readonly_fields = [field.name for field in MovieSyncAudit._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Actor)
class ActorAdmin(admin.ModelAdmin):
    list_display = ['name', 'birth_date', 'birth_place', 'popularity', 'is_featured']
    list_filter = ['is_featured']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['-popularity', 'name']
    readonly_fields = ['profile_path', 'photo_external_url']


@admin.register(Director)
class DirectorAdmin(admin.ModelAdmin):
    list_display = ['name', 'birth_date', 'birth_place', 'popularity', 'is_featured']
    list_filter = ['is_featured']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['-popularity', 'name']
    readonly_fields = ['profile_path', 'photo_external_url']


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ['name', 'code']
    search_fields = ['name', 'code']


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'is_featured']
    list_filter = ['is_featured']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = [
        'poster_thumb', 'title', 'release_year', 'content_format', 'imdb_rating',
        'tmdb_id', 'is_dubbed', 'has_subtitle',
        'is_published', 'is_featured', 'media_status', 'rights_verified',
        'auto_publish', 'view_count',
    ]
    list_display_links = ['poster_thumb', 'title']
    list_editable = ['is_published', 'is_featured']
    list_filter = [
        'is_published', 'is_featured', 'content_format',
        'is_dubbed', 'has_subtitle', 'is_uncensored', 'media_status',
        'rights_verified', 'auto_publish', 'metadata_source', 'genres', 'release_year',
    ]
    search_fields = [
        'title', 'original_title', 'slug', 'description', 'short_description',
        'imdb_id', 'tmdb_id', 'meta_title',
    ]
    prepopulated_fields = {'slug': ('title',)}
    filter_horizontal = ['genres', 'directors', 'countries', 'tags']
    inlines = [MovieActorInline]
    date_hierarchy = 'release_date'
    ordering = ['-updated_at']
    list_per_page = 40
    readonly_fields = [
        'poster_preview', 'backdrop_preview',
        'view_count', 'like_count', 'metadata_synced_at', 'source_metadata',
        'created_at', 'updated_at', 'duplicate_hints',
    ]
    actions = [
        'make_published', 'make_draft', 'make_featured', 'clear_featured',
        'sync_from_tmdb', 'sync_from_tmdb_overwrite',
    ]

    fieldsets = (
        (None, {
            'fields': (
                'title', 'original_title', 'slug', 'short_description', 'description',
                'duplicate_hints',
            ),
        }),
        (_('Details'), {
            'fields': (
                'release_year', 'release_date', 'duration_minutes', 'age_rating', 'language',
                'content_format', 'is_dubbed', 'has_subtitle', 'is_uncensored', 'content_warnings',
                'genres', 'directors', 'countries', 'tags',
            ),
        }),
        (_('Media'), {
            'fields': (
                'poster', 'poster_preview', 'backdrop', 'backdrop_preview',
                'trailer_url', 'video_url', 'download_key', 'download_links',
                'subtitle_tracks', 'media_status', 'rights_verified',
                'auto_publish', 'scheduled_publish_at',
            ),
        }),
        (_('Ratings'), {
            'fields': ('imdb_rating', 'site_rating'),
        }),
        (_('External IDs'), {
            'fields': ('imdb_id', 'tmdb_id'),
            'description': _(
                'Use staff API /api/admin/tmdb/search/ to find titles, then import by TMDB ID. '
                'Resync with the sync-from-TMDB admin action or POST /api/admin/movies/<id>/sync-tmdb/.'
            ),
        }),
        (_('SEO'), {
            'fields': ('meta_title', 'meta_description'),
        }),
        (_('Publication'), {
            'fields': ('is_published', 'is_featured'),
        }),
        (_('Metadata sync'), {
            'fields': ('metadata_source', 'metadata_synced_at', 'source_metadata'),
            'classes': ('collapse',),
        }),
        (_('Stats'), {
            'fields': ('view_count', 'like_count', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description=_('Poster'))
    def poster_thumb(self, obj):
        if not obj.poster:
            source = (obj.source_metadata or {}).get('poster_path')
            if source:
                return format_html(
                    '<img src="https://image.tmdb.org/t/p/w92{}" alt="" style="height:48px;border-radius:4px;" />',
                    source,
                )
            return '—'
        return format_html(
            '<img src="{}" alt="" style="height:48px;border-radius:4px;" />',
            obj.poster.url,
        )

    @admin.display(description=_('Poster preview'))
    def poster_preview(self, obj):
        if obj.poster:
            return format_html(
                '<img src="{}" alt="" style="max-height:220px;border-radius:8px;" />',
                obj.poster.url,
            )
        source = (obj.source_metadata or {}).get('poster_path')
        if source:
            return format_html(
                '<img src="https://image.tmdb.org/t/p/w342{}" alt="" style="max-height:220px;border-radius:8px;" />',
                source,
            )
        return '—'

    @admin.display(description=_('Backdrop preview'))
    def backdrop_preview(self, obj):
        if obj.backdrop:
            return format_html(
                '<img src="{}" alt="" style="max-height:180px;border-radius:8px;" />',
                obj.backdrop.url,
            )
        source = (obj.source_metadata or {}).get('backdrop_path')
        if source:
            return format_html(
                '<img src="https://image.tmdb.org/t/p/w780{}" alt="" style="max-height:180px;border-radius:8px;" />',
                source,
            )
        return '—'

    @admin.display(description=_('Duplicate hints'))
    def duplicate_hints(self, obj):
        if not obj.pk:
            return _('Save once to check duplicates.')
        hints = []
        if obj.tmdb_id and Movie.objects.filter(tmdb_id=obj.tmdb_id).exclude(pk=obj.pk).exists():
            hints.append(_('Another row shares this TMDB ID.'))
        if obj.imdb_id and Movie.objects.filter(imdb_id=obj.imdb_id).exclude(pk=obj.pk).exists():
            hints.append(_('Another row shares this IMDb ID.'))
        if obj.slug and Movie.objects.filter(slug=obj.slug).exclude(pk=obj.pk).exists():
            hints.append(_('Another row shares this slug.'))
        same_title = Movie.objects.filter(title__iexact=obj.title).exclude(pk=obj.pk)[:5]
        if same_title:
            hints.append(
                _('Same title: ') + ', '.join(f'{m.title} (#{m.pk})' for m in same_title),
            )
        return ' | '.join(str(h) for h in hints) if hints else _('No duplicates detected.')

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        term = (search_term or '').strip()
        if term.isdigit():
            queryset |= self.model.objects.filter(tmdb_id=int(term))
            use_distinct = True
        return queryset, use_distinct

    @admin.action(description=_('Publish selected movies'))
    def make_published(self, request, queryset):
        updated = queryset.update(is_published=True, publication_status=Movie.PublicationStatus.PUBLISHED)
        self.message_user(request, _(f'Published {updated} movie(s).'), messages.SUCCESS)

    @admin.action(description=_('Unpublish selected movies (set as draft)'))
    def make_draft(self, request, queryset):
        updated = queryset.update(is_published=False, publication_status=Movie.PublicationStatus.DRAFT)
        self.message_user(request, _(f'Set {updated} movie(s) to draft.'), messages.SUCCESS)

    @admin.action(description=_('Mark as featured'))
    def make_featured(self, request, queryset):
        updated = queryset.update(is_featured=True)
        self.message_user(request, _(f'Featured {updated} movie(s).'), messages.SUCCESS)

    @admin.action(description=_('Clear featured'))
    def clear_featured(self, request, queryset):
        updated = queryset.update(is_featured=False)
        self.message_user(request, _(f'Cleared featured on {updated} movie(s).'), messages.SUCCESS)

    def save_model(self, request, obj, form, change):
        if change:
            protected = set(obj.manual_override_fields or [])
            protected.update(name for name in form.changed_data if name not in {'metadata_source', 'source_metadata', 'metadata_synced_at'})
            obj.manual_override_fields = sorted(protected)
        if 'publication_status' in form.changed_data:
            obj.is_published = obj.publication_status == Movie.PublicationStatus.PUBLISHED
        elif 'is_published' in form.changed_data:
            obj.publication_status = Movie.PublicationStatus.PUBLISHED if obj.is_published else Movie.PublicationStatus.DRAFT
        super().save_model(request, obj, form, change)

    def _sync_selected(self, request, queryset, *, overwrite_manual):
        try:
            client = configured_tmdb_client()
        except Exception as exc:  # ImproperlyConfigured
            self.message_user(request, str(exc), messages.ERROR)
            return
        ok = 0
        for movie in queryset:
            if not movie.tmdb_id:
                self.message_user(request, _(f'{movie}: missing tmdb_id'), messages.WARNING)
                continue
            try:
                details = client.movie_details(movie.tmdb_id)
                upsert_tmdb_movie(details, overwrite_manual=overwrite_manual, auto_publish=False)
                ok += 1
            except TMDBError as exc:
                self.message_user(request, _(f'{movie}: {exc}'), messages.ERROR)
            except Exception as exc:  # noqa: BLE001
                self.message_user(request, _(f'{movie}: {exc}'), messages.ERROR)
        self.message_user(request, _(f'Synced {ok} movie(s) from TMDB.'), messages.SUCCESS)

    @admin.action(description=_('Sync from TMDB (keep manual fields)'))
    def sync_from_tmdb(self, request, queryset):
        self._sync_selected(request, queryset, overwrite_manual=False)

    @admin.action(description=_('Sync from TMDB (overwrite manual fields)'))
    def sync_from_tmdb_overwrite(self, request, queryset):
        self._sync_selected(request, queryset, overwrite_manual=True)


@admin.register(Series)
class SeriesAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'start_year', 'status', 'content_format', 'imdb_rating', 'tmdb_id',
        'is_dubbed', 'has_subtitle', 'is_uncensored', 'is_published', 'is_featured',
    ]
    list_filter = [
        'is_published', 'is_featured', 'status', 'content_format',
        'is_dubbed', 'has_subtitle', 'is_uncensored', 'genres',
    ]
    search_fields = ['title', 'original_title', 'description', 'imdb_id', 'tmdb_id']
    prepopulated_fields = {'slug': ('title',)}
    filter_horizontal = ['genres', 'directors', 'countries', 'tags']
    inlines = [SeriesActorInline, SeasonInline]
    actions = ['make_published', 'make_draft']

    @admin.action(description=_('Publish selected series'))
    def make_published(self, request, queryset):
        queryset.update(is_published=True)

    @admin.action(description=_('Unpublish selected series'))
    def make_draft(self, request, queryset):
        queryset.update(is_published=False)


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ['series', 'season_number', 'title', 'release_year']
    list_filter = ['release_year']
    search_fields = ['series__title', 'title']


@admin.register(Episode)
class EpisodeAdmin(admin.ModelAdmin):
    list_display = ['title', 'season', 'episode_number', 'duration_minutes', 'is_published', 'view_count']
    list_filter = ['is_published']
    search_fields = ['title', 'description', 'season__series__title']
    actions = ['make_published', 'make_draft']

    @admin.action(description=_('Publish selected episodes'))
    def make_published(self, request, queryset):
        queryset.update(is_published=True)

    @admin.action(description=_('Unpublish selected episodes'))
    def make_draft(self, request, queryset):
        queryset.update(is_published=False)


@admin.register(PlaybackSubtitleGap)
class PlaybackSubtitleGapAdmin(admin.ModelAdmin):
    list_display = (
        'content_type', 'object_id', 'episode_id', 'title', 'status',
        'report_count', 'last_result', 'playback_version', 'updated_at',
    )
    list_filter = ('status', 'content_type')
    search_fields = ('slug', 'title', 'object_id')
    readonly_fields = [field.name for field in PlaybackSubtitleGap._meta.fields]

    def has_add_permission(self, request):
        return False
