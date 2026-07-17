from django.contrib import admin

from .models import Recommendation, SearchLog, TasteProfile


@admin.register(TasteProfile)
class TasteProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_ready', 'updated_at']
    list_filter = ['is_ready']


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ['user', 'content_type', 'object_id', 'score', 'reason', 'is_consumed', 'created_at']
    list_filter = ['content_type', 'reason', 'is_consumed']
    search_fields = ['session_key']


@admin.register(SearchLog)
class SearchLogAdmin(admin.ModelAdmin):
    list_display = ['query', 'user', 'result_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['query']
