from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ['email', 'username', 'is_verified', 'is_staff', 'is_active', 'created_at']
    list_filter = ['is_staff', 'is_active', 'is_verified']
    search_fields = ['email', 'username', 'phone']
    ordering = ['-created_at']
