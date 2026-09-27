"""Detect and remediate titles that no browser can play in the online player.

Some catalog rows only carry sources that a *browser* ``<video>`` element cannot
decode, even though the file downloads fine:

* progressive **MKV / AVI / WMV** containers — Safari and Firefox have no demuxer
  for them (Chromium usually copes);
* **HEVC / H.265 / x265 / 10-bit** or **AV1** codecs — only Safari (and some
  HW-assisted Chromium builds) can decode HEVC in a page; Firefox/Chrome cannot.

When a title's *only* playable sources are like that, iOS/Safari/Firefox viewers
hit "پخش ویدیو ممکن نشد" (playback not possible) while the download still works.
The web player already prefers a browser-safe mirror *when one exists*; this
module finds the titles where none exists and re-crawls the providers to pull a
browser-safe encode (providers frequently list both an x265 MKV and an x264
MP4/HLS mirror — only some get imported on the first crawl).

The detection heuristics are a faithful Python port of the frontend
``utils/downloadMeta.ts`` container/codec logic, so the crawler flags exactly the
sources the strict (Safari/Firefox) client would reject.

Used by:
* ``apps.catalog.management.commands.crawl_playback_sources`` — the CLI pass.
* ``scripts/run_playback_source_loop.py`` — the permanent throttled crawler.
"""

from __future__ import annotations

import re
import time

from apps.catalog.playback_refresh import link_playable

# `PlaybackSourceGap.reason` marking a draft that has no source at all; owned by
# apps.catalog.draft_sources and excluded from this module's remediation budget.
DRAFT_GAP_REASON = 'no_source'

# Containers no strict browser (Safari/Firefox) will demux progressively.
_BAD_CONTAINER_RE = re.compile(r'\.(mkv|avi|wmv)($|[?#])', re.IGNORECASE)
# Native streaming containers every mainstream browser plays.
_FRIENDLY_CONTAINER_RE = re.compile(r'\.(m3u8|mp4|m4v|webm)($|[?#])', re.IGNORECASE)
# Non-video sidecars that must never count as a playable video source.
_NON_VIDEO_RE = re.compile(
    r'\.(vtt|webvtt|srt|ass|ssa|sub|aac|mka|mp3|wav|flac|jpe?g|png|webp|gif|zip|rar|7z|pdf|txt|html?)$',
    re.IGNORECASE,
)


def codec_family(blob: str) -> str:
    """Codec family read from a URL + quality/label tokens ('' when unknown).

    Mirrors ``videoCodecFamily`` in the frontend: provider filenames embed the
    codec (e.g. ``1080p.x265.10bit``), the only signal available before load.
    """
    text = (blob or '').lower()
    if re.search(r'(dolby[\s._-]*vision|dovi|\bdvhe\b|\bdvh1\b)', text):
        return 'hevc'
    if re.search(r'(\bx265\b|\bh265\b|\bhevc\b|\bhev1\b|\bhvc1\b)', text):
        return 'hevc'
    if re.search(r'(\bav1\b|\bav01\b)', text):
        return 'av1'
    if re.search(r'(\bx264\b|\bh264\b|\bavc1\b|\bavc\b)', text):
        return 'h264'
    # Standalone 10-bit encodes are virtually always HEVC in these providers.
    if re.search(r'\b10bit\b|\b10-bit\b', text):
        return 'hevc'
    return ''


def _classify_link(item, *, ignore_expiry: bool = False) -> str:
    """Classify one download link as ``safe`` / ``unsafe`` / ``skip``.

    * ``safe``   — a strict browser can play it (native container, decodable codec,
      or an ambiguous signed URL we must not false-flag).
    * ``unsafe`` — MKV/AVI/WMV container or HEVC/AV1 codec: no strict browser plays it.
    * ``skip``   — not a live video source (dead/expired host, subtitle/audio/image).

    ``ignore_expiry=True`` judges the *file* and not its access token, which is
    what :mod:`playback_gate` needs: a link whose signature has lapsed is a link
    to re-sign, and it has to survive classification to be re-signed at all.
    """
    if not isinstance(item, dict):
        return 'skip'
    url = str(item.get('url') or '').strip()
    key = str(item.get('key') or '').strip()
    quality = str(item.get('quality') or '')
    label = str(item.get('label') or '')

    # A stored HLS key is our own H.264/HLS transcode — always browser-safe.
    if key and not url:
        return 'safe'
    if not url:
        return 'skip'
    # Reuse the dead-host / expired-signature gate from the broken-link crawler.
    if not link_playable(item, ignore_expiry=ignore_expiry):
        return 'skip'

    path = re.split(r'[?#]', url, maxsplit=1)[0].lower()
    if _NON_VIDEO_RE.search(path):
        return 'skip'

    bad_container = bool(_BAD_CONTAINER_RE.search(url))
    bad_codec = codec_family(f'{url} {quality} {label}') in ('hevc', 'av1')
    if bad_container or bad_codec:
        return 'unsafe'
    return 'safe'


def _video_url_browser_safe(obj) -> bool:
    """A live HLS/MP4 own-stream on the object is a guaranteed browser-safe source.

    ``video_url`` holds an HLS manifest object key, so a non-empty value is a
    browser-safe H.264/HLS stream (only Movie/Episode carry it — Series does not).
    """
    url = str(getattr(obj, 'video_url', '') or '').strip()
    if not url:
        return False
    if not link_playable({'url': url}):
        return False
    if _BAD_CONTAINER_RE.search(url):
        return False
    # An .mp4 container is not enough: imported own-streams sometimes carry an
    # HEVC/x265/10-bit or AV1 encode (e.g. ``…1080p.HEVC.mp4``) that Firefox and
    # Chrome cannot decode. Mirror the frontend and treat those as unplayable so
    # the crawler keeps hunting an H.264/HLS mirror instead of trusting video_url.
    if codec_family(url) in ('hevc', 'av1'):
        return False
    return True


def _series_has_episode_hls(obj) -> bool:
    """True when any published episode of this series has its own HLS stream.

    A Series has no ``video_url`` of its own, but its Episodes do. Such a series
    plays fine in a browser even when every download link is MKV/HEVC, so it must
    never be flagged as unplayable.
    """
    from apps.catalog.models import Series

    if not isinstance(obj, Series):
        return False
    from apps.catalog.models import Episode

    return Episode.objects.filter(
        season__series_id=obj.pk, is_published=True,
    ).exclude(video_url='').exclude(video_url__isnull=True).exists()


def diagnose(obj) -> dict:
    """Return browser-playability facts for a Movie/Series.

    ``unplayable`` is True only when the title has at least one live video source
    and *every* one is MKV/AVI/WMV or HEVC/AV1 (and no browser-safe HLS/MP4 own
    stream exists). Ambiguous signed URLs count as safe, so the crawler never
    re-crawls a title that might already play.
    """
    if _video_url_browser_safe(obj):
        return {'unplayable': False, 'safe': 1, 'unsafe': 0, 'reason': ''}

    links = getattr(obj, 'download_links', None) or []
    safe = unsafe = 0
    containers: set[str] = set()
    codecs: set[str] = set()
    for item in links:
        verdict = _classify_link(item)
        if verdict == 'safe':
            safe += 1
        elif verdict == 'unsafe':
            unsafe += 1
            url = str(item.get('url') or '')
            match = _BAD_CONTAINER_RE.search(url)
            if match:
                containers.add(match.group(1).lower())
            fam = codec_family(f"{url} {item.get('quality') or ''} {item.get('label') or ''}")
            if fam in ('hevc', 'av1'):
                codecs.add(fam)

    unplayable = bool(unsafe) and safe == 0
    if unplayable and _series_has_episode_hls(obj):
        # Episode-level HLS makes the series browser-playable regardless of links.
        return {'unplayable': False, 'safe': 1, 'unsafe': unsafe, 'reason': ''}
    reason = ''
    if unplayable:
        if codecs and containers:
            reason = 'container_and_codec'
        elif codecs:
            reason = f"{'/'.join(sorted(codecs))}_only"
        elif containers:
            reason = f"{'/'.join(sorted(containers))}_only"
        else:
            reason = 'no_browser_safe'
    return {
        'unplayable': unplayable,
        'safe': safe,
        'unsafe': unsafe,
        'reason': reason,
        'containers': sorted(containers),
        'codecs': sorted(codecs),
    }


def browser_unplayable(obj) -> bool:
    """True when no browser can play any of this title's live sources."""
    return diagnose(obj)['unplayable']


def has_any_source(obj) -> bool:
    """True when the title carries *any* video source, playable in a browser or not.

    Distinct from :func:`browser_unplayable`, which asks whether the sources play;
    this asks whether there are any. A draft that answers False here is invisible
    to the whole playback pipeline and belongs to
    :mod:`apps.catalog.draft_sources` instead.
    """
    if str(getattr(obj, 'video_url', '') or '').strip():
        return True
    for item in (getattr(obj, 'download_links', None) or []):
        if not isinstance(item, dict):
            continue
        if str(item.get('url') or '').strip() or str(item.get('key') or '').strip():
            return True
    return _series_has_episode_hls(obj)


def episode_browser_safe(episode) -> bool:
    """True when this *specific* episode has a browser-safe source of its own.

    Series-level :func:`diagnose` deliberately calls a series playable as soon as
    any episode has HLS — right for "is the show broken?", wrong for a viewer who
    reported episode 27 and whose episode is still a bare ``.mkv``. Reports scoped
    to an episode must be judged on the episode's own source.
    """
    return _video_url_browser_safe(episode)


def _content_type_of(obj) -> str:
    from apps.catalog.models import Movie

    return 'movie' if isinstance(obj, Movie) else 'series'


def _recrawl_all_providers(obj) -> dict:
    """Merge every provider encode for ``obj`` so an unimported browser-safe mirror lands.

    Providers commonly list both an x265 MKV and an x264 MP4/HLS mirror; the first
    crawl may only keep one lane. ``replace`` on the first successful provider then
    merge on the rest re-pulls the full set.
    """
    from apps.catalog.playback_refresh import _crawl_one
    from apps.catalog.provider_import.exceptions import ProviderImportError
    from apps.catalog.provider_import.multi_provider_crawl import catalog_link_providers

    # Refresh only the fields this model actually has: a Movie carries its own
    # ``video_url`` (HLS key), a Series does not — its streams live on Episodes —
    # so a hardcoded Movie field list crashes a Series re-crawl with
    # ``Series has no field named 'video_url'``.
    model_fields = {f.name for f in type(obj)._meta.get_fields()}
    refresh_fields = [f for f in ('download_links', 'video_url', 'updated_at') if f in model_fields]

    codes: dict[str, tuple[str, object]] = {}
    provider_succeeded = False
    for slug in catalog_link_providers():
        try:
            result = _crawl_one(slug, obj, replace=not provider_succeeded, queue_softsub=False)
            codes[slug] = ('ok', int(result.get('imported_count') or 0))
            provider_succeeded = True
        except ProviderImportError as exc:
            codes[slug] = ('err', getattr(exc, 'code', '') or 'provider_import_error')
        except Exception as exc:  # noqa: BLE001
            codes[slug] = ('exc', type(exc).__name__)
        obj.refresh_from_db(fields=refresh_fields or None)
    return codes


def upsert_source_gap(obj, diag: dict, *, status: str | None = None, last_result: str = ''):
    """Record (or refresh) a PlaybackSourceGap row for a browser-unplayable title."""
    from django.db import transaction

    from apps.catalog.models import PlaybackSourceGap

    content_type = _content_type_of(obj)
    meta = {
        'containers': diag.get('containers') or [],
        'codecs': diag.get('codecs') or [],
        'unsafe': diag.get('unsafe') or 0,
    }
    defaults = {
        'slug': str(getattr(obj, 'slug', '') or '')[:255],
        'title': str(getattr(obj, 'original_title', '') or getattr(obj, 'title', '') or '')[:300],
        'reason': str(diag.get('reason') or '')[:32],
        'status': status or PlaybackSourceGap.Status.OPEN,
        'last_result': (last_result or '')[:64],
        'meta': meta,
    }
    with transaction.atomic():
        gap, created = PlaybackSourceGap.objects.select_for_update().get_or_create(
            content_type=content_type,
            object_id=obj.pk,
            episode_id=0,
            defaults=defaults,
        )
        if not created:
            gap.report_count = int(gap.report_count or 0) + 1
            gap.slug = defaults['slug'] or gap.slug
            gap.title = defaults['title'] or gap.title
            gap.reason = defaults['reason'] or gap.reason
            gap.meta = meta
            if last_result:
                gap.last_result = defaults['last_result']
            if status:
                gap.status = status
            elif gap.status == PlaybackSourceGap.Status.RESOLVED:
                # Regression: a previously-healed title is browser-unplayable
                # again. This happens when the browser-safe mirror it was resolved
                # with is a short-lived signed CDN URL that has since expired —
                # the gap must not stay RESOLVED (the remediation pass skips those
                # forever), so re-open it and let the crawler pull a fresh mirror.
                gap.status = PlaybackSourceGap.Status.OPEN
                gap.resolved_at = None
                if not last_result:
                    gap.last_result = 'regressed'
            gap.save(update_fields=[
                'report_count', 'slug', 'title', 'reason', 'meta',
                'last_result', 'status', 'resolved_at', 'updated_at',
            ])
    return gap


def resolve_source_gap(obj, *, last_result: str = 'browser_safe') -> int:
    """Close any open source gap once the title has a browser-safe mirror again."""
    from django.utils import timezone

    from apps.catalog.models import PlaybackSourceGap

    return PlaybackSourceGap.objects.filter(
        content_type=_content_type_of(obj),
        object_id=obj.pk,
    ).exclude(status=PlaybackSourceGap.Status.RESOLVED).update(
        status=PlaybackSourceGap.Status.RESOLVED,
        last_result=str(last_result or 'browser_safe')[:64],
        resolved_at=timezone.now(),
        updated_at=timezone.now(),
    )


def remediate(obj, diag: dict | None = None) -> dict:
    """Re-crawl providers for one browser-unplayable title and re-evaluate.

    Returns ``{'outcome', 'codes', 'diag_before', 'diag_after'}`` where outcome is
    one of ``refreshed`` (browser-safe mirror now present), ``unavailable`` (no
    provider carries a browser-safe encode) or ``provider_error`` (crawl failed,
    retry later).

    An Episode is not a valid remediation target: the provider crawl and the
    browser-safe diagnosis operate at the Series level (a series re-crawl re-pulls
    every episode's source), and Episode has no ``download_links`` list. So a call
    made with an Episode is transparently redirected to its parent Series — this is
    what makes episode-level «گزارش خطا» reports remediable instead of crashing on
    ``Episode has no field named 'download_links'``.
    """
    from apps.catalog.models import Episode, PlaybackSourceGap

    if isinstance(obj, Episode):
        obj = obj.season.series

    before = diag or diagnose(obj)
    codes = _recrawl_all_providers(obj)
    after = diagnose(obj)

    any_ok = any(status == 'ok' for status, _ in codes.values())
    if not after['unplayable']:
        resolve_source_gap(obj, last_result='browser_safe')
        outcome = 'refreshed'
    elif any_ok:
        # Providers answered but still no browser-safe encode exists upstream.
        upsert_source_gap(
            obj, after,
            status=PlaybackSourceGap.Status.UNAVAILABLE,
            last_result='no_browser_safe_upstream',
        )
        outcome = 'unavailable'
    else:
        # Every provider failed transiently — keep the gap open for a later pass.
        upsert_source_gap(
            obj, after,
            status=PlaybackSourceGap.Status.QUEUED,
            last_result='provider_error',
        )
        outcome = 'provider_error'
    return {'outcome': outcome, 'codes': codes, 'diag_before': before, 'diag_after': after}


def _iter_published(order: str, *, movies: bool, series: bool):
    """Yield published Movie/Series rows in the requested order."""
    from apps.catalog.models import Movie, Series

    def _ordered(qs):
        if order == 'random':
            return qs.order_by('?')
        if order == 'stale':
            return qs.order_by('updated_at', 'id')
        if order == 'hot':
            from apps.catalog.hot_titles import hot_order

            return hot_order(qs)
        return qs.order_by('-popularity', '-updated_at', '-id')

    if movies:
        qs = _ordered(Movie.objects.filter(is_published=True).only(
            'id', 'slug', 'title', 'original_title', 'download_links', 'video_url', 'popularity', 'updated_at',
        ))
        yield from qs.iterator(chunk_size=100)
    if series:
        qs = _ordered(Series.objects.filter(is_published=True).only(
            'id', 'slug', 'title', 'original_title', 'download_links', 'popularity', 'updated_at',
        ))
        yield from qs.iterator(chunk_size=100)


def scan(
    *,
    order: str = 'popularity',
    scan_limit: int = 0,
    movies: bool = True,
    series: bool = True,
    record: bool = True,
) -> dict:
    """Examine published titles; record open gaps for browser-unplayable ones.

    Also self-heals: a title that has regained a browser-safe mirror (e.g. the
    catalog crawler added an MP4) gets its open gap resolved.
    """
    stats = {'scanned': 0, 'unplayable': 0, 'recorded': 0, 'self_healed': 0}
    for obj in _iter_published(order, movies=movies, series=series):
        if scan_limit and stats['scanned'] >= scan_limit:
            break
        stats['scanned'] += 1
        diag = diagnose(obj)
        if diag['unplayable']:
            stats['unplayable'] += 1
            if record:
                upsert_source_gap(obj, diag)
                stats['recorded'] += 1
        elif record and has_any_source(obj):
            # `has_any_source` guard: a linkless title is not "playable again", it
            # has nothing to play. Resolving it here would silently retire the
            # `no_source` row that apps.catalog.draft_sources owns.
            if resolve_source_gap(obj, last_result='self_healed'):
                stats['self_healed'] += 1
    return stats


def remediate_open_gaps(
    *,
    fix_limit: int = 20,
    retry_unavailable_hours: float = 72.0,
    delay: float = 0.0,
    dry_run: bool = False,
    on_progress=None,
) -> dict:
    """Re-crawl providers for recorded gaps to pull a browser-safe mirror.

    Prioritises never-remediated (``open``) rows, then the least-recently-touched
    queued rows, and retries ``unavailable`` rows only after
    ``retry_unavailable_hours`` (a provider may add a mirror later). ``resolved``
    rows are skipped.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.catalog.models import Movie, PlaybackSourceGap, Series

    cutoff = timezone.now() - timedelta(hours=max(0.0, float(retry_unavailable_hours)))
    rows = list(
        PlaybackSourceGap.objects.filter(episode_id=0)
        .exclude(status=PlaybackSourceGap.Status.RESOLVED)
        # `no_source` rows are unpublished drafts with no source at all; they have
        # their own budget in apps.catalog.draft_sources so that a viewer hitting
        # "پخش ویدیو ممکن نشد" right now never queues behind the back archive.
        .exclude(reason=DRAFT_GAP_REASON)
        .filter(
            models_q_open_or_retryable(cutoff)
        )
        .order_by('status', 'updated_at', 'id')[: max(1, int(fix_limit or 1))]
    )

    stats = {
        'candidates': len(rows), 'refreshed': 0, 'unavailable': 0,
        'provider_error': 0, 'vanished': 0, 'skipped': 0,
    }
    delay = max(0.0, float(delay or 0))

    for index, gap in enumerate(rows, 1):
        model = Movie if gap.content_type == PlaybackSourceGap.ContentType.MOVIE else Series
        obj = model.objects.filter(pk=gap.object_id, is_published=True).first()
        if obj is None:
            # Title unpublished/deleted since detection — retire the stale gap.
            gap.status = PlaybackSourceGap.Status.RESOLVED
            gap.last_result = 'title_gone'
            gap.resolved_at = timezone.now()
            gap.save(update_fields=['status', 'last_result', 'resolved_at', 'updated_at'])
            stats['vanished'] += 1
            outcome = 'vanished'
        elif not browser_unplayable(obj):
            resolve_source_gap(obj, last_result='self_healed')
            stats['skipped'] += 1
            outcome = 'already_playable'
        elif dry_run:
            stats['skipped'] += 1
            outcome = 'dry_run'
        else:
            result = remediate(obj)
            outcome = result['outcome']
            if outcome == 'refreshed':
                stats['refreshed'] += 1
            elif outcome == 'unavailable':
                stats['unavailable'] += 1
            else:
                stats['provider_error'] += 1

        if on_progress is not None:
            on_progress(index, len(rows), outcome, gap)
        if delay:
            time.sleep(delay)

    stats['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    if not dry_run and stats['refreshed']:
        from apps.catalog.cache import bump_catalog_cache_version

        bump_catalog_cache_version()
    return stats


def models_q_open_or_retryable(cutoff):
    """Q filter: open/queued gaps, plus unavailable gaps last touched before cutoff."""
    from django.db.models import Q

    from apps.catalog.models import PlaybackSourceGap

    return (
        Q(status__in=[PlaybackSourceGap.Status.OPEN, PlaybackSourceGap.Status.QUEUED])
        | Q(status=PlaybackSourceGap.Status.UNAVAILABLE, updated_at__lt=cutoff)
    )
