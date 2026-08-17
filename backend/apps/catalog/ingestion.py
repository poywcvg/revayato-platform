import json
import logging
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.text import slugify

from config.public_urls import validate_object_key, validate_subtitle_tracks

from .models import (
    Actor, CatalogSyncRun, ContentFormat, Country, Director, Genre,
    MediaStatus, Movie, MovieActor, Season, Series, SeriesActor,
)
from .countries import persian_country_name
from .genres import GENRE_TITLE_BY_SLUG
from .imdb import enrich_imdb_rating
from .importer_config import get_importer_settings
from .tmdb import TMDBClient, configured_tmdb_client  # noqa: F401 — re-export for callers

logger = logging.getLogger(__name__)


# TMDB genre IDs → one or more canonical Persian catalog slugs.
TMDB_GENRE_SLUGS = {
    12: ('adventure',),
    14: ('fantasy',),
    16: ('animation',),
    18: ('drama',),
    27: ('horror',),
    28: ('action',),
    35: ('comedy',),
    36: ('history',),
    37: ('western',),
    53: ('thriller',),
    80: ('crime',),
    99: ('documentary',),
    878: ('sci-fi',),
    9648: ('mystery',),
    10402: ('music',),
    10749: ('romance',),
    10751: ('family',),
    10752: ('war',),
    10770: ('tv-movie',),
    10759: ('action', 'adventure'),
    10762: ('kids',),
    10764: ('reality-tv',),
    10765: ('sci-fi', 'fantasy'),
    10768: ('war', 'political'),
}

_EXTRA_GENRE_TITLES = {
    'news': 'خبری',
    'soap': 'سریال خانوادگی',
    'talk': 'تاک‌شو',
}


def persian_genre_title(slug, fallback=''):
    return GENRE_TITLE_BY_SLUG.get(slug) or _EXTRA_GENRE_TITLES.get(slug) or fallback or slug


def localize_tmdb_genres(genres):
    """Rewrite TMDB genre payloads to Persian titles used by the site."""
    localized = []
    for item in genres or []:
        if not isinstance(item, dict):
            continue
        genre_id = int(item.get('id') or 0)
        slugs = TMDB_GENRE_SLUGS.get(genre_id)
        if slugs:
            for slug in slugs:
                localized.append({
                    'id': genre_id,
                    'slug': slug,
                    'name': persian_genre_title(slug, item.get('name') or ''),
                })
            continue
        slug = f'tmdb-{genre_id}' if genre_id else 'unknown'
        localized.append({
            'id': genre_id,
            'slug': slug,
            'name': persian_genre_title(slug, (item.get('name') or '').strip() or slug),
        })
    seen = set()
    unique = []
    for item in localized:
        if item['slug'] in seen:
            continue
        seen.add(item['slug'])
        unique.append(item)
    return unique

# Fields considered "manual" once an editor has customized a catalog row.
MANUAL_PROTECTED_FIELDS = (
    'title', 'original_title', 'short_description', 'description',
    'slug', 'release_date', 'release_year', 'duration_minutes',
    'meta_title', 'meta_description', 'seo_keywords', 'age_rating', 'language',
    'original_language',
    'imdb_rating',
    'catalog_type', 'poster_external_url', 'backdrop_external_url',
    'trailer_external_url', 'spoken_languages', 'production_companies',
    'crew_metadata', 'writers',
)


def _as_rating(value):
    if value in (None, ''):
        return None
    try:
        rating = Decimal(str(value)).quantize(Decimal('0.1'))
    except (InvalidOperation, ValueError):
        return None
    if rating < 0 or rating > 10:
        return None
    return rating


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
    """Attach canonical Persian genres; never overwrite titles with English TMDB names."""
    genres = []
    seen_slugs = set()
    for item in details.get('genres') or []:
        genre_id = int(item.get('id') or 0)
        slugs = TMDB_GENRE_SLUGS.get(genre_id)
        if not slugs:
            # Skip unknown English-only TMDB genres rather than polluting the taxonomy.
            continue
        for slug in slugs:
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            title = persian_genre_title(slug)
            genre, created = Genre.objects.get_or_create(
                slug=slug,
                defaults={'title': title},
            )
            if not created and genre.title != title:
                genre.title = title
                genre.save(update_fields=['title'])
            genres.append(genre)
    movie.genres.set(genres)


def _upsert_countries(movie, details):
    countries = []
    seen: set[str] = set()
    for item in details.get('production_countries') or []:
        if isinstance(item, dict):
            code = (item.get('iso_3166_1') or '').strip().upper()[:2]
            label = item.get('name') or code
        else:
            code = str(item or '').strip().upper()[:2]
            label = code
        if not code or code in seen:
            continue
        seen.add(code)
        country, _ = Country.objects.update_or_create(
            code=code,
            defaults={'name': persian_country_name(code, label)},
        )
        countries.append(country)
    # TV payloads use origin_country (list of ISO codes) instead of production_countries.
    for raw in details.get('origin_country') or []:
        code = str(raw or '').strip().upper()[:2]
        if not code or code in seen:
            continue
        seen.add(code)
        country, _ = Country.objects.update_or_create(
            code=code,
            defaults={'name': persian_country_name(code, code)},
        )
        countries.append(country)
    movie.countries.set(countries)


def _normalize_cast_limit(value, default=15):
    try:
        limit = int(value if value is not None else default)
    except (TypeError, ValueError):
        limit = default
    return max(1, min(limit, 50))


def attach_person_photo(person, profile_path=None, *, download=True, force=False, kind='actor'):
    """Set TMDB profile URL and optionally download a local photo ImageField."""
    path = (profile_path or getattr(person, 'profile_path', None) or '')[:255]
    changed = []
    if path:
        if person.profile_path != path:
            person.profile_path = path
            changed.append('profile_path')
        external = _tmdb_image_url(path, 'w342')
        if external and person.photo_external_url != external:
            person.photo_external_url = external
            changed.append('photo_external_url')
        if download and _should_replace_image(getattr(person, 'photo', None), force=force):
            tmdb_id = getattr(person, 'tmdb_id', None) or getattr(person, 'pk', None) or 'unknown'
            content = _download_tmdb_image(path, size='w342', basename=f'tmdb-{tmdb_id}-{kind}-photo')
            if content is not None:
                person.photo.save(content.name, content, save=False)
                changed.append('photo')
    return changed


def _resolve_actor(item, *, order=0):
    from apps.catalog.localization import normalize_person_names

    localized = (item.get('name') or '').strip()
    original = (item.get('original_name') or '').strip()
    name, original = normalize_person_names(localized, original)
    if not name:
        return None, name
    tmdb_id = item.get('id') or None
    actor = Actor.objects.filter(tmdb_id=tmdb_id).first() if tmdb_id else None
    actor = actor or Actor.objects.filter(name__iexact=name, tmdb_id__isnull=True).first()
    if actor:
        if tmdb_id and not actor.tmdb_id:
            actor.tmdb_id = tmdb_id
        actor.name = name
        if original:
            actor.original_name = original[:255]
        actor.popularity = float(item.get('popularity') or actor.popularity)
        return actor, name
    actor = Actor(
        tmdb_id=tmdb_id,
        slug=_unique_slug(Actor, name, item.get('id') or order),
        name=name,
        original_name=original[:255],
        popularity=float(item.get('popularity') or 0),
        profile_path=(item.get('profile_path') or '')[:255],
        photo_external_url=_tmdb_image_url(item.get('profile_path'), 'w342'),
    )
    return actor, name


def _resolve_director(item, *, slug_suffix='director'):
    from apps.catalog.localization import normalize_person_names

    localized = (item.get('name') or '').strip()
    original = (item.get('original_name') or '').strip()
    name, original = normalize_person_names(localized, original)
    if not name:
        return None
    tmdb_id = item.get('id') or None
    director = Director.objects.filter(tmdb_id=tmdb_id).first() if tmdb_id else None
    director = director or Director.objects.filter(name__iexact=name, tmdb_id__isnull=True).first()
    if director:
        if tmdb_id and not director.tmdb_id:
            director.tmdb_id = tmdb_id
        director.name = name
        if original:
            director.original_name = original[:255]
        director.popularity = float(item.get('popularity') or director.popularity)
        return director
    return Director(
        tmdb_id=tmdb_id,
        slug=_unique_slug(Director, name, item.get('id') or slug_suffix),
        name=name,
        original_name=original[:255],
        popularity=float(item.get('popularity') or 0),
        profile_path=(item.get('profile_path') or '')[:255],
        photo_external_url=_tmdb_image_url(item.get('profile_path'), 'w342'),
    )


def _persist_person(person, item, *, download_photos, kind):
    from apps.catalog.localization import normalize_person_names

    path = (item.get('profile_path') or getattr(person, 'profile_path', None) or '')[:255]
    if path:
        person.profile_path = path
        person.photo_external_url = _tmdb_image_url(path, 'w342')
    localized = (item.get('name') or '').strip()
    original = (item.get('original_name') or '').strip()
    name, original = normalize_person_names(localized, original, english_name=original or localized)
    if name:
        person.name = name
    if original:
        person.original_name = original[:255]
    if not person.pk:
        person.save()
    photo_fields = attach_person_photo(person, path, download=download_photos, kind=kind)
    person.save(update_fields=sorted(set([
        'tmdb_id', 'name', 'original_name', 'popularity', 'profile_path', 'photo_external_url', 'updated_at', *photo_fields,
    ])))
    return person


def _upsert_movie_actors(movie, details, *, import_people_images=True, cast_limit=15):
    credits = details.get('credits') or {}
    limit = _normalize_cast_limit(cast_limit)
    actor_links = []
    for order, item in enumerate((credits.get('cast') or [])[:limit]):
        actor, name = _resolve_actor(item, order=order)
        if not name or actor is None:
            continue
        _persist_person(actor, item, download_photos=import_people_images, kind='actor')
        actor_links.append(MovieActor(
            movie=movie,
            actor=actor,
            role=(item.get('character') or '').strip()[:255],
            order=order,
            is_lead=order < 5,
        ))
    movie.movie_actors.all().delete()
    MovieActor.objects.bulk_create(actor_links, ignore_conflicts=True)


def _upsert_movie_directors(movie, details, *, import_people_images=True):
    credits = details.get('credits') or {}
    directors = []
    for item in credits.get('crew') or []:
        if item.get('job') != 'Director':
            continue
        director = _resolve_director(item, slug_suffix='director')
        if director is None:
            continue
        _persist_person(director, item, download_photos=import_people_images, kind='director')
        directors.append(director)
    movie.directors.set(directors)


def _upsert_credits(
    movie,
    details,
    *,
    import_people_images=True,
    cast_limit=15,
    update_actors=True,
    update_directors=True,
):
    """Upsert cast and/or directors independently so one protected relation cannot block the other."""
    if update_actors:
        _upsert_movie_actors(
            movie,
            details,
            import_people_images=import_people_images,
            cast_limit=cast_limit,
        )
    if update_directors:
        _upsert_movie_directors(
            movie,
            details,
            import_people_images=import_people_images,
        )


def _upsert_series_credits(series, details, *, import_people_images=True, cast_limit=15):
    credits = details.get('credits') or {}
    limit = _normalize_cast_limit(cast_limit)
    actor_links = []
    for order, item in enumerate((credits.get('cast') or [])[:limit]):
        actor, name = _resolve_actor(item, order=order)
        if not name or actor is None:
            continue
        _persist_person(actor, item, download_photos=import_people_images, kind='actor')
        actor_links.append(SeriesActor(
            series=series,
            actor=actor,
            role=(item.get('character') or '').strip()[:255],
            order=order,
            is_lead=order < 5,
        ))
    series.series_actors.all().delete()
    SeriesActor.objects.bulk_create(actor_links, ignore_conflicts=True)

    directors = []
    people = [
        *[item for item in credits.get('crew') or [] if item.get('job') == 'Director'],
        *(details.get('created_by') or []),
    ]
    for item in people:
        director = _resolve_director(item, slug_suffix='creator')
        if director is None:
            continue
        _persist_person(director, item, download_photos=import_people_images, kind='director')
        directors.append(director)
    series.directors.set(directors)


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
    if (
        not enabled
        or movie.is_published
        or movie.publication_status == Movie.PublicationStatus.ARCHIVED
        or not movie.auto_publish
        or not movie.ready_for_auto_publish
    ):
        return False
    if movie.scheduled_publish_at and movie.scheduled_publish_at > timezone.now():
        return False
    movie.is_published = True
    movie.publication_status = Movie.PublicationStatus.PUBLISHED
    return True


def _trailer_key_from_details(details):
    videos = ((details.get('videos') or {}).get('results') or [])
    candidates = [
        item for item in videos
        if item.get('site') == 'YouTube' and item.get('type') in {'Trailer', 'Teaser'}
    ]
    candidates.sort(
        key=lambda item: (
            item.get('type') == 'Trailer',
            bool(item.get('official')),
            item.get('published_at') or '',
        ),
        reverse=True,
    )
    trailer = candidates[0] if candidates else None
    return (trailer or {}).get('key') or ''


def _certification_from_details(details, region=None):
    results = (details.get('release_dates') or {}).get('results') or []
    preferred = [region or getattr(settings, 'TMDB_REGION', 'IR'), 'US', 'GB']
    by_region = {item.get('iso_3166_1'): item.get('release_dates') or [] for item in results}
    for region in preferred:
        certifications = [
            (item.get('certification') or '').strip()
            for item in by_region.get(region, [])
            if (item.get('certification') or '').strip()
        ]
        if certifications:
            return certifications[0][:20]
    return ''


def _tmdb_image_url(path, size):
    if not path:
        return ''
    if str(path).startswith(('http://', 'https://')):
        return str(path)
    base = getattr(settings, 'TMDB_IMAGE_BASE_URL', 'https://image.tmdb.org/t/p').rstrip('/')
    return f'{base}/{size}{path}'


def _download_tmdb_image(path, *, size='w500', basename='image'):
    """Fetch a TMDB still and return a Django ContentFile, or None on failure."""
    url = _tmdb_image_url(path, size)
    if not url:
        return None
    request = urllib.request.Request(
        url,
        headers={
            'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
            'User-Agent': 'RevayatoCatalog/1.0',
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = response.read()
            content_type = (response.headers.get('Content-Type') or '').split(';', 1)[0].strip().lower()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning('tmdb_image_download_failed url=%s error=%s', url, exc)
        return None
    if not payload:
        return None
    extension = {
        'image/jpeg': '.jpg',
        'image/jpg': '.jpg',
        'image/png': '.png',
        'image/webp': '.webp',
    }.get(content_type, Path(str(path)).suffix.lower() or '.jpg')
    if extension not in {'.jpg', '.jpeg', '.png', '.webp'}:
        extension = '.jpg'
    return ContentFile(payload, name=f'{basename}{extension}')


def _should_replace_image(field_file, *, force):
    if force:
        return True
    return not bool(getattr(field_file, 'name', None))


def _pick_backdrop_source_path(details, instance=None):
    """Prefer a real TMDB backdrop; fall back to poster when TMDB has none."""
    backdrop_path = (
        details.get('backdrop_path')
        or (getattr(instance, 'source_metadata', None) or {}).get('backdrop_path')
        or getattr(instance, 'backdrop_path', '')
        or ''
    )
    if backdrop_path:
        return str(backdrop_path), 'backdrop'
    images = details.get('images') or {}
    for item in images.get('backdrops') or []:
        path = (item or {}).get('file_path') or ''
        if path:
            return str(path), 'backdrop'
    poster_path = (
        details.get('poster_path')
        or (getattr(instance, 'source_metadata', None) or {}).get('poster_path')
        or getattr(instance, 'poster_path', '')
        or ''
    )
    if poster_path:
        return str(poster_path), 'poster_fallback'
    return '', ''


def attach_tmdb_artwork(instance, details, *, force=False, prefix='item', allow_poster_backdrop=True):
    """Persist TMDB poster/backdrop into local ImageFields when missing."""
    changed = []
    tmdb_id = details.get('id') or getattr(instance, 'tmdb_id', None) or 'unknown'
    poster_path = details.get('poster_path') or (getattr(instance, 'source_metadata', None) or {}).get('poster_path')
    backdrop_path, backdrop_source = _pick_backdrop_source_path(details, instance)
    if backdrop_source == 'poster_fallback' and not allow_poster_backdrop:
        backdrop_path = ''

    if poster_path and _should_replace_image(getattr(instance, 'poster', None), force=force):
        content = _download_tmdb_image(poster_path, size='w500', basename=f'tmdb-{tmdb_id}-{prefix}-poster')
        if content is not None:
            instance.poster.save(content.name, content, save=False)
            changed.append('poster')
        # The backend may be unable to reach the TMDB image CDN (egress blocked),
        # but browsers can. Persist the browser-reachable URL for the poster so a
        # freshly created/re-synced title is never left with bare placeholder art.
        if hasattr(instance, 'poster_external_url'):
            external = _tmdb_image_url(poster_path, 'w500')
            if external and external != getattr(instance, 'poster_external_url', ''):
                instance.poster_external_url = external
                if 'poster_external_url' not in changed:
                    changed.append('poster_external_url')

    if backdrop_path and hasattr(instance, 'backdrop') and _should_replace_image(getattr(instance, 'backdrop', None), force=force):
        # Poster fallbacks stay at w780; real backdrops use the wide still.
        size = 'w780' if backdrop_source == 'poster_fallback' else 'w1280'
        external = _tmdb_image_url(backdrop_path, size)
        content = _download_tmdb_image(
            backdrop_path,
            size=size,
            basename=f'tmdb-{tmdb_id}-{prefix}-backdrop',
        )
        if content is not None:
            instance.backdrop.save(content.name, content, save=False)
            changed.append('backdrop')
            if hasattr(instance, 'backdrop_path') and backdrop_source != 'poster_fallback':
                instance.backdrop_path = backdrop_path[:255]
                if 'backdrop_path' not in changed:
                    changed.append('backdrop_path')
        # Same CDN-egress fallback: keep the wide-still URL even when the local
        # download fails, so hero/detail pages have backdrop art to render.
        if hasattr(instance, 'backdrop_external_url'):
            if external and external != getattr(instance, 'backdrop_external_url', ''):
                instance.backdrop_external_url = external
                if 'backdrop_external_url' not in changed:
                    changed.append('backdrop_external_url')

    return changed


def ensure_local_backdrop_from_poster(instance):
    """Copy an existing local poster into the backdrop field when both are empty of art."""
    if not hasattr(instance, 'backdrop'):
        return []
    if not _should_replace_image(getattr(instance, 'backdrop', None), force=False):
        return []
    if getattr(instance, 'backdrop_external_url', ''):
        return []
    poster = getattr(instance, 'poster', None)
    if not poster or not getattr(poster, 'name', None):
        return []
    try:
        poster.open('rb')
        payload = poster.read()
    except (OSError, ValueError):
        return []
    finally:
        try:
            poster.close()
        except Exception:
            pass
    if not payload:
        return []
    name = f"backdrop-from-poster-{getattr(instance, 'pk', 'x')}-{poster.name.rsplit('/', 1)[-1]}"
    instance.backdrop.save(name, ContentFile(payload), save=False)
    changed = ['backdrop']
    if hasattr(instance, 'backdrop_external_url') and getattr(instance, 'poster_external_url', ''):
        instance.backdrop_external_url = instance.poster_external_url
        changed.append('backdrop_external_url')
    return changed


def build_tmdb_defaults(details, *, movie=None, importer=None):
    tmdb_id = int(details['id'])
    title = (details.get('title') or details.get('original_title') or f'Movie {tmdb_id}').strip()
    release_date = parse_date(details.get('release_date') or '')
    slug = _unique_slug(Movie, title, tmdb_id, movie.pk if movie else None)
    external_ids = details.get('external_ids') or {}
    imdb_id = (external_ids.get('imdb_id') or details.get('imdb_id') or '').strip() or None
    if imdb_id and Movie.objects.filter(imdb_id=imdb_id).exclude(tmdb_id=tmdb_id).exists():
        imdb_id = None
    description = (details.get('overview') or '').strip()
    vote_average = details.get('vote_average')
    trailer_key = _trailer_key_from_details(details)
    crew = (details.get('credits') or {}).get('crew') or []
    writers = [
        {'tmdb_id': item.get('id'), 'name': item.get('name'), 'job': item.get('job')}
        for item in crew if item.get('job') in {'Writer', 'Screenplay', 'Story'}
    ][:20]
    crew_metadata = [
        {
            'tmdb_id': item.get('id'), 'name': item.get('name'),
            'job': item.get('job'), 'department': item.get('department'),
            'profile_path': item.get('profile_path'),
        }
        for item in crew if item.get('job') in {'Director', 'Writer', 'Screenplay', 'Story', 'Producer', 'Executive Producer'}
    ][:40]
    genre_names = [item['name'] for item in localize_tmdb_genres(details.get('genres') or [])]
    return {
        'title': title,
        'original_title': (details.get('original_title') or title).strip(),
        'slug': slug,
        'short_description': description[:500],
        'description': description,
        'release_date': release_date,
        'release_year': release_date.year if release_date else None,
        'duration_minutes': details.get('runtime') or None,
        'language': (details.get('original_language') or '').strip(),
        'original_language': (details.get('original_language') or '').strip(),
        'spoken_languages': details.get('spoken_languages') or [],
        'production_companies': details.get('production_companies') or [],
        'crew_metadata': crew_metadata,
        'writers': writers,
        'content_format': ContentFormat.ANIMATION if any(int(item.get('id') or 0) == 16 for item in details.get('genres') or []) else ContentFormat.LIVE_ACTION,
        'catalog_type': Movie.CatalogType.DOCUMENTARY if any(int(item.get('id') or 0) == 99 for item in details.get('genres') or []) else Movie.CatalogType.MOVIE,
        'imdb_id': imdb_id,
        # IMDb-facing score: prefer OMDb/manual enrichment, else TMDB vote_average.
        'imdb_rating': (
            _as_rating(details.get('imdb_rating'))
            if details.get('imdb_rating') not in (None, '')
            else (
                _as_rating(vote_average)
                if vote_average not in (None, '')
                else getattr(movie, 'imdb_rating', None)
            )
        ),
        'rating_average': _as_rating(vote_average),
        'vote_count': max(0, int(details.get('vote_count') or 0)),
        'popularity': float(details.get('popularity') or 0),
        'age_rating': _certification_from_details(details, getattr(importer, 'region', None)),
        'poster_path': (details.get('poster_path') or '')[:255],
        'backdrop_path': (details.get('backdrop_path') or '')[:255],
        'poster_external_url': _tmdb_image_url(details.get('poster_path'), 'w500'),
        'backdrop_external_url': _tmdb_image_url(details.get('backdrop_path'), 'w1280'),
        'trailer_external_url': f'https://www.youtube.com/watch?v={trailer_key}' if trailer_key else '',
        'meta_title': title[:255],
        'meta_description': description[:500],
        'seo_keywords': list(dict.fromkeys([title, *genre_names]))[:12],
        'metadata_source': 'tmdb',
        'metadata_synced_at': timezone.now(),
        'last_tmdb_sync_at': timezone.now(),
        'source_metadata': {
            'tmdb_status': details.get('status'),
            'tagline': details.get('tagline'),
            'popularity': details.get('popularity'),
            'vote_average': details.get('vote_average'),
            'vote_count': details.get('vote_count'),
            'imdb_rating': details.get('imdb_rating'),
            'imdb_votes': details.get('imdb_votes'),
            'imdb_rating_source': details.get('imdb_rating_source') or 'tmdb',
            'persian_title_source': details.get('_persian_title_source'),
            'persian_overview_source': details.get('_persian_overview_source'),
            'title_source': details.get('_title_source'),
            'original_title_source': details.get('_original_title_source'),
            'native_original_title': details.get('_native_original_title'),
            'poster_source': details.get('_poster_source'),
            'poster_path': details.get('poster_path'),
            'backdrop_path': details.get('backdrop_path'),
            'trailer_youtube_key': trailer_key,
        },
    }


@transaction.atomic
def upsert_tmdb_movie(
    details,
    *,
    media_entry=None,
    auto_publish=False,
    overwrite_manual=False,
    dry_run=False,
    imdb_client=None,
    importer=None,
):
    importer = importer or get_importer_settings()
    enrich_imdb_rating(
        details,
        client=imdb_client,
        enabled=bool(importer.fetch_imdb_ratings),
    )
    tmdb_id = int(details['id'])
    movie = Movie.objects.filter(tmdb_id=tmdb_id).first()
    defaults = build_tmdb_defaults(details, movie=movie, importer=importer)
    skipped_fields = []
    changed_fields = []
    if movie:
        was_manual = movie.metadata_source == 'manual'
        manual_fields = set(movie.manual_override_fields or [])
        for field_name, value in defaults.items():
            if (
                not overwrite_manual
                and field_name in MANUAL_PROTECTED_FIELDS
                and (
                    field_name in manual_fields
                    or (was_manual and bool(getattr(movie, field_name)))
                )
            ):
                skipped_fields.append(field_name)
                continue
            if getattr(movie, field_name) != value:
                setattr(movie, field_name, value)
                changed_fields.append(field_name)
        created = False
    else:
        movie = Movie(tmdb_id=tmdb_id, is_published=False, **defaults)
        was_manual = False
        manual_fields = set()
        changed_fields = ['tmdb_id', *defaults.keys()]
        created = True
    apply_media_manifest(movie, media_entry or {})
    if auto_publish:
        movie.auto_publish = True
    movie._tmdb_changed_fields = sorted(set(changed_fields))
    if dry_run:
        return movie, created, False, skipped_fields
    movie.full_clean(exclude=[
        'genres', 'actors', 'directors', 'countries', 'tags',
        # Provider crawl may store absolute CDN URLs for online playback.
        'video_url', 'trailer_url', 'download_key',
    ])
    movie.save()

    # Prefer licensed manifest artwork when present; otherwise download TMDB stills.
    # Re-fetch when TMDB poster/backdrop path changes (e.g. localized → original).
    manifest_has_art = bool((media_entry or {}).get('poster_key') or (media_entry or {}).get('backdrop_key'))
    path_changed = bool({'poster_path', 'backdrop_path', 'poster_external_url', 'backdrop_external_url'} & set(changed_fields))
    artwork_force = bool((overwrite_manual or path_changed or created) and not manifest_has_art)
    artwork_changed = []
    if not manifest_has_art:
        artwork_changed = attach_tmdb_artwork(
            movie,
            details,
            force=artwork_force,
            prefix='movie',
        )
        if artwork_changed:
            movie.save(update_fields=[*artwork_changed, 'updated_at'])
            changed_fields.extend(artwork_changed)
            movie._tmdb_changed_fields = sorted(set(changed_fields))

    def relation_is_protected(field_name):
        if overwrite_manual or created:
            return False
        if field_name in manual_fields:
            return True
        relation = getattr(movie, field_name)
        return was_manual and relation.exists()

    if not relation_is_protected('genres'):
        _upsert_genres(movie, details)
    else:
        skipped_fields.append('genres')
    if not relation_is_protected('countries'):
        _upsert_countries(movie, details)
    else:
        skipped_fields.append('countries')
    update_actors = not relation_is_protected('actors')
    update_directors = not relation_is_protected('directors')
    if update_actors or update_directors:
        _upsert_credits(
            movie,
            details,
            import_people_images=bool(importer.import_people_images),
            cast_limit=getattr(importer, 'cast_import_limit', 15),
            update_actors=update_actors,
            update_directors=update_directors,
        )
    if not update_actors:
        skipped_fields.append('actors')
    if not update_directors:
        skipped_fields.append('directors')
    published = maybe_auto_publish(movie, enabled=auto_publish)
    if published:
        movie.save(update_fields=['is_published', 'publication_status', 'updated_at'])
    movie._tmdb_changed_fields = sorted(set(changed_fields))
    return movie, created, published, skipped_fields


def _series_status(value):
    normalized = (value or '').strip().lower()
    if normalized in {'ended'}:
        return Series.Status.ENDED
    if normalized in {'canceled', 'cancelled'}:
        return Series.Status.CANCELLED
    if normalized in {'planned', 'in production', 'pilot'}:
        return Series.Status.UPCOMING
    return Series.Status.ONGOING


def _series_content_rating(details):
    results = (details.get('content_ratings') or {}).get('results') or []
    by_region = {
        item.get('iso_3166_1'): (item.get('rating') or '').strip()
        for item in results
    }
    for region in (getattr(settings, 'TMDB_REGION', 'IR'), 'US', 'GB'):
        if region and by_region.get(region):
            return by_region[region][:20]
    return ''


def build_tmdb_series_defaults(details, *, series=None):
    tmdb_id = int(details['id'])
    title = (details.get('name') or details.get('original_name') or f'Series {tmdb_id}').strip()
    first_air_date = parse_date(details.get('first_air_date') or '')
    last_air_date = parse_date(details.get('last_air_date') or '')
    slug = _unique_slug(Series, title, tmdb_id, series.pk if series else None)
    external_ids = details.get('external_ids') or {}
    imdb_id = (external_ids.get('imdb_id') or '').strip() or None
    if imdb_id and Series.objects.filter(imdb_id=imdb_id).exclude(tmdb_id=tmdb_id).exists():
        imdb_id = None
    description = (details.get('overview') or '').strip()
    trailer_key = _trailer_key_from_details(details)
    return {
        'title': title,
        'original_title': (details.get('original_name') or title).strip(),
        'slug': slug,
        'short_description': description[:500],
        'description': description,
        'start_year': first_air_date.year if first_air_date else None,
        'end_year': last_air_date.year if last_air_date and details.get('status') == 'Ended' else None,
        'language': (details.get('original_language') or '').strip(),
        'original_language': (details.get('original_language') or '').strip(),
        'content_format': ContentFormat.ANIMATION if any(
            int(item.get('id') or 0) == 16 for item in details.get('genres') or []
        ) else ContentFormat.LIVE_ACTION,
        'status': _series_status(details.get('status')),
        'imdb_id': imdb_id,
        # IMDb-facing score: prefer OMDb/manual enrichment, else TMDB vote_average.
        'imdb_rating': (
            _as_rating(details.get('imdb_rating'))
            if details.get('imdb_rating') not in (None, '')
            else (
                _as_rating(details.get('vote_average'))
                if details.get('vote_average') not in (None, '')
                else getattr(series, 'imdb_rating', None)
            )
        ),
        'rating_average': _as_rating(details.get('vote_average')),
        'vote_count': max(0, int(details.get('vote_count') or 0)),
        'popularity': float(details.get('popularity') or 0),
        'age_rating': _series_content_rating(details),
        'poster_external_url': _tmdb_image_url(details.get('poster_path'), 'w500'),
        'backdrop_external_url': _tmdb_image_url(details.get('backdrop_path'), 'w1280'),
        'trailer_external_url': f'https://www.youtube.com/watch?v={trailer_key}' if trailer_key else '',
        'metadata_source': 'tmdb',
        'metadata_synced_at': timezone.now(),
        'last_tmdb_sync_at': timezone.now(),
        'source_metadata': {
            'tmdb_status': details.get('status'),
            'tagline': details.get('tagline'),
            'homepage': details.get('homepage'),
            'first_air_date': details.get('first_air_date'),
            'last_air_date': details.get('last_air_date'),
            'number_of_seasons': details.get('number_of_seasons'),
            'number_of_episodes': details.get('number_of_episodes'),
            'original_title_source': details.get('_original_title_source'),
            'native_original_title': details.get('_native_original_title'),
            'poster_source': details.get('_poster_source'),
            'poster_path': details.get('poster_path'),
            'backdrop_path': details.get('backdrop_path'),
            'trailer_youtube_key': trailer_key,
        },
    }


def _upsert_seasons(series, details):
    """Refresh TMDB metadata only for seasons that already exist.

    Do not create empty season shells from TMDB (S0 specials, unaired seasons,
    or seasons without download-backed episodes). Those rows have no playable
    value and clutter series UIs. Real Season/Episode rows are created from
    provider download links via ``ensure_episodes_from_download_links``.
    """
    existing = {
        season.season_number: season
        for season in Season.objects.filter(series=series)
    }
    if not existing:
        return

    for item in details.get('seasons') or []:
        season_number = item.get('season_number')
        if season_number is None:
            continue
        season_number = max(0, int(season_number))
        season = existing.get(season_number)
        if season is None:
            continue
        air_date = parse_date(item.get('air_date') or '')
        title = (item.get('name') or '')[:255]
        description = item.get('overview') or ''
        poster = _tmdb_image_url(item.get('poster_path'), 'w500')
        tmdb_id = item.get('id') or None
        fields: list[str] = []
        if tmdb_id and season.tmdb_id != tmdb_id:
            season.tmdb_id = tmdb_id
            fields.append('tmdb_id')
        # Prefer real TMDB titles over stub «فصل N» labels.
        stub_title = not season.title or season.title.strip() in {
            f'فصل {season_number}',
            f'Season {season_number}',
            f'S{season_number}',
        }
        if title and (stub_title or not season.title):
            season.title = title
            fields.append('title')
        if description and not (season.description or '').strip():
            season.description = description
            fields.append('description')
        if air_date:
            if season.air_date != air_date:
                season.air_date = air_date
                fields.append('air_date')
            year = air_date.year
            if season.release_year != year:
                season.release_year = year
                fields.append('release_year')
        if poster and not (season.poster_external_url or '').strip():
            season.poster_external_url = poster
            fields.append('poster_external_url')
        if fields:
            season.save(update_fields=[*dict.fromkeys(fields), 'updated_at'])


@transaction.atomic
def upsert_tmdb_series(details, *, dry_run=False, imdb_client=None, importer=None):
    importer = importer or get_importer_settings()
    enrich_imdb_rating(
        details,
        client=imdb_client,
        enabled=bool(importer.fetch_imdb_ratings),
    )
    tmdb_id = int(details['id'])
    series = Series.objects.filter(tmdb_id=tmdb_id).first()
    defaults = build_tmdb_series_defaults(details, series=series)
    previous_meta = dict(series.source_metadata or {}) if series and series.pk else {}
    previous_poster = (previous_meta.get('poster_path') or '') if series else ''
    if series:
        for field_name, value in defaults.items():
            setattr(series, field_name, value)
        created = False
    else:
        series = Series(tmdb_id=tmdb_id, is_published=False, **defaults)
        created = True
    if dry_run:
        return series, created
    series.full_clean(exclude=[
        'genres', 'actors', 'directors', 'countries', 'tags',
        'video_url', 'trailer_url', 'download_key',
    ])
    series.save()
    new_poster = (details.get('poster_path') or '')
    artwork_force = created or (bool(new_poster) and new_poster != previous_poster)
    artwork_changed = attach_tmdb_artwork(series, details, force=artwork_force, prefix='series')
    if artwork_changed:
        series.save(update_fields=[*artwork_changed, 'updated_at'])
    _upsert_genres(series, details)
    _upsert_countries(series, details)
    _upsert_series_credits(
        series,
        details,
        import_people_images=bool(importer.import_people_images),
        cast_limit=getattr(importer, 'cast_import_limit', 15),
    )
    _upsert_seasons(series, details)
    return series, created


def publish_ready_movies(*, enabled=True):
    if not enabled:
        return 0
    published = 0
    queryset = Movie.objects.filter(
        is_published=False,
        publication_status=Movie.PublicationStatus.DRAFT,
        auto_publish=True,
        rights_verified=True,
        media_status=MediaStatus.READY,
    )
    for movie in queryset.iterator():
        if maybe_auto_publish(movie, enabled=True):
            movie.save(update_fields=['is_published', 'publication_status', 'updated_at'])
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
                _movie, created, published, _skipped = upsert_tmdb_movie(
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
