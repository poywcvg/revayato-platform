from django.contrib import admin

from .models import WatchRoom, WatchRoomMember, WatchRoomMessage, WatchRoomPlaybackState


class WatchRoomMemberInline(admin.TabularInline):
    model = WatchRoomMember
    extra = 0
    readonly_fields = ('joined_at', 'last_seen_at')


@admin.register(WatchRoom)
class WatchRoomAdmin(admin.ModelAdmin):
    list_display = ('invite_code', 'host_user', 'status', 'created_at', 'expires_at')
    list_filter = ('status',)
    search_fields = ('invite_code', 'host_user__email', 'host_user__username')
    readonly_fields = ('invite_code', 'created_at')
    inlines = (WatchRoomMemberInline,)


@admin.register(WatchRoomMessage)
class WatchRoomMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'room', 'user', 'created_at', 'is_deleted')
    list_filter = ('is_deleted',)
    search_fields = ('message', 'user__username')


@admin.register(WatchRoomPlaybackState)
class WatchRoomPlaybackStateAdmin(admin.ModelAdmin):
    list_display = ('room', 'is_playing', 'position_seconds', 'playback_rate', 'updated_at')
