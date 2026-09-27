"""Every download link carries its file size — measured, never guessed.

Viewers pick a quality by its size: «۱۰۸۰p · 2.30 GB» is a decision, «1080p»
alone is a gamble on a phone plan. Only the provider that prints sizes on its
page (and only on the rounds the crawler's size lane reached) ever filled
``size_label``, so on 2026-09-24 about two thirds of all movie links, and some
link on almost every series, showed no size at all.

Two paths close that gap, both writing through :func:`stamp_sizes`:

* :func:`media_verification.verify_target` already asks the server about each
  mirror it tests and gets the byte count for free; it now keeps it.
* :func:`fill_missing_sizes` is a bounded sweep for everything else — IMDb
  Top 250 first, then by popularity — on a wall-clock budget, so it never
  holds a worker longer than one tick.

A link the server would not size is stamped ``size_probed_at`` and left alone
for :data:`RETRY_AFTER`; nothing here ever removes or rewrites a URL.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

from django.db import transaction
from django.db.models.expressions import RawSQL
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Anything smaller is an error page or a stub, not the film.
MIN_VIDEO_BYTES = 8 * 1024 * 1024
#: How long a link the server refused to size waits before it is asked again.
RETRY_AFTER = timedelta(days=7)

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


def stamp_sizes(obj, measured: dict[str, int], *, attempted: set[str] | None = None) -> int:
    """Write measured sizes onto the links of ``obj`` that lack one.

    ``measured`` maps URL → bytes. ``attempted`` names URLs that were asked but
    gave no usable size; they are stamped ``size_probed_at`` so the sweep moves
    on. The row is re-read under a lock: the in-memory copy may be minutes old,
    and saving it back would undo whatever an import wrote meanwhile.

    ``updated_at`` is deliberately left alone — a size is not news, and bumping
    it would push the title into the «تازه‌ها» feeds.
    """
    attempted = attempted or set()
    if not measured and not attempted:
        return 0
    model = type(obj)
    now = timezone.now().isoformat()
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
        if touched:
            fresh.download_links = links
            fresh.save(update_fields=['download_links'])
            # Keep the caller's copy current, so its own later save cannot
            # quietly drop what was just written.
            obj.download_links = links
    return stamped


def _measure(url: str) -> int:
    from apps.catalog.media_probe import probe_url

    probe = probe_url(url, expect='video')
    return int(probe.content_length or 0) if probe.live else 0


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


def _queue(limit: int):
    """Titles to size this tick: chart titles first, then the most watched."""
    from apps.catalog.models import Movie, Series

    cutoff = (timezone.now() - RETRY_AFTER).isoformat()
    picked: list = []
    for model in (Movie, Series):
        picked.extend(
            _unsized(model, cutoff).filter(imdb_rank__isnull=False)
            .order_by('imdb_rank').only('id', 'download_links')[:limit]
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


def fill_missing_sizes(
    *, limit: int = 40, workers: int = 4, budget_seconds: float = 150.0,
    max_links_per_title: int = 60,
) -> dict:
    """Measure unsized links of up to ``limit`` titles within ``budget_seconds``."""
    from apps.catalog.playback_sources import _classify_link

    started = time.monotonic()
    cutoff = (timezone.now() - RETRY_AFTER).isoformat()
    titles = sized = refused = skipped = 0
    for obj in _queue(limit):
        if time.monotonic() - started >= budget_seconds:
            break
        titles += 1
        urls = _pending_urls(obj, cutoff)[:max_links_per_title]
        # Subtitles, trailers and dead hosts have no film size to show; mark them
        # asked so this title stops matching instead of heading the queue forever.
        by_url = {str(i.get('url') or '').strip(): i for i in obj.download_links or [] if isinstance(i, dict)}
        not_video = {u for u in urls if _classify_link(by_url.get(u) or {}, ignore_expiry=True) == 'skip'}
        video = [u for u in urls if u not in not_video]
        measured: dict[str, int] = {}
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {pool.submit(_measure, url): url for url in video}
            for future in as_completed(futures):
                try:
                    measured[futures[future]] = future.result()
                except Exception:  # a probe never takes the sweep down
                    measured[futures[future]] = 0
        stamped = stamp_sizes(obj, measured, attempted=not_video)
        sized += stamped
        refused += len(video) - stamped
        skipped += len(not_video)
    result = {
        'titles': titles, 'sized': sized, 'refused': refused, 'not_video': skipped,
        'seconds': round(time.monotonic() - started, 1),
    }
    logger.info('link_sizes: %s', result)
    return result
