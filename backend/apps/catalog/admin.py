from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import (
    Actor, CatalogSyncRun, Country, Director, Episode, Genre, Movie,
    MovieActor, Season, Series, SeriesActor, Tag,
)


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
    list_display = ['title', 'slug']
    search_fields = ['title', 'slug']
    prepopulated_fields = {'slug': ('title',)}


@admin.register(CatalogSyncRun)
class CatalogSyncRunAdmin(admin.ModelAdmin):
    list_display = (
        'provider', 'status', 'started_at', 'discovered_count',
        'created_count', 'updated_count', 'published_count', 'error_count',
    )
    list_filter = ('provider', 'status')
    readonly_fields = [
        'provider', 'status', 'started_at', 'finished_at', 'discovered_count',
        'created_count', 'updated_count', 'published_count', 'error_count', 'errors',
    ]


@admin.register(Actor)
class ActorAdmin(admin.ModelAdmin):
    list_display = ['name', 'birth_date', 'birth_place']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Director)
class DirectorAdmin(admin.ModelAdmin):
    list_display = ['name', 'birth_date', 'birth_place']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ['name', 'code']
    search_fields = ['name']


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'release_year', 'content_format', 'imdb_rating',
        'is_dubbed', 'has_subtitle', 'is_uncensored',
        'is_published', 'is_featured', 'media_status', 'rights_verified',
        'auto_publish', 'scheduled_publish_at', 'view_count',
    ]
    list_editable = ['is_published', 'is_featured']
    list_filter = [
        'is_published', 'is_featured', 'content_format',
        'is_dubbed', 'has_subtitle', 'is_uncensored', 'media_status',
        'rights_verified', 'auto_publish', 'genres', 'release_year',
    ]
    search_fields = ['title', 'original_title', 'description', 'imdb_id', 'tmdb_id']
    prepopulated_fields = {'slug': ('title',)}
    filter_horizontal = ['genres', 'directors', 'countries', 'tags']
    inlines = [MovieActorInline]
    readonly_fields = [
        'view_count', 'like_count', 'metadata_synced_at', 'source_metadata',
        'created_at', 'updated_at',
    ]
    actions = ['make_published', 'make_draft']

    fieldsets = (
        (None, {
            'fields': ('title', 'original_title', 'slug', 'short_description', 'description'),
        }),
        (_('Details'), {
            'fields': (
                'release_year', 'duration_minutes', 'age_rating', 'language', 'content_format',
                'is_dubbed', 'has_subtitle', 'is_uncensored', 'content_warnings',
                'genres', 'directors', 'countries', 'tags',
            ),
        }),
        (_('Media'), {
            'fields': (
                'poster', 'backdrop', 'trailer_url', 'video_url', 'download_key',
                'subtitle_tracks', 'media_status', 'rights_verified',
                'auto_publish', 'scheduled_publish_at',
            ),
        }),
        (_('Ratings'), {
            'fields': ('imdb_rating', 'site_rating'),
        }),
        (_('External IDs'), {
            'fields': ('imdb_id', 'tmdb_id'),
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

    @admin.action(description=_('Publish selected movies'))
    def make_published(self, request, queryset):
        queryset.update(is_published=True)

    @admin.action(description=_('Unpublish selected movies (set as draft)'))
    def make_draft(self, request, queryset):
        queryset.update(is_published=False)


@admin.register(Series)
class SeriesAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'start_year', 'status', 'content_format', 'imdb_rating',
        'is_dubbed', 'has_subtitle', 'is_uncensored', 'is_published', 'is_featured',
    ]
    list_filter = [
        'is_published', 'is_featured', 'status', 'content_format',
        'is_dubbed', 'has_subtitle', 'is_uncensored', 'genres',
    ]
    search_fields = ['title', 'original_title', 'description']
    prepopulated_fields = {'slug': ('title',)}
    filter_horizontal = ['genres', 'directors', 'countries', 'tags']
    inlines = [SeriesActorInline, SeasonInline]


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
