from django.contrib import admin

from .models import Like, Rating, SupportMessage, SupportTicket, UserActivityEvent, WatchlistItem


@admin.register(UserActivityEvent)
class UserActivityEventAdmin(admin.ModelAdmin):
    list_display = ['action', 'content_type', 'object_id', 'user', 'session_key', 'value', 'created_at']
    list_filter = ['action', 'content_type', 'created_at']
    search_fields = ['session_key', 'query']
    date_hierarchy = 'created_at'


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ['user', 'content_type', 'object_id', 'score', 'is_spoiler', 'is_hidden', 'created_at']
    list_filter = ['content_type', 'is_spoiler', 'is_hidden', 'score']
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


class SupportMessageInline(admin.TabularInline):
    model = SupportMessage
    extra = 0
    readonly_fields = ['author', 'is_staff_reply', 'body', 'created_at']


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = [
        'tracking_code', 'subject', 'category', 'status', 'user',
        'unread_by_staff', 'last_message_at',
    ]
    list_filter = ['category', 'status', 'unread_by_staff']
    search_fields = ['tracking_code', 'subject', 'body', 'related_title', 'user__username', 'user__email']
    autocomplete_fields = ['user']
    inlines = [SupportMessageInline]
    readonly_fields = ['tracking_code', 'created_at', 'updated_at', 'last_message_at']
