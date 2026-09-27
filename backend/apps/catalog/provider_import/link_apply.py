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


def guard_provider_links(obj, normalized: list) -> tuple[list, list, list]:
    """Run incoming links through both storage guards. ``(kept, bad, dead)``.

    Split out of :func:`apply_provider_download_links` because it was the only
    caller of the guards, yet three other import paths write ``download_links``
    directly — the discovery crawlers (``dornatv_import``, ``myf2m_discover``)
    and the movie link-apply path — so contaminated and dead links reached
    storage through them untouched. The guards belong to *storing links*, not
    to one function.

    ``bad`` are links whose self-describing CDN path proves they belong to a
    different title; ``dead`` are links the host positively reports gone.
    """
    from apps.catalog.media_verification import screen_links
    from apps.catalog.provider_import.link_integrity import filter_contaminated_links

    kept, dropped = filter_contaminated_links(obj, normalized)
    if dropped:
        logger.warning(
            'link_integrity: rejected %d contaminated link(s) for %s %s: %s',
            len(dropped), obj.__class__.__name__, getattr(obj, 'pk', '?'),
            ', '.join(f'{cat}:{str(item.get("url") or "")[:80]}' for item, cat in dropped[:10]),
        )
    if not kept:
        return [], dropped, []

    kept, dead = screen_links(obj, kept)
    return kept, dropped, dead


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

    # Two guards before storage: the links must provably belong to this title
    # (link_integrity), and the files must still exist (media_verification).
    # Only positive verdicts drop a link — unreachable-from-here is kept and
    # re-checked later, because a CDN outage is not a broken film.
    normalized, _bad, dead = guard_provider_links(obj, normalized)
    if not normalized and not dead:
        raise ProviderImportError(empty_message, code=empty_code)
    if dead and not normalized:
        raise ProviderImportError(
            'Every provider link failed the pre-publish media check.',
            code='provider_links_dead',
        )

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
        # The link the player is handed is decided by testing the sources —
        # reachable, seekable, and a container/codec a browser really decodes —
        # not by whichever file name scored highest. See playback_gate.
        # A video_url that did not come from download_links was set by hand and
        # is still left alone.
        if not previous_video or previous_video in previous_download_urls:
            from apps.catalog import playback_gate

            _choice, gate_fields = playback_gate.gate_links(obj, obj.download_links or [])
            update_fields.extend(gate_fields)

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
        'rejected_dead_count': len(dead),
        'download_links': normalized,
        'is_dubbed': getattr(obj, 'is_dubbed', False),
        'has_subtitle': getattr(obj, 'has_subtitle', False),
    }
