"""Normalize and store provider download links onto Movie / Series rows."""

from __future__ import annotations

import logging

from django.conf import settings

from apps.catalog.models import Movie, Series
from apps.catalog.provider_import.exceptions import ProviderImportError

logger = logging.getLogger(__name__)


def _prefer_streamable_download(links: list) -> str:
    from apps.catalog.provider_import.catalog_lookup import _prefer_streamable_download as prefer
    return prefer(links)


def apply_provider_download_links(
    obj,
    links: list,
    *,
    replace: bool = True,
    queue_softsub_extract: bool = True,
    empty_code: str = 'provider_links_empty',
    empty_message: str = 'No usable download links after normalization.',
) -> dict:
    """Normalize and store public CDN links on a Movie or Series."""
    from config.public_urls import normalize_download_links
    from apps.catalog.subtitle_extract import (
        apply_availability_flags,
        coalesce_download_links,
        download_links_imply_softsub,
        ensure_episodes_from_download_links,
        _ranked_movie_stream_urls,
    )

    normalized = normalize_download_links(links or [])
    if not normalized:
        raise ProviderImportError(empty_message, code=empty_code)

    previous_download_urls = {
        str(item.get('url') or '').strip()
        for item in (getattr(obj, 'download_links', None) or [])
        if isinstance(item, dict) and str(item.get('url') or '').strip()
    }
    previous_video = (getattr(obj, 'video_url', None) or '').strip()

    obj.download_links = coalesce_download_links(
        getattr(obj, 'download_links', None) or [],
        normalized,
        replace=replace,
    )

    update_fields = ['download_links', 'updated_at']
    if isinstance(obj, Movie):
        if not obj.quality and normalized[0].get('quality'):
            obj.quality = normalized[0]['quality']
            update_fields.append('quality')
        preferred = _prefer_streamable_download(list(obj.download_links or []))
        if preferred and (
            not previous_video
            or previous_video in previous_download_urls
            or previous_video == preferred
        ):
            obj.video_url = preferred
            update_fields.append('video_url')

    flag_fields = apply_availability_flags(obj, obj.download_links)
    update_fields.extend(flag_fields)
    obj.save(update_fields=list(dict.fromkeys(update_fields)))

    if isinstance(obj, Series):
        try:
            ensure_episodes_from_download_links(obj)
        except Exception:
            logger.exception('failed to sync episodes from download links for series %s', obj.pk)

    if queue_softsub_extract:
        try:
            if isinstance(obj, Movie):
                should_queue = (
                    download_links_imply_softsub(obj.download_links or [])
                    or (
                        bool(getattr(settings, 'SUBTITLESTAR_ENABLED', True))
                        and bool(obj.imdb_id)
                        and bool(_ranked_movie_stream_urls(obj.download_links or []))
                    )
                )
                if should_queue:
                    from apps.catalog.tasks import enqueue_movie_softsub
                    enqueue_movie_softsub(obj.pk, force=not bool(obj.subtitle_tracks))
            else:
                if download_links_imply_softsub(obj.download_links or []) or obj.imdb_id:
                    from apps.catalog.tasks import enqueue_series_softsub
                    enqueue_series_softsub(obj.pk, force=False, episode_limit=40)
        except Exception:
            logger.exception('failed to queue softsub for %s %s', obj.__class__.__name__, obj.pk)

    return {
        'imported_count': len(normalized),
        'download_links': normalized,
        'is_dubbed': getattr(obj, 'is_dubbed', False),
        'has_subtitle': getattr(obj, 'has_subtitle', False),
    }
