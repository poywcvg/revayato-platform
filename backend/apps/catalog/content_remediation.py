"""Auto-remediation engine for viewer :class:`ContentIssueReport` rows.

A viewer taps «گزارش خطا» in the web or Android player and picks *what* is
wrong. This module turns that one machine-readable ``problem_type`` into the
right, already-battle-tested fix — no free-text parsing, no guesswork.

The buttons themselves live in :mod:`apps.catalog.report_catalog`, and the rule
there is the rule here: a symptom earns its own button only because this module
does something *different* with it. The table below is that mapping.

================= ===============================================================
problem_type      remediation
================= ===============================================================
playback          :func:`apps.catalog.playback_sources.remediate` re-crawls
                  providers for a browser-safe (HLS/MP4 + H.264) mirror.
buffering         Re-probes every mirror, prunes the ones a host reports gone,
                  then re-crawls. All mirrors healthy → viewer-side, not ours.
audio_silent      ffprobe reads the audio codec. DTS/TrueHD/(E-)AC-3 is decoded
                  by no browser and raises no player error, so it is re-crawled
                  for an AAC mirror and confirmed by a second probe.
audio_desync      Drift is baked into the encode; only a different encode fixes
                  it. Re-crawl, then a human if the pool had no alternative.
subtitle_missing  :func:`apps.catalog.playback_subtitle.ensure_playback_subtitles`
                  re-runs the SoftSub pipeline (embedded → SubtitleStar → Subzone)
                  and opens/refreshes a ``PlaybackSubtitleGap`` the worker drains.
subtitle_sync     Same pipeline, whose store path re-checks cue spans against the
                  encode's real runtime and bakes in a framerate correction.
subtitle_garbled  Same pipeline, but the unusable track is deleted first — else
                  the "already has subtitles" short-circuit re-serves it.
wrong_title       :func:`link_integrity.filter_contaminated_links` strips CDN links
                  that provably belong to a different film, then re-crawls a
                  correct source. If nothing is provably wrong → needs review.
wrong_episode     Same link-integrity strip scoped to the series, then a fresh
                  provider re-crawl of the episode. Unprovable → needs review.
quality           ffprobe settles it: a source shorter than its label promises is
                  mislabelled and re-crawled; one that matches goes to a human.
download_dead     Probes every stored download link, drops the dead ones, and
                  re-crawls to refill the pool.
other             No machine-readable symptom → queued for a human (in the inbox).
================= ===============================================================

Everything here is idempotent and conservative: the link-integrity classifier
only drops a link when the encoded CDN identity *proves* a different title, so
remediation can never blank out a legitimate title by mistake. In the same
spirit, a handler reports ``needs_review`` or ``unavailable`` rather than
``resolved`` whenever it could not verify the viewer's symptom is actually gone
— a report marked fixed that is not fixed is worse than one still open. The
entry point is :func:`remediate_report`; the batch drainer is
:func:`remediate_open_reports`, exposed to operators as
``manage.py remediate_content_reports``.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

# --- retry policy -----------------------------------------------------------
# A report that could not be fixed on the spot is retried on a widening backoff
# (minutes since its last attempt, indexed by ``attempts``) instead of a flat cap:
# a provider that adds a browser-safe mirror tomorrow still gets picked up, and a
# permanently unfixable title stops costing crawl time after MAX_AUTO_ATTEMPTS and
# is handed to a human (status ``needs_review``, action ``auto_exhausted``).
MAX_AUTO_ATTEMPTS = 8
_BACKOFF_MINUTES = (0, 10, 30, 60, 180, 360, 720, 1440)
# A row stuck in REMEDIATING (worker killed mid-crawl) is recovered after this.
STALE_REMEDIATING_SECONDS = 900
# Two callers (the report task and the linked ticket) must not both crawl the same
# title back-to-back; a remediation newer than this is reused, not repeated.
RECENT_REMEDIATION_SECONDS = 300
_LOCK_TTL_SECONDS = 600

_TERMINAL = frozenset({'resolved', 'rejected'})


def _backoff_seconds(attempts: int) -> int:
    idx = min(max(int(attempts or 0), 0), len(_BACKOFF_MINUTES) - 1)
    return _BACKOFF_MINUTES[idx] * 60


@contextmanager
def _report_lock(report_id: int):
    """Best-effort cross-worker mutex so one report is never crawled twice at once."""
    key = f'content_report:remediating:{int(report_id)}'
    acquired = False
    try:
        acquired = bool(cache.add(key, '1', _LOCK_TTL_SECONDS))
    except Exception:  # noqa: BLE001 — a cache outage must not stop remediation
        acquired = True
    try:
        yield acquired
    finally:
        if acquired:
            try:
                cache.delete(key)
            except Exception:  # noqa: BLE001
                pass


# --- resolution helpers ----------------------------------------------------

def _resolve_target(report):
    """Return ``(obj, episode)`` for a report, or ``(None, None)`` if gone.

    ``obj`` is the Movie or Series; ``episode`` is the Episode for a scoped
    series report, else ``None``.
    """
    from apps.catalog.models import Episode, Movie, Series

    if report.content_type == 'movie':
        return Movie.objects.filter(pk=report.object_id).first(), None

    series = Series.objects.filter(pk=report.object_id).first()
    episode = None
    if report.episode_id:
        episode = (
            Episode.objects.select_related('season__series')
            .filter(pk=report.episode_id)
            .first()
        )
    return series, episode


def target_playable(obj, episode=None) -> bool:
    """Crawl-free truth: can a strict browser play the thing that was reported?

    Episode-scoped reports are judged on the episode's *own* source (a series with
    one HLS episode is "playable" at series level while episode 27 is still an
    ``.mkv``). Movie/series-wide reports use the title-level diagnosis.
    """
    from apps.catalog import playback_sources

    if episode is not None:
        return playback_sources.episode_browser_safe(episode)
    return not playback_sources.browser_unplayable(obj)


def _mark(report, *, status, action='', result='', remediated=False, **meta_updates):
    """Persist a remediation outcome on the report in one place."""
    now = timezone.now()
    report.status = status
    if action:
        report.remediation_action = action
    report.last_result = (result or '')[:200]
    report.attempts = (report.attempts or 0) + 1
    if remediated:
        report.remediated_at = now
    if status in {'resolved', 'rejected', 'unavailable'}:
        report.resolved_at = now
    if meta_updates:
        merged = dict(report.meta or {})
        merged.update(meta_updates)
        report.meta = merged
    report.save(update_fields=[
        'status', 'remediation_action', 'last_result', 'attempts',
        'remediated_at', 'resolved_at', 'meta', 'updated_at',
    ])
    return {
        'report_id': report.pk,
        'status': report.status,
        'action': report.remediation_action,
        'result': report.last_result,
    }


# --- per-problem remediation ----------------------------------------------

def _remediate_subtitle(report, obj, episode) -> dict[str, Any]:
    from apps.catalog.playback_subtitle import ensure_playback_subtitles

    result = ensure_playback_subtitles(
        content_type=report.content_type,
        slug=report.slug or getattr(obj, 'slug', ''),
        episode_id=report.episode_id or (episode.pk if episode else 0),
        playback_version=report.playback_version,
        playback_source_url=report.source_url,
        sync=True,
        timeout_seconds=14,
    )
    state = str(result.get('status') or result.get('state') or '').lower()
    ready = bool(result.get('ready') or state in {'ready', 'resolved', 'attached'})
    if ready:
        return _mark(
            report, status='resolved', action='subtitle_ensure',
            result=f'softsub_ready:{state or "ok"}', remediated=True,
            ensure=result,
        )
    # Not instant — the SoftSub worker owns the long tail; the gap it opened is
    # drained by extract_softsub_tracks / drain_playback_gaps.
    return _mark(
        report, status='queued', action='subtitle_ensure',
        result=f'softsub_queued:{state or "pending"}',
        ensure=result, softsub_report_id=result.get('report_id'),
    )


def _remediate_playback(report, obj, episode) -> dict[str, Any]:
    from apps.catalog import playback_sources

    # Already fine (a crawler landed a mirror since the viewer looked): no network.
    if target_playable(obj, episode):
        return _mark(
            report, status='resolved', action='playback_recheck',
            result='browser_safe:already_playable', remediated=True,
        )

    outcome = playback_sources.remediate(episode or obj)
    # ``remediate`` reports under the key ``outcome`` (refreshed / unavailable /
    # provider_error). Re-judge the *reported* target ourselves: for an episode the
    # series-level "refreshed" verdict says nothing about that episode's own source.
    state = str(outcome.get('outcome') or '').lower()
    if episode is not None:
        episode.refresh_from_db(fields=['video_url'])
    detail = {
        'outcome': state,
        'codes': outcome.get('codes'),
        'reason': (outcome.get('diag_after') or {}).get('reason', ''),
    }

    if target_playable(obj, episode):
        return _mark(
            report, status='resolved', action='playback_recrawl',
            result=f'browser_safe:{state or "ok"}', remediated=True, playback=detail,
        )
    if state == 'provider_error':
        # Every provider failed transiently — the drain retries on its backoff.
        return _mark(
            report, status='queued', action='playback_recrawl',
            result='provider_error:retry_later', playback=detail,
        )
    reason = detail['reason'] or ('episode_source_not_browser_safe' if episode is not None else 'no_browser_safe')
    return _mark(
        report, status='unavailable', action='playback_recrawl',
        result=f'no_browser_safe_source:{reason}'[:200], playback=detail,
    )


def _strip_wrong_links(report, obj, *, action: str) -> dict[str, Any]:
    """Shared body for wrong_title / wrong_episode.

    Runs the link-integrity classifier over the object's download links,
    persists the survivors, then re-crawls providers for a correct source.
    A report whose target has no *provably* wrong link is escalated for human
    review rather than silently closed — the viewer may be right about a
    mismatch the CDN path can't reveal.
    """
    from apps.catalog import playback_sources
    from apps.catalog.provider_import.link_integrity import filter_contaminated_links

    links = list(getattr(obj, 'download_links', None) or [])
    kept, dropped = filter_contaminated_links(obj, links)
    dropped_cats = [cat for _item, cat in dropped]

    if dropped:
        with transaction.atomic():
            locked = type(obj).objects.select_for_update().get(pk=obj.pk)
            locked.download_links = kept
            locked.save(update_fields=['download_links', 'updated_at'])
        obj = locked
        # A fresh, correct source to replace what we just removed.
        recrawl = playback_sources.remediate(obj)
        return _mark(
            report, status='resolved', action=action,
            result=f'stripped_{len(dropped)}_wrong_link(s):{",".join(sorted(set(dropped_cats)))[:80]}',
            remediated=True, dropped=dropped_cats, kept_count=len(kept), recrawl=recrawl,
        )

    # Nothing provably wrong from the CDN identity. Re-crawl anyway (a fresh
    # correct mirror often supersedes a bad one) and flag for review.
    recrawl = playback_sources.remediate(obj)
    return _mark(
        report, status='needs_review', action=action,
        result='no_provable_mismatch:recrawled_and_escalated',
        recrawl=recrawl, kept_count=len(kept),
    )


def _remediate_wrong_title(report, obj, episode) -> dict[str, Any]:
    return _strip_wrong_links(report, obj, action='wrong_title_integrity')


def _remediate_wrong_episode(report, obj, episode) -> dict[str, Any]:
    # Series-scoped: the classifier catches wrong-*series* contamination on the
    # series link pool; a fresh episode re-crawl handles wrong-episode files.
    return _strip_wrong_links(report, obj, action='wrong_episode_integrity')


def _source_for(report, obj, episode) -> str:
    """The URL the viewer was actually watching, else the target's own stream."""
    url = (report.source_url or '').strip()
    if url:
        return url
    owner = episode if episode is not None else obj
    return str(getattr(owner, 'video_url', '') or '').strip()


def _remediate_buffering(report, obj, episode) -> dict[str, Any]:
    """Constant stalling is a half-dead mirror, not a missing title.

    The media check asks every source for its first bytes and prunes only the
    ones a host positively reports gone; a re-crawl then replaces what it took.
    When every source answers healthily the problem is between the viewer and
    the CDN, and saying so beats staging a repair that fixes nothing.
    """
    from apps.catalog import playback_sources
    from apps.catalog.media_verification import verify_target

    verdict = verify_target(obj, episode=episode, use_cache=False)
    detail = {
        'status': verdict.get('status'), 'reason': verdict.get('reason'),
        'checked': verdict.get('checked'), 'dead': verdict.get('dead'),
    }
    if not verdict.get('dead'):
        return _mark(
            report, status='needs_review', action='buffering_probe',
            result=f'all_sources_healthy:{verdict.get("reason") or "ok"}'[:200],
            probe=detail,
        )

    outcome = playback_sources.remediate(episode or obj)
    if target_playable(obj, episode):
        return _mark(
            report, status='resolved', action='buffering_recrawl',
            result=f'pruned_{verdict.get("dead")}_stalled_mirror(s)', remediated=True,
            probe=detail, recrawl=outcome,
        )
    return _mark(
        report, status='queued', action='buffering_recrawl',
        result=f'pruned_{verdict.get("dead")}_stalled_mirror(s):awaiting_replacement',
        probe=detail, recrawl=outcome,
    )


def _remediate_audio_silent(report, obj, episode) -> dict[str, Any]:
    """Picture but no sound is a codec fact, and ffprobe can simply read it.

    DTS, TrueHD and (E-)AC-3 are the usual culprits: the browser decodes the
    picture and drops the audio track without ever raising an error, which is
    why this never surfaces as a playback failure and the gateway's on-error
    fallback never engages. A mirror with AAC is the real cure, so we re-crawl
    and re-probe rather than declaring victory.
    """
    from apps.catalog import media_tech, playback_sources

    url = _source_for(report, obj, episode)
    tech = media_tech.verify_source(url) if url else {'verdict': 'unknown', 'reason': 'no_source'}
    audio = (tech.get('audio') or '').lower()

    if audio and audio not in media_tech.BROWSER_UNSAFE_AUDIO:
        # The track is one browsers decode, so silence is not this file's doing.
        return _mark(
            report, status='needs_review', action='audio_probe',
            result=f'audio_codec_is_playable:{audio}'[:200], tech=tech,
        )
    if not audio and tech.get('verdict') == 'unknown':
        return _mark(
            report, status='queued', action='audio_probe',
            result=f'codec_unknown:{tech.get("reason") or "not_probed"}'[:200], tech=tech,
        )

    outcome = playback_sources.remediate(episode or obj)
    fresh = _source_for(report, obj, episode)
    after = media_tech.verify_source(fresh, refresh=True) if fresh and fresh != url else {}
    new_audio = (after.get('audio') or '').lower()
    if new_audio and new_audio not in media_tech.BROWSER_UNSAFE_AUDIO:
        return _mark(
            report, status='resolved', action='audio_recrawl',
            result=f'replaced_{audio or "unknown"}_with_{new_audio}'[:200],
            remediated=True, tech=tech, tech_after=after, recrawl=outcome,
        )
    # Nothing with browser-decodable audio exists upstream yet. The picture
    # still plays, so this is a real but partial failure, named precisely.
    return _mark(
        report, status='unavailable', action='audio_recrawl',
        result=f'no_browser_safe_audio:{audio or "unknown"}'[:200],
        tech=tech, tech_after=after, recrawl=outcome, requires_gateway=True,
    )


def _remediate_audio_desync(report, obj, episode) -> dict[str, Any]:
    """Audio drifting from picture is baked into the encode; only another
    encode fixes it. We re-crawl for a different mirror and hand the report to a
    human if the pool had nothing else — there is no safe way to "repair" A/V
    drift in a file we do not own.
    """
    from apps.catalog import playback_sources

    before = _source_for(report, obj, episode)
    outcome = playback_sources.remediate(episode or obj)
    after = _source_for(report, obj, episode)
    if after and after != before:
        return _mark(
            report, status='queued', action='audio_desync_recrawl',
            result='swapped_to_a_different_encode:awaiting_confirmation',
            recrawl=outcome,
        )
    return _mark(
        report, status='needs_review', action='audio_desync_recrawl',
        result='no_alternative_encode:escalated', recrawl=outcome,
    )


def _remediate_subtitle_sync(report, obj, episode) -> dict[str, Any]:
    """A mistimed subtitle is checkable: cue spans against the encode's real
    runtime. The store path bakes in a framerate correction when one clean ratio
    explains the drift, so re-running the pipeline is what applies the fix.
    """
    return _resubtitle(report, obj, episode, action='subtitle_resync', drop_current=False)


def _remediate_subtitle_garbled(report, obj, episode) -> dict[str, Any]:
    """Mojibake or plain wrong text: the stored file is unusable, so it is
    removed before re-running the pipeline — otherwise the "already has a
    track" short-circuit would hand the viewer the same broken file again.
    """
    return _resubtitle(report, obj, episode, action='subtitle_refetch', drop_current=True)


def _drop_subtitle_tracks(obj, episode) -> int:
    """Clear stored cues on the row that owns them. Returns how many went."""
    from apps.catalog.models import Movie

    owner = episode if episode is not None else obj
    tracks = list(getattr(owner, 'subtitle_tracks', None) or [])
    if not tracks:
        return 0
    with transaction.atomic():
        locked = type(owner).objects.select_for_update().get(pk=owner.pk)
        locked.subtitle_tracks = []
        fields = ['subtitle_tracks', 'updated_at']
        # ``has_subtitle`` is the catalog-level flag the cards and filters read.
        if isinstance(locked, Movie) and hasattr(locked, 'has_subtitle'):
            locked.has_subtitle = False
            fields.insert(1, 'has_subtitle')
        locked.save(update_fields=fields)
    return len(tracks)


def _resubtitle(report, obj, episode, *, action: str, drop_current: bool) -> dict[str, Any]:
    from apps.catalog.playback_subtitle import ensure_playback_subtitles

    dropped = _drop_subtitle_tracks(obj, episode) if drop_current else 0
    result = ensure_playback_subtitles(
        content_type=report.content_type,
        slug=report.slug or getattr(obj, 'slug', ''),
        episode_id=report.episode_id or (episode.pk if episode else 0),
        playback_version=report.playback_version,
        playback_source_url=report.source_url,
        sync=True,
        timeout_seconds=14,
    )
    state = str(result.get('status') or result.get('state') or '').lower()
    ready = bool(result.get('ready') or state in {'ready', 'resolved', 'attached'})
    if ready:
        return _mark(
            report, status='resolved', action=action,
            result=f'subtitle_replaced:{state or "ok"}'[:200], remediated=True,
            ensure=result, dropped_tracks=dropped,
        )
    return _mark(
        report, status='queued', action=action,
        result=f'subtitle_queued:{state or "pending"}'[:200],
        ensure=result, dropped_tracks=dropped, softsub_report_id=result.get('report_id'),
    )


def _remediate_quality(report, obj, episode) -> dict[str, Any]:
    """"Blurry" is only actionable when the file really is smaller than its
    label claims, which ffprobe settles. A 1080p-labelled 640×360 file is a
    mislabelled source worth replacing; a genuine 1080p file that looks soft to
    the viewer is not something a re-crawl improves.
    """
    from apps.catalog import media_tech, playback_sources

    url = _source_for(report, obj, episode)
    tech = media_tech.verify_source(url) if url else {}
    height = int(tech.get('height') or 0)
    claimed = (report.playback_version or '').lower()
    promised = 1080 if '1080' in claimed else 720 if '720' in claimed else 480 if '480' in claimed else 0

    if height and promised and height >= promised - 80:
        return _mark(
            report, status='needs_review', action='quality_probe',
            result=f'source_matches_label:{height}p_vs_{promised}p', tech=tech,
        )
    outcome = playback_sources.remediate(episode or obj)
    detail = f'{height or "unknown"}p_below_{promised or "unlabelled"}'
    return _mark(
        report, status='queued', action='quality_recrawl',
        result=f'recrawled_for_better_source:{detail}'[:200], tech=tech, recrawl=outcome,
    )


def _remediate_download(report, obj, episode) -> dict[str, Any]:
    """A download link that does nothing is the media check's home ground: it
    probes every stored link, drops the ones a host reports gone, and a re-crawl
    refills the pool. Links that all answer fine mean the failure was local to
    the viewer, which we report instead of churning the catalog.
    """
    from apps.catalog import playback_sources
    from apps.catalog.media_verification import verify_target

    verdict = verify_target(obj, episode=episode, use_cache=False)
    detail = {
        'status': verdict.get('status'), 'reason': verdict.get('reason'),
        'checked': verdict.get('checked'), 'dead': verdict.get('dead'),
    }
    if not verdict.get('dead'):
        if verdict.get('downloadable'):
            return _mark(
                report, status='needs_review', action='download_probe',
                result='every_link_serves:viewer_side_failure', probe=detail,
            )
        return _mark(
            report, status='queued', action='download_probe',
            result=f'links_unreachable:{verdict.get("reason") or "unknown"}'[:200],
            probe=detail,
        )

    outcome = playback_sources.remediate(obj)
    obj.refresh_from_db(fields=['download_links'])
    if list(getattr(obj, 'download_links', None) or []):
        return _mark(
            report, status='resolved', action='download_repair',
            result=f'dropped_{verdict.get("dead")}_dead_link(s):pool_refilled',
            remediated=True, probe=detail, recrawl=outcome,
        )
    return _mark(
        report, status='unavailable', action='download_repair',
        result=f'dropped_{verdict.get("dead")}_dead_link(s):nothing_left',
        probe=detail, recrawl=outcome,
    )


_DISPATCH = {
    'playback': _remediate_playback,
    'buffering': _remediate_buffering,
    'audio_silent': _remediate_audio_silent,
    'audio_desync': _remediate_audio_desync,
    'subtitle_missing': _remediate_subtitle,
    'subtitle_sync': _remediate_subtitle_sync,
    'subtitle_garbled': _remediate_subtitle_garbled,
    'wrong_title': _remediate_wrong_title,
    'wrong_episode': _remediate_wrong_episode,
    'quality': _remediate_quality,
    'download_dead': _remediate_download,
    # Retired spellings: rows written before the split still dispatch.
    'subtitle': _remediate_subtitle,
    'audio': _remediate_audio_silent,
}


# --- public entry points ---------------------------------------------------

def recheck_report(report) -> bool:
    """Crawl-free self-heal: close a playback report whose target now plays.

    Pure DB read. The dedicated playback crawler lands browser-safe mirrors
    on its own schedule; this is how a viewer's report notices that without
    another crawl. Returns ``True`` when the report was just marked resolved.
    """
    if report.problem_type != 'playback' or str(report.status) in _TERMINAL:
        return False
    obj, episode = _resolve_target(report)
    if obj is None or not target_playable(obj, episode):
        return False
    _mark(
        report, status='resolved', action='playback_recheck',
        result='browser_safe:already_playable', remediated=True,
    )
    return True


def remediate_report(report, *, force: bool = False, min_interval_seconds: int = 0) -> dict[str, Any]:
    """Attempt an automatic fix for a single report; return an outcome dict.

    Safe to call repeatedly. Already-resolved rows are skipped unless
    ``force``. Problem types with no safe automatic fix (``other``) and reports
    whose target has vanished are marked ``needs_review``.
    ``min_interval_seconds`` reuses a remediation newer than that instead of
    crawling again (two callers racing on one report do the work once).
    """
    from apps.catalog.models import ContentIssueReport

    if report.status in {ContentIssueReport.Status.RESOLVED, ContentIssueReport.Status.REJECTED} and not force:
        return {
            'report_id': report.pk, 'status': report.status,
            'action': report.remediation_action, 'result': 'skipped_terminal',
        }
    if (
        min_interval_seconds and not force and report.attempts
        and (timezone.now() - report.updated_at).total_seconds() < min_interval_seconds
    ):
        return {
            'report_id': report.pk, 'status': report.status,
            'action': report.remediation_action, 'result': report.last_result or 'skipped_recent',
        }

    with _report_lock(report.pk) as acquired:
        if not acquired:
            return {
                'report_id': report.pk, 'status': report.status,
                'action': report.remediation_action, 'result': 'skipped_in_progress',
            }
        return _remediate_locked(report)


def _remediate_locked(report) -> dict[str, Any]:
    from apps.catalog.models import ContentIssueReport

    obj, episode = _resolve_target(report)
    if obj is None:
        return _mark(
            report, status='rejected', action='resolve_target',
            result='target_missing',
        )

    handler = _DISPATCH.get(report.problem_type)
    if handler is None:
        # audio / other — no safe automation; keep it in the human queue.
        return _mark(
            report, status='needs_review', action='manual',
            result=f'no_auto_remediation_for:{report.problem_type}',
        )

    report.status = ContentIssueReport.Status.REMEDIATING
    report.save(update_fields=['status', 'updated_at'])
    try:
        return handler(report, obj, episode)
    except Exception as exc:  # noqa: BLE001 — never let one report break a batch
        logger.exception('content report %s remediation failed', report.pk)
        return _mark(
            report, status='needs_review', action='error',
            result=f'{type(exc).__name__}: {exc}'[:200],
        )


def sync_reports_with_reality(*, limit: int = 500) -> dict[str, Any]:
    """Crawl-free sweep: resolve every playback report whose target now plays.

    Covers every non-terminal state (including ``unavailable`` and a report a
    human is still holding in ``needs_review``) so a mirror landed by any crawler
    closes the loop without another provider hit.
    """
    from apps.catalog.models import ContentIssueReport

    rows = (
        ContentIssueReport.objects
        .filter(problem_type='playback')
        .exclude(status__in=list(_TERMINAL))
        .order_by('-report_count', 'created_at')[:max(1, limit)]
    )
    stats: dict[str, Any] = {'checked': 0, 'resolved': 0, 'resolved_report_ids': []}
    for report in rows:
        stats['checked'] += 1
        try:
            if recheck_report(report):
                stats['resolved'] += 1
                stats['resolved_report_ids'].append(report.pk)
        except Exception:  # noqa: BLE001 — one bad row must not stop the sweep
            logger.exception('recheck of content report %s failed', report.pk)
    return stats


def _drain_candidates(problem_type: str | None):
    from apps.catalog.models import ContentIssueReport

    S = ContentIssueReport.Status
    stale = timezone.now() - timedelta(seconds=STALE_REMEDIATING_SECONDS)
    qs = ContentIssueReport.objects.filter(problem_type__in=list(ContentIssueReport.AUTO_PROBLEMS)).filter(
        Q(status__in=[S.OPEN, S.QUEUED, S.UNAVAILABLE])
        # An earlier crash left it parked; the cause may be fixed since.
        | Q(status=S.NEEDS_REVIEW, remediation_action='error')
        # A worker died mid-crawl and never wrote a result.
        | Q(status=S.REMEDIATING, updated_at__lt=stale)
    )
    if problem_type:
        qs = qs.filter(problem_type=problem_type)
    # Most-reported, then oldest — fix what hurts the most viewers first.
    return qs.order_by('-report_count', 'created_at')


def remediate_open_reports(
    *,
    limit: int = 25,
    problem_type: str | None = None,
    max_attempts: int = MAX_AUTO_ATTEMPTS,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Drain due reports through :func:`remediate_report` on a widening backoff.

    A row is *due* once ``_BACKOFF_MINUTES[attempts]`` has passed since its last
    attempt. Past ``max_attempts`` it is handed to a human (``needs_review`` /
    ``auto_exhausted``) so a permanently-unfixable title never loops forever.
    Backs the ``remediate_content_reports`` command and the periodic drain task.
    """
    from apps.catalog.models import ContentIssueReport

    now = timezone.now()
    due: list = []
    exhausted: list = []
    for report in _drain_candidates(problem_type).iterator():
        if (report.attempts or 0) >= max_attempts:
            exhausted.append(report)
            continue
        waited = (now - report.updated_at).total_seconds()
        if report.attempts and waited < _backoff_seconds(report.attempts):
            continue
        due.append(report)
        if len(due) >= max(1, limit):
            break

    stats: dict[str, Any] = {
        'processed': 0, 'resolved': 0, 'queued': 0, 'needs_review': 0, 'other': 0,
        'exhausted': 0,
    }
    outcomes: list[dict[str, Any]] = []

    if not dry_run:
        for report in exhausted:
            _mark(
                report, status='needs_review', action='auto_exhausted',
                result=f'auto_retries_exhausted:{report.last_result}'[:200],
            )
            stats['exhausted'] += 1

    for report in due:
        stats['processed'] += 1
        if dry_run:
            outcomes.append({'report_id': report.pk, 'problem_type': report.problem_type, 'would': 'remediate'})
            continue
        outcome = remediate_report(report)
        outcomes.append(outcome)
        status = outcome.get('status')
        if status == ContentIssueReport.Status.RESOLVED:
            stats['resolved'] += 1
        elif status == ContentIssueReport.Status.QUEUED:
            stats['queued'] += 1
        elif status == ContentIssueReport.Status.NEEDS_REVIEW:
            stats['needs_review'] += 1
        else:
            stats['other'] += 1
    stats['outcomes'] = outcomes
    return stats
