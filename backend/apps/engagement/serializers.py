from rest_framework import serializers

from . import selectors
from .models import Like, Rating, UserActivityEvent, WatchlistItem


PRIVACY_SAFE_EVENT_TYPES = [
    'search',
    'empty_search',
    'view_movie',
    'view_series',
    'play_trailer',
    'start_watch',
    'continue_watch',
    'pause_watch',
    'watch_progress',
    'complete_watch',
    'add_watchlist',
    'remove_watchlist',
    'like',
    'remove_like',
    'dislike',
    'rate',
    'recommendation_click',
    'click_genre',
    'click_cast',
    'click_director',
    'filter_apply',
    'sort_apply',
]

EVENT_ACTION_MAP = {
    'search': 'search',
    'view_movie': 'view_movie',
    'view_series': 'view_series',
    'play_trailer': 'trailer_watch',
    'start_watch': 'play',
    'pause_watch': 'pause',
    'watch_progress': 'watch_progress',
    'complete_watch': 'complete_watch',
    'add_watchlist': 'add_to_watchlist',
    'remove_watchlist': 'remove_from_watchlist',
    'like': 'like',
    'remove_like': 'remove_like',
    'dislike': 'dislike',
    'rate': 'rate',
    'recommendation_click': 'click_search_result',
    'click_genre': 'filter_genre',
    'click_cast': 'open_actor_page',
    'click_director': 'open_director_page',
    'filter_apply': 'filter_genre',
    'sort_apply': 'search',
    'continue_watch': 'play',
    'empty_search': 'search',
}


class PrivacySafeEventInputSerializer(serializers.Serializer):
    """Allow-list serializer for consented, first-party recommendation signals."""

    event_id = serializers.RegexField(regex=r'^[A-Za-z0-9:_\-.]{8,100}$', required=False)
    event_type = serializers.ChoiceField(choices=PRIVACY_SAFE_EVENT_TYPES)
    title_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    title_slug = serializers.SlugField(max_length=120, required=False, allow_blank=True, allow_null=True)
    # Temporary aliases for older clients. New clients use title_id/title_slug.
    movie_id = serializers.IntegerField(min_value=1, required=False, allow_null=True, write_only=True)
    movie_slug = serializers.SlugField(max_length=120, required=False, allow_blank=True, allow_null=True, write_only=True)
    content_type = serializers.ChoiceField(choices=['movie', 'series'], required=False)
    query = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True, trim_whitespace=True)
    genre = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True, trim_whitespace=True)
    progress_percent = serializers.FloatField(min_value=0, max_value=100, required=False, allow_null=True)
    rating = serializers.FloatField(min_value=0, max_value=10, required=False, allow_null=True)
    result_count = serializers.IntegerField(min_value=0, required=False)
    filter_name = serializers.CharField(max_length=60, required=False, allow_blank=True)
    filter_value = serializers.CharField(max_length=120, required=False, allow_blank=True)
    sort = serializers.CharField(max_length=60, required=False, allow_blank=True)
    source_page = serializers.CharField(max_length=180)
    timestamp = serializers.DateTimeField(required=False)
    anonymous_session_id = serializers.RegexField(
        regex=r'^[A-Za-z0-9_-]{16,100}$', required=False, allow_blank=True,
    )
    is_empty_query = serializers.BooleanField(required=False)

    def validate(self, attrs):
        title_id = attrs.get('title_id')
        movie_id = attrs.pop('movie_id', None)
        title_slug = attrs.get('title_slug')
        movie_slug = attrs.pop('movie_slug', None)
        if title_id and movie_id and title_id != movie_id:
            raise serializers.ValidationError({'title_id': 'Conflicts with legacy movie_id.'})
        if title_slug and movie_slug and title_slug != movie_slug:
            raise serializers.ValidationError({'title_slug': 'Conflicts with legacy movie_slug.'})
        if not title_id and movie_id:
            attrs['title_id'] = movie_id
        if not title_slug and movie_slug:
            attrs['title_slug'] = movie_slug
        return attrs

    def validate_source_page(self, value):
        if not value.startswith('/') or value.startswith('//'):
            raise serializers.ValidationError('source_page must be an internal site path.')
        return value.split('?', 1)[0]

    def create(self, validated_data):
        user = validated_data.pop('user', None)
        event_type = validated_data['event_type']
        action = EVENT_ACTION_MAP[event_type]
        event_id = validated_data.get('event_id', '')
        if event_id:
            existing = UserActivityEvent.objects.filter(client_event_id=event_id).first()
            if existing:
                return existing
        filter_name = validated_data.get('filter_name', '')
        if event_type == 'filter_apply':
            action = {
                'year': 'filter_year',
                'country': 'filter_country',
            }.get(filter_name, 'filter_genre')

        content_type = validated_data.get('content_type') or 'movie'
        if event_type in {'search', 'filter_apply', 'sort_apply'}:
            content_type = 'search'
        elif event_type == 'click_genre':
            content_type = 'genre'
        elif event_type == 'click_cast':
            content_type = 'actor'
        elif event_type == 'click_director':
            content_type = 'director'

        client_timestamp = validated_data.get('timestamp')
        metadata = {
            'event_id': event_id,
            'event_type': event_type,
            'title_slug': validated_data.get('title_slug', ''),
            'genre': validated_data.get('genre', ''),
            'source_page': validated_data['source_page'],
            'client_timestamp': client_timestamp.isoformat() if client_timestamp else None,
            'result_count': validated_data.get('result_count'),
            'filter_name': filter_name,
            'filter_value': validated_data.get('filter_value', ''),
            'sort': validated_data.get('sort', ''),
            'is_empty_query': validated_data.get('is_empty_query', False),
        }
        metadata = {key: value for key, value in metadata.items() if value not in (None, '')}

        return UserActivityEvent.objects.create(
            user=user if getattr(user, 'is_authenticated', False) else None,
            client_event_id=event_id or None,
            session_key=validated_data.get('anonymous_session_id', ''),
            content_type=content_type,
            object_id=validated_data.get('title_id'),
            action=action,
            value=validated_data.get('rating') if validated_data.get('rating') is not None else 1.0,
            progress=validated_data.get('progress_percent'),
            query=validated_data.get('query') or '',
            metadata=metadata,
            # Privacy boundary: IP, user-agent and device fields are intentionally unset.
            ip_address=None,
            user_agent='',
            device_type='',
        )


class UserActivityEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserActivityEvent
        fields = [
            'id', 'content_type', 'object_id', 'action',
            'value', 'duration', 'progress', 'query', 'metadata',
            'session_key', 'device_type',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class RatingSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = Rating
        fields = [
            'id', 'username', 'content_type', 'object_id',
            'score', 'review', 'is_spoiler', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'username', 'created_at', 'updated_at']


class RateContentInputSerializer(serializers.Serializer):
    content_type = serializers.ChoiceField(choices=Rating._meta.get_field('content_type').choices)
    object_id = serializers.IntegerField(min_value=1)
    score = serializers.DecimalField(max_digits=3, decimal_places=1, min_value=0, max_value=10)
    review = serializers.CharField(required=False, allow_blank=True, default='')
    is_spoiler = serializers.BooleanField(required=False, default=False)


class WatchlistItemSerializer(serializers.ModelSerializer):
    content = serializers.SerializerMethodField()

    class Meta:
        model = WatchlistItem
        fields = ['id', 'content_type', 'object_id', 'list_type', 'content', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_content(self, obj):
        return selectors.resolve_content_summary(obj.content_type, obj.object_id)


class WatchlistToggleInputSerializer(serializers.Serializer):
    content_type = serializers.ChoiceField(choices=WatchlistItem._meta.get_field('content_type').choices)
    object_id = serializers.IntegerField(min_value=1)
    list_type = serializers.ChoiceField(choices=WatchlistItem.ListType.choices, default=WatchlistItem.ListType.WATCHLIST)


class LikeToggleInputSerializer(serializers.Serializer):
    content_type = serializers.ChoiceField(choices=Like._meta.get_field('content_type').choices)
    object_id = serializers.IntegerField(min_value=1)
