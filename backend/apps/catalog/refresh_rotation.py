"""Let the provider re-crawl lanes move past titles the provider no longer has.

The movie/series refresh lanes take a fixed-size slice of published titles
each round (oldest-``updated_at`` first for movies, most popular first for
series). A failed crawl changes nothing on the row, so a title that was taken
down from the provider keeps its place at the front of the slice and is tried
— and fails — again every round. On 2026-09-26 the whole 200-movie slice was
such titles: ``tried=200 ok=0 failed=200`` round after round, while every other
published movie waited behind them and never gained its new encodes.

A failure is remembered in the shared cache for a while and the next rounds
skip that title, so the slice fills up with titles that can still gain links.
It is a cache entry, not a column: nothing about the title changes, and when
the entry expires the title is simply tried again (the provider may have
re-listed it, and the heal-by-search path may find a new page).
"""

from __future__ import annotations

import os

from django.core.cache import cache

DEFAULT_FAIL_TTL_SECONDS = 3 * 24 * 3600


def _ttl() -> int:
    try:
        value = int(os.environ.get('MYF2M_REFRESH_FAIL_TTL_SECONDS', DEFAULT_FAIL_TTL_SECONDS))
    except (TypeError, ValueError):
        value = DEFAULT_FAIL_TTL_SECONDS
    return max(0, value)


def _key(kind: str, pk: int) -> str:
    return f'catalog:refresh-failed:{kind}:{int(pk)}'


def recently_failed(kind: str, pks) -> set[int]:
    """The subset of ``pks`` whose last refresh failed within the TTL."""
    pks = [int(pk) for pk in pks]
    if not pks:
        return set()
    try:
        found = cache.get_many([_key(kind, pk) for pk in pks])
    except Exception:
        # A cache outage must never stop the lane; it just loses the rotation.
        return set()
    return {pk for pk in pks if _key(kind, pk) in found}


def remember_failure(kind: str, pk: int, *, ttl: int | None = None) -> None:
    ttl = _ttl() if ttl is None else max(0, int(ttl))
    if not ttl:
        return
    try:
        cache.set(_key(kind, pk), 1, ttl)
    except Exception:
        pass


def forget_failure(kind: str, pk: int) -> None:
    try:
        cache.delete(_key(kind, pk))
    except Exception:
        pass


def is_rotating_failure(exc: BaseException) -> bool:
    """Provider said no for this title. Rate limits are the provider's state, not the title's."""
    from apps.catalog.provider_import.exceptions import ProviderImportError, ProviderRateLimited

    return isinstance(exc, ProviderImportError) and not isinstance(exc, ProviderRateLimited)
