"""Staff operations desk — the controls that keep a published catalog honest.

The admin panel could already *create* titles: search TMDB, preview it, import
the metadata, send the crawlers after playable links. What it could not do was
fix one afterwards. Links arrived read-only, so a wrong mirror could only be
removed by hand-editing a JSON field; the gap tables that already know which
titles are broken (:class:`PlaybackSourceGap`, :class:`PlaybackSubtitleGap`,
:class:`MediaCheck`, :class:`ContentIssueReport`) were invisible to staff; and
every repair was a one-title-at-a-time trip through the detail page.

This module is the other half of the panel:

* :func:`media_desk` — everything known about one title's playable sources and
  subtitles, plus the actions that change them (verify, re-crawl, add, drop,
  re-subtitle, publish).
* :func:`bulk_action` — the same verbs applied to a selection.
* :func:`catalog_health` — the problem queues, read straight off the models that
  already record them, so the panel shows the same truth the crawlers act on.
* :func:`ops_overview` — the crawlers themselves: queue depth per lane, recent
  jobs, what the sweeps last did.
* :func:`audit_feed` — who changed what.

**Nothing here destroys a row.** "Delete" archives (the existing soft-delete);
removing a link drops one entry from a JSON list that the next crawl refills;
the only bytes that leave for good are links the *host itself* reported gone,
and that path is the existing pruner in :mod:`media_verification`, not new code.
Every state-changing action writes a :class:`MovieSyncAudit` row, so the panel
can answer "who archived this and when" without reading container logs.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .admin_api import IsStaffUser, StaffAdminThrottle, _audit
from .playback_sources import DRAFT_GAP_REASON
from .models import (
    ContentIssueReport,
    Episode,
    MediaCheck,
    Movie,
    MovieSyncAudit,
    PlaybackSourceGap,
    PlaybackSubtitleGap,
    ProviderImportJob,
    Series,
)

logger = logging.getLogger(__name__)

#: The two catalog rows a staff member operates on. Episodes are addressed as a
#: sub-target of their series rather than a kind of their own, because that is
#: how every underlying helper (verification, subtitles, gaps) already takes them.
KINDS = {'movie': Movie, 'series': Series}

#: Health words used across the desk and the queues. Kept deliberately small:
#: a link is either known good, known gone, or nobody has asked.
LIVE, DEAD, UNKNOWN, UNCHECKED = 'live', 'dead', 'unknown', 'unchecked'


def _bad_request(detail, code='invalid'):
    return Response({'detail': detail, 'code': code}, status=status.HTTP_400_BAD_REQUEST)


#: The neighbouring admin routes spell these plural (``/admin/catalog/movies/…``),
#: so both spellings resolve here rather than 400-ing on a URL an admin copied.
KIND_ALIASES = {'movies': 'movie', 'movie': 'movie', 'series': 'series', 'serie': 'series'}


def _resolve_target(kind, object_id):
    """Return the Movie/Series for ``kind``, or ``None`` when the kind is junk."""
    model = KINDS.get(KIND_ALIASES.get(str(kind or '').lower(), ''))
    if model is None:
        return None
    queryset = model.objects.all()
    if model is Movie:
        queryset = queryset.prefetch_related('genres', 'countries')
    return get_object_or_404(queryset, pk=object_id)


def _kind_of(obj) -> str:
    return 'series' if isinstance(obj, Series) else 'movie'


def _episode_of(obj, episode_id) -> Episode | None:
    """The episode a request is aimed at, validated to belong to ``obj``.

    Guards against an id from another series arriving in the body: an admin
    action must never write one show's verdict onto another's episode.
    """
    if not episode_id:
        return None
    if not isinstance(obj, Series):
        return None
    return Episode.objects.filter(pk=int(episode_id), season__series=obj).select_related('season').first()


def _probe_index(obj, *, kind: str) -> dict[str, dict]:
    """Map every probed URL for this title to what the probe found.

    Series checks live one row per episode, so the whole set is folded into one
    index: the series' own ``download_links`` carry season/episode tags and are
    probed under whichever episode claimed them.
    """
    index: dict[str, dict] = {}
    checks = MediaCheck.objects.filter(content_type=kind, object_id=obj.pk).order_by('checked_at')
    for check in checks:
        for probe in ((check.detail or {}).get('probes') or []):
            url = str(probe.get('url') or '').strip()
            if not url:
                continue
            tech = probe.get('tech') or {}
            index[url] = {
                'verdict': str(probe.get('verdict') or UNKNOWN),
                'reason': str(probe.get('reason') or ''),
                'browser_safe': bool(probe.get('safe')),
                'container': str(tech.get('container') or ''),
                'video_codec': str(tech.get('video_codec') or tech.get('vcodec') or ''),
                'audio_codec': str(tech.get('audio_codec') or tech.get('acodec') or ''),
                'duration': tech.get('duration') or None,
                'checked_at': check.checked_at.isoformat() if check.checked_at else None,
            }
    return index


def _integrity_of(obj, url: str) -> dict:
    """Ask the self-describing-path guard whether this link is even ours.

    The same classifier the importer uses at the choke point, surfaced so staff
    can see *why* a link was kept or would be stripped instead of guessing.
    """
    from .provider_import.link_integrity import (
        STRIP_CATS, classify_movie_link, classify_series_link,
    )

    if not url:
        return {'category': 'ok', 'contaminated': False}
    try:
        category = (
            classify_series_link(obj, url) if isinstance(obj, Series)
            else classify_movie_link(obj, url)
        )
    except Exception:  # a malformed URL must never break the desk
        return {'category': 'unknown', 'contaminated': False}
    return {'category': category, 'contaminated': category in STRIP_CATS}


def _link_rows(obj, probes: dict[str, dict]) -> list[dict]:
    """The title's download links, each carrying what is known about it."""
    from .playback_sources import codec_family

    rows = []
    for index, item in enumerate(getattr(obj, 'download_links', None) or []):
        if not isinstance(item, dict):
            continue
        url = str(item.get('url') or item.get('key') or '').strip()
        probe = probes.get(url) or {}
        health = probe.get('verdict') or UNCHECKED
        if health not in {LIVE, DEAD, UNKNOWN}:
            health = UNCHECKED
        rows.append({
            'index': index,
            'url': url,
            'label': str(item.get('label') or ''),
            'quality': str(item.get('quality') or ''),
            'size_label': str(item.get('size_label') or ''),
            'kind': str(item.get('kind') or ''),
            'source': str(item.get('source') or ''),
            'season_number': item.get('season_number'),
            'episode_number': item.get('episode_number'),
            'health': health,
            'reason': probe.get('reason') or '',
            'browser_safe': probe.get('browser_safe'),
            'container': probe.get('container') or '',
            'video_codec': probe.get('video_codec') or '',
            'audio_codec': probe.get('audio_codec') or '',
            'codec_family': codec_family(f"{url} {item.get('quality') or ''} {item.get('label') or ''}"),
            'checked_at': probe.get('checked_at'),
            'integrity': _integrity_of(obj, url),
        })
    return rows


def _subtitle_rows(holder) -> list[dict]:
    rows = []
    for index, track in enumerate(getattr(holder, 'subtitle_tracks', None) or []):
        if not isinstance(track, dict):
            continue
        rows.append({
            'index': index,
            'src': str(track.get('src') or ''),
            'label': str(track.get('label') or ''),
            'lang': str(track.get('lang') or track.get('srclang') or ''),
            'format': str(track.get('format') or ''),
            'provider': str(track.get('provider') or ''),
            'offset': track.get('offset') or track.get('offset_seconds') or 0,
            'default': bool(track.get('default')),
        })
    return rows


def _check_row(check) -> dict | None:
    if check is None:
        return None
    return {
        'status': check.status,
        'playable': check.playable,
        'downloadable': check.downloadable,
        'reason': check.reason,
        'checked_urls': check.checked_urls,
        'dead_urls': check.dead_urls,
        'attempts': check.attempts,
        'checked_at': check.checked_at.isoformat() if check.checked_at else None,
        'tech': (check.detail or {}).get('tech') or None,
    }


def _gap_row(gap) -> dict | None:
    if gap is None:
        return None
    return {
        'id': gap.id,
        'status': gap.status,
        'reason': getattr(gap, 'reason', '') or '',
        'episode_id': gap.episode_id,
        'report_count': gap.report_count,
        'last_result': gap.last_result,
        'updated_at': gap.updated_at.isoformat() if gap.updated_at else None,
    }


def _report_row(report) -> dict:
    return {
        'id': report.id,
        'problem_type': report.problem_type,
        'problem_label': report.get_problem_type_display(),
        'status': report.status,
        'status_label': report.get_status_display(),
        'episode_id': report.episode_id,
        'season_number': report.season_number,
        'episode_number': report.episode_number,
        'report_count': report.report_count,
        'attempts': report.attempts,
        'remediation_action': report.remediation_action,
        'last_result': report.last_result,
        'detail': report.detail[:400],
        'created_at': report.created_at.isoformat(),
        'updated_at': report.updated_at.isoformat(),
    }


def _audit_row(entry) -> dict:
    return {
        'id': entry.id,
        'action': entry.action,
        'action_label': entry.get_action_display(),
        'movie_id': entry.movie_id,
        'actor': getattr(entry.actor, 'username', '') or '',
        'changed_fields': entry.changed_fields or [],
        'details': entry.details or {},
        'created_at': entry.created_at.isoformat(),
    }


def _episode_rows(series, probes: dict[str, dict]) -> list[dict]:
    """Per-episode state for a series, so staff can see *which* episode is broken.

    A series' own ``download_links`` carry ``season_number``/``episode_number``
    tags, so the episode's link count is read from there rather than from a
    field episodes do not have. ``video_url`` is the episode's own stream and is
    what actually makes it playable in a browser.
    """
    checks = {
        check.episode_id: check
        for check in MediaCheck.objects.filter(content_type='series', object_id=series.pk).exclude(episode_id=0)
    }
    tally: dict[tuple[int, int], dict] = {}
    for item in (series.download_links or []):
        if not isinstance(item, dict):
            continue
        key = (int(item.get('season_number') or 0), int(item.get('episode_number') or 0))
        bucket = tally.setdefault(key, {'links': 0, 'dead': 0})
        bucket['links'] += 1
        url = str(item.get('url') or '').strip()
        if (probes.get(url) or {}).get('verdict') == DEAD:
            bucket['dead'] += 1

    rows = []
    episodes = (
        Episode.objects.filter(season__series=series)
        .select_related('season')
        .order_by('season__season_number', 'episode_number')
    )
    for episode in episodes:
        season_number = episode.season.season_number
        bucket = tally.get((season_number, episode.episode_number), {'links': 0, 'dead': 0})
        check = checks.get(episode.pk)
        rows.append({
            'id': episode.pk,
            'season_number': season_number,
            'episode_number': episode.episode_number,
            'title': episode.title,
            'is_published': episode.is_published,
            'has_stream': bool(episode.video_url),
            'playback_mode': episode.playback_mode,
            'link_count': bucket['links'],
            'dead_links': bucket['dead'],
            'subtitle_count': len([t for t in (episode.subtitle_tracks or []) if isinstance(t, dict)]),
            'check': _check_row(check),
        })
    return rows


def _desk_payload(request, obj) -> dict:
    """Everything the media desk shows for one title, in one round-trip.

    Deliberately one payload rather than five endpoints: a staff member deciding
    whether a title is broken needs the links, the last verdict, the open gaps
    and the viewer reports side by side — fetching them separately guarantees
    they sometimes disagree on screen.
    """
    from . import media_verification
    from .completeness import metadata_gaps, publish_blockers
    from .playback_sources import diagnose

    kind = _kind_of(obj)
    probes = _probe_index(obj, kind=kind)
    is_series = isinstance(obj, Series)

    payload = {
        'kind': kind,
        'id': obj.pk,
        'title': obj.title,
        'slug': obj.slug,
        'year': getattr(obj, 'release_year', None) or getattr(obj, 'start_year', None),
        'is_published': obj.is_published,
        'publication_status': getattr(obj, 'publication_status', None),
        'tmdb_id': obj.tmdb_id,
        'imdb_id': obj.imdb_id,
        'playback_mode': getattr(obj, 'playback_mode', ''),
        'playback_checked_at': (
            getattr(obj, 'playback_checked_at', None).isoformat()
            if getattr(obj, 'playback_checked_at', None) else None
        ),
        'links': _link_rows(obj, probes),
        'subtitles': [] if is_series else _subtitle_rows(obj),
        'check': _check_row(media_verification.latest_check(obj)),
        'diagnosis': diagnose(obj),
        'metadata_gaps': metadata_gaps(obj),
        'publish_blockers': publish_blockers(obj),
        'source_gap': _gap_row(
            PlaybackSourceGap.objects.filter(content_type=kind, object_id=obj.pk)
            .exclude(status=PlaybackSourceGap.Status.RESOLVED).first()
        ),
        'subtitle_gap': _gap_row(
            PlaybackSubtitleGap.objects.filter(content_type=kind, object_id=obj.pk)
            .exclude(status=PlaybackSubtitleGap.Status.RESOLVED).first()
        ),
        'reports': [
            _report_row(report)
            for report in ContentIssueReport.objects.filter(content_type=kind, object_id=obj.pk)
            .exclude(status__in=[
                ContentIssueReport.Status.RESOLVED,
                ContentIssueReport.Status.REJECTED,
            ])[:25]
        ],
        'jobs': [
            {
                'id': str(job.id),
                'status': job.status,
                'mode': job.mode,
                'trigger': job.trigger,
                'error_message': job.error_message,
                'created_at': job.created_at.isoformat(),
                'finished_at': job.finished_at.isoformat() if job.finished_at else None,
            }
            for job in ProviderImportJob.objects.filter(
                **({'target_series': obj} if is_series else {'target_movie': obj})
            ).order_by('-created_at')[:8]
        ],
    }
    if is_series:
        payload['episodes'] = _episode_rows(obj, probes)
        payload['audits'] = []
    else:
        payload['audits'] = [
            _audit_row(entry)
            for entry in MovieSyncAudit.objects.filter(movie=obj).select_related('actor')[:15]
        ]
    return payload


# --------------------------------------------------------------------------
# Actions
# --------------------------------------------------------------------------

def _save_links(obj, links: list, *, request, reason: str, removed: list | None = None):
    """Persist a rewritten link list and record who rewrote it.

    Goes through the admin serializer's normalizer rather than assigning the raw
    list, so a hand-added link picks up the same season/episode parsing, dead-host
    rejection and dub/subtitle flag derivation the crawler's links get. Writing
    the field directly is how the two paths drift apart.
    """
    from config.public_urls import normalize_download_links

    from .subtitle_extract import download_links_imply_dub, download_links_imply_subtitle

    normalized = normalize_download_links(links)
    obj.download_links = normalized
    fields = ['download_links', 'updated_at']
    obj.has_subtitle = download_links_imply_subtitle(normalized)
    obj.is_dubbed = download_links_imply_dub(normalized)
    fields += ['has_subtitle', 'is_dubbed']
    if getattr(obj, 'subtitle_tracks', None):
        obj.has_subtitle = True
    obj.save(update_fields=fields)
    _audit(
        request,
        MovieSyncAudit.Action.MANUAL_UPDATE,
        movie=obj if isinstance(obj, Movie) else None,
        tmdb_id=obj.tmdb_id,
        changed=['download_links'],
        details={
            'kind': _kind_of(obj),
            'object_id': obj.pk,
            'title': obj.title,
            'reason': reason,
            'removed': removed or [],
            'remaining': len(normalized),
        },
    )
    return normalized


def _set_publication(obj, state: str, *, request, force: bool = False) -> dict:
    """Move a title between draft / published / archived.

    Publishing runs the same structural and media gates the importer runs, so a
    title can never reach the site through the admin panel that the importer
    would have refused. ``force`` records an override in the audit rather than
    silently skipping the check — an admin may know better than the gate, but
    the panel should say that they did.
    """
    from . import media_verification
    from .completeness import publish_blockers

    state = str(state or '').lower()
    if state not in {'published', 'draft', 'archived'}:
        return {'error': 'state must be published, draft or archived'}

    blockers: list[str] = []
    if state == 'published':
        blockers = list(publish_blockers(obj))
        blockers += media_verification.media_publish_blockers(obj)
        if blockers and not force:
            return {'error': 'publish_blocked', 'blockers': blockers}

    fields = ['is_published', 'updated_at']
    obj.is_published = state == 'published'
    if isinstance(obj, Movie):
        obj.publication_status = {
            'published': Movie.PublicationStatus.PUBLISHED,
            'draft': Movie.PublicationStatus.DRAFT,
            'archived': Movie.PublicationStatus.ARCHIVED,
        }[state]
        fields.append('publication_status')
    obj.save(update_fields=fields)

    action = (
        MovieSyncAudit.Action.ARCHIVE if state == 'archived'
        else MovieSyncAudit.Action.MANUAL_UPDATE
    )
    _audit(
        request, action,
        movie=obj if isinstance(obj, Movie) else None,
        tmdb_id=obj.tmdb_id,
        changed=['is_published'],
        details={
            'kind': _kind_of(obj), 'object_id': obj.pk, 'title': obj.title,
            'state': state, 'forced': bool(force and blockers), 'blockers': blockers,
        },
    )
    return {
        'state': state, 'is_published': obj.is_published,
        'publication_status': getattr(obj, 'publication_status', None),
        'forced_blockers': blockers if force else [],
    }


def _queue_discover(obj, *, request, mode: str, force: bool) -> dict:
    """Send the crawlers back out after this one title.

    This is «جستجوی دوباره با کمک خزنده»: the same discovery job the importer
    runs, aimed at a row that already exists, so a title whose links died gets
    re-searched across every configured provider without re-importing it.
    """
    from .provider_import.api import _queue_job
    from .provider_import.catalog_lookup import append_log, create_catalog_discover_job

    job = create_catalog_discover_job(
        content_type=_kind_of(obj),
        object_id=obj.pk,
        user=request.user,
        force=bool(force),
        trigger=ProviderImportJob.Trigger.MANUAL,
        mode=mode,
    )
    append_log(job, 'info', 'Re-crawl requested from the operations desk.')
    try:
        _queue_job(job)
    except Exception:
        job.status = ProviderImportJob.Status.FAILED
        job.error_message = 'Could not queue Celery task.'
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])
        return {'error': 'queue_failed', 'job_id': str(job.id)}
    return {'job_id': str(job.id), 'status': job.status, 'mode': mode}


def _act_verify(obj, request, body):
    from . import media_verification

    episode = _episode_of(obj, body.get('episode_id'))
    verdict = media_verification.verify_target(obj, episode=episode, use_cache=False)
    verdict.pop('probes', None)
    obj.refresh_from_db()
    return {'verdict': verdict}


def _act_remove_link(obj, request, body):
    links = [item for item in (obj.download_links or []) if isinstance(item, dict)]
    target_url = str(body.get('url') or '').strip()
    index = body.get('index')
    removed = []
    kept = []
    for position, item in enumerate(links):
        url = str(item.get('url') or item.get('key') or '').strip()
        matched = (target_url and url == target_url) or (index is not None and position == int(index))
        (removed if matched else kept).append(item)
    if not removed:
        return {'error': 'link_not_found'}
    _save_links(obj, kept, request=request, reason='remove_link',
                removed=[str(i.get('url') or '') for i in removed])
    return {'removed': len(removed), 'remaining': len(obj.download_links or [])}


def _act_add_link(obj, request, body):
    """Attach a link by hand — through the same identity guard the importer uses.

    A staff member pasting a URL is exactly the case the contamination guard was
    written for (the شورش incident started as a hand-checked link), so the guard
    runs here too. It reports rather than refuses when ``force`` is set, because
    an admin looking at the provider page can outrank a path heuristic.
    """
    url = str(body.get('url') or '').strip()
    if not url:
        return {'error': 'url is required'}
    integrity = _integrity_of(obj, url)
    if integrity['contaminated'] and not body.get('force'):
        return {'error': 'contaminated_link', 'integrity': integrity}

    links = [item for item in (obj.download_links or []) if isinstance(item, dict)]
    if any(str(item.get('url') or '').strip() == url for item in links):
        return {'error': 'link_already_present'}
    entry = {
        'url': url,
        'label': str(body.get('label') or '').strip(),
        'quality': str(body.get('quality') or '').strip(),
        'size_label': str(body.get('size_label') or '').strip(),
        'source': 'manual',
    }
    for key in ('season_number', 'episode_number'):
        if body.get(key) not in (None, ''):
            try:
                entry[key] = int(body[key])
            except (TypeError, ValueError):
                pass
    links.append(entry)
    normalized = _save_links(obj, links, request=request, reason='add_link')
    if not any(str(item.get('url') or '') == url for item in normalized):
        # normalize_download_links silently drops trailers, known-dead hosts and
        # malformed media suffixes. Saying so beats a "saved" that saved nothing.
        return {'error': 'link_rejected_by_normalizer', 'integrity': integrity}
    return {'added': 1, 'total': len(normalized), 'integrity': integrity}


def _act_prune_dead(obj, request, body):
    """Drop the links the host itself answered "gone" for, and nothing else."""
    probes = _probe_index(obj, kind=_kind_of(obj))
    links = [item for item in (obj.download_links or []) if isinstance(item, dict)]
    kept, removed = [], []
    for item in links:
        url = str(item.get('url') or '').strip()
        if (probes.get(url) or {}).get('verdict') == DEAD:
            removed.append(url)
        else:
            kept.append(item)
    if not removed:
        return {'removed': 0, 'detail': 'no link is recorded dead'}
    _save_links(obj, kept, request=request, reason='prune_dead', removed=removed)
    return {'removed': len(removed), 'remaining': len(kept), 'urls': removed}


def _act_strip_contaminated(obj, request, body):
    """Remove links whose CDN path proves they belong to a different title."""
    from .provider_import.link_integrity import filter_contaminated_links

    links = [item for item in (obj.download_links or []) if isinstance(item, dict)]
    kept, dropped = filter_contaminated_links(obj, links)
    if not dropped:
        return {'removed': 0, 'detail': 'no contaminated link found'}
    _save_links(
        obj, kept, request=request, reason='strip_contaminated',
        removed=[f"{str(item.get('url') or '')} [{cat}]" for item, cat in dropped],
    )
    return {
        'removed': len(dropped), 'remaining': len(kept),
        'dropped': [{'url': str(item.get('url') or ''), 'category': cat} for item, cat in dropped],
    }


def _act_recrawl(obj, request, body):
    mode = str(body.get('mode') or ProviderImportJob.Mode.DISCOVER_ONLY)
    if mode not in dict(ProviderImportJob.Mode.choices):
        mode = ProviderImportJob.Mode.DISCOVER_ONLY
    return _queue_discover(obj, request=request, mode=mode, force=bool(body.get('force', True)))


def _act_refresh_subtitles(obj, request, body):
    """Queue a fresh subtitle hunt for this title (or one episode of it)."""
    from .tasks import extract_movie_softsub_task, extract_series_softsub_task

    force = bool(body.get('force', True))
    if isinstance(obj, Series):
        episode = _episode_of(obj, body.get('episode_id'))
        extract_series_softsub_task.delay(
            obj.pk, force=force, preferred_episode_id=getattr(episode, 'pk', 0) or 0,
        )
        return {'queued': 'series', 'episode_id': getattr(episode, 'pk', 0) or 0}
    if not obj.is_published:
        # The worker filters on is_published, so a draft would silently no-op.
        return {'error': 'subtitle_worker_needs_published_title'}
    extract_movie_softsub_task.delay(obj.pk, force=force)
    return {'queued': 'movie'}


def _act_remove_subtitle(obj, request, body):
    holder = _episode_of(obj, body.get('episode_id')) or obj
    if isinstance(holder, Series):
        return {'error': 'series_subtitles_live_on_episodes'}
    tracks = [t for t in (holder.subtitle_tracks or []) if isinstance(t, dict)]
    src = str(body.get('src') or '').strip()
    index = body.get('index')
    kept, removed = [], []
    for position, track in enumerate(tracks):
        matched = (src and str(track.get('src') or '') == src) or (index is not None and position == int(index))
        (removed if matched else kept).append(track)
    if not removed:
        return {'error': 'subtitle_not_found'}
    holder.subtitle_tracks = kept
    fields = ['subtitle_tracks', 'updated_at']
    if isinstance(holder, Movie):
        holder.has_subtitle = bool(kept)
        fields.append('has_subtitle')
    holder.save(update_fields=fields)
    _audit(
        request, MovieSyncAudit.Action.MANUAL_UPDATE,
        movie=holder if isinstance(holder, Movie) else None,
        changed=['subtitle_tracks'],
        details={
            'kind': _kind_of(obj), 'object_id': obj.pk, 'title': obj.title,
            'reason': 'remove_subtitle', 'episode_id': getattr(holder, 'pk', 0) if holder is not obj else 0,
            'removed': [str(t.get('src') or '') for t in removed],
        },
    )
    return {'removed': len(removed), 'remaining': len(kept)}


def _act_publish(obj, request, body):
    return _set_publication(obj, 'published', request=request, force=bool(body.get('force')))


def _act_unpublish(obj, request, body):
    return _set_publication(obj, 'draft', request=request)


def _act_archive(obj, request, body):
    return _set_publication(obj, 'archived', request=request)


def _resync_tmdb(obj, *, overwrite: bool = False) -> dict:
    """Pull this title's metadata from TMDB again.

    Uses the same ``upsert_tmdb_*`` the importer and the existing per-title sync
    endpoint use, so a re-sync from the desk or from a bulk selection produces
    exactly the metadata a fresh import would — manual overrides are preserved
    unless ``overwrite`` says otherwise.
    """
    from django.conf import settings as django_settings

    from .ingestion import load_media_manifest, upsert_tmdb_movie, upsert_tmdb_series
    from .tmdb import configured_tmdb_client

    if not obj.tmdb_id:
        return {'error': 'missing_tmdb_id'}
    client = configured_tmdb_client()
    if isinstance(obj, Series):
        details = client.tv_details(obj.tmdb_id)
        synced = upsert_tmdb_series(details)
        synced = synced[0] if isinstance(synced, tuple) else synced
        return {'synced': True, 'tmdb_id': obj.tmdb_id}
    details = client.movie_details(obj.tmdb_id)
    manifest = load_media_manifest(getattr(django_settings, 'CATALOG_MEDIA_MANIFEST', ''))
    synced, created, published, skipped = upsert_tmdb_movie(
        details,
        media_entry=manifest.get(str(obj.tmdb_id)),
        auto_publish=False,
        overwrite_manual=overwrite,
    )
    return {
        'synced': True, 'created': created, 'published': published,
        'skipped_manual_fields': skipped, 'tmdb_id': obj.tmdb_id,
    }


def _act_sync_tmdb(obj, request, body):
    """Pull metadata from TMDB again without touching manual overrides."""
    result = _resync_tmdb(obj, overwrite=bool(body.get('overwrite')))
    if not result.get('error'):
        _audit(
            request, MovieSyncAudit.Action.SYNC,
            movie=obj if isinstance(obj, Movie) else None,
            tmdb_id=obj.tmdb_id, overwrite=bool(body.get('overwrite')),
            details={'kind': _kind_of(obj), 'object_id': obj.pk, 'title': obj.title},
        )
    return result


def _act_resolve_gaps(obj, request, body):
    """Close this title's open gap rows by hand, for a fix made outside the panel."""
    from .playback_sources import resolve_source_gap
    from .playback_subtitle import resolve_playback_subtitle_gaps

    kind = _kind_of(obj)
    sources = resolve_source_gap(obj, last_result='staff_resolved')
    subtitles = resolve_playback_subtitle_gaps(
        content_type=kind, object_id=obj.pk, last_result='staff_resolved',
    )
    _audit(
        request, MovieSyncAudit.Action.MANUAL_UPDATE,
        movie=obj if isinstance(obj, Movie) else None,
        details={'kind': kind, 'object_id': obj.pk, 'title': obj.title, 'reason': 'resolve_gaps'},
    )
    return {'source_gaps_closed': sources, 'subtitle_gaps_closed': subtitles or 0}


#: Everything the desk can do, and whether the caller must confirm it. The map is
#: also the contract the frontend reads, so a button can never name an action the
#: backend does not have.
DESK_ACTIONS = {
    'verify': _act_verify,
    'remove_link': _act_remove_link,
    'add_link': _act_add_link,
    'prune_dead': _act_prune_dead,
    'strip_contaminated': _act_strip_contaminated,
    'recrawl': _act_recrawl,
    'refresh_subtitles': _act_refresh_subtitles,
    'remove_subtitle': _act_remove_subtitle,
    'publish': _act_publish,
    'unpublish': _act_unpublish,
    'archive': _act_archive,
    'sync_tmdb': _act_sync_tmdb,
    'resolve_gaps': _act_resolve_gaps,
}


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def media_desk(request, kind, object_id):
    """One title's playable state, and the controls that change it."""
    obj = _resolve_target(kind, object_id)
    if obj is None:
        return _bad_request('kind must be movie or series', 'unknown_kind')

    if request.method == 'GET':
        return Response(_desk_payload(request, obj))

    body = request.data if isinstance(request.data, dict) else {}
    action = str(body.get('action') or '').strip()
    handler = DESK_ACTIONS.get(action)
    if handler is None:
        return _bad_request(f'unknown action: {action or "(none)"}', 'unknown_action')

    try:
        result = handler(obj, request, body)
    except Exception as exc:  # a failed action must return a reason, not a 500
        logger.exception('admin_ops: action %s failed on %s %s', action, kind, object_id)
        return Response(
            {'detail': str(exc)[:300], 'code': 'action_failed', 'action': action},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if isinstance(result, dict) and result.get('error'):
        return Response({'code': result['error'], 'action': action, **result}, status=status.HTTP_400_BAD_REQUEST)

    obj.refresh_from_db()
    return Response({'action': action, 'result': result, 'desk': _desk_payload(request, obj)})


# --------------------------------------------------------------------------
# Bulk actions
# --------------------------------------------------------------------------

#: Actions that only touch the database. A selection of any size is fine.
BULK_FAST = {'publish', 'unpublish', 'archive', 'prune_dead', 'strip_contaminated', 'resolve_gaps'}
#: Actions that hand work to a worker. Cheap per title, so a large selection is
#: still fine — the cost lands on the queue, not on this request.
BULK_QUEUED = {'recrawl', 'refresh_subtitles'}
#: Actions that talk to the network *inside this request*. Capped hard, because
#: a 200-title verify would hold an HTTP worker for the better part of an hour
#: and time out long before it finished — leaving the admin with no idea how far
#: it got. Small batches that visibly complete beat one that silently dies.
BULK_SLOW = {'verify', 'sync_tmdb'}
BULK_SLOW_LIMIT = 20
BULK_MAX_IDS = 250


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def bulk_action(request):
    """Apply one desk action to a selection of titles.

    Reports per-title outcomes rather than a single success flag: in a batch of
    fifty, three failing for three different reasons is the normal case, and an
    admin needs to see which three.
    """
    body = request.data if isinstance(request.data, dict) else {}
    kind = KIND_ALIASES.get(str(body.get('kind') or '').lower(), '')
    if kind not in KINDS:
        return _bad_request('kind must be movie or series', 'unknown_kind')
    action = str(body.get('action') or '').strip()
    handler = DESK_ACTIONS.get(action)
    if handler is None or action not in (BULK_FAST | BULK_QUEUED | BULK_SLOW):
        return _bad_request(f'action {action or "(none)"} cannot be applied in bulk', 'unknown_action')

    try:
        ids = [int(value) for value in (body.get('ids') or [])][:BULK_MAX_IDS]
    except (TypeError, ValueError):
        return _bad_request('ids must be a list of integers', 'bad_ids')
    if not ids:
        return _bad_request('ids is required', 'bad_ids')
    if action in BULK_SLOW and len(ids) > BULK_SLOW_LIMIT:
        return _bad_request(
            f'«{action}» probes the network for every title; select at most {BULK_SLOW_LIMIT}.',
            'selection_too_large',
        )

    model = KINDS[kind]
    found = {obj.pk: obj for obj in model.objects.filter(pk__in=ids)}
    results = []
    succeeded = failed = 0
    for object_id in ids:
        obj = found.get(object_id)
        if obj is None:
            results.append({'id': object_id, 'ok': False, 'error': 'not_found'})
            failed += 1
            continue
        try:
            outcome = handler(obj, request, body)
        except Exception as exc:
            logger.exception('admin_ops: bulk %s failed on %s %s', action, kind, object_id)
            results.append({'id': object_id, 'title': obj.title, 'ok': False, 'error': str(exc)[:200]})
            failed += 1
            continue
        ok = not (isinstance(outcome, dict) and outcome.get('error'))
        results.append({
            'id': object_id, 'title': obj.title, 'ok': ok,
            'error': (outcome or {}).get('error') if not ok else None,
            'result': outcome if ok else outcome,
        })
        succeeded += 1 if ok else 0
        failed += 0 if ok else 1

    return Response({
        'action': action, 'kind': kind,
        'requested': len(ids), 'succeeded': succeeded, 'failed': failed,
        'results': results,
    })


# --------------------------------------------------------------------------
# Health queues
# --------------------------------------------------------------------------

def _target_label(kind: str, object_id: int, cache: dict) -> dict:
    """Resolve a gap row's target to something a human can click.

    Gap tables store ``content_type``/``object_id``, not a relation, so the
    queues would otherwise render as bare numbers. Batched per queue page.
    """
    return cache.get((kind, object_id)) or {'id': object_id, 'kind': kind, 'title': '', 'slug': ''}


def _label_cache(rows) -> dict:
    wanted = {'movie': set(), 'series': set()}
    for row in rows:
        kind = getattr(row, 'content_type', '')
        if kind in wanted:
            wanted[kind].add(row.object_id)
    cache = {}
    for kind, ids in wanted.items():
        if not ids:
            continue
        for obj in KINDS[kind].objects.filter(pk__in=ids).only('id', 'title', 'slug', 'is_published'):
            cache[(kind, obj.pk)] = {
                'id': obj.pk, 'kind': kind, 'title': obj.title,
                'slug': obj.slug, 'is_published': obj.is_published,
            }
    return cache


def _gap_rows(queryset, limit, offset):
    rows = list(queryset.order_by('-report_count', '-updated_at')[offset:offset + limit])
    cache = _label_cache(rows)
    return [{
        'id': row.id, 'target': _target_label(row.content_type, row.object_id, cache),
        'episode_id': row.episode_id, 'status': row.status, 'reason': row.reason,
        'report_count': row.report_count, 'last_result': row.last_result,
        'updated_at': row.updated_at.isoformat(),
    } for row in rows]


def _open_source_gaps():
    """Published titles a browser cannot play — the queue a viewer is waiting on.

    Deliberately excludes ``no_source`` rows: those are unpublished drafts with no
    download links at all (apps.catalog.draft_sources), a back-archive backlog
    thousands of rows deep that would otherwise bury the handful of titles someone
    is actually staring at a failed player for.
    """
    return (
        PlaybackSourceGap.objects
        .exclude(status=PlaybackSourceGap.Status.RESOLVED)
        .exclude(reason=DRAFT_GAP_REASON)
    )


def _sourceless_draft_gaps():
    """Unpublished titles with no download links, waiting for a provider match."""
    return (
        PlaybackSourceGap.objects
        .filter(reason=DRAFT_GAP_REASON)
        .exclude(status=PlaybackSourceGap.Status.RESOLVED)
    )


def _queue_source_gaps(limit, offset):
    return _gap_rows(_open_source_gaps(), limit, offset)


def _queue_sourceless_drafts(limit, offset):
    return _gap_rows(_sourceless_draft_gaps(), limit, offset)


def _queue_subtitle_gaps(limit, offset):
    rows = list(
        PlaybackSubtitleGap.objects
        .exclude(status=PlaybackSubtitleGap.Status.RESOLVED)
        .order_by('-report_count', '-updated_at')[offset:offset + limit]
    )
    cache = _label_cache(rows)
    return [{
        'id': row.id, 'target': _target_label(row.content_type, row.object_id, cache),
        'episode_id': row.episode_id, 'status': row.status,
        'report_count': row.report_count, 'last_result': row.last_result,
        'updated_at': row.updated_at.isoformat(),
    } for row in rows]


def _queue_failed_checks(limit, offset):
    rows = list(
        MediaCheck.objects.filter(status=MediaCheck.Status.FAILED)
        .order_by('-updated_at')[offset:offset + limit]
    )
    cache = _label_cache(rows)
    return [{
        'id': row.id, 'target': _target_label(row.content_type, row.object_id, cache),
        'episode_id': row.episode_id, 'status': row.status, 'reason': row.reason,
        'checked_urls': row.checked_urls, 'dead_urls': row.dead_urls,
        'attempts': row.attempts,
        'checked_at': row.checked_at.isoformat() if row.checked_at else None,
        'updated_at': row.updated_at.isoformat(),
    } for row in rows]


def _queue_reports(limit, offset):
    rows = list(
        ContentIssueReport.objects
        .exclude(status__in=[ContentIssueReport.Status.RESOLVED, ContentIssueReport.Status.REJECTED])
        .order_by('-report_count', '-updated_at')[offset:offset + limit]
    )
    cache = _label_cache(rows)
    return [{
        **_report_row(row),
        'target': _target_label(row.content_type, row.object_id, cache),
    } for row in rows]


def _unverified_queryset(model, kind):
    """Published titles whose media verdict is missing or stale.

    These are the ones the site is currently telling viewers it can play without
    anyone having checked — the gap the verification sweep exists to close, made
    visible so staff can see whether it is keeping up.
    """
    from .media_verification import FRESH_SECONDS

    cutoff = timezone.now() - timedelta(seconds=FRESH_SECONDS)
    fresh_ids = MediaCheck.objects.filter(
        content_type=kind, episode_id=0, checked_at__gte=cutoff,
    ).values_list('object_id', flat=True)
    return model.objects.filter(is_published=True).exclude(pk__in=fresh_ids)


def _queue_unverified(limit, offset):
    rows = []
    for kind, model in KINDS.items():
        for obj in _unverified_queryset(model, kind).order_by('-updated_at')[:limit]:
            rows.append({
                'target': {
                    'id': obj.pk, 'kind': kind, 'title': obj.title,
                    'slug': obj.slug, 'is_published': obj.is_published,
                },
                'updated_at': obj.updated_at.isoformat(),
                'link_count': len([i for i in (obj.download_links or []) if isinstance(i, dict)]),
            })
    rows.sort(key=lambda row: row['updated_at'], reverse=True)
    return rows[offset:offset + limit]


def _incomplete_filter():
    """DB-expressible half of :func:`completeness.publish_blockers`.

    ``metadata_gaps`` walks relations per row, so it cannot drive a catalog-wide
    query. These four conditions are the blockers that live on the row itself and
    account for nearly every incomplete title in practice; the per-title gap list
    on the desk stays authoritative.
    """
    return (
        Q(imdb_rating__isnull=True) | Q(imdb_rating__lte=0)
        | Q(description='') | Q(original_title='')
        | (Q(poster='') & Q(poster_external_url=''))
    )


def _queue_incomplete(limit, offset):
    rows = []
    for kind, model in KINDS.items():
        queryset = model.objects.filter(is_published=True).filter(_incomplete_filter())
        for obj in queryset.order_by('-updated_at')[:limit]:
            rows.append({
                'target': {
                    'id': obj.pk, 'kind': kind, 'title': obj.title,
                    'slug': obj.slug, 'is_published': obj.is_published,
                },
                'gaps': publish_blockers_safe(obj),
                'updated_at': obj.updated_at.isoformat(),
            })
    rows.sort(key=lambda row: row['updated_at'], reverse=True)
    return rows[offset:offset + limit]


#: Rating provenance that means "this is IMDb's own number". Anything else on a
#: published title is a placeholder the six-hourly sync has not replaced yet.
EXACT_RATING_SOURCES = ('imdb', 'omdb', 'manual')


def _approx_rating_filter():
    """Published titles still showing a score that is not IMDb's.

    Restricted to rows that carry an ``imdb_id``: without one there is nothing
    to look the real score up by, so listing them would be asking an admin to
    fix something no action can fix.
    """
    return (
        Q(is_published=True)
        & ~Q(imdb_id__isnull=True) & ~Q(imdb_id='')
        & ~Q(imdb_rating_source__in=EXACT_RATING_SOURCES)
    )


def _queue_approx_ratings(limit, offset):
    rows = []
    for kind, model in KINDS.items():
        queryset = model.objects.filter(_approx_rating_filter())
        for obj in queryset.order_by('-updated_at')[:limit]:
            rows.append({
                'target': {
                    'id': obj.pk, 'kind': kind, 'title': obj.title,
                    'slug': obj.slug, 'is_published': obj.is_published,
                },
                'imdb_id': obj.imdb_id,
                'imdb_rating': float(obj.imdb_rating) if obj.imdb_rating is not None else None,
                'status': obj.imdb_rating_source or 'unset',
                'status_label': 'تقریبی (TMDB)' if obj.imdb_rating_source == 'tmdb' else 'بدون منبع',
                'updated_at': obj.updated_at.isoformat(),
            })
    rows.sort(key=lambda row: row['updated_at'], reverse=True)
    return rows[offset:offset + limit]


def publish_blockers_safe(obj) -> list[str]:
    from .completeness import publish_blockers

    try:
        return publish_blockers(obj)
    except Exception:
        return []


QUEUES = {
    'source_gaps': _queue_source_gaps,
    'subtitle_gaps': _queue_subtitle_gaps,
    'failed_checks': _queue_failed_checks,
    'reports': _queue_reports,
    'unverified': _queue_unverified,
    'incomplete': _queue_incomplete,
    'approx_ratings': _queue_approx_ratings,
    'sourceless_drafts': _queue_sourceless_drafts,
}


def _health_counts() -> dict:
    from .media_verification import FRESH_SECONDS

    cutoff = timezone.now() - timedelta(seconds=FRESH_SECONDS)
    unverified = 0
    incomplete = 0
    approx_ratings = 0
    for kind, model in KINDS.items():
        fresh_ids = MediaCheck.objects.filter(
            content_type=kind, episode_id=0, checked_at__gte=cutoff,
        ).values_list('object_id', flat=True)
        unverified += model.objects.filter(is_published=True).exclude(pk__in=fresh_ids).count()
        incomplete += model.objects.filter(is_published=True).filter(_incomplete_filter()).count()
        approx_ratings += model.objects.filter(_approx_rating_filter()).count()
    return {
        'source_gaps': _open_source_gaps().count(),
        'sourceless_drafts': _sourceless_draft_gaps().count(),
        'subtitle_gaps': PlaybackSubtitleGap.objects.exclude(status=PlaybackSubtitleGap.Status.RESOLVED).count(),
        'failed_checks': MediaCheck.objects.filter(status=MediaCheck.Status.FAILED).count(),
        'reports': ContentIssueReport.objects.exclude(status__in=[
            ContentIssueReport.Status.RESOLVED, ContentIssueReport.Status.REJECTED,
        ]).count(),
        'unverified': unverified,
        'incomplete': incomplete,
        'approx_ratings': approx_ratings,
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def catalog_health(request):
    """The problem queues — every title the platform already knows is broken.

    Every count always comes back, so the page can show its tabs in one request;
    only the requested queue's rows are materialised.
    """
    queue = str(request.GET.get('queue') or 'source_gaps')
    if queue not in QUEUES:
        return _bad_request(f'unknown queue: {queue}', 'unknown_queue')
    try:
        limit = max(1, min(int(request.GET.get('limit') or 50), 200))
        offset = max(0, int(request.GET.get('offset') or 0))
    except (TypeError, ValueError):
        limit, offset = 50, 0
    return Response({
        'queue': queue,
        'counts': _health_counts(),
        'results': QUEUES[queue](limit, offset),
        'limit': limit,
        'offset': offset,
    })


# --------------------------------------------------------------------------
# Crawler / queue operations
# --------------------------------------------------------------------------

#: The lanes declared in ``CELERY_TASK_ROUTES``, with what each one is for. The
#: panel shows depth per lane because that is the only number that explains a
#: stalled crawl: a 50k-deep ``softsub`` backlog and an empty ``celery`` lane
#: mean something completely different from the reverse.
QUEUE_LANES = (
    ('celery', 'نگهداری و زمان‌بندی'),
    ('imports', 'ایمپورت و خزش'),
    ('softsub', 'استخراج زیرنویس (انبوه)'),
    ('softsub-urgent', 'زیرنویس فوری پلیر'),
    ('support', 'پشتیبانی و گزارش‌ها'),
)


def _queue_depths() -> list[dict]:
    """Messages waiting per Celery lane, straight from the broker.

    Read-only and best-effort: a broker hiccup must degrade the page to "unknown",
    never 500 it, because this is the page an admin opens *because* something is
    wrong with the workers.
    """
    from django.conf import settings as django_settings

    try:
        import redis

        client = redis.from_url(django_settings.CELERY_BROKER_URL, socket_timeout=2)
        depths = []
        for name, label in QUEUE_LANES:
            try:
                depths.append({'queue': name, 'label': label, 'depth': int(client.llen(name))})
            except Exception:
                depths.append({'queue': name, 'label': label, 'depth': None})
        return depths
    except Exception:
        return [{'queue': name, 'label': label, 'depth': None} for name, label in QUEUE_LANES]


#: Each ``inspect`` call is a broadcast that waits out its *whole* timeout even
#: after every worker has answered — there is no "all replies in" signal. Two
#: calls at 2s each cost this page 4.7s of its 5.4s on the production host, so
#: the budget is small on purpose: workers share a Redis broker on the same
#: docker network and answer in milliseconds, and a worker that cannot make 1s
#: round-trip is not healthy anyway.
WORKER_PING_TIMEOUT = 1.0


def _worker_ping() -> dict:
    """Which workers answer, and which lanes they are consuming."""
    try:
        from config.celery import app as celery_app

        inspector = celery_app.control.inspect(timeout=WORKER_PING_TIMEOUT)
        active = inspector.active() or {}
        consumers = inspector.active_queues() or {}
        return {
            'reachable': True,
            'workers': [
                {
                    'name': name,
                    'active_tasks': len(active.get(name) or []),
                    'queues': sorted({q.get('name') for q in (consumers.get(name) or []) if q.get('name')}),
                }
                for name in sorted(set(active) | set(consumers))
            ],
        }
    except Exception:
        return {'reachable': False, 'workers': []}


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def ops_overview(request):
    """The crawlers themselves: lanes, workers, jobs and catalog totals."""
    from .importer_config import get_importer_settings
    from .models import CatalogSyncRun, ProviderSource

    now = timezone.now()
    day_ago = now - timedelta(days=1)

    jobs = ProviderImportJob.objects.all()
    active_statuses = [
        ProviderImportJob.Status.QUEUED, ProviderImportJob.Status.VALIDATING,
        ProviderImportJob.Status.SEARCHING, ProviderImportJob.Status.AWAITING_REVIEW,
        ProviderImportJob.Status.RUNNING, ProviderImportJob.Status.TRANSFERRING,
        ProviderImportJob.Status.CANCEL_REQUESTED,
    ]
    settings_row = get_importer_settings()

    catalog = {}
    for kind, model in KINDS.items():
        total = model.objects.count()
        published = model.objects.filter(is_published=True).count()
        entry = {'total': total, 'published': published, 'draft': total - published}
        if model is Movie:
            entry['archived'] = model.objects.filter(
                publication_status=Movie.PublicationStatus.ARCHIVED,
            ).count()
        catalog[kind] = entry

    return Response({
        'queues': _queue_depths(),
        'workers': _worker_ping(),
        'jobs': {
            'active': jobs.filter(status__in=active_statuses).count(),
            'last_24h': jobs.filter(created_at__gte=day_ago).count(),
            'by_status': {
                row['status']: row['count']
                for row in jobs.filter(created_at__gte=day_ago).values('status').annotate(count=Count('id'))
            },
            'recent': [
                {
                    'id': str(job.id), 'provider': job.provider.name,
                    'status': job.status, 'mode': job.mode, 'trigger': job.trigger,
                    'label': job.current_item_label,
                    'processed': job.processed_items, 'total': job.total_items,
                    'matched': job.matched_items, 'failed': job.failed_items,
                    'error_message': job.error_message,
                    'created_at': job.created_at.isoformat(),
                    'finished_at': job.finished_at.isoformat() if job.finished_at else None,
                }
                for job in jobs.select_related('provider').order_by('-created_at')[:15]
            ],
        },
        'providers': [
            {
                'id': provider.id, 'name': provider.name, 'slug': provider.slug,
                'type': provider.provider_type, 'base_url': provider.base_url,
                'is_active': provider.is_active,
                'rate_limit_per_minute': provider.rate_limit_per_minute,
                'jobs_24h': jobs.filter(provider=provider, created_at__gte=day_ago).count(),
            }
            for provider in ProviderSource.objects.order_by('name')
        ],
        'sync_runs': [
            {
                'id': run.id, 'status': run.status, 'mode': run.mode, 'phase': run.phase,
                'processed': run.processed_count, 'total': run.total_count,
                'created': run.created_count, 'updated': run.updated_count,
                'errors': run.error_count,
                'started_at': run.started_at.isoformat(),
                'finished_at': run.finished_at.isoformat() if run.finished_at else None,
            }
            for run in CatalogSyncRun.objects.order_by('-started_at')[:5]
        ],
        'importer_settings': {
            'auto_publish': getattr(settings_row, 'auto_publish', None),
            'fetch_imdb_ratings': getattr(settings_row, 'fetch_imdb_ratings', None),
            'automation_enabled': getattr(settings_row, 'automation_enabled', None),
            'automation_mode': getattr(settings_row, 'automation_mode', None),
            'automation_interval_hours': getattr(settings_row, 'automation_interval_hours', None),
            'daily_max_pages': getattr(settings_row, 'daily_max_pages', None),
        },
        'catalog': catalog,
        'health': _health_counts(),
        'generated_at': now.isoformat(),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def audit_feed(request):
    """Who changed what, newest first — the panel's answer to "why is this gone?"."""
    queryset = MovieSyncAudit.objects.select_related('actor', 'movie')
    action = (request.GET.get('action') or '').strip()
    if action in dict(MovieSyncAudit.Action.choices):
        queryset = queryset.filter(action=action)
    movie_id = (request.GET.get('movie_id') or '').strip()
    if movie_id.isdigit():
        queryset = queryset.filter(movie_id=int(movie_id))
    try:
        limit = max(1, min(int(request.GET.get('limit') or 50), 200))
        offset = max(0, int(request.GET.get('offset') or 0))
    except (TypeError, ValueError):
        limit, offset = 50, 0
    rows = queryset[offset:offset + limit]
    return Response({
        'count': queryset.count(),
        'limit': limit,
        'offset': offset,
        'results': [
            {**_audit_row(entry), 'movie_title': getattr(entry.movie, 'title', '') or ''}
            for entry in rows
        ],
    })
