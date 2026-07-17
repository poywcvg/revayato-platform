from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.html import strip_tags
from rest_framework import serializers

from apps.catalog.models import Episode, Movie

from .models import WatchRoomMessage
from .services import playback_payload, public_user_payload, room_payload


class WatchRoomCreateSerializer(serializers.Serializer):
    content_type = serializers.ChoiceField(choices=('movie', 'episode'))
    content_id = serializers.IntegerField(min_value=1)
    expires_in_minutes = serializers.IntegerField(min_value=30, max_value=480, required=False)

    def validate(self, attrs):
        if attrs['content_type'] == 'movie':
            content = Movie.objects.filter(pk=attrs['content_id'], is_published=True).first()
        else:
            content = Episode.objects.select_related('season__series').filter(
                pk=attrs['content_id'], is_published=True,
                season__is_published=True, season__series__is_published=True,
            ).first()
        if not content:
            raise serializers.ValidationError({'content_id': 'محتوای منتشرشده پیدا نشد یا در دسترس نیست.'})
        attrs['content_object'] = content
        return attrs

    def expiry(self):
        minutes = self.validated_data.get(
            'expires_in_minutes', getattr(settings, 'WATCH_PARTY_DEFAULT_EXPIRY_MINUTES', 240),
        )
        return timezone.now() + timedelta(minutes=minutes)


class WatchRoomSerializer(serializers.Serializer):
    def to_representation(self, instance):
        data = room_payload(instance, self.context.get('request').user if self.context.get('request') else None)
        try:
            data['playback_state'] = playback_payload(instance.playback_state)
        except Exception:
            data['playback_state'] = None
        return data


class WatchRoomMessageSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta:
        model = WatchRoomMessage
        fields = ('id', 'user', 'message', 'created_at')

    def get_user(self, obj):
        return public_user_payload(obj.user)


class ChatMessageInputSerializer(serializers.Serializer):
    message = serializers.CharField(trim_whitespace=True)

    def validate_message(self, value):
        value = strip_tags(value).strip()
        max_length = getattr(settings, 'WATCH_PARTY_CHAT_MAX_LENGTH', 1000)
        if not value:
            raise serializers.ValidationError('پیام نمی‌تواند خالی باشد.')
        if len(value) > max_length:
            raise serializers.ValidationError(f'پیام حداکثر {max_length} کاراکتر است.')
        return value
