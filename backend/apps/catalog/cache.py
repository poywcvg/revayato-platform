"""Redis-backed response cache for hot public catalog reads."""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import threading
from typing import Any

from django.core.cache import cache
from django.conf import settings
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

CATALOG_CACHE_VERSION_KEY = 'catalog:cache_version'
CATALOG_CACHE_BUMP_LOCK_KEY = 'catalog:cache_version:bump_lock'
CATALOG_CACHE_NS = 'catalog:resp'

_TTL_DEFAULTS = {
    'list': 180,
    'detail': 300,
    'trending': 120,
    'home': 300,
    'slider': 60,
    'genres': 600,
    'search': 30,
    'actors': 600,
}
_TTL_ENV = {
    'list': 'CATALOG_CACHE_LIST_TTL',
    'detail': 'CATALOG_CACHE_DETAIL_TTL',
    'trending': 'CATALOG_CACHE_TRENDING_TTL',
    'home': 'CATALOG_CACHE_HOME_TTL',
    'slider': 'CATALOG_CACHE_SLIDER_TTL',
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


def _running_tests() -> bool:
    """Django's test runner forces ``DEBUG = False``, so DEBUG alone cannot tell
    a test run from production. Without this check the coalescing window below
    stayed armed under test and publish-then-read assertions saw stale HITs."""
    if os.environ.get('PYTEST_CURRENT_TEST'):
        return True
    return any(arg == 'test' for arg in sys.argv[1:3])


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
    if settings.DEBUG or _running_tests():
        return 0
    return 300


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


def catalog_stale_ttl() -> int:
    """How long the last good payload may be served while a fresh one builds.

    The importer saves titles around the clock, so the global version bumps
    every invalidation window and the versioned keys above almost never HIT:
    menu pages were paying 0.3–1.9 s cold builds on nearly every visit. The
    stale copy keeps navigation at Redis speed; the rebuild happens off the
    request path.
    """
    raw = os.environ.get('CATALOG_CACHE_STALE_TTL', '').strip()
    if raw.isdigit():
        return int(raw)
    if settings.DEBUG or _running_tests():
        return 0
    return 3600


_refresh_slots = threading.BoundedSemaphore(
    max(1, int(os.environ.get('CATALOG_CACHE_REFRESH_THREADS', '3') or 3)),
)


def _run_refresh_sync(job) -> None:
    try:
        job()
    except Exception as exc:
        if getattr(exc, 'status_code', None) == 404 or type(exc).__name__ == 'Http404':
            logger.info('background catalog cache refresh: gone (%s)', exc)
        else:
            logger.exception('background catalog cache refresh failed')


def _run_refresh(job) -> None:
    from django.db import close_old_connections, connections

    try:
        close_old_connections()
        _run_refresh_sync(job)
    finally:
        _refresh_slots.release()
        # The thread's own DB connection goes back (to the pool, when enabled).
        connections.close_all()


def _spawn_refresh(job) -> bool:
    """Run ``job`` in a daemon thread if a refresh slot is free."""
    if not _refresh_slots.acquire(blocking=False):
        return False
    try:
        threading.Thread(target=_run_refresh, args=(job,), name='catalog-cache-refresh', daemon=True).start()
    except Exception:
        _refresh_slots.release()
        raise
    return True


def cached_catalog_payload(namespace: str, request, kind: str, compute, *,
                       allow_stale: bool = True) -> tuple[Any, str]:
    """Return ``(payload, 'HIT' | 'STALE' | 'MISS')`` for a public catalog read.

    Fresh versioned entries are served as before. When the version has moved
    on, the previous payload for the same URL is served at once (``STALE``)
    and a single background rebuild per URL refreshes both copies.

    ``allow_stale=False`` skips the stale copy and builds fresh immediately.
    Reserved for admin-curated payloads (the home slider): the build costs a
    fraction of a second, while serving a stale hero after an explicit editorial
    save reads as "the panel and the site disagree".
    """
    ttl = catalog_cache_ttl(kind)
    if ttl <= 0:
        return compute(), 'MISS'
    version = catalog_cache_version()
    raw = request.META.get('QUERY_STRING', '') or ''
    digest = hashlib.sha256(f'{request.path}?{raw}'.encode()).hexdigest()[:24]
    fresh_key = f'{CATALOG_CACHE_NS}:v{version}:{namespace}:{digest}'
    stale_key = f'{CATALOG_CACHE_NS}:last:{namespace}:{digest}'
    stale_ttl = catalog_stale_ttl() if allow_stale else 0

    cached = cache.get(fresh_key)
    if cached is not None:
        return cached, 'HIT'

    def store(payload):
        cache.set(fresh_key, payload, timeout=ttl)
        if stale_ttl > 0:
            cache.set(stale_key, payload, timeout=max(stale_ttl, ttl))

    if stale_ttl > 0:
        stale = cache.get(stale_key)
        if stale is not None:
            def refresh():
                try:
                    payload = compute()
                except Exception:
                    # A title that was unpublished/deleted 404s here: drop the
                    # old copy so the next request answers from the truth.
                    cache.delete(stale_key)
                    raise
                store(payload)

            lock_key = f'{CATALOG_CACHE_NS}:refreshing:{namespace}:{digest}'
            if cache.add(lock_key, 1, timeout=60) and not _spawn_refresh(refresh):
                # Every refresh slot is busy: let a later request retry.
                cache.delete(lock_key)
            return stale, 'STALE'

    payload = compute()
    store(payload)
    return payload, 'MISS'


def cache_control_for(kind: str = 'list') -> str:
    ttl = catalog_cache_ttl(kind)
    if ttl <= 0:
        return 'private, no-store'
    swr = max(ttl * 3, 180)
    # s-maxage lets Cloudflare/CDN reuse anonymous JSON; browsers still honor max-age.
    return f'public, max-age={ttl}, s-maxage={ttl}, stale-while-revalidate={swr}'


def _register_invalidation_signals() -> None:
    from .models import Actor, Country, Director, Genre, Movie, Series, Tag

    @receiver(post_save, sender=Movie, dispatch_uid='catalog_cache_invalidate_movie', weak=False)
    @receiver(post_delete, sender=Movie, dispatch_uid='catalog_cache_delete_movie', weak=False)
    @receiver(post_save, sender=Series, dispatch_uid='catalog_cache_invalidate_series', weak=False)
    @receiver(post_delete, sender=Series, dispatch_uid='catalog_cache_delete_series', weak=False)
    @receiver(post_save, sender=Genre, dispatch_uid='catalog_cache_invalidate_genre', weak=False)
    @receiver(post_delete, sender=Genre, dispatch_uid='catalog_cache_delete_genre', weak=False)
    @receiver(post_save, sender=Actor, dispatch_uid='catalog_cache_invalidate_actor', weak=False)
    @receiver(post_delete, sender=Actor, dispatch_uid='catalog_cache_delete_actor', weak=False)
    @receiver(post_save, sender=Director, dispatch_uid='catalog_cache_invalidate_director', weak=False)
    @receiver(post_delete, sender=Director, dispatch_uid='catalog_cache_delete_director', weak=False)
    @receiver(post_save, sender=Country, dispatch_uid='catalog_cache_invalidate_country', weak=False)
    @receiver(post_delete, sender=Country, dispatch_uid='catalog_cache_delete_country', weak=False)
    @receiver(post_save, sender=Tag, dispatch_uid='catalog_cache_invalidate_tag', weak=False)
    @receiver(post_delete, sender=Tag, dispatch_uid='catalog_cache_delete_tag', weak=False)
    # ``weak=False`` on every connection above and below is load-bearing: these
    # receivers are closures over this function, so the signal registry's default
    # weak reference is the only one left once it returns. CPython then collects
    # them immediately and every catalog invalidation silently stops firing.
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
            weak=False,
        )


def connect_cache_signals() -> None:
    _register_invalidation_signals()
