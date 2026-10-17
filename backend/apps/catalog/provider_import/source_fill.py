"""Fill the sources a catalog title is missing.

Every title should carry links from every provider that has it (myf2m, dornatv,
kargadan): more qualities, dub/sub versions, and a fallback when one site's CDN
dies or its signed links lapse. The shared multi-provider crawl already merges all
of them, but only ran when a title was first imported or its links went stale. A
title first found on one site therefore stayed on that one site: on 2026-09-28
only 22% of published movies and 5% of series had links from more than one.

This lane walks published titles hot chart → Top 250 → most popular, and for
each one asks only the providers it has no links from, merging (never replacing)
through the same guarded apply path every crawl uses. Each (title, provider)
attempt is remembered, so a provider that does not have a title is asked again
in a week, not every tick. Kargadan is skipped without a request while it has
no signed-in session, and is not remembered then, so the day a cookie is set
every title becomes due for it.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

PROVIDERS = ('myf2m', 'dornatv', 'kargadan')
# Older rows carry no ``source``; their CDN host names the provider instead.
_HOST_HINTS = (('kargadan', 'kargadan'), ('dlyar', 'dornatv'), ('dornatv', 'dornatv'))
ASKED_TTL = 7 * 24 * 60 * 60
ERROR_TTL = 24 * 60 * 60


def link_provider(item: dict) -> str:
    """The provider a stored link came from; ``''`` for a row without a URL."""
    source = str(item.get('source') or '').strip().lower()
    if source in PROVIDERS:
        return source
    host = (urlsplit(str(item.get('url') or '')).hostname or '').lower()
    for needle, provider in _HOST_HINTS:
        if needle in host:
            return provider
    return 'myf2m' if host else ''


def providers_present(links) -> set[str]:
    return {
        link_provider(item) for item in links or []
        if isinstance(item, dict) and item.get('url')
    } - {''}


def _asked_key(label: str, pk: int, provider: str) -> str:
    return f'srcfill:{label}:{pk}:{provider}'


def wanted_providers() -> tuple[list[str], str]:
    """Providers worth asking now, and why Kargadan is left out (``''`` if it is not)."""
    from apps.catalog.provider_import.multi_provider_crawl import catalog_link_providers

    wanted = [slug for slug in catalog_link_providers() if slug in PROVIDERS]
    blocker = ''
    if 'kargadan' in wanted:
        from apps.catalog.provider_import.providers.kargadan import session_blocker

        blocker = session_blocker()
        if blocker:
            wanted.remove('kargadan')
    return wanted, blocker


def missing_for(obj, wanted: list[str]) -> list[str]:
    """Providers ``obj`` has no links from and that were not asked recently."""
    missing = [p for p in wanted if p not in providers_present(obj.download_links)]
    if not missing:
        return []
    label = obj._meta.label_lower
    asked = cache.get_many([_asked_key(label, obj.pk, p) for p in missing])
    return [p for p in missing if _asked_key(label, obj.pk, p) not in asked]


def _remember(obj, providers, ttl: int) -> None:
    label = obj._meta.label_lower
    cache.set_many({_asked_key(label, obj.pk, p): 1 for p in providers}, ttl)


def _candidates(scan_window: int):
    """Published titles in fill order: hot chart, Top 250, then a popularity window.

    The popularity window advances a cursor every tick and wraps at the end, so
    the whole catalog is covered over time without re-reading it every tick.
    """
    from apps.catalog.link_sizes import _hot_ids
    from apps.catalog.models import Movie, Series

    fields = ('id', 'download_links')
    seen: set = set()
    hot = _hot_ids()
    for model in (Movie, Series):
        tmdb_ids = hot.get(model) or []
        if tmdb_ids:
            for obj in model.objects.filter(is_published=True, tmdb_id__in=tmdb_ids).only(*fields):
                seen.add((model, obj.pk))
                yield obj
    for model in (Movie, Series):
        for obj in (
            model.objects.filter(is_published=True, imdb_rank__isnull=False)
            .order_by('imdb_rank').only(*fields)
        ):
            if (model, obj.pk) not in seen:
                seen.add((model, obj.pk))
                yield obj
    for model in (Movie, Series):
        key = f'srcfill:offset:{model._meta.label_lower}'
        offset = int(cache.get(key) or 0)
        rows = list(
            model.objects.filter(is_published=True).order_by('-popularity', '-id')
            .only(*fields)[offset:offset + scan_window]
        )
        cache.set(key, offset + len(rows) if len(rows) == scan_window else 0, None)
        for obj in rows:
            if (model, obj.pk) not in seen:
                yield obj


# Codes that mean "could not ask", not "the provider does not have it".
_TRANSIENT_SUFFIXES = (
    '_http_error', '_crawl_failed', '_bad_json', '_request_failed',
    '_unreachable', '_sitemap_failed', '_sitemap_unparsed', 'unexpected_error',
)


def _verdict_for(exc) -> str:
    code = str(getattr(exc, 'code', '') or '')
    if not code or code.endswith(_TRANSIENT_SUFFIXES):
        return 'error'
    return 'not_found'


def fill_title(obj, providers: list[str]) -> dict:
    """Ask each of ``providers`` for ``obj`` and merge what it has. Per-provider verdicts.

    Each provider goes through the same per-provider crawl the multi-provider
    import uses, always in merge mode, so links already on the title are kept
    and the new ones pass the integrity/dead-link guard before they land.
    """
    from apps.catalog.models import Movie
    from apps.catalog.provider_import.exceptions import ProviderImportError
    from apps.catalog.provider_import.multi_provider_crawl import _crawl_one_movie, _crawl_one_series

    full = type(obj).objects.get(pk=obj.pk)
    crawl = _crawl_one_movie if isinstance(full, Movie) else _crawl_one_series
    verdicts = {}
    for slug in providers:
        try:
            crawl(slug, full, replace=False, queue_softsub=False)
            full.refresh_from_db()
            verdicts[slug] = 'filled'
        except ProviderImportError as exc:
            verdicts[slug] = _verdict_for(exc)
            logger.info('source fill %s %s via %s: %s', full._meta.label_lower, full.pk, slug, exc)
        except Exception:
            verdicts[slug] = 'error'
            logger.exception('source fill %s %s via %s failed', full._meta.label_lower, full.pk, slug)
    _remember(full, [p for p, v in verdicts.items() if v != 'error'], ASKED_TTL)
    _remember(full, [p for p, v in verdicts.items() if v == 'error'], ERROR_TTL)
    if isinstance(full, Movie) and 'filled' in verdicts.values() and not full.subtitle_tracks:
        # New files may carry the Persian soft subs the movie still lacks.
        try:
            from apps.catalog.tasks import enqueue_movie_softsub

            enqueue_movie_softsub(full.pk, force=False)
        except Exception:
            logger.exception('source fill: softsub enqueue failed for movie %s', full.pk)
    return verdicts


def run_source_fill(*, titles: int | None = None, budget_seconds: float | None = None) -> dict:
    """One bounded tick of the fill lane."""
    titles = int(titles if titles is not None else getattr(settings, 'CATALOG_SOURCE_FILL_TITLES_PER_TICK', 25))
    budget = float(
        budget_seconds if budget_seconds is not None
        else getattr(settings, 'CATALOG_SOURCE_FILL_BUDGET_SECONDS', 300)
    )
    scan_window = int(getattr(settings, 'CATALOG_SOURCE_FILL_SCAN_WINDOW', 400))
    started = time.monotonic()
    wanted, kargadan_blocker = wanted_providers()
    stats = {
        'titles': 0, 'scanned': 0, 'complete': 0,
        'filled': Counter(), 'not_found': Counter(), 'errors': Counter(),
        'kargadan': kargadan_blocker or 'ok',
    }
    if not wanted:
        return {**stats, 'status': 'no_providers'}
    status = 'ok'
    for obj in _candidates(scan_window):
        if stats['titles'] >= titles:
            break
        if time.monotonic() - started >= budget:
            status = 'budget'
            break
        stats['scanned'] += 1
        missing = missing_for(obj, wanted)
        if not missing:
            stats['complete'] += 1
            continue
        stats['titles'] += 1
        try:
            verdicts = fill_title(obj, missing)
        except Exception:
            logger.exception('source fill failed for %s %s', obj._meta.label_lower, obj.pk)
            _remember(obj, missing, ERROR_TTL)
            verdicts = {p: 'error' for p in missing}
        for provider, verdict in verdicts.items():
            stats[{'filled': 'filled', 'not_found': 'not_found'}.get(verdict, 'errors')][provider] += 1
    stats.update({k: dict(stats[k]) for k in ('filled', 'not_found', 'errors')})
    return {**stats, 'status': status, 'seconds': round(time.monotonic() - started, 1)}
