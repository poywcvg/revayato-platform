from django.contrib import admin

from .models import Like, Rating, UserActivityEvent, WatchlistItem


@admin.register(UserActivityEvent)
class UserActivityEventAdmin(admin.ModelAdmin):
    list_display = ['action', 'content_type', 'object_id', 'user', 'session_key', 'value', 'created_at']
    list_filter = ['action', 'content_type', 'created_at']
    search_fields = ['session_key', 'query']
    date_hierarchy = 'created_at'


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ['user', 'content_type', 'object_id', 'score', 'is_spoiler', 'created_at']
    list_filter = ['content_type', 'is_spoiler', 'score']
    search_fields = ['user__username', 'user__email', 'review']
    autocomplete_fields = ['user']


@admin.register(WatchlistItem)
class WatchlistItemAdmin(admin.ModelAdmin):
    list_display = ['user', 'content_type', 'object_id', 'list_type', 'created_at']
    list_filter = ['content_type', 'list_type']
    search_fields = ['user__username', 'user__email']
    autocomplete_fields = ['user']


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ['user', 'content_type', 'object_id', 'created_at']
    list_filter = ['content_type']
    search_fields = ['user__username', 'user__email']
    autocomplete_fields = ['user']
