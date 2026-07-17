from rest_framework import serializers

from config.public_urls import media_url, signed_download_url

from .models import (
    Actor, Country, Director, Episode, Genre, Movie,
    MovieActor, Season, Series, SeriesActor, Tag,
)


class PublicMediaSerializer(serializers.ModelSerializer):
    """Replace stored keys and upload paths with the configured media URL."""

    public_media_fields = ()
    public_download_fields = {}

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for field_name in self.public_media_fields:
            data[field_name] = media_url(getattr(instance, field_name, None)) or None
        for output_name, source_name in self.public_download_fields.items():
            data[output_name] = signed_download_url(getattr(instance, source_name, None)) or None
        if 'subtitle_tracks' in data:
            data['subtitle_tracks'] = [
                {
                    **track,
                    'src': media_url(track.get('key') or track.get('src')) or None,
                }
                for track in (getattr(instance, 'subtitle_tracks', None) or [])
                if isinstance(track, dict) and (track.get('key') or track.get('src'))
            ]
            for track in data['subtitle_tracks']:
                track.pop('key', None)
        return data


class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = ['id', 'title', 'slug']


class ActorListSerializer(PublicMediaSerializer):
    public_media_fields = ('photo',)

    class Meta:
        model = Actor
        fields = ['id', 'name', 'slug', 'photo', 'birth_place']


class DirectorListSerializer(PublicMediaSerializer):
    public_media_fields = ('photo',)

    class Meta:
        model = Director
        fields = ['id', 'name', 'slug', 'photo']


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ['id', 'name', 'code']


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug']


class MovieActorSerializer(serializers.ModelSerializer):
    actor = ActorListSerializer(read_only=True)

    class Meta:
        model = MovieActor
        fields = ['id', 'actor', 'role', 'order']


class MovieListSerializer(PublicMediaSerializer):
    public_media_fields = ('poster', 'backdrop', 'trailer_url')
    genres = GenreSerializer(many=True, read_only=True)
    directors = DirectorListSerializer(many=True, read_only=True)
    countries = CountrySerializer(many=True, read_only=True)

    class Meta:
        model = Movie
        fields = [
            'id', 'title', 'original_title', 'slug', 'short_description', 'description',
            'release_year', 'duration_minutes', 'age_rating', 'language',
            'content_format', 'is_dubbed', 'has_subtitle', 'is_uncensored',
            'imdb_rating', 'site_rating',
            'poster', 'backdrop', 'trailer_url',
            'genres', 'directors', 'countries',
            'is_published', 'is_featured', 'view_count', 'like_count',
            'created_at',
        ]


class MovieDetailSerializer(PublicMediaSerializer):
    public_media_fields = ('poster', 'backdrop', 'trailer_url', 'video_url')
    public_download_fields = {'download_url': 'download_key'}
    download_url = serializers.CharField(source='download_key', read_only=True)
    genres = GenreSerializer(many=True, read_only=True)
    movie_actors = MovieActorSerializer(many=True, read_only=True)
    directors = DirectorListSerializer(many=True, read_only=True)
    countries = CountrySerializer(many=True, read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    seo_title = serializers.ReadOnlyField()
    seo_description = serializers.ReadOnlyField()

    class Meta:
        model = Movie
        fields = [
            'id', 'title', 'original_title', 'slug', 'description',
            'release_year', 'duration_minutes', 'age_rating', 'language',
            'content_format', 'is_dubbed', 'has_subtitle', 'is_uncensored', 'content_warnings',
            'imdb_rating', 'site_rating', 'imdb_id', 'tmdb_id',
            'poster', 'backdrop', 'trailer_url', 'video_url', 'download_url', 'subtitle_tracks',
            'genres', 'movie_actors', 'directors', 'countries', 'tags',
            'is_published', 'view_count', 'like_count',
            'seo_title', 'seo_description',
            'created_at', 'updated_at',
        ]


class EpisodeSerializer(PublicMediaSerializer):
    public_media_fields = ('poster', 'video_url', 'trailer_url')
    public_download_fields = {'download_url': 'download_key'}
    download_url = serializers.CharField(source='download_key', read_only=True)

    class Meta:
        model = Episode
        fields = [
            'id', 'title', 'episode_number', 'description',
            'duration_minutes', 'poster', 'video_url', 'trailer_url', 'download_url', 'subtitle_tracks', 'air_date',
            'is_published', 'view_count',
            'created_at',
        ]


class SeasonSerializer(PublicMediaSerializer):
    public_media_fields = ('poster',)
    episodes = serializers.SerializerMethodField()

    class Meta:
        model = Season
        fields = [
            'id', 'title', 'season_number', 'description',
            'release_year', 'poster',
            'episode_count', 'air_date', 'episodes',
        ]

    def get_episodes(self, obj):
        episodes = getattr(obj, 'published_episodes', None)
        if episodes is None:
            episodes = obj.episodes.filter(is_published=True).order_by('episode_number')
        return EpisodeSerializer(episodes, many=True, context=self.context).data


class SeriesListSerializer(PublicMediaSerializer):
    public_media_fields = ('poster', 'backdrop', 'trailer_url')
    genres = GenreSerializer(many=True, read_only=True)
    directors = DirectorListSerializer(many=True, read_only=True)
    countries = CountrySerializer(many=True, read_only=True)

    class Meta:
        model = Series
        fields = [
            'id', 'title', 'original_title', 'slug', 'short_description', 'description',
            'start_year', 'end_year', 'age_rating', 'language',
            'content_format', 'is_dubbed', 'has_subtitle', 'is_uncensored',
            'imdb_rating', 'site_rating',
            'poster', 'backdrop', 'trailer_url',
            'genres', 'directors', 'countries',
            'status', 'is_published', 'is_featured', 'view_count', 'like_count',
            'created_at',
        ]


class SeriesDetailSerializer(PublicMediaSerializer):
    public_media_fields = ('poster', 'backdrop', 'trailer_url')
    genres = GenreSerializer(many=True, read_only=True)
    seasons = serializers.SerializerMethodField()
    series_actors = serializers.SerializerMethodField()
    directors = DirectorListSerializer(many=True, read_only=True)
    countries = CountrySerializer(many=True, read_only=True)
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Series
        fields = [
            'id', 'title', 'original_title', 'slug', 'description',
            'start_year', 'end_year', 'age_rating', 'language',
            'content_format', 'is_dubbed', 'has_subtitle', 'is_uncensored', 'content_warnings',
            'imdb_rating', 'site_rating',
            'poster', 'backdrop', 'trailer_url',
            'genres', 'series_actors', 'directors', 'countries', 'tags',
            'status', 'is_published', 'view_count', 'like_count',
            'created_at', 'updated_at',
            'seasons',
        ]

    def get_series_actors(self, obj):
        actors_qs = obj.series_actors.select_related('actor').order_by('order')
        return [
            {
                'id': sa.id,
                'actor': ActorListSerializer(sa.actor).data,
                'role': sa.role,
                'order': sa.order,
            }
            for sa in actors_qs
        ]

    def get_seasons(self, obj):
        seasons = getattr(obj, 'published_seasons', None)
        if seasons is None:
            seasons = obj.seasons.filter(is_published=True).order_by('season_number')
        return SeasonSerializer(seasons, many=True, context=self.context).data
