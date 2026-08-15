"""Import movies/series download links from dornatv.com into the catalog.

CDN link shape is direct .mkv/.mp4 (dlyar.top); storage uses apply_provider_download_links.
"""

from __future__ import annotations

import logging
import re
from types import SimpleNamespace
from urllib.parse import unquote

from django.conf import settings

from apps.catalog.models import Movie, ProviderSource, Series
from apps.catalog.provider_import.exceptions import ProviderImportError
from apps.catalog.provider_import.link_apply import apply_provider_download_links
from apps.catalog.provider_import.matching import (
    score_provider_candidate_against_movie,
    score_provider_candidate_against_series,
)
from apps.catalog.provider_import.providers.dornatv_parser import slugify_title

logger = logging.getLogger(__name__)


def _validate_dornatv_identity(obj, crawled: dict) -> None:
    """Reject a detail page unless its own metadata exactly matches the target.

    Search ranking is only discovery.  A shared word such as ``Room`` or
    ``Terminator`` must never be enough to attach a different title's files.
    Prefer an exact IMDb id; otherwise require exact normalized title + year.
    """
    candidate = SimpleNamespace(
        tmdb_id=None,
        imdb_id=str(crawled.get('imdb_id') or '').strip(),
        title=str(
            crawled.get('title_en')
            or crawled.get('original_title')
            or crawled.get('title')
            or ''
        ).strip(),
        original_title=str(crawled.get('original_title') or '').strip(),
        year=crawled.get('year'),
    )
    if isinstance(obj, Movie):
        match = score_provider_candidate_against_movie(candidate, obj)
    else:
        match = score_provider_candidate_against_series(candidate, obj)
    if match.score >= 0.95 and not match.requires_manual_approval:
        return

    # A few otherwise valid Dornatv pages have malformed/translated H1 metadata.
    # In that case the canonical detail path is useful independent evidence, but
    # only when both the complete English title and year are exact path tokens.
    # Never let path evidence override an explicit IMDb conflict.
    object_imdb = str(getattr(obj, 'imdb_id', '') or '').strip().lower()
    crawled_imdb = str(crawled.get('imdb_id') or '').strip().lower()
    has_imdb_conflict = bool(
        object_imdb and crawled_imdb and object_imdb != crawled_imdb
    )
    page_slug = slugify_title(unquote(str(crawled.get('page_path') or '')))
    target_slug = slugify_title(str(getattr(obj, 'original_title', '') or ''))
    expected_year = (
        getattr(obj, 'release_year', None)
        if isinstance(obj, Movie)
        else getattr(obj, 'start_year', None)
    )
    title_in_path = bool(
        target_slug
        and re.search(rf'(?:^|-){re.escape(target_slug)}(?:-|$)', page_slug)
    )
    year_in_path = bool(
        expected_year
        and re.search(rf'(?:^|-){int(expected_year)}(?:-|$)', page_slug)
    )
    if not has_imdb_conflict and title_in_path and year_in_path:
        return

    # Dornatv sometimes shortens the English title on the detail page (for
    # example "House of Ashur" for "Spartacus: House of Ashur"). Accept when
    # every significant token of the crawled title is contained in the target
    # title and the years agree, but never when only a short fragment overlaps.
    crawled_title = str(crawled.get('title_en') or crawled.get('original_title') or '').strip()
    target_title = str(getattr(obj, 'original_title', '') or getattr(obj, 'title', '') or '').strip()
    if not has_imdb_conflict and crawled_title and target_title:
        stop = {'the', 'and', 'or', 'of', 'a', 'an', 'to', 'in', 'for', 'with', 'on'}
        crawled_tokens = {
            token for token in re.findall(r"[a-z0-9']+", crawled_title.lower())
            if token not in stop
        }
        target_tokens = {
            token for token in re.findall(r"[a-z0-9']+", target_title.lower())
            if token not in stop
        }
        years_ok = (
            not expected_year
            or not (crawled.get('year') or '')
            or int(crawled['year']) == int(expected_year)
        )
        if (
            crawled_tokens
            and crawled_tokens.issubset(target_tokens)
            and len(target_tokens) >= 2
            and years_ok
            and (len(target_tokens) >= 3 or len(crawled_tokens) == len(target_tokens))
        ):
            return
    raise ProviderImportError(
        f'Dornatv detail page identity mismatch ({match.reason}).',
        code='dornatv_identity_mismatch',
    )


def ensure_dornatv_provider() -> ProviderSource:
    provider, _ = ProviderSource.objects.update_or_create(
        slug='dornatv',
        defaults={
            'name': 'Dornatv (dornatv.com)',
            'provider_type': ProviderSource.ProviderType.STATIC_LINKS,
            'base_url': getattr(settings, 'DORNATV_BASE_URL', 'https://dornatv.com'),
            'auth_type': ProviderSource.AuthType.NONE,
            'is_active': True,
            'rate_limit_per_minute': getattr(settings, 'DORNATV_RATE_LIMIT_PER_MINUTE', 30),
            'timeout_seconds': getattr(settings, 'DORNATV_TIMEOUT_SECONDS', 30),
            'verify_ssl': getattr(settings, 'DORNATV_VERIFY_SSL', True),
            'config': {
                'supports_movies': True,
                'supports_series': True,
                'public_downloads': True,
                'wp_rest': True,
                'theme': 'BartarTheme',
                'requires_fa_en_titles': True,
            },
        },
    )
    return provider


def _apply_dornatv_page_metadata(obj, crawled: dict) -> list[str]:
    """Fill catalog fields from Dornatv page metadata. Prefer FA title + EN original_title."""
    fields: list[str] = []
    imdb_id = str(crawled.get('imdb_id') or '').strip().lower()
    if imdb_id and not (getattr(obj, 'imdb_id', None) or '').strip():
        obj.imdb_id = imdb_id
        fields.append('imdb_id')

    title_fa = str(crawled.get('title_fa') or crawled.get('title') or '').strip()
    title_en = str(crawled.get('title_en') or crawled.get('original_title') or '').strip()
    if title_fa and (getattr(obj, 'title', None) or '').strip() != title_fa[:255]:
        obj.title = title_fa[:255]
        fields.append('title')
    if title_en:
        current_orig = (getattr(obj, 'original_title', None) or '').strip()
        if not current_orig or current_orig == (getattr(obj, 'title', None) or '').strip() or not re.search(r'[A-Za-z]', current_orig):
            obj.original_title = title_en[:255]
            fields.append('original_title')

    year = crawled.get('year')
    try:
        year_i = int(year) if year else None
    except (TypeError, ValueError):
        year_i = None
    if year_i:
        if isinstance(obj, Movie) and not obj.release_year:
            obj.release_year = year_i
            fields.append('release_year')
        elif isinstance(obj, Series) and not obj.start_year:
            obj.start_year = year_i
            fields.append('start_year')

    description = str(crawled.get('description') or '').strip()
    if description:
        if not (getattr(obj, 'description', None) or '').strip():
            obj.description = description
            fields.append('description')
        if not (getattr(obj, 'short_description', None) or '').strip():
            obj.short_description = description[:500]
            fields.append('short_description')

    poster_url = str(crawled.get('poster_url') or '').strip()
    has_poster = bool(getattr(obj, 'poster', None))
    has_external = bool((getattr(obj, 'poster_external_url', None) or '').strip())
    has_path = bool((getattr(obj, 'poster_path', None) or '').strip())
    if poster_url and not has_poster and not has_external and not has_path:
        obj.poster_external_url = poster_url[:500]
        fields.append('poster_external_url')

    duration = crawled.get('duration_minutes')
    try:
        duration_i = int(duration) if duration else None
    except (TypeError, ValueError):
        duration_i = None
    if duration_i and isinstance(obj, Movie) and not getattr(obj, 'duration_minutes', None):
        obj.duration_minutes = duration_i
        fields.append('duration_minutes')

    if fields:
        obj.save(update_fields=[*dict.fromkeys(fields), 'updated_at'])
    return fields


def _auto_resolve_movie_target(connector, movie: Movie) -> str:
    query = {
        'title': movie.title,
        'original_title': movie.original_title,
        'year': movie.release_year,
        'titles': [t for t in (movie.original_title, movie.title) if t],
    }
    hits = connector.search_movie(query) or []
    return hits[0].provider_item_id if hits else ''


def _auto_resolve_series_target(connector, series: Series) -> str:
    query = {
        'title': series.title,
        'original_title': series.original_title,
        'year': series.start_year,
        'titles': [t for t in (series.original_title, series.title) if t],
    }
    hits = connector.search_series(query) or []
    return hits[0].provider_item_id if hits else ''


def crawl_dornatv_downloads_for_movie(
    *,
    movie: Movie,
    page_url: str = '',
    provider_item_id: str = '',
    replace: bool = True,
    queue_softsub_extract: bool = True,
) -> dict:
    from apps.catalog.provider_import.registry import get_connector

    ensure_dornatv_provider()
    target = (page_url or provider_item_id or '').strip()
    connector = get_connector('dornatv')
    try:
        if not target:
            target = _auto_resolve_movie_target(connector, movie)
        if not target:
            raise ProviderImportError(
                'Provide a Dornatv page URL or ensure the title matches a listing.',
                code='dornatv_page_required',
            )
        crawled = connector.crawl_download_links(target, content_type='movie')
        _validate_dornatv_identity(movie, crawled)
    except ProviderImportError:
        raise
    except Exception as exc:
        raise ProviderImportError(f'dornatv crawl failed: {exc}', code='dornatv_crawl_failed') from exc
    finally:
        close = getattr(connector, 'close', None)
        if callable(close):
            close()

    links = crawled.get('available_links') or []
    if not links:
        raise ProviderImportError(
            crawled.get('message') or 'No download links were available on the Dornatv page.',
            code=crawled.get('code') or 'dornatv_links_empty',
        )

    metadata_fields = _apply_dornatv_page_metadata(movie, crawled)
    applied = apply_provider_download_links(
        movie,
        links,
        replace=replace,
        queue_softsub_extract=queue_softsub_extract,
        empty_code='dornatv_links_empty',
        empty_message='No usable Dornatv download links after normalization.',
    )
    return {
        'movie_id': movie.id,
        'page_path': crawled.get('page_path'),
        'page_url': crawled.get('page_url'),
        'imdb_id': crawled.get('imdb_id') or movie.imdb_id,
        'imported_count': applied.get('imported_count', 0),
        'download_links': applied.get('download_links') or [],
        'video_url': movie.video_url,
        'is_dubbed': movie.is_dubbed,
        'has_subtitle': movie.has_subtitle,
        'metadata_fields': metadata_fields,
        'code': crawled.get('code') or 'ok',
        'provider': 'dornatv',
    }


def crawl_dornatv_downloads_for_series(
    *,
    series: Series,
    page_url: str = '',
    provider_item_id: str = '',
    replace: bool = True,
    queue_softsub_extract: bool = True,
) -> dict:
    from apps.catalog.provider_import.registry import get_connector

    ensure_dornatv_provider()
    target = (page_url or provider_item_id or '').strip()
    connector = get_connector('dornatv')
    try:
        if not target:
            target = _auto_resolve_series_target(connector, series)
        if not target:
            raise ProviderImportError(
                'Provide a Dornatv series URL or ensure the title matches a listing.',
                code='dornatv_page_required',
            )
        crawled = connector.crawl_download_links(target, content_type='series')
        _validate_dornatv_identity(series, crawled)
    except ProviderImportError:
        raise
    except Exception as exc:
        raise ProviderImportError(
            f'dornatv series crawl failed: {exc}',
            code='dornatv_crawl_failed',
        ) from exc
    finally:
        close = getattr(connector, 'close', None)
        if callable(close):
            close()

    links = crawled.get('available_links') or []
    if not links:
        raise ProviderImportError(
            crawled.get('message') or 'No download links were available on the Dornatv series page.',
            code=crawled.get('code') or 'dornatv_links_empty',
        )

    metadata_fields = _apply_dornatv_page_metadata(series, crawled)
    applied = apply_provider_download_links(
        series,
        links,
        replace=replace,
        queue_softsub_extract=queue_softsub_extract,
        empty_code='dornatv_links_empty',
        empty_message='No usable Dornatv download links after normalization.',
    )
    return {
        'series_id': series.id,
        'page_path': crawled.get('page_path'),
        'page_url': crawled.get('page_url'),
        'imdb_id': crawled.get('imdb_id') or series.imdb_id,
        'imported_count': applied.get('imported_count', 0),
        'download_links': applied.get('download_links') or [],
        'is_dubbed': series.is_dubbed,
        'has_subtitle': series.has_subtitle,
        'metadata_fields': metadata_fields,
        'code': crawled.get('code') or 'ok',
        'provider': 'dornatv',
    }
