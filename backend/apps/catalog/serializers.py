from rest_framework import serializers
from django.utils.text import slugify

from config.public_urls import media_url, normalize_download_links, object_key, public_download_links, signed_download_url

from .countries import persian_country_name
from .localization import contains_persian, is_latin_text, secondary_title_for
from .models import (
    Actor, CatalogImporterSettings, Country, Director, Episode, Genre, Movie,
    MovieActor, Season, Series, SeriesActor, Tag,
)


def _require_persian_title(attrs, instance=None):
    title = (attrs.get('title') if 'title' in attrs else getattr(instance, 'title', '') or '').strip()
    if not title:
        raise serializers.ValidationError({'title': 'عنوان فارسی الزامی است.'})
    if not contains_persian(title):
        raise serializers.ValidationError({'title': 'عنوان باید فارسی باشد.'})
    attrs['title'] = title

    if 'original_title' in attrs:
        original = (attrs.get('original_title') or '').strip()
        if original and not is_latin_text(original):
            raise serializers.ValidationError({
                'original_title': 'عنوان انگلیسی باید با حروف لاتین باشد.',
            })
        attrs['original_title'] = original
    return attrs


class CatalogTitleMixin(metaclass=serializers.SerializerMetaclass):
    """Expose display titles resolved on the backend."""

    secondary_title = serializers.SerializerMethodField()

    def get_secondary_title(self, obj):
        return secondary_title_for(getattr(obj, 'title', ''), getattr(obj, 'original_title', ''))



class CatalogImporterSettingsSerializer(serializers.ModelSerializer):
    tmdb_configured = serializers.SerializerMethodField()
    imdb_rating_provider_configured = serializers.SerializerMethodField()

    class Meta:
        model = CatalogImporterSettings
        fields = [
            'language', 'fallback_language', 'region',
            'daily_lookback_days', 'daily_lookahead_days', 'daily_max_pages',
            'trending_window', 'trending_max_pages',
            'import_people_images', 'cast_import_limit', 'fetch_imdb_ratings',
            'feature_trending', 'auto_publish', 'automation_enabled',
            'automation_mode', 'automation_interval_hours', 'tmdb_configured',
            'imdb_rating_provider_configured', 'updated_at',
        ]
        read_only_fields = [
            'tmdb_configured', 'imdb_rating_provider_configured', 'updated_at',
        ]

    @staticmethod
    def _validate_language(value):
        value = (value or '').strip()
        parts = value.split('-')
        if not value or len(parts) > 2 or not all(part.isalpha() for part in parts):
            raise serializers.ValidationError('Use a language code such as fa-IR or en-US.')
        return value

    def validate_language(self, value):
        return self._validate_language(value)

    def validate_fallback_language(self, value):
        return self._validate_language(value)

    def validate_region(self, value):
        value = (value or '').strip().upper()
        if value and (len(value) != 2 or not value.isalpha()):
            raise serializers.ValidationError('Use a two-letter region code such as IR or US.')
        return value

    def get_tmdb_configured(self, _obj):
        from django.conf import settings
        return bool(settings.TMDB_READ_ACCESS_TOKEN or settings.TMDB_API_KEY)

    def get_imdb_rating_provider_configured(self, _obj):
        from django.conf import settings
        return bool(
            getattr(settings, 'OMDB_API_KEY', '')
            or settings.TMDB_READ_ACCESS_TOKEN
            or settings.TMDB_API_KEY
        )


class PublicMediaSerializer(serializers.ModelSerializer):
    """Replace stored keys and upload paths with the configured media URL."""

    public_media_fields = ()
    public_download_fields = {}

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for field_name in self.public_media_fields:
            field_value = getattr(instance, field_name, None)
            has_local_file = bool(getattr(field_value, 'name', None))
            raw = ''
            if has_local_file:
                raw = media_url(field_value) or ''
            elif isinstance(field_value, str):
                raw = field_value.strip()
            external_value = getattr(instance, f'{field_name.removesuffix("_url")}_external_url', None) or None
            if raw.startswith(('http://', 'https://', '//')):
                data[field_name] = raw
            elif raw:
                data[field_name] = media_url(raw) or external_value or raw
            else:
                data[field_name] = external_value or None
        for output_name, source_name in self.public_download_fields.items():
            data[output_name] = signed_download_url(getattr(instance, source_name, None)) or None
        if 'subtitle_tracks' in data:
            from apps.catalog.subtitle_contract import publicize_subtitle_tracks
            data['subtitle_tracks'] = publicize_subtitle_tracks(
                getattr(instance, 'subtitle_tracks', None) or [],
            )
        return data


class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = ['id', 'title', 'slug', 'is_featured']


class GenreListSerializer(serializers.ModelSerializer):
    """Public genre index with live published title counts."""

    movie_count = serializers.IntegerField(read_only=True, default=0)
    series_count = serializers.IntegerField(read_only=True, default=0)
    title_count = serializers.SerializerMethodField()

    def get_title_count(self, obj):
        movies = int(getattr(obj, 'movie_count', 0) or 0)
        series = int(getattr(obj, 'series_count', 0) or 0)
        return movies + series

    class Meta:
        model = Genre
        fields = [
            'id', 'title', 'slug', 'is_featured',
            'movie_count', 'series_count', 'title_count',
        ]


class ActorListSerializer(PublicMediaSerializer):
    public_media_fields = ('photo',)

    class Meta:
        model = Actor
        fields = [
            'id', 'name', 'original_name', 'slug', 'photo', 'photo_external_url', 'birth_place', 'popularity', 'is_featured',
        ]


class ActorDetailSerializer(PublicMediaSerializer):
    public_media_fields = ('photo',)
    movies = serializers.SerializerMethodField()
    series = serializers.SerializerMethodField()

    class Meta:
        model = Actor
        fields = [
            'id', 'name', 'original_name', 'slug', 'photo', 'biography', 'birth_date', 'birth_place',
            'popularity', 'is_featured', 'photo_external_url', 'movies', 'series',
        ]

    def get_movies(self, obj):
        qs = (
            Movie.objects.filter(is_published=True, movie_actors__actor=obj)
            .distinct()
            .prefetch_related('genres', 'directors', 'countries')
            .order_by('-release_year', '-popularity')[:120]
        )
        return MovieListSerializer(qs, many=True, context=self.context).data

    def get_series(self, obj):
        qs = (
            Series.objects.filter(is_published=True, series_actors__actor=obj)
            .distinct()
            .prefetch_related('genres', 'directors', 'countries')
            .order_by('-start_year', '-popularity')[:80]
        )
        return SeriesListSerializer(qs, many=True, context=self.context).data


class DirectorListSerializer(PublicMediaSerializer):
    public_media_fields = ('photo',)

    class Meta:
        model = Director
        fields = ['id', 'name', 'original_name', 'slug', 'photo']


class CountrySerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    movie_count = serializers.SerializerMethodField()
    series_count = serializers.SerializerMethodField()

    def get_name(self, obj):
        return persian_country_name(obj.code, obj.name)

    def get_movie_count(self, obj):
        return int(getattr(obj, 'movie_count', 0) or 0)

    def get_series_count(self, obj):
        return int(getattr(obj, 'series_count', 0) or 0)

    class Meta:
        model = Country
        fields = ['id', 'name', 'code', 'movie_count', 'series_count']


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug']


class MovieActorSerializer(serializers.ModelSerializer):
    actor = ActorListSerializer(read_only=True)

    class Meta:
        model = MovieActor
        fields = ['id', 'actor', 'role', 'order']


class MediaRatingsMixin:
    """Attach normalized, validated external/site ratings to catalog payloads."""

    def get_ratings(self, obj):
        from .ratings import build_ratings_from_local, serialize_media_ratings
        # List endpoints stay local/cached fields only — never fan out to OMDb.
        request = self.context.get('request')
        view = self.context.get('view')
        detail = bool(getattr(view, 'detail', False) or (request and getattr(request.resolver_match, 'url_name', '') or '').endswith('-detail'))
        if not detail and self.__class__.__name__.endswith('ListSerializer'):
            return [item for item in build_ratings_from_local(obj) if item]
        return serialize_media_ratings(obj)


class MovieListSerializer(CatalogTitleMixin, MediaRatingsMixin, PublicMediaSerializer):
    public_media_fields = ('poster', 'backdrop', 'trailer_url')
    genres = GenreSerializer(many=True, read_only=True)
    directors = DirectorListSerializer(many=True, read_only=True)
    countries = CountrySerializer(many=True, read_only=True)
    has_downloads = serializers.BooleanField(read_only=True)
    # Declared on the serializer (not mixin) so DRF metaclass registers it.
    ratings = serializers.SerializerMethodField()

    class Meta:
        model = Movie
        # Keep list payloads lean: cards/hero use short_description; full synopsis
        # is loaded from the detail endpoint.
        fields = [
            'id', 'title', 'original_title', 'secondary_title', 'slug', 'short_description',
            'release_year', 'duration_minutes', 'age_rating', 'language',
            'content_format', 'is_dubbed', 'has_subtitle', 'is_uncensored',
            'imdb_rating', 'imdb_rank', 'rating_average', 'site_rating', 'ratings', 'popularity',
            'poster', 'backdrop', 'trailer_url', 'has_downloads',
            'genres', 'directors', 'countries',
            'is_published', 'is_featured', 'is_recommended', 'view_count', 'like_count',
            'created_at', 'updated_at',
        ]


class MovieDetailSerializer(CatalogTitleMixin, MediaRatingsMixin, PublicMediaSerializer):
    public_media_fields = ('poster', 'backdrop', 'trailer_url', 'video_url')
    public_download_fields = {'download_url': 'download_key'}
    download_url = serializers.CharField(source='download_key', read_only=True)
    download_links = serializers.SerializerMethodField()
    genres = GenreSerializer(many=True, read_only=True)
    movie_actors = MovieActorSerializer(many=True, read_only=True)
    directors = DirectorListSerializer(many=True, read_only=True)
    countries = CountrySerializer(many=True, read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    seo_title = serializers.ReadOnlyField()
    seo_description = serializers.ReadOnlyField()
    seo_keywords = serializers.SerializerMethodField()
    has_downloads = serializers.BooleanField(read_only=True)
    download_qualities = serializers.ListField(child=serializers.CharField(), read_only=True)
    ratings = serializers.SerializerMethodField()

    class Meta:
        model = Movie
        fields = [
            'id', 'title', 'original_title', 'secondary_title', 'slug', 'description',
            'release_year', 'duration_minutes', 'age_rating', 'language',
            'content_format', 'is_dubbed', 'has_subtitle', 'is_uncensored', 'content_warnings',
            'imdb_rating', 'imdb_rank', 'rating_average', 'site_rating', 'ratings', 'imdb_id', 'tmdb_id',
            'poster', 'backdrop', 'trailer_url', 'video_url', 'download_url', 'download_links',
            'quality', 'subtitle_tracks', 'has_downloads', 'download_qualities',
            'genres', 'movie_actors', 'directors', 'countries', 'tags',
            'is_published', 'is_featured', 'is_recommended', 'popularity', 'view_count', 'like_count',
            'seo_title', 'seo_description', 'seo_keywords',
            'created_at', 'updated_at',
        ]

    def get_download_links(self, obj):
        return public_download_links(obj)

    def get_seo_keywords(self, obj):
        return obj.effective_seo_keywords


class AdminMovieSerializer(serializers.ModelSerializer):
    """Staff write contract; records every manually changed TMDb-managed field."""

    genre_ids = serializers.PrimaryKeyRelatedField(source='genres', queryset=Genre.objects.all(), many=True, required=False)
    country_ids = serializers.PrimaryKeyRelatedField(source='countries', queryset=Country.objects.all(), many=True, required=False)
    clear_genres = serializers.BooleanField(write_only=True, required=False, default=False)
    clear_countries = serializers.BooleanField(write_only=True, required=False, default=False)
    poster_url = serializers.SerializerMethodField()
    backdrop_url = serializers.SerializerMethodField()
    duplicate_warnings = serializers.SerializerMethodField()
    movie_actors = MovieActorSerializer(many=True, read_only=True)
    directors = DirectorListSerializer(many=True, read_only=True)

    class Meta:
        model = Movie
        fields = [
            'id', 'title', 'original_title', 'slug', 'short_description', 'description',
            'release_date', 'release_year', 'duration_minutes', 'duration_text', 'catalog_type', 'publication_status',
            'genre_ids', 'country_ids', 'clear_genres', 'clear_countries', 'language', 'original_language', 'spoken_languages', 'age_rating',
            'imdb_id', 'tmdb_id', 'poster', 'backdrop', 'poster_path', 'backdrop_path', 'poster_external_url',
            'backdrop_external_url', 'poster_url', 'backdrop_url', 'trailer_url',
            'trailer_external_url', 'video_url', 'download_key', 'download_links', 'quality', 'subtitle_tracks',
            'content_format', 'is_dubbed', 'has_subtitle', 'is_uncensored', 'content_warnings',
            'imdb_rating', 'rating_average', 'vote_count', 'popularity', 'production_companies',
            'crew_metadata', 'writers', 'movie_actors', 'directors', 'is_featured', 'is_recommended',
            'meta_title', 'meta_description', 'seo_keywords', 'media_status',
            'rights_verified', 'metadata_source', 'manual_override_fields',
            'last_tmdb_sync_at', 'created_at', 'updated_at', 'duplicate_warnings',
        ]
        read_only_fields = [
            'metadata_source', 'manual_override_fields', 'last_tmdb_sync_at',
            'poster_path', 'backdrop_path', 'rating_average', 'duration_text',
            'created_at', 'updated_at', 'duplicate_warnings',
        ]
        extra_kwargs = {
            'slug': {'required': False, 'allow_blank': True},
            'poster': {'required': False, 'allow_null': True},
            'backdrop': {'required': False, 'allow_null': True},
        }

    def get_poster_url(self, obj):
        return media_url(obj.poster) or obj.poster_external_url or None

    def get_backdrop_url(self, obj):
        return media_url(obj.backdrop) or obj.backdrop_external_url or None

    def get_duplicate_warnings(self, obj):
        queryset = Movie.objects.exclude(pk=obj.pk)
        warnings = []
        if obj.tmdb_id and queryset.filter(tmdb_id=obj.tmdb_id).exists():
            warnings.append('tmdb_id')
        if obj.imdb_id and queryset.filter(imdb_id=obj.imdb_id).exists():
            warnings.append('imdb_id')
        if obj.slug and queryset.filter(slug=obj.slug).exists():
            warnings.append('slug')
        if obj.title and obj.release_year and queryset.filter(title__iexact=obj.title, release_year=obj.release_year).exists():
            warnings.append('title_release_year')
        return warnings

    def _validate_image(self, value, field):
        if not value:
            return value
        if value.size > 8 * 1024 * 1024:
            raise serializers.ValidationError(f'{field} must be smaller than 8 MB.')
        content_type = getattr(value, 'content_type', '')
        if content_type and content_type not in {'image/jpeg', 'image/png', 'image/webp'}:
            raise serializers.ValidationError(f'{field} must be JPEG, PNG, or WebP.')
        return value

    def validate_poster(self, value):
        return self._validate_image(value, 'poster')

    def validate_backdrop(self, value):
        return self._validate_image(value, 'backdrop')

    def validate_imdb_id(self, value):
        return (value or '').strip() or None

    def _normalize_object_key(self, value):
        """Accept pasted CDN URLs and persist only the relative object key."""
        if value in (None, ''):
            return ''
        return object_key(value)

    def validate_video_url(self, value):
        return self._normalize_object_key(value)

    def validate_trailer_url(self, value):
        return self._normalize_object_key(value)

    def validate_download_key(self, value):
        return self._normalize_object_key(value)

    def validate_download_links(self, value):
        normalized = normalize_download_links(value)
        # Do not let an empty admin form wipe auto-crawled provider links.
        if not normalized and self.instance is not None:
            existing = normalize_download_links(getattr(self.instance, 'download_links', None))
            if existing:
                return existing
        return normalized

    def validate(self, attrs):
        attrs = _require_persian_title(attrs, self.instance)
        title = attrs['title']
        if not attrs.get('slug') and not getattr(self.instance, 'slug', ''):
            base = slugify(title, allow_unicode=True) or 'movie'
            slug = base
            index = 2
            while Movie.objects.filter(slug=slug).exists():
                slug = f'{base}-{index}'
                index += 1
            attrs['slug'] = slug

        links = attrs.get('download_links')
        if links is None and self.instance is not None:
            links = self.instance.download_links
        if links is not None:
            attrs['download_links'] = normalize_download_links(links)
            first = attrs['download_links'][0] if attrs['download_links'] else None
            if first and not attrs.get('quality') and not getattr(self.instance, 'quality', ''):
                attrs['quality'] = first.get('quality') or ''
            # Only mirror relative keys into download_key (external URLs stay in download_links).
            if first and first.get('key') and not attrs.get('download_key') and not getattr(self.instance, 'download_key', ''):
                attrs['download_key'] = first['key']

            from apps.catalog.subtitle_extract import download_links_imply_dub, download_links_imply_subtitle

            # Keep public badges honest: derive from link metadata, never leave stale flags.
            attrs['has_subtitle'] = download_links_imply_subtitle(attrs['download_links'])
            attrs['is_dubbed'] = download_links_imply_dub(attrs['download_links'])
            tracks = attrs.get('subtitle_tracks')
            if tracks is None and self.instance is not None:
                tracks = getattr(self.instance, 'subtitle_tracks', None) or []
            if any(isinstance(track, dict) and str(track.get('src') or '').strip() for track in (tracks or [])):
                attrs['has_subtitle'] = True

        return attrs

    @staticmethod
    def _apply_publication(instance):
        instance.is_published = instance.publication_status == Movie.PublicationStatus.PUBLISHED
        return instance

    def create(self, validated_data):
        clear_genres = validated_data.pop('clear_genres', False)
        clear_countries = validated_data.pop('clear_countries', False)
        if clear_genres and 'genres' not in validated_data:
            validated_data['genres'] = []
        if clear_countries and 'countries' not in validated_data:
            validated_data['countries'] = []
        manual_fields = set(validated_data.keys())
        instance = super().create(validated_data)
        instance.metadata_source = 'manual'
        instance.manual_override_fields = sorted(manual_fields)
        instance._manual_changed_fields = sorted(manual_fields)
        self._apply_publication(instance)
        instance.save(update_fields=['metadata_source', 'manual_override_fields', 'is_published', 'updated_at'])
        return instance

    def update(self, instance, validated_data):
        clear_genres = validated_data.pop('clear_genres', False)
        clear_countries = validated_data.pop('clear_countries', False)
        if clear_genres and 'genres' not in validated_data:
            validated_data['genres'] = []
        if clear_countries and 'countries' not in validated_data:
            validated_data['countries'] = []
        changed = set()
        for field_name, value in validated_data.items():
            if field_name in {'genres', 'countries'}:
                current_ids = set(getattr(instance, field_name).values_list('pk', flat=True))
                incoming_ids = {item.pk for item in value}
                if current_ids != incoming_ids:
                    changed.add(field_name)
                continue
            current = getattr(instance, field_name)
            if hasattr(current, 'name'):
                current = current.name
            incoming = value.name if hasattr(value, 'name') else value
            if current != incoming:
                changed.add(field_name)
        instance = super().update(instance, validated_data)
        instance.manual_override_fields = sorted(set(instance.manual_override_fields or []) | changed)
        instance._manual_changed_fields = sorted(changed)
        self._apply_publication(instance)
        instance.save(update_fields=['manual_override_fields', 'is_published', 'updated_at'])
        return instance


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
            'release_year', 'poster', 'tmdb_id',
            'episode_count', 'air_date', 'episodes',
        ]

    def get_episodes(self, obj):
        episodes = getattr(obj, 'published_episodes', None)
        if episodes is None:
            episodes = obj.episodes.filter(is_published=True).order_by('episode_number')
        return EpisodeSerializer(episodes, many=True, context=self.context).data


class SeriesListSerializer(CatalogTitleMixin, MediaRatingsMixin, PublicMediaSerializer):
    public_media_fields = ('poster', 'backdrop', 'trailer_url')
    genres = GenreSerializer(many=True, read_only=True)
    directors = DirectorListSerializer(many=True, read_only=True)
    countries = CountrySerializer(many=True, read_only=True)
    has_downloads = serializers.BooleanField(read_only=True)
    ratings = serializers.SerializerMethodField()

    class Meta:
        model = Series
        fields = [
            'id', 'title', 'original_title', 'secondary_title', 'slug', 'short_description',
            'start_year', 'end_year', 'age_rating', 'language',
            'content_format', 'is_dubbed', 'has_subtitle', 'is_uncensored',
            'imdb_rating', 'imdb_rank', 'rating_average', 'site_rating', 'ratings', 'tmdb_id', 'popularity',
            'poster', 'backdrop', 'trailer_url', 'has_downloads',
            'genres', 'directors', 'countries',
            'status', 'is_published', 'is_featured', 'view_count', 'like_count',
            'created_at', 'updated_at',
        ]


class SeriesDetailSerializer(CatalogTitleMixin, MediaRatingsMixin, PublicMediaSerializer):
    public_media_fields = ('poster', 'backdrop', 'trailer_url')
    genres = GenreSerializer(many=True, read_only=True)
    seasons = serializers.SerializerMethodField()
    series_actors = serializers.SerializerMethodField()
    directors = DirectorListSerializer(many=True, read_only=True)
    countries = CountrySerializer(many=True, read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    download_links = serializers.SerializerMethodField()
    has_downloads = serializers.BooleanField(read_only=True)
    download_qualities = serializers.ListField(child=serializers.CharField(), read_only=True)
    ratings = serializers.SerializerMethodField()

    class Meta:
        model = Series
        fields = [
            'id', 'title', 'original_title', 'secondary_title', 'slug', 'short_description', 'description',
            'start_year', 'end_year', 'age_rating', 'language',
            'content_format', 'is_dubbed', 'has_subtitle', 'is_uncensored', 'content_warnings',
            'imdb_rating', 'imdb_rank', 'rating_average', 'site_rating', 'ratings', 'imdb_id', 'tmdb_id',
            'poster', 'backdrop', 'trailer_url', 'download_links',
            'has_downloads', 'download_qualities',
            'genres', 'series_actors', 'directors', 'countries', 'tags',
            'status', 'is_published', 'is_featured', 'view_count', 'like_count',
            'created_at', 'updated_at',
            'seasons',
        ]

    def get_download_links(self, obj):
        return public_download_links(obj)

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
        # Never expose empty / non-playable season shells on the public detail.
        playable = []
        for season in seasons:
            episodes = getattr(season, 'published_episodes', None)
            if episodes is None:
                episodes = list(
                    season.episodes.filter(is_published=True).order_by('episode_number')
                )
            else:
                episodes = list(episodes)
            has_stream = any(
                str(getattr(ep, 'video_url', '') or '').strip()
                or str(getattr(ep, 'download_key', '') or '').strip()
                for ep in episodes
            )
            if not has_stream:
                continue
            season.published_episodes = [
                ep for ep in episodes if (
                    str(getattr(ep, 'video_url', '') or '').strip()
                    or str(getattr(ep, 'download_key', '') or '').strip()
                )
            ]
            playable.append(season)
        return SeasonSerializer(playable, many=True, context=self.context).data


class AdminSeriesSerializer(serializers.ModelSerializer):
    """Staff write contract for series; derives dub/subtitle flags from download_links."""

    genre_ids = serializers.PrimaryKeyRelatedField(source='genres', queryset=Genre.objects.all(), many=True, required=False)
    country_ids = serializers.PrimaryKeyRelatedField(source='countries', queryset=Country.objects.all(), many=True, required=False)
    clear_genres = serializers.BooleanField(write_only=True, required=False, default=False)
    clear_countries = serializers.BooleanField(write_only=True, required=False, default=False)
    poster_url = serializers.SerializerMethodField()
    backdrop_url = serializers.SerializerMethodField()
    duplicate_warnings = serializers.SerializerMethodField()
    series_actors = serializers.SerializerMethodField()
    directors = DirectorListSerializer(many=True, read_only=True)
    has_downloads = serializers.BooleanField(read_only=True)
    download_qualities = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = Series
        fields = [
            'id', 'title', 'original_title', 'slug', 'short_description', 'description',
            'start_year', 'end_year', 'genre_ids', 'country_ids', 'clear_genres', 'clear_countries',
            'language', 'original_language', 'age_rating',
            'imdb_id', 'tmdb_id', 'poster', 'backdrop', 'poster_external_url',
            'backdrop_external_url', 'poster_url', 'backdrop_url', 'trailer_url',
            'trailer_external_url', 'download_links', 'has_downloads', 'download_qualities',
            'content_format', 'is_dubbed', 'has_subtitle', 'is_uncensored', 'content_warnings',
            'imdb_rating', 'rating_average', 'vote_count', 'popularity',
            'series_actors', 'directors', 'status', 'is_published', 'is_featured',
            'metadata_source', 'last_tmdb_sync_at', 'created_at', 'updated_at', 'duplicate_warnings',
        ]
        read_only_fields = [
            'metadata_source', 'last_tmdb_sync_at', 'rating_average',
            'created_at', 'updated_at', 'duplicate_warnings', 'has_downloads', 'download_qualities',
        ]
        extra_kwargs = {
            'slug': {'required': False, 'allow_blank': True},
            'poster': {'required': False, 'allow_null': True},
            'backdrop': {'required': False, 'allow_null': True},
        }

    def get_poster_url(self, obj):
        return media_url(obj.poster) or obj.poster_external_url or None

    def get_backdrop_url(self, obj):
        return media_url(obj.backdrop) or obj.backdrop_external_url or None

    def get_duplicate_warnings(self, obj):
        queryset = Series.objects.exclude(pk=obj.pk)
        warnings = []
        if obj.tmdb_id and queryset.filter(tmdb_id=obj.tmdb_id).exists():
            warnings.append('tmdb_id')
        if obj.imdb_id and queryset.filter(imdb_id=obj.imdb_id).exists():
            warnings.append('imdb_id')
        if obj.slug and queryset.filter(slug=obj.slug).exists():
            warnings.append('slug')
        if obj.title and obj.start_year and queryset.filter(title__iexact=obj.title, start_year=obj.start_year).exists():
            warnings.append('title_start_year')
        return warnings

    def get_series_actors(self, obj):
        actors_qs = obj.series_actors.select_related('actor').order_by('order')
        return [
            {
                'id': sa.id,
                'role': sa.role,
                'order': sa.order,
                'actor': {
                    'id': sa.actor_id,
                    'name': sa.actor.name,
                    'slug': sa.actor.slug,
                    'photo': media_url(sa.actor.photo) if sa.actor.photo else None,
                    'photo_external_url': sa.actor.photo_external_url or None,
                },
            }
            for sa in actors_qs
        ]

    def _validate_image(self, value, field):
        if not value:
            return value
        if value.size > 8 * 1024 * 1024:
            raise serializers.ValidationError(f'{field} must be smaller than 8 MB.')
        content_type = getattr(value, 'content_type', '')
        if content_type and content_type not in {'image/jpeg', 'image/png', 'image/webp'}:
            raise serializers.ValidationError(f'{field} must be JPEG, PNG, or WebP.')
        return value

    def validate_poster(self, value):
        return self._validate_image(value, 'poster')

    def validate_backdrop(self, value):
        return self._validate_image(value, 'backdrop')

    def validate_imdb_id(self, value):
        return (value or '').strip() or None

    def validate_trailer_url(self, value):
        if value in (None, ''):
            return ''
        return object_key(value)

    def validate_download_links(self, value):
        normalized = normalize_download_links(value)
        if not normalized and self.instance is not None:
            existing = normalize_download_links(getattr(self.instance, 'download_links', None))
            if existing:
                return existing
        return normalized

    def validate(self, attrs):
        attrs = _require_persian_title(attrs, self.instance)
        title = attrs['title']
        if not attrs.get('slug') and not getattr(self.instance, 'slug', ''):
            base = slugify(title, allow_unicode=True) or 'series'
            slug = base
            index = 2
            while Series.objects.filter(slug=slug).exists():
                slug = f'{base}-{index}'
                index += 1
            attrs['slug'] = slug

        links = attrs.get('download_links')
        if links is None and self.instance is not None:
            links = self.instance.download_links
        if links is not None:
            attrs['download_links'] = normalize_download_links(links)
            from apps.catalog.subtitle_extract import download_links_imply_dub, download_links_imply_subtitle
            attrs['has_subtitle'] = download_links_imply_subtitle(attrs['download_links'])
            attrs['is_dubbed'] = download_links_imply_dub(attrs['download_links'])
        return attrs

    def create(self, validated_data):
        clear_genres = validated_data.pop('clear_genres', False)
        clear_countries = validated_data.pop('clear_countries', False)
        if clear_genres and 'genres' not in validated_data:
            validated_data['genres'] = []
        if clear_countries and 'countries' not in validated_data:
            validated_data['countries'] = []
        instance = super().create(validated_data)
        instance.metadata_source = 'manual'
        instance.save(update_fields=['metadata_source', 'updated_at'])
        return instance

    def update(self, instance, validated_data):
        clear_genres = validated_data.pop('clear_genres', False)
        clear_countries = validated_data.pop('clear_countries', False)
        if clear_genres and 'genres' not in validated_data:
            validated_data['genres'] = []
        if clear_countries and 'countries' not in validated_data:
            validated_data['countries'] = []
        return super().update(instance, validated_data)
