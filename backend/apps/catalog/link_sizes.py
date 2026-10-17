"""Every download link carries its file size — measured, never guessed.

Viewers pick a quality by its size: «۱۰۸۰p · 2.30 GB» is a decision, «1080p»
alone is a gamble on a phone plan. Only the provider that prints sizes on its
page (and only on the rounds the crawler's size lane reached) ever filled
``size_label``, so on 2026-09-24 about two thirds of all movie links, and some
link on almost every series, showed no size at all.

Three paths close that gap, all writing through :func:`stamp_sizes`:

* **At import.** Every save that leaves a Movie/Series with links nobody has
  sized yet queues :func:`size_title` for that one title, right after commit
  (:func:`queue_title_sizing`, wired as a ``post_save`` receiver so no import
  path — apply, discovery crawlers, refresh, admin — can skip it). This is the
  only moment signed links (``?expires=…``) can still be measured at all.
* :func:`media_verification.verify_target` already asks the server about each
  mirror it tests and gets the byte count for free; it keeps it.
* :func:`fill_missing_sizes` is a bounded sweep for the backlog — this week's
  hot titles and the IMDb Top 250 first, then by popularity — on a wall-clock
  budget, so it never holds a worker longer than one tick.

A host that keeps answering without a usable size (the Iranian CDNs that show
this French datacenter a «فیلترشکن را خاموش کنید» page) is recognised after
:data:`HOST_MIN_TRIES` answers and not asked again for :data:`HOST_WINDOW`:
its links are stamped as asked, never given a made-up size.

A link the server would not size is stamped ``size_probed_at`` and left alone
for :data:`RETRY_AFTER`; nothing here ever removes or rewrites a URL.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models.expressions import RawSQL
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Anything smaller is an error page or a stub, not the film.
MIN_VIDEO_BYTES = 8 * 1024 * 1024
#: How long a link the server refused to size waits before it is asked again.
RETRY_AFTER = timedelta(days=7)

#: Celery queue the per-title runs go to (consumed by catalog-worker-imports).
QUEUE = 'link-sizes'
#: Past this broker depth new per-title runs are dropped; the sweep catches up.
#: A dedup lock cannot bound a queue, only a depth ceiling can.
QUEUE_MAX_DEPTH = 2000
#: A queued run older than this is dropped unrun (the sweep takes over).
MESSAGE_TTL = 6 * 60 * 60
#: A host that answered this many probes in :data:`HOST_WINDOW` without one
#: usable size is not asked again until the window ends.
HOST_MIN_TRIES = 12
HOST_WINDOW = 6 * 60 * 60
#: Probe answers that never reached the host and may differ next time.
_NOT_ASKED = {'host_circuit_open'}
#: Never reached the host, and never will for this URL string: a lapsed token
#: is only fixed by a re-crawl, which stores a new URL. Stamped as asked.
_UNASKABLE = {'signature_expired', 'not_http', 'empty_url'}

#: A link still needs sizing when it has no label and was not asked recently.
UNSIZED_PATH = (
    '$[*] ? ((!(exists(@.size_label)) || @.size_label == "") && '
    '(!(exists(@.size_probed_at)) || @.size_probed_at < $cutoff))'
)


def size_label(size_bytes: int) -> str:
    """Same format as the crawler's own enrichment, so every label reads alike."""
    from apps.catalog.provider_import.providers.myf2m import _file_size_label

    return _file_size_label(size_bytes)


def _has_size(item: dict) -> bool:
    return bool(str(item.get('size_label') or '').strip())


def stamp_sizes(
    obj, measured: dict[str, int], *, attempted: set[str] | None = None, soon: set[str] | None = None,
) -> int:
    """Write measured sizes onto the links of ``obj`` that lack one.

    ``measured`` maps URL → bytes. ``attempted`` names URLs that were asked but
    gave no usable size; they are stamped ``size_probed_at`` so the sweep moves
    on. The row is re-read under a lock: the in-memory copy may be minutes old,
    and saving it back would undo whatever an import wrote meanwhile.

    ``soon`` names URLs that were *not* asked because their host is refusing
    right now (:func:`host_refuses`); they are stamped so they fall due again
    when that host's window ends, not a week later — a block can be temporary.

    ``updated_at`` is deliberately left alone — a size is not news, and bumping
    it would push the title into the «تازه‌ها» feeds.
    """
    attempted = attempted or set()
    soon = soon or set()
    if not measured and not attempted and not soon:
        return 0
    model = type(obj)
    now = timezone.now().isoformat()
    due_soon = (timezone.now() - RETRY_AFTER + timedelta(seconds=HOST_WINDOW)).isoformat()
    with transaction.atomic():
        fresh = model.objects.select_for_update().only('id', 'download_links').get(pk=obj.pk)
        links = [dict(item) if isinstance(item, dict) else item for item in (fresh.download_links or [])]
        stamped = touched = 0
        for item in links:
            if not isinstance(item, dict) or _has_size(item):
                continue
            url = str(item.get('url') or '').strip()
            size = int(measured.get(url) or 0)
            if size >= MIN_VIDEO_BYTES:
                item['size_bytes'] = size
                item['size_label'] = size_label(size)
                item.pop('size_probed_at', None)
                stamped += 1
                touched += 1
            elif url in attempted or url in measured:
                item['size_probed_at'] = now
                touched += 1
            elif url in soon:
                item['size_probed_at'] = due_soon
                touched += 1
        if touched:
            fresh.download_links = links
            fresh.save(update_fields=['download_links'])
            # Keep the caller's copy current, so its own later save cannot
            # quietly drop what was just written.
            obj.download_links = links
    return stamped


def _host(url: str) -> str:
    return (urlsplit(url).hostname or '').lower()


def _host_keys(host: str) -> tuple[str, str]:
    return f'linksize:host:{host}:tries', f'linksize:host:{host}:sized'


def host_refuses(host: str) -> bool:
    """Has ``host`` answered :data:`HOST_MIN_TRIES` probes lately, none sized?"""
    tries_key, sized_key = _host_keys(host)
    got = cache.get_many([tries_key, sized_key])
    return int(got.get(tries_key) or 0) >= HOST_MIN_TRIES and not int(got.get(sized_key) or 0)


def _bump(key: str) -> None:
    if not cache.add(key, 1, HOST_WINDOW):
        try:
            cache.incr(key)
        except ValueError:  # expired between add and incr
            cache.set(key, 1, HOST_WINDOW)


def _note_host(host: str, *, sized: bool) -> None:
    tries_key, sized_key = _host_keys(host)
    _bump(tries_key)
    if sized:
        _bump(sized_key)


def _measure(url: str, deadline: float | None = None) -> int | None:
    """Bytes of the file at ``url``, 0 when the server would not say.

    ``None`` means *not asked* (out of time, lapsed signature, tripped host):
    the link stays pending instead of being stamped as refused.
    """
    from apps.catalog.media_probe import probe_url

    if deadline is not None and time.monotonic() >= deadline:
        return None
    probe = probe_url(url, expect='video')
    if probe.reason in _NOT_ASKED:
        return None
    if probe.reason in _UNASKABLE:
        return 0
    size = int(probe.content_length or 0) if probe.live else 0
    _note_host(_host(url), sized=size >= MIN_VIDEO_BYTES)
    return size


def _unsized(model, cutoff: str):
    table = model._meta.db_table
    return model.objects.filter(
        is_published=True,
        id__in=RawSQL(
            f'SELECT id FROM {table} WHERE jsonb_path_exists('
            'download_links, %s::jsonpath, jsonb_build_object(%s, %s::text))',
            (UNSIZED_PATH, 'cutoff', cutoff),
        ),
    )


def _hot_ids() -> dict:
    """TMDB ids on this week's hot chart, per model; empty when there is none."""
    from apps.catalog.models import Movie, Series

    try:
        from apps.catalog.hot_titles import get_hot_chart

        chart = get_hot_chart() or {}
    except Exception:  # the chart is an ordering hint, never a requirement
        logger.exception('link_sizes: hot chart unavailable')
        return {}
    return {
        model: [row['tmdb_id'] for row in chart.get(kind) or [] if row.get('tmdb_id')]
        for kind, model in (('movie', Movie), ('series', Series))
    }


def _queue(limit: int):
    """Titles to size this tick: hot chart, then Top 250, then the most watched."""
    from apps.catalog.models import Movie, Series

    cutoff = (timezone.now() - RETRY_AFTER).isoformat()
    picked: list = []
    for model, tmdb_ids in _hot_ids().items():
        if tmdb_ids:
            picked.extend(
                _unsized(model, cutoff).filter(tmdb_id__in=tmdb_ids)
                .only('id', 'download_links')[:limit]
            )
    seen = {(type(o), o.pk) for o in picked}
    for model in (Movie, Series):
        picked.extend(
            obj for obj in _unsized(model, cutoff).filter(imdb_rank__isnull=False)
            .order_by('imdb_rank').only('id', 'download_links')[:limit]
            if (type(obj), obj.pk) not in seen
        )
    rest = max(0, limit - len(picked))
    if rest:
        seen = {(type(o), o.pk) for o in picked}
        for model in (Movie, Series):
            for obj in (
                _unsized(model, cutoff).order_by('-popularity', '-id')
                .only('id', 'download_links')[:rest]
            ):
                if (type(obj), obj.pk) not in seen:
                    picked.append(obj)
    return picked[: max(limit, 1)]


def _pending_urls(obj, cutoff: str) -> list[str]:
    urls = []
    for item in obj.download_links or []:
        if not isinstance(item, dict) or _has_size(item):
            continue
        probed = str(item.get('size_probed_at') or '')
        if probed and probed >= cutoff:
            continue
        url = str(item.get('url') or '').strip()
        if url.startswith(('http://', 'https://')):
            urls.append(url)
    return urls


def _size_links(obj, *, cutoff: str, workers: int, deadline: float, max_links: int) -> dict:
    """Measure the pending links of one title and stamp the answers."""
    from apps.catalog.playback_sources import _classify_link

    pending = list(dict.fromkeys(_pending_urls(obj, cutoff)))
    urls = pending[:max_links]
    # Subtitles, trailers and dead hosts have no film size to show; mark them
    # asked so this title stops matching instead of heading the queue forever.
    by_url = {str(i.get('url') or '').strip(): i for i in obj.download_links or [] if isinstance(i, dict)}
    not_video = {u for u in urls if _classify_link(by_url.get(u) or {}, ignore_expiry=True) == 'skip'}
    refusing = {u for u in urls if u not in not_video and host_refuses(_host(u))}
    video = [u for u in urls if u not in not_video and u not in refusing]
    measured: dict[str, int] = {}
    if video:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {pool.submit(_measure, url, deadline): url for url in video}
            for future in as_completed(futures):
                try:
                    size = future.result()
                except Exception:  # a probe never takes the sweep down
                    size = 0
                if size is not None:
                    measured[futures[future]] = size
    stamped = stamp_sizes(obj, measured, attempted=not_video, soon=refusing)
    return {
        'sized': stamped,
        'refused': len(measured) - stamped,
        'host_refuses': len(refusing),
        'not_video': len(not_video),
        'left': len(pending) - len(measured) - len(not_video) - len(refusing),
    }


def size_title(obj, *, workers: int = 6, budget_seconds: float = 240.0, max_links: int = 600) -> dict:
    """Size every link of one title nobody has asked about yet — the import-time path."""
    cutoff = (timezone.now() - RETRY_AFTER).isoformat()
    result = _size_links(
        obj, cutoff=cutoff, workers=workers,
        deadline=time.monotonic() + budget_seconds, max_links=max_links,
    )
    logger.info('link_sizes: %s %s %s', type(obj).__name__, obj.pk, result)
    return result


def _has_unasked(links) -> bool:
    """Cheap in-memory test: a link with no size that was never asked."""
    for item in links or []:
        if (
            isinstance(item, dict) and not _has_size(item) and not item.get('size_probed_at')
            and str(item.get('url') or '').startswith(('http://', 'https://'))
        ):
            return True
    return False


def _queue_depth() -> int:
    try:
        from config.celery import app as celery_app

        with celery_app.connection_or_acquire() as conn:
            return int(conn.default_channel.client.llen(QUEUE))
    except Exception:
        return -1


def queue_title_sizing(obj) -> bool:
    """Queue :func:`size_title` for ``obj`` after commit. True when queued."""
    if not getattr(settings, 'CATALOG_LINK_SIZE_ON_IMPORT', True) or not obj.pk:
        return False
    if not _has_unasked(getattr(obj, 'download_links', None)):
        return False
    label = obj._meta.label_lower
    lock = f'linksize:title:{label}:{obj.pk}'
    # Held until the run ends (released there; it lives as long as the message
    # may wait), so the run's own save and a burst of import saves are one run.
    if not cache.add(lock, 1, MESSAGE_TTL):
        return False

    def _enqueue():
        depth = _queue_depth()
        if depth >= QUEUE_MAX_DEPTH:
            cache.delete(lock)
            logger.info('link_sizes: %s depth %s, %s %s left to the sweep', QUEUE, depth, label, obj.pk)
            return
        try:
            from apps.catalog.tasks import size_title_links_task

            size_title_links_task.apply_async((label, obj.pk), queue=QUEUE, expires=MESSAGE_TTL)
        except Exception:
            cache.delete(lock)
            logger.exception('link_sizes: could not queue %s %s', label, obj.pk)

    transaction.on_commit(_enqueue)
    return True


def run_title_sizing(label: str, pk: int) -> dict:
    """Body of the per-title task; releases the lock and re-queues leftovers."""
    from django.apps import apps as django_apps

    lock = f'linksize:title:{label}:{pk}'
    try:
        model = django_apps.get_model(label)
        obj = model.objects.only('id', 'download_links').filter(pk=pk).first()
        if obj is None:
            return {'missing': True}
        result = size_title(
            obj,
            budget_seconds=float(getattr(settings, 'CATALOG_LINK_SIZE_TITLE_BUDGET_SECONDS', 240)),
        )
    finally:
        cache.delete(lock)
    # Go again when a long series outran this run, or when an import added links
    # while it ran (its own queue attempt met this run's lock). A run that asked
    # nothing (host tripped) stops here: the sweep retries it later.
    if result['left'] == 0 or result['sized'] + result['refused'] > 0:
        fresh = model.objects.only('id', 'download_links').filter(pk=pk).first()
        if fresh is not None:
            queue_title_sizing(fresh)
    return result


def connect_link_size_signals() -> None:
    from django.db.models.signals import post_save

    from apps.catalog.models import Movie, Series

    for model in (Movie, Series):
        post_save.connect(
            _on_title_saved, sender=model, dispatch_uid=f'link-sizes-on-save-{model.__name__}',
        )


def _on_title_saved(sender, instance, update_fields=None, raw=False, **kwargs) -> None:
    if raw or (update_fields is not None and 'download_links' not in update_fields):
        return
    try:
        queue_title_sizing(instance)
    except Exception:  # sizing is never a reason for an import to fail
        logger.exception('link_sizes: queueing failed for %s %s', sender.__name__, instance.pk)


def fill_missing_sizes(
    *, limit: int = 40, workers: int = 4, budget_seconds: float = 150.0,
    max_links_per_title: int = 60,
) -> dict:
    """Measure unsized links of up to ``limit`` titles within ``budget_seconds``."""
    started = time.monotonic()
    deadline = started + budget_seconds
    cutoff = (timezone.now() - RETRY_AFTER).isoformat()
    totals = {'titles': 0, 'sized': 0, 'refused': 0, 'host_refuses': 0, 'not_video': 0}
    for obj in _queue(limit):
        if time.monotonic() >= deadline:
            break
        totals['titles'] += 1
        one = _size_links(
            obj, cutoff=cutoff, workers=workers, deadline=deadline, max_links=max_links_per_title,
        )
        for key in ('sized', 'refused', 'host_refuses', 'not_video'):
            totals[key] += one[key]
    totals['seconds'] = round(time.monotonic() - started, 1)
    logger.info('link_sizes: %s', totals)
    return totals
