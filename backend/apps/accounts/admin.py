from django.contrib import admin

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'preferred_language', 'is_email_verified', 'created_at']
    search_fields = ['user__username', 'user__email']
    list_filter = ['is_email_verified', 'preferred_language']
