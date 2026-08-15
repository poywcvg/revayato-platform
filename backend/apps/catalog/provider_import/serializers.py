"""Serializers for provider import admin APIs. Never include secrets or download URLs."""

from __future__ import annotations

from rest_framework import serializers

from apps.catalog.models import (
    ProviderImportItem,
    ProviderImportJob,
    ProviderImportLog,
    ProviderSource,
)

from .base import sanitize_payload
from .service import secret_flags_for_provider


class ProviderSourceSerializer(serializers.ModelSerializer):
    secrets = serializers.SerializerMethodField()
    credential_status = serializers.SerializerMethodField()
    last_validated_at = serializers.SerializerMethodField()
    last_validation_message = serializers.SerializerMethodField()
    login_url = serializers.SerializerMethodField()
    movies_url = serializers.SerializerMethodField()
    series_url = serializers.SerializerMethodField()

    class Meta:
        model = ProviderSource
        fields = [
            'id', 'name', 'slug', 'provider_type', 'base_url', 'auth_type',
            'is_active', 'rate_limit_per_minute', 'timeout_seconds', 'verify_ssl',
            'config', 'login_url', 'movies_url', 'series_url',
            'secrets', 'credential_status', 'last_validated_at',
            'last_validation_message', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at', 'slug']

    def get_secrets(self, obj):
        return secret_flags_for_provider(obj)

    def get_credential_status(self, obj):
        cred = getattr(obj, 'credential', None)
        return cred.status if cred else 'unknown'

    def get_last_validated_at(self, obj):
        cred = getattr(obj, 'credential', None)
        return cred.last_validated_at if cred else None

    def get_last_validation_message(self, obj):
        cred = getattr(obj, 'credential', None)
        return cred.last_validation_message if cred else ''

    def get_login_url(self, obj):
        return (obj.config or {}).get('login_url') or ''

    def get_movies_url(self, obj):
        return (obj.config or {}).get('movies_url') or ''

    def get_series_url(self, obj):
        return (obj.config or {}).get('series_url') or ''

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['config'] = sanitize_payload(data.get('config') or {})
        return data


class ProviderSourceWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderSource
        fields = [
            'name', 'provider_type', 'base_url', 'auth_type', 'is_active',
            'rate_limit_per_minute', 'timeout_seconds', 'verify_ssl', 'config',
        ]

    def validate_config(self, value):
        return sanitize_payload(value or {})


class ProviderImportJobSerializer(serializers.ModelSerializer):
    provider_slug = serializers.CharField(source='provider.slug', read_only=True)
    provider_name = serializers.CharField(source='provider.name', read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = ProviderImportJob
        fields = [
            'id', 'provider', 'provider_slug', 'provider_name', 'trigger',
            'target_movie', 'target_series', 'content_type', 'status', 'mode',
            'params', 'total_items', 'processed_items', 'matched_items',
            'imported_files', 'skipped_items', 'failed_items',
            'current_item_label', 'cancel_requested', 'error_message',
            'sanitized_error_code', 'is_active', 'started_at', 'finished_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['params'] = sanitize_payload(data.get('params') or {})
        return data


class ProviderImportItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderImportItem
        fields = [
            'id', 'provider_item_id', 'content_type', 'title', 'original_title',
            'year', 'season_number', 'episode_number', 'tmdb_id', 'imdb_id',
            'match_score', 'match_reasons', 'selected', 'manually_approved',
            'matched_movie_id', 'matched_series_id', 'matched_episode_id',
            'archive_asset_id', 'selected_candidate', 'status', 'status_message',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['selected_candidate'] = sanitize_payload(data.get('selected_candidate') or {})
        data['match_reasons'] = sanitize_payload(data.get('match_reasons') or [])
        return data


class ProviderImportLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderImportLog
        fields = ['id', 'level', 'event_code', 'message', 'context', 'created_at']
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['context'] = sanitize_payload(data.get('context') or {})
        data['message'] = sanitize_payload(data.get('message') or '')
        return data


class DiscoverImportRequestSerializer(serializers.Serializer):
    content_type = serializers.ChoiceField(
        choices=ProviderImportJob.ContentType.choices,
        default=ProviderImportJob.ContentType.MOVIES,
    )
    mode = serializers.ChoiceField(
        choices=ProviderImportJob.Mode.choices,
        default=ProviderImportJob.Mode.DISCOVER_ONLY,
    )
    limit = serializers.IntegerField(required=False, min_value=1, max_value=500, default=100)
    dry_run = serializers.BooleanField(required=False, default=False)
    overwrite = serializers.BooleanField(required=False, default=False)
    quality_preference = serializers.ListField(
        child=serializers.CharField(max_length=32),
        required=False,
        allow_empty=True,
        default=list,
    )


class CatalogDiscoverRequestSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(
        choices=[ProviderImportJob.Mode.DISCOVER_ONLY],
        default=ProviderImportJob.Mode.DISCOVER_ONLY,
    )
    force = serializers.BooleanField(required=False, default=False)


class ApproveMatchSerializer(serializers.Serializer):
    candidate_id = serializers.IntegerField(min_value=1)
