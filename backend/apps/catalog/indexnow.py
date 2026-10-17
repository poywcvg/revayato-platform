"""Tell Bing, Yandex, Seznam and Naver about new and changed title pages at once.

Without this a newly published title waits for the next sitemap crawl, which
for a site of this size is days. IndexNow (https://www.indexnow.org) takes a
list of changed URLs in one POST and shares it between every engine that
supports it. Google does not take part; for Google the sitemap ``lastmod`` is
the signal.

Flow: a published movie/series save queues its URL (at most once per
``INDEXNOW_RESUBMIT_SECONDS`` per title, so crawler churn — sizes, links,
subtitles re-saving the row all day — does not turn into a ping storm); a beat
task sends the queue in one batch. The key proves the site owns the URLs; the
frontend serves it at ``/indexnow-key.txt`` from ``/api/catalog/indexnow-key/``,
so this module is its only source.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse

logger = logging.getLogger(__name__)

ENDPOINT = 'https://api.indexnow.org/indexnow'
PENDING_KEY = 'indexnow:pending'
# IndexNow accepts up to 10,000 URLs per request.
MAX_BATCH = 10_000
PENDING_CAP = 20_000


def enabled() -> bool:
    return bool(
        getattr(settings, 'INDEXNOW_ENABLED', False)
        and getattr(settings, 'INDEXNOW_KEY', '')
        and site_url()
    )


def site_url() -> str:
    return str(getattr(settings, 'SITE_BASE_URL', '') or '').rstrip('/')


def key_location() -> str:
    return f'{site_url()}/indexnow-key.txt'


def title_path(obj) -> str:
    from apps.catalog.models import Series

    return f"/{'series' if isinstance(obj, Series) else 'movies'}/{obj.slug}"


def _seen_key(obj) -> str:
    return f'indexnow:seen:{obj._meta.label_lower}:{obj.pk}'


def queue_title(obj) -> bool:
    """Queue ``obj``'s page if it is published and was not submitted recently."""
    if not enabled() or not getattr(obj, 'is_published', False) or not getattr(obj, 'slug', ''):
        return False
    ttl = int(getattr(settings, 'INDEXNOW_RESUBMIT_SECONDS', 30 * 24 * 60 * 60))
    # A slug change is a new URL: key the dedup on the slug as well.
    if not cache.add(f'{_seen_key(obj)}:{obj.slug}', 1, ttl):
        return False
    return queue_paths([title_path(obj)])


def queue_paths(paths) -> bool:
    paths = [p for p in paths if p]
    if not paths:
        return False
    pending = cache.get(PENDING_KEY) or []
    merged = list(dict.fromkeys([*pending, *paths]))[-PENDING_CAP:]
    cache.set(PENDING_KEY, merged, 7 * 24 * 60 * 60)
    return True


def submit(urls: list[str], *, timeout: float = 20.0) -> dict:
    """POST ``urls`` (absolute) in batches; returns per-batch HTTP statuses."""
    from urllib.parse import urlsplit

    host = urlsplit(site_url()).hostname or ''
    statuses = []
    submitted = 0
    for start in range(0, len(urls), MAX_BATCH):
        batch = urls[start:start + MAX_BATCH]
        response = requests.post(
            ENDPOINT,
            json={
                'host': host,
                'key': settings.INDEXNOW_KEY,
                'keyLocation': key_location(),
                'urlList': batch,
            },
            headers={'Content-Type': 'application/json; charset=utf-8'},
            timeout=timeout,
        )
        statuses.append(response.status_code)
        # 200 OK / 202 Accepted (key validation pending). Anything else — 403
        # key not found, 422 URLs not on host, 429 too many — stops the run so
        # the rest stays queued for the next tick.
        if response.status_code not in (200, 202):
            logger.warning('indexnow: HTTP %s for %d URLs: %s', response.status_code, len(batch), response.text[:200])
            break
        submitted += len(batch)
    return {'submitted': submitted, 'statuses': statuses}


def flush_pending() -> dict:
    """Send everything queued; what a failed batch did not deliver stays queued."""
    if not enabled():
        return {'status': 'disabled'}
    pending = cache.get(PENDING_KEY) or []
    if not pending:
        return {'status': 'empty', 'submitted': 0}
    urls = [f'{site_url()}{path}' for path in pending]
    try:
        result = submit(urls)
    except requests.RequestException as exc:
        logger.warning('indexnow: request failed: %s', exc)
        return {'status': 'error', 'submitted': 0, 'pending': len(pending)}
    done = result['submitted']
    # Paths queued while this ran are appended after the ones just sent.
    sent = set(pending[:done])
    remaining = [p for p in (cache.get(PENDING_KEY) or []) if p not in sent]
    cache.set(PENDING_KEY, remaining, 7 * 24 * 60 * 60)
    return {'status': 'ok' if done == len(urls) else 'partial', **result, 'pending': len(remaining)}


def indexnow_key_file(request):
    """The key text the frontend serves at /indexnow-key.txt."""
    key = getattr(settings, 'INDEXNOW_KEY', '')
    if not key:
        return HttpResponse(status=404)
    response = HttpResponse(key, content_type='text/plain; charset=utf-8')
    response['Cache-Control'] = 'public, max-age=86400'
    return response


def connect_indexnow_signals() -> None:
    from django.db.models.signals import post_save

    from apps.catalog.models import Movie, Series

    for model in (Movie, Series):
        post_save.connect(_on_title_saved, sender=model, dispatch_uid=f'indexnow-on-save-{model.__name__}')


def _on_title_saved(sender, instance, raw=False, **kwargs) -> None:
    if raw:
        return
    try:
        queue_title(instance)
    except Exception:  # a ping is never a reason for a save to fail
        logger.exception('indexnow: queueing failed for %s %s', sender.__name__, instance.pk)
