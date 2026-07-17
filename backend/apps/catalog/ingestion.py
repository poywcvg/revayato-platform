import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.text import slugify

from config.public_urls import validate_object_key, validate_subtitle_tracks

from .models import (
    Actor, CatalogSyncRun, ContentFormat, Country, Director, Genre,
    MediaStatus, Movie, MovieActor,
)


TMDB_GENRE_SLUGS = {
    12: 'adventure', 14: 'fantasy', 16: 'animation', 18: 'drama',
    27: 'horror', 28: 'action', 35: 'comedy', 36: 'history',
    37: 'western', 53: 'thriller', 80: 'crime', 99: 'documentary',
    878: 'sci-fi', 9648: 'mystery', 10402: 'music', 10749: 'romance',
    10751: 'family', 10752: 'war', 10770: 'tv-movie',
}


class TMDBClient:
    def __init__(self, *, token='', api_key='', api_base='', language='fa-IR', region=''):
        self.token = token.strip()
        self.api_key = api_key.strip()
        self.api_base = api_base.rstrip('/')
        self.language = language
        self.region = region
        if not self.api_base:
            raise ImproperlyConfigured('TMDB_API_BASE_URL is required for catalog sync.')
        if not self.token and not self.api_key:
            raise ImproperlyConfigured('Set TMDB_API_TOKEN or TMDB_API_KEY before catalog sync.')

    def _request(self, path, params=None):
        query = dict(params or {})
        query.setdefault('language', self.language)
        if self.region:
            query.setdefault('region', self.region)
        if self.api_key and not self.token:
            query['api_key'] = self.api_key
        request = Request(
            f'{self.api_base}/{path.lstrip("/")}?{urlencode(query)}',
            headers={
                'Accept': 'application/json',
                **({'Authorization': f'Bearer {self.token}'} if self.token else {}),
            },
        )
        with urlopen(request, timeout=20) as response:  # noqa: S310 - configured trusted provider
            return json.loads(response.read().decode('utf-8'))

    def discover_movies(self, *, released_from, released_until, max_pages=1):
        for page in range(1, max_pages + 1):
            payload = self._request('discover/movie', {
                'include_adult': 'false',
                'include_video': 'false',
                'page': page,
                'primary_release_date.gte': released_from.isoformat(),
                'primary_release_date.lte': released_until.isoformat(),
                'sort_by': 'primary_release_date.desc',
            })
            for movie in payload.get('results', []):
                if movie.get('id'):
                    yield movie
            if page >= int(payload.get('total_pages') or 1):
                break

    def movie_details(self, movie_id):
        return self._request(f'movie/{int(movie_id)}', {
            'append_to_response': 'credits,external_ids,release_dates',
        })


def configured_tmdb_client():
    return TMDBClient(
        token=getattr(settings, 'TMDB_API_TOKEN', ''),
        api_key=getattr(settings, 'TMDB_API_KEY', ''),
        api_base=getattr(settings, 'TMDB_API_BASE_URL', ''),
        language=getattr(settings, 'TMDB_LANGUAGE', 'fa-IR'),
        region=getattr(settings, 'TMDB_REGION', ''),
    )


def load_media_manifest(path):
    if not path:
        return {}
    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    entries = payload.get('movies', payload)
    if isinstance(entries, list):
        return {
            str(entry['tmdb_id']): entry
            for entry in entries
            if isinstance(entry, dict) and entry.get('tmdb_id')
        }
    if not isinstance(entries, dict):
        raise ValidationError('Media manifest must contain a movies object or list.')
    return {str(key).removeprefix('tmdb:'): value for key, value in entries.items()}


def _unique_slug(model, value, suffix, current_pk=None):
    base = slugify(value, allow_unicode=True) or f'item-{suffix}'
    queryset = model.objects.filter(slug=base)
    if current_pk:
        queryset = queryset.exclude(pk=current_pk)
    return f'{base}-{suffix}' if queryset.exists() else base


def _upsert_genres(movie, details):
    genres = []
    for item in details.get('genres') or []:
        genre_id = int(item.get('id') or 0)
        title = (item.get('name') or f'TMDB {genre_id}').strip()
        genre, _ = Genre.objects.update_or_create(
            slug=TMDB_GENRE_SLUGS.get(genre_id, f'tmdb-{genre_id}'),
            defaults={'title': title},
        )
        genres.append(genre)
    movie.genres.set(genres)


def _upsert_countries(movie, details):
    countries = []
    for item in details.get('production_countries') or []:
        code = (item.get('iso_3166_1') or '').strip().upper()[:2]
        if not code:
            continue
        country, _ = Country.objects.update_or_create(
            code=code,
            defaults={'name': (item.get('name') or code).strip()},
        )
        countries.append(country)
    movie.countries.set(countries)


def _upsert_credits(movie, details):
    credits = details.get('credits') or {}
    actor_links = []
    for order, item in enumerate((credits.get('cast') or [])[:20]):
        name = (item.get('name') or '').strip()
        if not name:
            continue
        actor = Actor.objects.filter(name__iexact=name).first()
        if actor:
            actor.popularity = float(item.get('popularity') or actor.popularity)
            actor.save(update_fields=['popularity', 'updated_at'])
        else:
            actor = Actor.objects.create(
                slug=_unique_slug(Actor, name, item.get('id') or order),
                name=name,
                popularity=float(item.get('popularity') or 0),
            )
        actor_links.append(MovieActor(
            movie=movie,
            actor=actor,
            role=(item.get('character') or '').strip()[:255],
            order=order,
            is_lead=order < 5,
        ))
    movie.movie_actors.all().delete()
    MovieActor.objects.bulk_create(actor_links, ignore_conflicts=True)

    directors = []
    for item in credits.get('crew') or []:
        if item.get('job') != 'Director':
            continue
        name = (item.get('name') or '').strip()
        if not name:
            continue
        director = Director.objects.filter(name__iexact=name).first()
        if director:
            director.popularity = float(item.get('popularity') or director.popularity)
            director.save(update_fields=['popularity', 'updated_at'])
        else:
            director = Director.objects.create(
                slug=_unique_slug(Director, name, item.get('id') or 'director'),
                name=name,
                popularity=float(item.get('popularity') or 0),
            )
        directors.append(director)
    movie.directors.set(directors)


def _parse_publish_time(value):
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def apply_media_manifest(movie, entry):
    if not entry:
        return False
    field_map = {
        'hls_key': 'video_url',
        'trailer_key': 'trailer_url',
        'download_key': 'download_key',
        'poster_key': 'poster',
        'backdrop_key': 'backdrop',
    }
    changed = False
    for manifest_name, model_name in field_map.items():
        key = (entry.get(manifest_name) or '').strip()
        if not key:
            continue
        validate_object_key(key)
        if str(getattr(movie, model_name) or '') != key:
            setattr(movie, model_name, key)
            changed = True

    if 'subtitles' in entry:
        tracks = entry.get('subtitles') or []
        validate_subtitle_tracks(tracks)
        normalized_tracks = [
            {
                'id': str(track.get('id') or f'{track.get("language", "und")}-{index}'),
                'label': str(track.get('label') or track.get('language') or 'Subtitle'),
                'language': str(track.get('language') or 'und'),
                'key': str(track.get('key') or track.get('src')),
                'default': bool(track.get('default', False)),
            }
            for index, track in enumerate(tracks)
        ]
        movie.subtitle_tracks = normalized_tracks
        movie.has_subtitle = bool(normalized_tracks)
        changed = True

    for field_name in ('rights_verified', 'auto_publish'):
        if field_name in entry:
            setattr(movie, field_name, bool(entry[field_name]))
            changed = True
    if 'publish_at' in entry:
        movie.scheduled_publish_at = _parse_publish_time(entry.get('publish_at'))
        changed = True
    if 'media_status' in entry:
        movie.media_status = entry['media_status']
        changed = True
    elif movie.video_url:
        movie.media_status = MediaStatus.READY
        changed = True
    return changed


def maybe_auto_publish(movie, *, enabled):
    if not enabled or movie.is_published or not movie.auto_publish or not movie.ready_for_auto_publish:
        return False
    if movie.scheduled_publish_at and movie.scheduled_publish_at > timezone.now():
        return False
    movie.is_published = True
    return True


@transaction.atomic
def upsert_tmdb_movie(details, *, media_entry=None, auto_publish=False):
    tmdb_id = int(details['id'])
    title = (details.get('title') or details.get('original_title') or f'Movie {tmdb_id}').strip()
    release_date = parse_date(details.get('release_date') or '')
    movie = Movie.objects.filter(tmdb_id=tmdb_id).first()
    slug = _unique_slug(Movie, title, tmdb_id, movie.pk if movie else None)
    external_ids = details.get('external_ids') or {}
    imdb_id = (external_ids.get('imdb_id') or details.get('imdb_id') or '').strip() or None
    if imdb_id and Movie.objects.filter(imdb_id=imdb_id).exclude(tmdb_id=tmdb_id).exists():
        imdb_id = None
    description = (details.get('overview') or '').strip()
    defaults = {
        'title': title,
        'original_title': (details.get('original_title') or title).strip(),
        'slug': slug,
        'short_description': description[:500],
        'description': description,
        'release_date': release_date,
        'release_year': release_date.year if release_date else None,
        'duration_minutes': details.get('runtime') or None,
        'language': (details.get('original_language') or '').strip(),
        'content_format': ContentFormat.ANIMATION if any(int(item.get('id') or 0) == 16 for item in details.get('genres') or []) else ContentFormat.LIVE_ACTION,
        'imdb_id': imdb_id,
        'metadata_source': 'tmdb',
        'metadata_synced_at': timezone.now(),
        'source_metadata': {
            'tmdb_status': details.get('status'),
            'tagline': details.get('tagline'),
            'popularity': details.get('popularity'),
            'vote_average': details.get('vote_average'),
            'vote_count': details.get('vote_count'),
            'poster_path': details.get('poster_path'),
            'backdrop_path': details.get('backdrop_path'),
        },
    }
    if movie:
        for field_name, value in defaults.items():
            setattr(movie, field_name, value)
        created = False
    else:
        movie = Movie(tmdb_id=tmdb_id, is_published=False, **defaults)
        created = True
    apply_media_manifest(movie, media_entry or {})
    movie.full_clean(exclude=['genres', 'actors', 'directors', 'countries', 'tags'])
    movie.save()
    _upsert_genres(movie, details)
    _upsert_countries(movie, details)
    _upsert_credits(movie, details)
    published = maybe_auto_publish(movie, enabled=auto_publish)
    if published:
        movie.save(update_fields=['is_published', 'updated_at'])
    return movie, created, published


def publish_ready_movies(*, enabled=True):
    if not enabled:
        return 0
    published = 0
    queryset = Movie.objects.filter(
        is_published=False,
        auto_publish=True,
        rights_verified=True,
        media_status=MediaStatus.READY,
    )
    for movie in queryset.iterator():
        if maybe_auto_publish(movie, enabled=True):
            movie.save(update_fields=['is_published', 'updated_at'])
            published += 1
    return published


def sync_recent_tmdb_movies(*, client=None, manifest=None, max_pages=None, lookback_days=None, lookahead_days=None):
    client = client or configured_tmdb_client()
    manifest = manifest if manifest is not None else load_media_manifest(
        getattr(settings, 'CATALOG_MEDIA_MANIFEST', ''),
    )
    max_pages = max_pages or getattr(settings, 'CATALOG_SYNC_MAX_PAGES', 2)
    lookback_days = lookback_days if lookback_days is not None else getattr(settings, 'CATALOG_SYNC_LOOKBACK_DAYS', 14)
    lookahead_days = lookahead_days if lookahead_days is not None else getattr(settings, 'CATALOG_SYNC_LOOKAHEAD_DAYS', 7)
    auto_publish = getattr(settings, 'CATALOG_AUTO_PUBLISH', False)
    run = CatalogSyncRun.objects.create(provider='tmdb')
    errors = []
    stats = {'discovered': 0, 'created': 0, 'updated': 0, 'published': 0, 'errors': 0}
    try:
        released_from = date.today() - timedelta(days=lookback_days)
        released_until = date.today() + timedelta(days=lookahead_days)
        for summary in client.discover_movies(
            released_from=released_from,
            released_until=released_until,
            max_pages=max_pages,
        ):
            stats['discovered'] += 1
            try:
                details = client.movie_details(summary['id'])
                _movie, created, published = upsert_tmdb_movie(
                    details,
                    media_entry=manifest.get(str(summary['id'])),
                    auto_publish=auto_publish,
                )
                stats['created' if created else 'updated'] += 1
                stats['published'] += int(published)
            except Exception as exc:  # continue syncing other titles
                stats['errors'] += 1
                errors.append({'tmdb_id': summary.get('id'), 'error': str(exc)[:500]})
        run.status = CatalogSyncRun.Status.SUCCEEDED
    except Exception as exc:
        run.status = CatalogSyncRun.Status.FAILED
        stats['errors'] += 1
        errors.append({'error': str(exc)[:500]})
        raise
    finally:
        run.finished_at = timezone.now()
        run.discovered_count = stats['discovered']
        run.created_count = stats['created']
        run.updated_count = stats['updated']
        run.published_count = stats['published']
        run.error_count = stats['errors']
        run.errors = errors[:100]
        run.save()
    return stats
