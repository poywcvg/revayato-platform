"""Redis-backed response cache for hot public catalog reads."""

from __future__ import annotations

import hashlib
import os
from typing import Any

from django.core.cache import cache
from django.conf import settings
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

CATALOG_CACHE_VERSION_KEY = 'catalog:cache_version'
CATALOG_CACHE_BUMP_LOCK_KEY = 'catalog:cache_version:bump_lock'
CATALOG_CACHE_NS = 'catalog:resp'

_TTL_DEFAULTS = {
    'list': 180,
    'detail': 300,
    'trending': 120,
    'home': 300,
    'genres': 600,
    'search': 30,
    'actors': 600,
}
_TTL_ENV = {
    'list': 'CATALOG_CACHE_LIST_TTL',
    'detail': 'CATALOG_CACHE_DETAIL_TTL',
    'trending': 'CATALOG_CACHE_TRENDING_TTL',
    'home': 'CATALOG_CACHE_HOME_TTL',
    'genres': 'CATALOG_CACHE_GENRES_TTL',
    'search': 'CATALOG_CACHE_SEARCH_TTL',
    'actors': 'CATALOG_CACHE_ACTORS_TTL',
}


def catalog_cache_ttl(kind: str = 'list') -> int:
    env_name = _TTL_ENV.get(kind, 'CATALOG_CACHE_LIST_TTL')
    raw = os.environ.get(env_name, '')
    if raw.strip().isdigit():
        return max(0, int(raw))
    return _TTL_DEFAULTS.get(kind, 90)


def catalog_cache_version() -> int:
    version = cache.get(CATALOG_CACHE_VERSION_KEY)
    if version is None:
        cache.add(CATALOG_CACHE_VERSION_KEY, 1, timeout=None)
        return 1
    try:
        return int(version)
    except (TypeError, ValueError):
        return 1


def catalog_cache_invalidation_interval() -> int:
    """Minimum seconds between global invalidations during bulk ingestion.

    Importers can save several catalog objects per second. Invalidating the
    global namespace for every save makes otherwise hot list/home responses
    permanent cache misses. Tests and development retain immediate
    invalidation; production coalesces the burst into one invalidation per
    short freshness window.
    """
    raw = os.environ.get('CATALOG_CACHE_INVALIDATION_MIN_INTERVAL', '').strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return 0 if settings.DEBUG else 300


def bump_catalog_cache_version(*, force: bool = False) -> int:
    """Invalidate versioned responses, coalescing production write bursts."""
    interval = catalog_cache_invalidation_interval()
    if not force and interval > 0 and not cache.add(
        CATALOG_CACHE_BUMP_LOCK_KEY,
        1,
        timeout=interval,
    ):
        return catalog_cache_version()
    try:
        return int(cache.incr(CATALOG_CACHE_VERSION_KEY))
    except ValueError:
        cache.set(CATALOG_CACHE_VERSION_KEY, 2, timeout=None)
        return 2


def build_catalog_cache_key(namespace: str, request) -> str:
    raw = request.META.get('QUERY_STRING', '') or ''
    path = request.path
    digest = hashlib.sha256(f'{path}?{raw}'.encode()).hexdigest()[:24]
    return f'{CATALOG_CACHE_NS}:v{catalog_cache_version()}:{namespace}:{digest}'


def get_cached_payload(key: str) -> Any | None:
    return cache.get(key)


def set_cached_payload(key: str, payload: Any, ttl: int) -> None:
    if ttl <= 0:
        return
    cache.set(key, payload, timeout=ttl)


def cache_control_for(kind: str = 'list') -> str:
    ttl = catalog_cache_ttl(kind)
    if ttl <= 0:
        return 'private, no-store'
    swr = max(ttl * 3, 180)
    # s-maxage lets Cloudflare/CDN reuse anonymous JSON; browsers still honor max-age.
    return f'public, max-age={ttl}, s-maxage={ttl}, stale-while-revalidate={swr}'


def _register_invalidation_signals() -> None:
    from .models import Actor, Country, Director, Genre, Movie, Series, Tag

    @receiver(post_save, sender=Movie, dispatch_uid='catalog_cache_invalidate_movie')
    @receiver(post_delete, sender=Movie, dispatch_uid='catalog_cache_delete_movie')
    @receiver(post_save, sender=Series, dispatch_uid='catalog_cache_invalidate_series')
    @receiver(post_delete, sender=Series, dispatch_uid='catalog_cache_delete_series')
    @receiver(post_save, sender=Genre, dispatch_uid='catalog_cache_invalidate_genre')
    @receiver(post_delete, sender=Genre, dispatch_uid='catalog_cache_delete_genre')
    @receiver(post_save, sender=Actor, dispatch_uid='catalog_cache_invalidate_actor')
    @receiver(post_delete, sender=Actor, dispatch_uid='catalog_cache_delete_actor')
    @receiver(post_save, sender=Director, dispatch_uid='catalog_cache_invalidate_director')
    @receiver(post_delete, sender=Director, dispatch_uid='catalog_cache_delete_director')
    @receiver(post_save, sender=Country, dispatch_uid='catalog_cache_invalidate_country')
    @receiver(post_delete, sender=Country, dispatch_uid='catalog_cache_delete_country')
    @receiver(post_save, sender=Tag, dispatch_uid='catalog_cache_invalidate_tag')
    @receiver(post_delete, sender=Tag, dispatch_uid='catalog_cache_delete_tag')
    def _invalidate_catalog_cache(**_kwargs):
        bump_catalog_cache_version()

    # Episode/season changes are intentionally not wired to the global version:
    # they are absent from list payloads and a subtitle backfill can save dozens
    # per minute. Series detail responses have a short TTL, so accepting at most
    # that bounded staleness avoids turning every public list request into a MISS.

    def _invalidate_m2m(sender, **_kwargs):
        bump_catalog_cache_version()

    for through in (
        Movie.genres.through,
        Movie.directors.through,
        Movie.countries.through,
        Movie.tags.through,
        Series.genres.through,
        Series.directors.through,
        Series.countries.through,
        Series.tags.through,
    ):
        m2m_changed.connect(
            _invalidate_m2m,
            sender=through,
            dispatch_uid=f'catalog_cache_m2m_{through._meta.label_lower}',
        )


def connect_cache_signals() -> None:
    _register_invalidation_signals()
