"""Shared re-crawl logic for titles whose download/playback links are broken.

Dornatv CDN signatures self-expire (~13 h). Titles whose every download link is
an expired signed URL (or a known-dead host) stop playing in the online player.
This module re-crawls those titles (myf2m + dornatv) to refresh the signatures,
and deletes titles that no provider carries anymore.

It is used by two entry points:

* ``scripts/refresh_expired_playback.py`` — a one-off CLI for full passes.
* ``apps.catalog.tasks.refresh_expired_playback_task`` — a bounded Celery beat
  task that keeps signatures fresh so the player never goes dark again.
"""

from __future__ import annotations

import time
from urllib.parse import urlparse

DEAD_HOSTS = {'cdnhost.lol', 'dlyar.top'}
VIDEO_EXTS = ('.mkv', '.mp4', '.m4v', '.webm', '.m3u8', '.ts', '.avi', '.mov')

# Codes that mean the provider genuinely does not carry the title (safe to delete).
DEFINITIVE_MISS = {
    'page_not_found',
    'myf2m_page_required', 'myf2m_links_empty',
    'dornatv_page_required', 'dornatv_links_empty', 'dornatv_identity_mismatch',
}
# Codes that mean the crawl failed transiently (keep the title for a later pass).
TRANSIENT = {
    'provider_rate_limited', 'provider_captcha_required',
    'interactive_verification_required', 'provider_access_denied',
}


def _expired(url: str) -> bool:
    """Delegates to :func:`media_probe.signature_expired`.

    There was a second, narrower copy of this parse here. Two implementations of
    "is this token lapsed" is one too many when the whole player depends on both
    agreeing: the probe must refuse to judge exactly the links this module is
    meant to re-crawl, or a title is condemned by one and skipped by the other.
    """
    from apps.catalog.media_probe import signature_expired

    return signature_expired(url)


def _dead_host(url: str) -> bool:
    host = (urlparse(url).hostname or '').lower()
    return any(host == d or host.endswith('.' + d) for d in DEAD_HOSTS)


def link_playable(item, *, ignore_expiry: bool = False) -> bool:
    """Can a viewer be handed this link right now?

    ``ignore_expiry=True`` asks the different question the playback gate needs:
    *would* this be a usable source if its token were re-signed. The two must
    not be conflated. Answering the first question for the gate is what took
    4,119 movies off the air: a lapsed link was dropped before ranking, which
    left the title with no candidates at all, and "no candidates" is the
    beginning of the path that blanks a link — for films sitting untouched on
    the origin, needing nothing but a fresh token.
    """
    if not isinstance(item, dict):
        return False
    url = str(item.get('url') or '').strip()
    key = str(item.get('key') or '').strip()
    if not url and not key:
        return False
    if key:
        return True
    if not url.startswith(('http://', 'https://')):
        return True
    if _dead_host(url):
        return False
    if not ignore_expiry and _expired(url):
        return False
    path = url.split('?', 1)[0].lower()
    if path.endswith(VIDEO_EXTS):
        return True
    return True


def has_playable(obj) -> bool:
    links = getattr(obj, 'download_links', None) or []
    return any(link_playable(item) for item in links)


def is_broken(obj) -> bool:
    links = getattr(obj, 'download_links', None) or []
    if not links:
        return False
    return not has_playable(obj)


def _crawl_one(slug: str, obj, *, replace: bool, queue_softsub: bool) -> dict:
    from apps.catalog.models import Movie
    from apps.catalog.provider_import.multi_provider_crawl import (
        _crawl_one_movie,
        _crawl_one_series,
    )

    if isinstance(obj, Movie):
        return _crawl_one_movie(slug, obj, replace=replace, queue_softsub=queue_softsub)
    return _crawl_one_series(slug, obj, replace=replace, queue_softsub=queue_softsub)


def needs_refresh(obj) -> bool:
    """A published title needs a provider pass when links are absent or unusable."""
    links = getattr(obj, 'download_links', None) or []
    return not links or not has_playable(obj)


def collect_broken(
    *, movies: bool = True, series: bool = True, order: str = 'popularity',
) -> list[tuple[str, int, object]]:
    """Return every published title missing usable download/playback links.

    Missing rows are deliberately included: these are the rows that need a final
    provider lookup before they can safely be removed from the public catalog.

    ``order='popularity'`` (default) surfaces the most-watched broken titles
    first, so a bounded refresh batch always heals what viewers actually open
    before the long tail. ``order='id'`` keeps the legacy stable ordering.
    """
    from apps.catalog.models import Movie, Series

    work: list[tuple[str, int, object]] = []
    if movies:
        qs = Movie.objects.filter(is_published=True).only(
            'id', 'title', 'original_title', 'release_year', 'download_links', 'popularity',
        )
        work.extend(('movie', m.id, m) for m in qs.iterator(chunk_size=200) if needs_refresh(m))
    if series:
        qs = Series.objects.filter(is_published=True).only(
            'id', 'title', 'original_title', 'start_year', 'download_links', 'popularity',
        )
        work.extend(('series', s.id, s) for s in qs.iterator(chunk_size=200) if needs_refresh(s))
    if order == 'popularity':
        # Highest popularity first; ties fall back to a stable (type, id) order.
        work.sort(key=lambda row: (
            -float(getattr(row[2], 'popularity', 0) or 0),
            0 if row[0] == 'movie' else 1,
            row[1],
        ))
    else:
        work.sort(key=lambda row: (0 if row[0] == 'movie' else 1, row[1]))
    return work


def refresh_broken_playback(
    *,
    max_batch: int = 0,
    delete: bool = True,
    delay: float = 0.0,
    movies_only: bool = False,
    series_only: bool = False,
    dry_run: bool = False,
    on_progress=None,
) -> dict:
    """Re-crawl broken published titles and delete ones no provider carries.

    ``on_progress`` (optional) is called with ``(index, total, outcome, label)``
    so both the CLI and the Celery task can emit progress without forcing a
    print-based contract.
    """
    from apps.catalog.cache import bump_catalog_cache_version
    from apps.catalog.provider_import.exceptions import ProviderImportError
    from apps.catalog.provider_import.multi_provider_crawl import catalog_link_providers

    providers = catalog_link_providers()
    work = collect_broken(
        movies=not series_only,
        series=not movies_only,
    )
    if max_batch:
        work = work[: max(1, int(max_batch))]

    delay = max(0.0, float(delay or 0))
    stats = {
        'total': len(work), 'refreshed': 0, 'deleted': 0,
        'kept_still_broken': 0, 'failed': 0, 'skipped': 0,
        'providers': providers,
    }

    for index, (content_type, pk, obj) in enumerate(work, 1):
        label = obj.original_title or obj.title
        before = len(obj.download_links or [])
        after = before
        codes = {}
        outcome = 'skipped'
        if dry_run:
            stats['skipped'] += 1
            outcome = 'dry_run'
        else:
            provider_succeeded = False
            for slug in providers:
                try:
                    result = _crawl_one(
                        slug, obj, replace=not provider_succeeded, queue_softsub=False,
                    )
                    codes[slug] = ('ok', int(result.get('imported_count') or 0))
                    provider_succeeded = True
                except ProviderImportError as exc:
                    codes[slug] = ('err', getattr(exc, 'code', '') or 'provider_import_error')
                except Exception as exc:  # noqa: BLE001
                    codes[slug] = ('exc', type(exc).__name__)
                obj.refresh_from_db(fields=['download_links', 'updated_at'])

            after = len(obj.download_links or [])
            still_broken = not has_playable(obj)
            miss_codes = {
                code for (status, code) in codes.values()
                if status == 'err' and code in DEFINITIVE_MISS
            }
            transient = {
                code for (status, code) in codes.values()
                if status in {'err', 'exc'} and code in TRANSIENT
            }
            any_ok = any(status == 'ok' for status, _ in codes.values())

            # Deletion is intentionally strict: every configured provider must
            # return an explicit, definitive miss.  One provider miss alongside
            # an unexpected exception or an empty-but-successful crawl is not
            # enough evidence to destroy catalog metadata.
            all_providers_definitive_miss = bool(providers) and all(
                codes.get(slug, ('missing', ''))[0] == 'err'
                and codes.get(slug, ('missing', ''))[1] in DEFINITIVE_MISS
                for slug in providers
            )
            if not still_broken:
                stats['refreshed'] += 1
                outcome = 'refreshed'
            elif any_ok and not miss_codes and not transient:
                stats['kept_still_broken'] += 1
                outcome = 'keep_no_playable'
            elif all_providers_definitive_miss and not transient and delete:
                obj.delete()
                stats['deleted'] += 1
                outcome = 'deleted'
            else:
                stats['failed'] += 1
                outcome = 'keep_transient'

        if on_progress is not None:
            on_progress(index, len(work), outcome, content_type, pk, label, before, after, codes)

        if delay:
            time.sleep(delay)

    stats['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    if not dry_run and (stats['refreshed'] or stats['deleted']):
        bump_catalog_cache_version()
    return stats
