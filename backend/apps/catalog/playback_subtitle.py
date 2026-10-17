"""Urgent SoftSub / SubtitleStar ensure for online playback gaps."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any
from urllib.parse import urlsplit

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.catalog.slugs import canonical_slug

logger = logging.getLogger(__name__)


def _safe_source_path(url: str) -> str:
    try:
        return urlsplit(str(url or '')).path[:1000]
    except ValueError:
        return ''


def _has_tracks(tracks) -> bool:
    return any(
        isinstance(item, dict) and (item.get('src') or item.get('key'))
        for item in (tracks or [])
    )


def _clear_subtitlestar_miss_for_movie(movie) -> None:
    from apps.catalog.subtitle_star import normalize_imdb_id, resolve_subtitlestar_search_title

    imdb_id = normalize_imdb_id(getattr(movie, 'imdb_id', ''))
    year = getattr(movie, 'release_year', None)
    links = [item for item in (getattr(movie, 'download_links', None) or []) if isinstance(item, dict)]
    video_urls = [str(item.get('url') or '') for item in links if item.get('url')]
    title, _fa = resolve_subtitlestar_search_title(
        original_title=str(getattr(movie, 'original_title', '') or ''),
        display_title=str(getattr(movie, 'title', '') or ''),
        video_urls=video_urls,
    )
    identity = imdb_id or hashlib.sha256(f'{title}|{year}'.encode()).hexdigest()[:24]
    cache.delete(f'catalog:subtitlestar:miss:{identity}')
    # Legacy miss keys from older title-resolution bugs (e.g. Dreams: Sueños).
    if imdb_id:
        cache.delete(f'catalog:subtitlestar:miss:{imdb_id}')


def _clear_subtitlestar_miss_for_series(series) -> None:
    from apps.catalog.subtitle_star import normalize_imdb_id

    imdb_id = normalize_imdb_id(getattr(series, 'imdb_id', ''))
    title = str(getattr(series, 'original_title', '') or getattr(series, 'title', '') or '').strip()
    year = getattr(series, 'start_year', None)
    identity = imdb_id or hashlib.sha256(f'{title}|{year}'.encode()).hexdigest()[:24]
    cache.delete(f'catalog:subtitlestar:series-miss:{identity}')
    cache.delete(f'catalog:subtitlestar:miss:{identity}')


def _upsert_gap(
    *,
    content_type: str,
    object_id: int,
    episode_id: int = 0,
    slug: str = '',
    title: str = '',
    playback_version: str = '',
    meta: dict | None = None,
):
    from apps.catalog.models import PlaybackSubtitleGap

    defaults = {
        'slug': (slug or '')[:255],
        'title': (title or '')[:300],
        'playback_version': (playback_version or '')[:32],
        'status': PlaybackSubtitleGap.Status.OPEN,
        'meta': meta or {},
    }
    with transaction.atomic():
        gap, created = PlaybackSubtitleGap.objects.select_for_update().get_or_create(
            content_type=content_type,
            object_id=object_id,
            episode_id=int(episode_id or 0),
            defaults=defaults,
        )
        if not created:
            gap.report_count = int(gap.report_count or 0) + 1
            gap.slug = defaults['slug'] or gap.slug
            gap.title = defaults['title'] or gap.title
            gap.playback_version = defaults['playback_version'] or gap.playback_version
            if meta:
                merged = dict(gap.meta or {})
                merged.update(meta)
                gap.meta = merged
            if gap.status == PlaybackSubtitleGap.Status.RESOLVED:
                gap.status = PlaybackSubtitleGap.Status.OPEN
                gap.resolved_at = None
            gap.save(update_fields=[
                'report_count', 'slug', 'title', 'playback_version', 'meta',
                'status', 'resolved_at', 'updated_at',
            ])
    return gap


def _mark_gap(gap, *, status: str, last_result: str) -> None:
    from apps.catalog.models import PlaybackSubtitleGap

    gap.status = status
    gap.last_result = (last_result or '')[:64]
    fields = ['status', 'last_result', 'updated_at']
    if status == PlaybackSubtitleGap.Status.RESOLVED:
        gap.resolved_at = timezone.now()
        fields.append('resolved_at')
    gap.save(update_fields=fields)


def resolve_playback_subtitle_gaps(
    *,
    content_type: str,
    object_id: int,
    episode_ids: list[int] | None = None,
    last_result: str = 'ready',
) -> int:
    """Close reports after a background import has persisted playable tracks."""
    from apps.catalog.models import PlaybackSubtitleGap

    rows = PlaybackSubtitleGap.objects.filter(
        content_type=str(content_type or ''),
        object_id=int(object_id),
    ).exclude(status=PlaybackSubtitleGap.Status.RESOLVED)
    if episode_ids is not None:
        rows = rows.filter(episode_id__in=[int(value) for value in episode_ids])
    return rows.update(
        status=PlaybackSubtitleGap.Status.RESOLVED,
        last_result=str(last_result or 'ready')[:64],
        resolved_at=timezone.now(),
        updated_at=timezone.now(),
    )


EXHAUSTED_RESULT = 'exhausted'


def mark_playback_subtitle_gaps_exhausted(
    *,
    content_type: str,
    object_id: int,
    episode_ids: list[int] | None = None,
    reason: str = '',
) -> int:
    """Record that a complete worker pass found no Persian subtitle for these gaps.

    Stored as UNAVAILABLE + ``last_result='exhausted'`` with the time and the
    source file that was searched, so a later report for a different file (a new
    encode or mirror) is not blocked by this verdict.
    """
    from apps.catalog.models import PlaybackSubtitleGap

    rows = PlaybackSubtitleGap.objects.filter(
        content_type=str(content_type or ''),
        object_id=int(object_id),
    ).exclude(status=PlaybackSubtitleGap.Status.RESOLVED)
    if episode_ids is not None:
        rows = rows.filter(episode_id__in=[int(value) for value in episode_ids])
    now = timezone.now()
    marked = 0
    for gap in rows:
        meta = dict(gap.meta or {})
        meta['exhausted_at'] = now.isoformat()
        meta['exhausted_source_path'] = str(meta.get('source_path') or '')
        meta['exhausted_count'] = int(meta.get('exhausted_count') or 0) + 1
        meta['exhausted_reason'] = str(reason or '')[:32]
        # A real verdict resets the outage budget for the next (cooldown) round.
        meta.pop('deferred_count', None)
        gap.meta = meta
        gap.status = PlaybackSubtitleGap.Status.UNAVAILABLE
        gap.last_result = EXHAUSTED_RESULT
        gap.save(update_fields=['meta', 'status', 'last_result', 'updated_at'])
        marked += 1
    return marked


PROVIDER_UNAVAILABLE = 'provider_unavailable'


def defer_playback_subtitle_gaps(
    *,
    content_type: str,
    object_id: int,
    episode_ids: list[int] | None = None,
    providers: set[str] | frozenset[str] | tuple = (),
) -> int:
    """An empty pass while a provider could not answer: retry, never "exhausted".

    The gap stays QUEUED with ``last_result='provider_unavailable'`` so the beat
    drain re-runs it once the provider is back. Deferrals are bounded per gap
    (``PLAYBACK_SUBTITLE_MAX_DEFERRALS``): a provider that never recovers ends in
    the ordinary exhausted verdict instead of an endless loop.
    """
    from django.conf import settings
    from apps.catalog.models import PlaybackSubtitleGap

    rows = PlaybackSubtitleGap.objects.filter(
        content_type=str(content_type or ''),
        object_id=int(object_id),
    ).exclude(status=PlaybackSubtitleGap.Status.RESOLVED)
    if episode_ids is not None:
        rows = rows.filter(episode_id__in=[int(value) for value in episode_ids])
    cap = max(1, int(getattr(settings, 'PLAYBACK_SUBTITLE_MAX_DEFERRALS', 8)))
    now = timezone.now()
    deferred = 0
    for gap in rows:
        meta = dict(gap.meta or {})
        count = int(meta.get('deferred_count') or 0) + 1
        if count > cap:
            mark_playback_subtitle_gaps_exhausted(
                content_type=gap.content_type,
                object_id=gap.object_id,
                episode_ids=[int(gap.episode_id or 0)],
                reason='providers_down',
            )
            continue
        meta['deferred_count'] = count
        meta['deferred_at'] = now.isoformat()
        meta['deferred_providers'] = sorted(str(name) for name in providers)[:6]
        gap.meta = meta
        gap.status = PlaybackSubtitleGap.Status.QUEUED
        gap.last_result = PROVIDER_UNAVAILABLE
        gap.save(update_fields=['meta', 'status', 'last_result', 'updated_at'])
        deferred += 1
    return deferred


def settle_empty_playback_gaps(
    *,
    content_type: str,
    object_id: int,
    episode_ids: list[int] | None = None,
    outages: set[str] | frozenset[str] | tuple = (),
) -> dict[str, int]:
    """The one place a worker pass that found nothing records its verdict.

    ``exhausted`` is a claim that the subtitle does not exist; it is only true
    when every provider actually answered. Any outage during the pass defers.
    """
    if outages:
        return {
            'deferred': defer_playback_subtitle_gaps(
                content_type=content_type,
                object_id=object_id,
                episode_ids=episode_ids,
                providers=outages,
            ),
            'exhausted': 0,
        }
    return {
        'deferred': 0,
        'exhausted': mark_playback_subtitle_gaps_exhausted(
            content_type=content_type,
            object_id=object_id,
            episode_ids=episode_ids,
        ),
    }


def gap_is_exhausted(gap) -> bool:
    """True while an exhausted verdict still applies to this gap's current source."""
    from datetime import datetime

    from django.conf import settings
    from apps.catalog.models import PlaybackSubtitleGap

    if gap is None or gap.status != PlaybackSubtitleGap.Status.UNAVAILABLE:
        return False
    if gap.last_result != EXHAUSTED_RESULT:
        return False
    meta = gap.meta or {}
    try:
        exhausted_at = datetime.fromisoformat(str(meta.get('exhausted_at') or ''))
    except ValueError:
        return False
    if timezone.is_naive(exhausted_at):
        exhausted_at = timezone.make_aware(exhausted_at)
    cooldown = int(getattr(settings, 'PLAYBACK_SUBTITLE_EXHAUSTED_COOLDOWN_SECONDS', 6 * 60 * 60))
    if meta.get('exhausted_reason') == BURNED_IN_ONLY:
        # Only a new file (different source_path, checked below) can change this.
        cooldown = max(cooldown, 7 * 24 * 60 * 60)
    if (timezone.now() - exhausted_at).total_seconds() >= cooldown:
        return False
    searched = str(meta.get('exhausted_source_path') or '')
    current = str(meta.get('source_path') or '')
    return not (searched and current and searched != current)


def _exhausted_payload(gap, *, episode_id: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'status': EXHAUSTED_RESULT,
        'reported': True,
        'queued': False,
        'has_subtitle_tracks': False,
        'report_id': gap.pk,
        'message': 'no_subtitle_found',
    }
    if episode_id is not None:
        payload['episode_id'] = episode_id or None
    return payload


NOT_NEEDED_RESULT = 'not_needed'
_PERSIAN_LANGUAGE_CODES = {'fa', 'fas', 'per', 'persian', 'farsi'}


def playback_subtitle_not_needed(
    obj,
    *,
    version: str = '',
    active_link: dict | None = None,
    preferred_source_url: str = '',
) -> str:
    """Why this playback needs no Persian sidecar, or ``''`` when it does.

    A dubbed stream carries Persian in the audio and a Persian-language title
    is already Persian, so neither is a gap: registering one only puts the
    title on the urgent crawler lane every time someone presses play.
    HardSub is deliberately *not* here — providers mislabel encodes often
    enough that burned-in Persian cannot be trusted before the worker has
    probed the file (see ``title_is_burned_in_only``).
    """
    from apps.catalog.subtitle_extract import looks_like_dub_link, url_implies_dub

    if str(version or '').strip().lower() in {'dub', 'dubbed'}:
        return 'dubbed_stream'
    if active_link is not None:
        if looks_like_dub_link(active_link):
            return 'dubbed_stream'
    elif preferred_source_url and url_implies_dub({'url': preferred_source_url}):
        return 'dubbed_stream'
    language = str(getattr(obj, 'original_language', '') or '').strip().lower()
    if language in _PERSIAN_LANGUAGE_CODES:
        return 'persian_original'
    return ''


BURNED_IN_ONLY = 'burned_in_only'


def title_is_burned_in_only(obj) -> bool:
    """Every stream's CDN file name says Dubbed or HardSub (Çukur: 490 Dubbed +
    262 HardSub files, nothing else). No subtitle-less stream exists for a
    sidecar to bind to, and one drawn over burned-in Persian doubles the text.
    File names only — provider labels are too often wrong to trust here.
    """
    from apps.catalog.subtitle_extract import url_implies_dub, url_implies_hardsub

    links = [
        row for row in (getattr(obj, 'download_links', None) or [])
        if isinstance(row, dict) and str(row.get('url') or '').startswith(('https://', 'http://'))
    ]
    return bool(links) and all(url_implies_dub(row) or url_implies_hardsub(row) for row in links)


def _not_needed_payload(reason: str, *, episode_id: int | None = None) -> dict[str, Any]:
    payload = {
        'status': NOT_NEEDED_RESULT,
        'reported': False,
        'queued': False,
        'has_subtitle_tracks': False,
        'reason': reason,
        'message': NOT_NEEDED_RESULT,
    }
    if episode_id:
        payload['episode_id'] = episode_id
    return payload


def _sync_budget(timeout_seconds: int) -> int:
    """Wall-clock cap for the in-request sidecar lookup.

    Provider sidecars are a best-effort acceleration for the open player; the
    worker performs the full embedded-demux → SubtitleStar → Subzone pipeline
    with a real time budget. Keeping this small guarantees the ensure endpoint
    returns quickly instead of stalling the player request for 10+ seconds.
    """
    from django.conf import settings

    cap = max(1, int(getattr(settings, 'PLAYBACK_SYNC_ATTACH_SECONDS', 4)))
    return min(cap, max(1, int(timeout_seconds or cap)))


def _sync_embedded_budget() -> int:
    """Wall-clock cap for the file-first embedded attempt in the sync lane.

    ``0`` disables the file-first attempt (providers only, the old
    behaviour). Kept small: the worker owns the thorough multi-minute demux,
    this is only the quick win when the playing file carries Persian cues.
    """
    from django.conf import settings

    try:
        return max(0, int(getattr(settings, 'PLAYBACK_SYNC_EMBEDDED_SECONDS', 4)))
    except (TypeError, ValueError):
        return 4


def _attach_providers_sync_movie(movie, *, timeout_seconds: int, preferred_source_url: str = '') -> bool:
    """SubtitleStar → SubDL → Subzone sidecar attach for the movie the player is open on.

    Deliberately avoids ``attach_extracted_subtitle``: ffmpeg demux belongs on the
    Celery worker, not on the player request thread. The open player gets cues in
    seconds even when an embedded extraction is still queued. One deadline is
    shared, so a provider that fails fast (open circuit, no key) hands its time
    to the next instead of burning a fixed slice.
    """
    from apps.catalog.subtitle_extract import (
        _attach_subdl_subtitle,
        _attach_subtitlestar_subtitle,
        _attach_subzone_subtitle,
    )

    links = [item for item in (movie.download_links or []) if isinstance(item, dict)]
    budget = max(1, int(timeout_seconds or 4))
    deadline = time.monotonic() + budget
    chain = (
        (_attach_subtitlestar_subtitle, max(1, budget * 2 // 3)),
        (_attach_subdl_subtitle, budget),
        (_attach_subzone_subtitle, budget),
    )
    for attach, cap in chain:
        left = int(deadline - time.monotonic())
        if left < 1:
            return False
        if attach(movie, links, timeout_seconds=min(cap, left), preferred_source_url=preferred_source_url):
            return True
    return False


def _attach_open_episode_subtitlestar(series, episode, *, timeout_seconds: int, preferred_source_url: str = '') -> bool:
    """SubtitleStar → SubDL → Subzone lookup scoped to the episode open in the player."""
    from apps.catalog.subtitle_contract import normalize_subtitle_tracks
    from apps.catalog.subtitle_extract import (
        _episode_video_map,
        _fps_prealigned_payload,
        _is_usable_persian_webvtt,
        _links_for_episode,
        _measured_runtime,
        _non_conflicting_release_sources,
        _store_webvtt,
        _strict_release_sources,
        _track_payload,
        _with_preferred_source,
        ensure_episodes_from_download_links,
        looks_like_dub_link,
        normalize_subtitle_payload,
    )
    from apps.catalog.subdl import find_series_episode_subtitles as find_subdl_episode_subtitles
    from apps.catalog.subtitle_star import find_series_episode_subtitles
    from apps.catalog.subzone import find_series_episode_subtitles as find_subzone_episode_subtitles

    links = [item for item in (series.download_links or []) if isinstance(item, dict)]
    if links:
        ensure_episodes_from_download_links(series)
        episode.refresh_from_db(fields=['subtitle_tracks', 'video_url'])

    if _has_tracks(getattr(episode, 'subtitle_tracks', None)):
        return True

    season_no = int(getattr(episode.season, 'season_number', 1) or 1)
    ep_no = int(episode.episode_number or 0)
    scoped = _links_for_episode(links, season_no, ep_no)
    videos = _episode_video_map(series, scoped or links)
    key = (season_no, ep_no)
    if key not in videos:
        videos = _episode_video_map(series, links)
    if key not in videos:
        url = str(getattr(episode, 'video_url', '') or '').strip()
        if url.startswith(('http://', 'https://')):
            videos[key] = [url]
    if key not in videos:
        return False

    budget = max(1, int(timeout_seconds or 4))
    deadline = time.monotonic() + budget
    chain = (
        ('subtitlestar', find_series_episode_subtitles, max(1, budget * 2 // 3)),
        ('subdl', find_subdl_episode_subtitles, budget),
        ('subzone', find_subzone_episode_subtitles, budget),
    )
    match = None
    payload = b''
    provider = ''
    for provider, finder, cap in chain:
        left = int(deadline - time.monotonic())
        if left < 1:
            return False
        matches = finder(
            series,
            episode_videos={key: videos[key]},
            timeout_seconds=min(cap, left),
        ) or []
        # Accuracy guard: only bind cues that provably belong to this exact
        # season/episode. A "closest" match would play with the wrong timing,
        # which is worse than a short wait — the worker lane re-probes with
        # release matching and the beat drain guarantees an eventual retry.
        match = next(
            (
                row for row in matches
                if int(row.season_number) == season_no and int(row.episode_number) == ep_no
            ),
            None,
        )
        if match is None:
            continue
        payload = normalize_subtitle_payload(match.payload, filename=match.filename)
        if _is_usable_persian_webvtt(payload):
            break
        match = None
    if match is None:
        return False
    # Same FPS pre-alignment the worker lane applies (23.976 ↔ 25 releases),
    # timed against the viewer's own stream when we know it.
    episode_urls = videos.get(key, [])
    payload = _fps_prealigned_payload(
        payload,
        subtitle_release=match.release_name,
        video_reference=(preferred_source_url or (episode_urls[0] if episode_urls else '')),
    )

    filename = f'series-{series.pk}-s{season_no}e{ep_no}-fa-{provider}.vtt'
    saved = _store_webvtt(
        payload, filename=filename,
        duration=_measured_runtime(series, episode=episode),
    )
    if not saved:
        return False
    bound_sources = _strict_release_sources(match.release_name, (
        url for url in match.source_urls
        if url and not looks_like_dub_link({'url': url, 'label': url})
    ))[:12]
    sync_confidence = 'release-match'
    if not bound_sources:
        bound_sources = _non_conflicting_release_sources(match.release_name, [
            url for url in episode_urls
            if url and not looks_like_dub_link({'url': url, 'label': url})
        ])[:1]
        sync_confidence = 'title-fallback'
    if not bound_sources:
        # Last resort: bind the first playable URL so a found Persian release
        # is not lost over strict source/FPS evidence.
        bound_sources = [
            url for url in [*match.source_urls, *episode_urls]
            if url and not looks_like_dub_link({'url': url, 'label': url})
        ][:1]
        sync_confidence = 'title-fallback'
    if not bound_sources:
        return False
    # Bind the exact URL being played first so the player pairs cues to the
    # active stream (highest sync confidence) instead of a ranked mirror.
    bound_sources = _with_preferred_source(bound_sources, preferred_source_url)

    tracks = []
    for index, source_url in enumerate(bound_sources, start=1):
        track = _track_payload(
            saved,
            source_url,
            track_id=f'fa-{provider}-s{season_no}e{ep_no}-{index}',
            source_priority=2 if provider == 'subtitlestar' else 3,
            sync_confidence=sync_confidence,
        )
        track.update({
            'provider': provider,
            'provider_page': match.page_url[:1000],
            'release': match.release_name[:300],
            'imdb_id': match.imdb_id,
            'season_number': season_no,
            'episode_number': ep_no,
        })
        tracks.append(track)

    episode.subtitle_tracks = normalize_subtitle_tracks(tracks)
    episode.save(update_fields=['subtitle_tracks', 'updated_at'])
    try:
        from apps.catalog.cache import bump_catalog_cache_version
        bump_catalog_cache_version()
    except Exception:
        pass
    return True


def ensure_playback_subtitles(**kwargs) -> dict[str, Any]:
    """Viewer-facing entry: provider calls here spend the *live* quota lane.

    See :func:`_ensure_playback_subtitles` for the behaviour.
    """
    from apps.catalog.subtitle_provider_health import LIVE, subtitle_lane

    with subtitle_lane(LIVE):
        return _ensure_playback_subtitles(**kwargs)


def _ensure_playback_subtitles(
    *,
    content_type: str,
    slug: str,
    episode_id: int | None = None,
    playback_version: str = '',
    playback_source_url: str = '',
    sync: bool = True,
    timeout_seconds: int = 28,
) -> dict[str, Any]:
    """Auto-report a SoftSub gap and urgently attach cues for the open player.

    Priority:
      1. Queue urgent embedded extraction from the exact playback file
      2. SubtitleStar release/IMDb match when no embedded track is available
      3. SubDL exact IMDb/TMDb-id API lookup
      4. Subzone (robots-gated canonical slugs, metadata-verified)

    A title that already carries tracks answers at once and is never searched.

    Remote ffmpeg stays on the worker so flaky TLS cannot freeze the player.
    """
    from django.conf import settings as django_settings

    from apps.catalog.models import Episode, Movie, PlaybackSubtitleGap, Series
    from apps.catalog.subtitle_contract import publicize_subtitle_tracks
    from apps.catalog.subtitle_extract import (
        attach_extracted_subtitle,
        attach_series_softsub_tracks,
        download_links_imply_softsub,
        _attach_embedded_sync_movie,
        _links_for_episode,
        looks_like_hardsub_link,
        url_implies_softsub,
    )
    from apps.catalog.tasks import enqueue_movie_softsub_urgent, enqueue_series_softsub_urgent

    kind = str(content_type or '').strip().lower()
    slug = str(slug or '').strip()
    version = str(playback_version or '').strip().lower()
    preferred_source_url = str(playback_source_url or '').strip()[:2000]
    ep_id = int(episode_id or 0)

    if kind not in {'movie', 'series'} or not slug:
        return {'status': 'invalid', 'reported': False, 'queued': False, 'has_subtitle_tracks': False}

    # Soft rate-limit per title so one open player cannot stampede SubtitleStar.
    rate_key = f'catalog:playback-sub-ensure:{kind}:{slug}:{ep_id}'
    first_hit = cache.add(rate_key, '1', timeout=15)

    def _allow_ffmpeg(links: list) -> bool:
        soft = (
            any(url_implies_softsub(item) for item in links if isinstance(item, dict))
            or download_links_imply_softsub(links)
        )
        return bool(getattr(django_settings, 'SOFTSUB_ALLOW_FFMPEG', False)) or soft

    def _active_source_link(links: list[dict]) -> dict | None:
        """Return metadata for the exact stream open in the player.

        A title can expose both HardSub and original encodes. Looking at *any*
        HardSub link used to suppress/report the wrong lane. The viewer report
        must describe the selected stream, because subtitle timing is bound to
        that release and URL.
        """
        if preferred_source_url:
            selected = next(
                (row for row in links if str(row.get('url') or '').strip() == preferred_source_url),
                None,
            )
            if selected is not None:
                return selected
        return None

    def _active_source_is_hardsub(links: list[dict]) -> bool:
        selected = _active_source_link(links)
        if selected is not None:
            return bool(looks_like_hardsub_link(selected))
        return version == 'hardsub'

    if kind == 'movie':
        movie = Movie.objects.filter(is_published=True, slug=canonical_slug(Movie, slug)).first()
        if movie is None:
            return {'status': 'missing', 'reported': False, 'queued': False, 'has_subtitle_tracks': False}

        if _has_tracks(movie.subtitle_tracks):
            return {
                'status': 'ready',
                'reported': False,
                'queued': False,
                'has_subtitle_tracks': True,
                'subtitle_tracks': publicize_subtitle_tracks(movie.subtitle_tracks or []),
                'message': 'tracks_present',
            }

        links = [item for item in (movie.download_links or []) if isinstance(item, dict)]
        not_needed = playback_subtitle_not_needed(
            movie,
            version=version,
            active_link=_active_source_link(links),
            preferred_source_url=preferred_source_url,
        )
        if not_needed:
            return _not_needed_payload(not_needed)
        has_soft = (
            any(url_implies_softsub(item) for item in links)
            or download_links_imply_softsub(links)
        )
        allow_ffmpeg = _allow_ffmpeg(links)
        has_hard = _active_source_is_hardsub(links)
        prefer_embedded = bool(has_soft and allow_ffmpeg)
        soft_only = bool(links) and prefer_embedded and not has_hard
        burned_in_only = bool(links) and has_hard and not allow_ffmpeg

        gap = _upsert_gap(
            content_type='movie',
            object_id=movie.pk,
            episode_id=0,
            slug=movie.slug,
            title=str(movie.title or ''),
            playback_version=version,
            meta={
                'hardsub_lane': burned_in_only or version == 'hardsub',
                'soft_only': soft_only,
                'prefer_embedded': prefer_embedded,
                'allow_ffmpeg': allow_ffmpeg,
                'source_path': _safe_source_path(preferred_source_url),
                'preferred_source_url': preferred_source_url,
            },
        )

        # A full pass already came back empty for this file: answer at once
        # rather than re-queue the same hunt for every viewer.
        if gap_is_exhausted(gap):
            return _exhausted_payload(gap)

        # Player soft-poll: the gap is registered above so the beat drain can
        # retry it, but never re-queue or hit providers from a poll — the caller
        # only wants to know whether cues have landed yet.
        if not sync:
            return {
                'status': 'queued',
                'reported': True,
                'queued': True,
                'has_subtitle_tracks': False,
                'report_id': gap.pk,
                'message': 'polling',
            }

        if burned_in_only:
            # HardSub-only rows still get SubtitleStar sidecars so online SoftSub
            # can appear even when Persian is burned into the picture.
            if not first_hit:
                _mark_gap(gap, status=PlaybackSubtitleGap.Status.QUEUED, last_result='rate_limited')
                return {
                    'status': 'queued',
                    'reported': True,
                    'queued': True,
                    'has_subtitle_tracks': False,
                    'report_id': gap.pk,
                    'message': 'rate_limited',
                }

            # Only a genuinely-fresh report (row just created) clears stale
            # provider miss caches so providers get one re-probe. Circuit keys
            # are never cleared here: a genuinely-down provider must stay closed.
            fresh = int(gap.report_count or 0) <= 1
            if fresh:
                _clear_subtitlestar_miss_for_movie(movie)
                from apps.catalog.subzone import clear_subzone_miss_for_movie
                clear_subzone_miss_for_movie(movie)
                from apps.catalog.subdl import clear_subdl_miss_for_movie
                clear_subdl_miss_for_movie(movie)
            try:
                queued = enqueue_movie_softsub_urgent(
                    movie.pk,
                    force=True,
                    preferred_source_url=preferred_source_url,
                )
            except Exception:
                # Broker hiccup: never dead-end the viewer — the beat drain
                # re-enqueues this gap on its next pass.
                logger.warning('urgent softsub enqueue failed movie=%s', movie.pk, exc_info=True)
                queued = False

            attached = False
            if sync:
                sync_budget = _sync_budget(timeout_seconds)
                try:
                    attached = bool(attach_extracted_subtitle(
                        movie,
                        force=True,
                        timeout_seconds=sync_budget,
                        allow_ffmpeg=False,
                        preferred_source_url=preferred_source_url,
                    ))
                except Exception as exc:
                    logger.info('playback subtitle hardsub-star failed movie=%s: %s', movie.pk, exc)
                    attached = False
                movie.refresh_from_db(fields=['subtitle_tracks', 'has_subtitle'])

            if _has_tracks(movie.subtitle_tracks):
                _mark_gap(gap, status=PlaybackSubtitleGap.Status.RESOLVED, last_result='ready')
                return {
                    'status': 'ready',
                    'reported': True,
                    'queued': queued,
                    'has_subtitle_tracks': True,
                    'subtitle_tracks': publicize_subtitle_tracks(movie.subtitle_tracks or []),
                    'report_id': gap.pk,
                    'synced': attached,
                    'message': 'attached' if attached else 'ready',
                }

            # A held worker queue-lock (enqueue False) means extraction is already
            # in flight; a broker error is retried by the beat drain. Either way the
            # open player must keep waiting instead of seeing a dead-end.
            # This return belongs to the burned-in lane only — at module
            # indentation it made every soft/no-subtitle movie below unreachable
            # and raised UnboundLocalError on ``queued``.
            _mark_gap(
                gap,
                status=PlaybackSubtitleGap.Status.QUEUED,
                last_result='burned_in_queued' if queued else 'burned_in_pending',
            )
            return {
                'status': 'queued',
                'reported': True,
                'queued': True,
                'has_subtitle_tracks': False,
                'report_id': gap.pk,
                'message': 'loading',
            }

        # Rate-limited repeats only report the gap — do not clear Star caches or
        # re-stampede the urgent SoftSub queue (that blocked online playback).
        if not first_hit:
            _mark_gap(gap, status=PlaybackSubtitleGap.Status.QUEUED, last_result='rate_limited')
            return {
                'status': 'queued',
                'reported': True,
                'queued': True,
                'has_subtitle_tracks': False,
                'report_id': gap.pk,
                'message': 'rate_limited',
            }

        # First hit queues the embedded-first urgent worker. Provider sync only
        # runs here when the catalog has no extractable Soft source.
        fresh = int(gap.report_count or 0) <= 1
        if fresh:
            _clear_subtitlestar_miss_for_movie(movie)
            from apps.catalog.subzone import clear_subzone_miss_for_movie
            clear_subzone_miss_for_movie(movie)
            from apps.catalog.subdl import clear_subdl_miss_for_movie
            clear_subdl_miss_for_movie(movie)
        try:
            queued = enqueue_movie_softsub_urgent(
                movie.pk,
                force=True,
                preferred_source_url=preferred_source_url,
            )
        except Exception:
            # Broker hiccup: never dead-end the viewer — the beat drain
            # re-enqueues this gap on its next pass.
            logger.warning('urgent softsub enqueue failed movie=%s', movie.pk, exc_info=True)
            queued = False

        attached = False
        if sync:
            # File first: demux Persian SoftSub from the exact container being
            # watched inside a hard few-second cap. Its cues are natively in
            # sync and usually land faster than a provider round-trip; when the
            # file has nothing usable this returns in seconds and providers run
            # next, so the player never waits longer than before plus the cap.
            sync_budget = _sync_budget(timeout_seconds)
            embedded_cap = _sync_embedded_budget()
            if allow_ffmpeg and embedded_cap > 0:
                try:
                    attached = bool(_attach_embedded_sync_movie(
                        movie,
                        links,
                        timeout_seconds=embedded_cap,
                        preferred_source_url=preferred_source_url,
                    ))
                except Exception as exc:
                    logger.info('playback subtitle sync embedded failed movie=%s: %s', movie.pk, exc)
                    attached = False
                movie.refresh_from_db(fields=['subtitle_tracks', 'has_subtitle'])
            if not attached:
                try:
                    attached = bool(_attach_providers_sync_movie(
                        movie,
                        timeout_seconds=sync_budget,
                        preferred_source_url=preferred_source_url,
                    ))
                except Exception as exc:
                    logger.info('playback subtitle sync failed movie=%s: %s', movie.pk, exc)
                    attached = False
                movie.refresh_from_db(fields=['subtitle_tracks', 'has_subtitle'])

        if _has_tracks(movie.subtitle_tracks):
            _mark_gap(gap, status=PlaybackSubtitleGap.Status.RESOLVED, last_result='ready')
            return {
                'status': 'ready',
                'reported': True,
                'queued': queued,
                'has_subtitle_tracks': True,
                'subtitle_tracks': publicize_subtitle_tracks(movie.subtitle_tracks or []),
                'report_id': gap.pk,
                'synced': attached,
                'message': 'attached' if attached else 'ready',
            }

        # A held worker queue-lock (enqueue False) means extraction is already
        # in flight; a broker error is retried by the beat drain. Either way the
        # open player must keep waiting instead of seeing a dead-end.
        _mark_gap(
            gap,
            status=PlaybackSubtitleGap.Status.QUEUED,
            last_result='queued' if queued else 'pending_enqueue',
        )
        return {
            'status': 'queued',
            'reported': True,
            'queued': True,
            'has_subtitle_tracks': False,
            'report_id': gap.pk,
            'message': (
                'extracting_embedded' if queued and prefer_embedded
                else 'loading'
            ),
        }

    # series
    series = Series.objects.filter(is_published=True, slug=canonical_slug(Series, slug)).first()
    if series is None:
        return {'status': 'missing', 'reported': False, 'queued': False, 'has_subtitle_tracks': False}

    episode = None
    if ep_id:
        episode = Episode.objects.filter(
            pk=ep_id, season__series_id=series.pk, is_published=True,
        ).select_related('season').first()

    if episode is not None and _has_tracks(episode.subtitle_tracks):
        return {
            'status': 'ready',
            'reported': False,
            'queued': False,
            'has_subtitle_tracks': True,
            'episode_id': episode.pk,
            'subtitle_tracks': publicize_subtitle_tracks(episode.subtitle_tracks or []),
            'message': 'tracks_present',
        }

    links = [item for item in (series.download_links or []) if isinstance(item, dict)]
    not_needed = playback_subtitle_not_needed(
        series,
        version=version,
        active_link=_active_source_link(links),
        preferred_source_url=preferred_source_url,
    )
    if not_needed:
        return _not_needed_payload(not_needed, episode_id=ep_id)
    allow_ffmpeg = _allow_ffmpeg(links)
    episode_links = (
        _links_for_episode(
            links,
            int(getattr(getattr(episode, 'season', None), 'season_number', 1) or 1),
            int(getattr(episode, 'episode_number', 0) or 0),
        )
        if episode is not None else links
    )
    episode_video = str(getattr(episode, 'video_url', '') or '') if episode is not None else ''
    target_has_soft = bool(
        any(url_implies_softsub(item) for item in episode_links)
        or download_links_imply_softsub(episode_links)
        or (episode_video and url_implies_softsub({'url': episode_video}))
    )
    prefer_embedded = bool(allow_ffmpeg and target_has_soft)
    has_hard = _active_source_is_hardsub(episode_links)
    burned_in_only = bool(links) and has_hard and not allow_ffmpeg

    gap = _upsert_gap(
        content_type='series',
        object_id=series.pk,
        episode_id=ep_id,
        slug=series.slug,
        title=str(series.title or ''),
        playback_version=version,
        meta={
            'episode_id': ep_id,
            'allow_ffmpeg': allow_ffmpeg,
            'prefer_embedded': prefer_embedded,
            'hardsub_lane': burned_in_only,
            'source_path': _safe_source_path(preferred_source_url),
            'preferred_source_url': preferred_source_url,
        },
    )

    if gap_is_exhausted(gap):
        return _exhausted_payload(gap, episode_id=ep_id)

    # Player soft-poll: the gap is registered above so the beat drain can retry
    # it, but a poll never re-queues Celery or hits SubtitleStar.
    if not sync:
        return {
            'status': 'queued',
            'reported': True,
            'queued': True,
            'has_subtitle_tracks': False,
            'episode_id': ep_id or None,
            'report_id': gap.pk,
            'message': 'polling',
        }

    if burned_in_only:
        # HardSub-only catalog rows still often need SubtitleStar sidecars —
        # burned-in Persian is unreliable and leaving the player with zero cues
        # feels like "online playback brings nothing".
        if not first_hit:
            _mark_gap(gap, status=PlaybackSubtitleGap.Status.QUEUED, last_result='rate_limited')
            return {
                'status': 'queued',
                'reported': True,
                'queued': True,
                'has_subtitle_tracks': False,
                'episode_id': ep_id or None,
                'report_id': gap.pk,
                'message': 'rate_limited',
            }

        fresh = int(gap.report_count or 0) <= 1
        if fresh:
            _clear_subtitlestar_miss_for_series(series)
            from apps.catalog.subzone import clear_subzone_miss_for_series
            clear_subzone_miss_for_series(series)
            from apps.catalog.subdl import clear_subdl_miss_for_series
            clear_subdl_miss_for_series(series)
        try:
            queued = enqueue_series_softsub_urgent(
                series.pk,
                force=True,
                episode_limit=8 if ep_id else 24,
                episode_id=ep_id,
                preferred_source_url=preferred_source_url,
            )
        except Exception:
            # Broker hiccup: never dead-end the viewer — the beat drain
            # re-enqueues this gap on its next pass.
            logger.warning('urgent softsub enqueue failed series=%s', series.pk, exc_info=True)
            queued = False
        attached_eps = 0
        if sync and episode is not None:
            sync_budget = _sync_budget(timeout_seconds)
            try:
                if _attach_open_episode_subtitlestar(
                    series, episode, timeout_seconds=sync_budget, preferred_source_url=preferred_source_url,
                ):
                    attached_eps = 1
            except Exception as exc:
                logger.info('playback subtitle hardsub-star failed series=%s: %s', series.pk, exc)
            episode.refresh_from_db(fields=['subtitle_tracks'])
            if _has_tracks(episode.subtitle_tracks):
                _mark_gap(gap, status=PlaybackSubtitleGap.Status.RESOLVED, last_result='ready')
                return {
                    'status': 'ready',
                    'reported': True,
                    'queued': queued,
                    'has_subtitle_tracks': True,
                    'episode_id': episode.pk,
                    'subtitle_tracks': publicize_subtitle_tracks(episode.subtitle_tracks or []),
                    'report_id': gap.pk,
                    'synced_episodes': attached_eps,
                    'message': 'attached',
                }
        _mark_gap(
            gap,
            status=PlaybackSubtitleGap.Status.QUEUED,
            last_result='burned_in_queued' if queued else 'burned_in_pending',
        )
        return {
            'status': 'queued',
            'reported': True,
            'queued': True,
            'has_subtitle_tracks': False,
            'episode_id': ep_id or None,
            'report_id': gap.pk,
            'message': 'loading',
        }

    if not first_hit:
        _mark_gap(gap, status=PlaybackSubtitleGap.Status.QUEUED, last_result='rate_limited')
        return {
            'status': 'queued',
            'reported': True,
            'queued': True,
            'has_subtitle_tracks': False,
            'episode_id': ep_id or None,
            'report_id': gap.pk,
            'message': 'rate_limited',
        }

    fresh = int(gap.report_count or 0) <= 1
    if fresh:
        _clear_subtitlestar_miss_for_series(series)
        from apps.catalog.subzone import clear_subzone_miss_for_series
        clear_subzone_miss_for_series(series)
        from apps.catalog.subdl import clear_subdl_miss_for_series
        clear_subdl_miss_for_series(series)
    # Prefer a small urgent batch so the open episode is covered quickly.
    try:
        queued = enqueue_series_softsub_urgent(
            series.pk,
            force=True,
            episode_limit=8 if ep_id else 24,
            episode_id=ep_id,
            preferred_source_url=preferred_source_url,
        )
    except Exception:
        # Broker hiccup: never dead-end the viewer — the beat drain
        # re-enqueues this gap on its next pass.
        logger.warning('urgent softsub enqueue failed series=%s', series.pk, exc_info=True)
        queued = False

    attached_eps = 0
    if sync:
        # File first, same as movies: the playing episode's own container is
        # attempted inside a hard few-second cap before any sidecar provider.
        sync_budget = _sync_budget(timeout_seconds)
        embedded_cap = _sync_embedded_budget()
        if episode is not None and allow_ffmpeg and embedded_cap > 0:
            try:
                from apps.catalog.subtitle_extract import _attach_embedded_sync_episode
                if _attach_embedded_sync_episode(
                    series,
                    episode,
                    episode_links,
                    timeout_seconds=embedded_cap,
                    preferred_source_url=preferred_source_url,
                ):
                    attached_eps = 1
            except Exception as exc:
                logger.info('playback subtitle sync embedded failed series=%s: %s', series.pk, exc)
        try:
            if episode is not None:
                if not attached_eps and _attach_open_episode_subtitlestar(
                    series, episode, timeout_seconds=sync_budget, preferred_source_url=preferred_source_url,
                ):
                    attached_eps = 1
            else:
                result = attach_series_softsub_tracks(
                    series,
                    force=True,
                    timeout_seconds=sync_budget,
                    limit=4,
                    allow_ffmpeg=False,
                )
                attached_eps = int(result.get('extracted') or result.get('subtitlestar_attached') or 0)
        except Exception as exc:
            logger.info('playback subtitle sync failed series=%s: %s', series.pk, exc)

        if episode is not None:
            episode.refresh_from_db(fields=['subtitle_tracks'])

    if episode is not None:
        episode.refresh_from_db(fields=['subtitle_tracks'])
        if _has_tracks(episode.subtitle_tracks):
            _mark_gap(gap, status=PlaybackSubtitleGap.Status.RESOLVED, last_result='ready')
            return {
                'status': 'ready',
                'reported': True,
                'queued': queued,
                'has_subtitle_tracks': True,
                'episode_id': episode.pk,
                'subtitle_tracks': publicize_subtitle_tracks(episode.subtitle_tracks or []),
                'report_id': gap.pk,
                'synced_episodes': attached_eps,
                'message': 'attached',
            }

    has_any = Episode.objects.filter(
        season__series_id=series.pk, is_published=True,
    ).exclude(subtitle_tracks=[]).exclude(subtitle_tracks__isnull=True).exists()
    if has_any and attached_eps:
        _mark_gap(gap, status=PlaybackSubtitleGap.Status.QUEUED, last_result='partial')
        return {
            'status': 'queued',
            'reported': True,
            'queued': True,
            'has_subtitle_tracks': False,
            'report_id': gap.pk,
            'synced_episodes': attached_eps,
            'message': 'partial_attached',
        }

    _mark_gap(
        gap,
        status=PlaybackSubtitleGap.Status.QUEUED,
        last_result='queued' if queued else 'pending_enqueue',
    )
    return {
        'status': 'queued',
        'reported': True,
        'queued': True,
        'has_subtitle_tracks': False,
        'episode_id': ep_id or None,
        'report_id': gap.pk,
        'message': (
            'extracting_embedded' if queued and prefer_embedded
            else 'loading'
        ),
    }


def read_playback_subtitle_status(
    *,
    report_id: int | None = None,
    content_type: str = '',
    slug: str = '',
    episode_id: int = 0,
) -> dict[str, Any]:
    """Lightweight answer to "has the reported subtitle gap been filled yet?".

    This is a pure read: it never enqueues a worker, never probes SubtitleStar /
    Subzone, and never clears provider caches. The player polls this instead of
    re-submitting the heavy ensure POST. A short Redis micro-cache (keyed on the
    report identity) keeps the DB read cheap under many concurrent pollers.
    """
    from django.conf import settings as django_settings

    kind = str(content_type or '').strip().lower()
    slug = str(slug or '').strip()
    ep_id = int(episode_id or 0)

    if kind not in {'movie', 'series'} or not slug:
        return {
            'status': 'invalid',
            'has_subtitle_tracks': False,
            'report_id': report_id,
            'message': 'invalid_request',
        }

    cache_seconds = max(1, int(getattr(django_settings, 'PLAYBACK_SUBTITLE_STATUS_CACHE_SECONDS', 3)))
    cache_key = f'catalog:playback-sub-status:{kind}:{slug}:{ep_id}'
    if report_id:
        cache_key = f'{cache_key}:report:{int(report_id)}'
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached

    payload = _build_status_payload(
        kind=kind,
        slug=slug,
        episode_id=ep_id,
        report_id=report_id,
    )
    cache.set(cache_key, payload, timeout=cache_seconds)
    return payload


def _build_status_payload(*, kind: str, slug: str, episode_id: int, report_id: int | None) -> dict[str, Any]:
    """DB-backed status payload for the lightweight poll endpoint."""
    from apps.catalog.models import Episode, Movie, PlaybackSubtitleGap, Series
    from apps.catalog.subtitle_contract import publicize_subtitle_tracks

    ep_id = int(episode_id or 0)
    gap = None
    if report_id:
        gap = PlaybackSubtitleGap.objects.filter(pk=int(report_id)).first()
        if gap is None:
            return {
                'status': 'missing_report',
                'has_subtitle_tracks': False,
                'report_id': report_id,
                'message': 'report_not_found',
            }

    if kind == 'movie':
        movie = Movie.objects.filter(is_published=True, slug=canonical_slug(Movie, slug)).first()
        if movie is None:
            return {
                'status': 'missing',
                'has_subtitle_tracks': False,
                'report_id': gap.pk if gap else None,
                'message': 'title_not_found',
            }
        if gap is None:
            gap = PlaybackSubtitleGap.objects.filter(
                content_type=PlaybackSubtitleGap.ContentType.MOVIE,
                object_id=movie.pk,
                episode_id=0,
            ).first()
        if gap and (
            gap.content_type != PlaybackSubtitleGap.ContentType.MOVIE
            or gap.object_id != movie.pk
            or gap.episode_id != 0
        ):
            return {
                'status': 'invalid_report',
                'has_subtitle_tracks': False,
                'report_id': report_id,
                'message': 'report_target_mismatch',
            }
        tracks = movie.subtitle_tracks or []
        ready = _has_tracks(tracks)
        return {
            'status': 'ready' if ready else _gap_status_label(gap),
            'reported': gap is not None,
            'queued': bool(gap and gap.status != PlaybackSubtitleGap.Status.UNAVAILABLE),
            'has_subtitle_tracks': ready,
            'subtitle_tracks': publicize_subtitle_tracks(tracks) if ready else [],
            'report_id': gap.pk if gap else None,
            'message': 'tracks_present' if ready else 'loading',
        }

    series = Series.objects.filter(is_published=True, slug=canonical_slug(Series, slug)).first()
    if series is None:
        return {
            'status': 'missing',
            'has_subtitle_tracks': False,
            'report_id': gap.pk if gap else None,
            'message': 'title_not_found',
        }

    if gap is None:
        gap = PlaybackSubtitleGap.objects.filter(
            content_type=PlaybackSubtitleGap.ContentType.SERIES,
            object_id=series.pk,
            episode_id=ep_id,
        ).first()

    if gap and (
        gap.content_type != PlaybackSubtitleGap.ContentType.SERIES
        or gap.object_id != series.pk
        or gap.episode_id != ep_id
    ):
        return {
            'status': 'invalid_report',
            'has_subtitle_tracks': False,
            'episode_id': ep_id or None,
            'report_id': report_id,
            'message': 'report_target_mismatch',
        }

    if ep_id:
        episode = Episode.objects.filter(
            pk=ep_id, season__series_id=series.pk, is_published=True,
        ).first()
        if episode is None:
            return {
                'status': 'missing',
                'has_subtitle_tracks': False,
                'episode_id': ep_id,
                'report_id': gap.pk if gap else None,
                'message': 'episode_not_found',
            }
        ready = _has_tracks(episode.subtitle_tracks)
        return {
            'status': 'ready' if ready else _gap_status_label(gap),
            'reported': gap is not None,
            'queued': bool(gap and gap.status != PlaybackSubtitleGap.Status.UNAVAILABLE),
            'has_subtitle_tracks': ready,
            'subtitle_tracks': publicize_subtitle_tracks(episode.subtitle_tracks or []) if ready else [],
            'episode_id': episode.pk,
            'report_id': gap.pk if gap else None,
            'message': 'tracks_present' if ready else 'loading',
        }

    series_ready = _has_tracks(series.subtitle_tracks)
    has_any = Episode.objects.filter(
        season__series_id=series.pk, is_published=True,
    ).exclude(subtitle_tracks=[]).exclude(subtitle_tracks__isnull=True).exists()
    ready = bool(series_ready or has_any)
    return {
        'status': 'ready' if ready else _gap_status_label(gap),
        'reported': gap is not None,
        'queued': bool(gap and gap.status != PlaybackSubtitleGap.Status.UNAVAILABLE),
        'has_subtitle_tracks': ready,
        'subtitle_tracks': publicize_subtitle_tracks(series.subtitle_tracks or []) if ready else [],
        'report_id': gap.pk if gap else None,
        'message': 'tracks_present' if ready else 'loading',
    }


def _gap_status_label(gap) -> str:
    """Map a gap row's status onto the lightweight public status vocabulary."""
    from apps.catalog.models import PlaybackSubtitleGap

    if gap is None or gap.status == PlaybackSubtitleGap.Status.OPEN:
        return 'queued'
    if gap.status == PlaybackSubtitleGap.Status.RESOLVED:
        return 'queued'
    if gap.status == PlaybackSubtitleGap.Status.UNAVAILABLE:
        return EXHAUSTED_RESULT if gap_is_exhausted(gap) else 'unavailable'
    return 'queued'
