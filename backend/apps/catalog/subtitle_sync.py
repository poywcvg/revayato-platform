"""Self-healing subtitle timing: crowd-sourced offset convergence + FPS rescale.

The subtitle pipeline is otherwise *preventive* — it picks a release-matched
Persian subtitle so timing lines up (see ``subtitle_extract`` / ``subzone`` /
``subtitle_metadata``). This module adds the *corrective* half the catalog was
missing:

* **Crowd consensus (the workhorse).** The player reports the manual offset each
  viewer settles on for a served VTT (``SubtitleSyncVote``). When enough
  independent viewers agree, :func:`promote_pending_offsets` bakes the trimmed
  cluster centre straight into the stored cue timestamps, bumps the file key
  (cache-bust + vote invalidation), and clears the consumed votes. Fast (pure
  arithmetic, no audio work) and accurate (real human ground-truth), and it
  self-corrects: once baked, fresh viewers start at zero and re-converge on zero.

* **FPS rescale (cheap prevention booster).** A subtitle authored for a 25 fps
  PAL encode drifts ~4% on a 23.976 fps source. When both framerates are known
  from release tags, :func:`shift_and_scale_webvtt` can linearly rescale the
  cues at ingestion so the drift never reaches a viewer.

Deliberately no audio/ASR forced-alignment here: it would pin the box and fight
the "keep the site fast" constraint. The crowd layer covers real desync at a
fraction of the cost.
"""

from __future__ import annotations

import logging
import re
import statistics

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

# --- consensus tuning -------------------------------------------------------
# Independent viewers required before we trust a correction.
MIN_SAMPLES = 4
# Votes within this many seconds of the median form the agreeing cluster.
CONSENSUS_TOLERANCE = 0.6
# Never bake a correction smaller than this — sub-frame noise, not desync.
MIN_APPLY_SECONDS = 0.35
# Guard against absurd/garbage reports.
MAX_APPLY_SECONDS = 30.0

# --- WebVTT timestamp rewriting --------------------------------------------
# Matches HH:MM:SS.mmm and MM:SS.mmm (VTT uses '.', SRT ',' — accept both).
_TS_TOKEN = re.compile(r'\d{1,3}:\d{2}:\d{2}[.,]\d{1,3}|\d{1,2}:\d{2}[.,]\d{1,3}')


def _ts_to_seconds(token: str) -> float:
    token = token.strip().replace(',', '.')
    parts = token.split(':')
    if len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        hours, (minutes, seconds) = '0', parts
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _seconds_to_ts(value: float) -> str:
    value = max(0.0, value)
    hours = int(value // 3600)
    value -= hours * 3600
    minutes = int(value // 60)
    value -= minutes * 60
    return f'{hours:02d}:{minutes:02d}:{value:06.3f}'


def shift_and_scale_webvtt(text: str, *, shift: float = 0.0, scale: float = 1.0) -> str:
    """Return ``text`` with every cue timestamp mapped to ``ts * scale + shift``.

    Only lines carrying a ``-->`` cue range are touched, so cue text that merely
    happens to look like a timestamp is never rewritten. ``scale`` handles FPS
    drift (linear); ``shift`` handles a constant offset. Both no-ops (1.0 / 0.0)
    return the text unchanged.
    """
    if scale == 1.0 and shift == 0.0:
        return text

    def rewrite_line(line: str) -> str:
        if '-->' not in line:
            return line

        def repl(match: re.Match[str]) -> str:
            return _seconds_to_ts(_ts_to_seconds(match.group(0)) * scale + shift)

        return _TS_TOKEN.sub(repl, line)

    # Preserve the document's original newline style where possible.
    return '\n'.join(rewrite_line(line) for line in text.split('\n'))


# --- FPS detection ----------------------------------------------------------
_STANDARD_FPS = (23.976, 24.0, 25.0, 29.97, 30.0, 50.0, 59.94, 60.0)
_FPS_TAG = re.compile(r'(\d{2}(?:[.,]\d{1,3})?)\s*fps', re.IGNORECASE)


def detect_fps_from_release(name: str) -> float | None:
    """Best-effort standard framerate from a release name / URL. None if unsure.

    Only returns a value we are confident about — an explicit ``NNfps`` tag, or
    the unambiguous ``PAL`` (25) marker. NTSC is intentionally skipped (it maps
    to both 23.976 and 29.97) so we never rescale on a guess.
    """
    text = str(name or '')
    if not text:
        return None
    match = _FPS_TAG.search(text)
    if match:
        try:
            value = float(match.group(1).replace(',', '.'))
        except ValueError:
            value = 0.0
        return min(_STANDARD_FPS, key=lambda f: abs(f - value)) if value else None
    if re.search(r'\bpal\b', text, re.IGNORECASE):
        return 25.0
    return None


def fps_rescale_factor(src_fps: float | None, dst_fps: float | None) -> float:
    """Scale to map cues authored at ``src_fps`` onto a ``dst_fps`` encode.

    A 25 fps sub on a 23.976 fps video needs each timestamp multiplied by
    ``25 / 23.976`` (stretched), so the factor is ``src / dst``. Returns 1.0 when
    either side is unknown or already equal.
    """
    if not src_fps or not dst_fps or src_fps <= 0 or dst_fps <= 0:
        return 1.0
    if abs(src_fps - dst_fps) < 0.05:
        return 1.0
    return src_fps / dst_fps


# --- consensus --------------------------------------------------------------
def compute_consensus_offset(
    offsets,
    *,
    min_samples: int = MIN_SAMPLES,
    tolerance: float = CONSENSUS_TOLERANCE,
) -> float | None:
    """Trimmed-cluster centre of viewer offsets, or None if there is no consensus.

    Uses the median as a robust anchor, keeps only votes within ``tolerance`` of
    it, and requires the agreeing cluster to be both large enough (``min_samples``)
    and a majority of all votes — so a couple of outliers or a split field never
    triggers a bake. Returns the mean of the agreeing cluster, rounded.
    """
    values = sorted(
        float(offset) for offset in offsets
        if offset is not None and abs(float(offset)) <= MAX_APPLY_SECONDS
    )
    total = len(values)
    if total < min_samples:
        return None
    median = statistics.median(values)
    cluster = [value for value in values if abs(value - median) <= tolerance]
    if len(cluster) < min_samples or len(cluster) * 2 <= total:
        return None
    return round(sum(cluster) / len(cluster), 3)


# --- baking -----------------------------------------------------------------
_VERSION_SUFFIX = re.compile(r'^(?P<base>.*?)(?:\.s(?P<ver>\d+))?(?P<ext>\.[^.]+)$')


def next_version_key(key: str) -> str:
    """`catalog/subtitles/x.vtt` → `x.s1.vtt` → `x.s2.vtt` … for cache-busting."""
    match = _VERSION_SUFFIX.match(str(key or ''))
    if not match:
        return f'{key}.s1'
    version = int(match.group('ver')) + 1 if match.group('ver') else 1
    return f"{match.group('base')}.s{version}{match.group('ext')}"


def _read_stored_text(key: str) -> str | None:
    try:
        with default_storage.open(key, 'rb') as handle:
            raw = handle.read()
    except Exception:  # noqa: BLE001 — storage/network hiccup, skip this bake
        logger.warning('subtitle-sync: could not read %s for re-timing', key, exc_info=True)
        return None
    if raw[:3] == b'\xef\xbb\xbf':  # strip UTF-8 BOM
        raw = raw[3:]
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('utf-8', errors='replace')


def rebake_track_timing(track: dict, *, shift: float) -> dict | None:
    """Bake ``shift`` seconds into a track's stored VTT under a fresh key.

    Returns the updated track dict (new ``key`` + accumulated ``sync_offset``),
    or None if nothing changed / the file was unreadable. The caller is
    responsible for persisting the parent object and clearing consumed votes.
    Positive ``shift`` moves cues later; to *correct* subtitles that ran late by
    ``C`` seconds (viewers pushed them earlier), pass ``shift = -C``.
    """
    if not shift:
        return None
    old_key = str(track.get('key') or track.get('src') or '').strip()
    if not old_key:
        return None
    text = _read_stored_text(old_key)
    if text is None:
        return None
    retimed = shift_and_scale_webvtt(text, shift=shift)
    if retimed == text:
        return None
    new_key = next_version_key(old_key)
    try:
        if default_storage.exists(new_key):
            default_storage.delete(new_key)
        saved = default_storage.save(new_key, ContentFile(retimed.encode('utf-8')))
    except Exception:  # noqa: BLE001
        logger.warning('subtitle-sync: could not write re-timed %s', new_key, exc_info=True)
        return None
    updated = dict(track)
    updated['key'] = saved
    # sync_offset tracks how much lateness we have removed so far (positive).
    try:
        previous = float(updated.get('sync_offset') or 0.0)
    except (TypeError, ValueError):
        previous = 0.0
    updated['sync_offset'] = round(previous - shift, 3)
    # Best-effort cleanup of the superseded file.
    try:
        if old_key != saved and default_storage.exists(old_key):
            default_storage.delete(old_key)
    except Exception:  # noqa: BLE001
        logger.debug('subtitle-sync: stale file %s left in place', old_key, exc_info=True)
    return updated


# --- promotion driver -------------------------------------------------------
def _load_sync_target(content_type: str, object_id: int, episode_id: int):
    """Return the model instance whose ``subtitle_tracks`` holds the voted track.

    Movie tracks live on the movie; series tracks live on the episode.
    """
    from apps.catalog.models import Episode, Movie

    if content_type == 'series':
        if not episode_id:
            return None
        return Episode.objects.filter(pk=episode_id).first()
    return Movie.objects.filter(pk=object_id).first()


def promote_pending_offsets(*, max_groups: int = 200) -> dict:
    """Bake crowd-agreed offsets into stored VTTs and clear the consumed votes.

    Groups votes by (content, episode, track, file signature); for each group
    with enough independent voters it computes the consensus and either bakes the
    correction (>= :data:`MIN_APPLY_SECONDS`), or drops the votes as resolved
    when viewers agree the file is already fine. Stale-signature groups (the file
    changed since the vote) are pruned. Safe to run repeatedly; converges to zero.
    """
    from django.db.models import Count

    from apps.catalog.models import SubtitleSyncVote
    from apps.catalog.subtitle_contract import (
        normalize_subtitle_tracks,
        subtitle_sync_signature,
    )

    summary = {'groups': 0, 'baked': 0, 'resolved': 0, 'stale': 0, 'skipped': 0}
    groups = (
        SubtitleSyncVote.objects
        .values('content_type', 'object_id', 'episode_id', 'track_id', 'sig')
        .annotate(vote_count=Count('id'))
        .filter(vote_count__gte=MIN_SAMPLES)
        .order_by('-vote_count')[:max_groups]
    )
    for group in groups:
        summary['groups'] += 1
        vote_filter = {
            'content_type': group['content_type'],
            'object_id': group['object_id'],
            'episode_id': group['episode_id'],
            'track_id': group['track_id'],
            'sig': group['sig'],
        }
        offsets = list(
            SubtitleSyncVote.objects.filter(**vote_filter).values_list('offset', flat=True)
        )
        target = _load_sync_target(
            group['content_type'], group['object_id'], group['episode_id'],
        )
        if target is None:
            SubtitleSyncVote.objects.filter(**vote_filter).delete()
            summary['stale'] += 1
            continue

        tracks = normalize_subtitle_tracks(getattr(target, 'subtitle_tracks', None) or [])
        index = next(
            (i for i, track in enumerate(tracks) if track.get('id') == group['track_id']),
            None,
        )
        if index is None or subtitle_sync_signature(tracks[index].get('key')) != group['sig']:
            # File was re-synced/replaced since these votes — they no longer apply.
            SubtitleSyncVote.objects.filter(**vote_filter).delete()
            summary['stale'] += 1
            continue

        consensus = compute_consensus_offset(offsets)
        if consensus is None:
            summary['skipped'] += 1  # no agreement yet — let more votes arrive
            continue
        if abs(consensus) < MIN_APPLY_SECONDS:
            # Viewers agree it is already in sync — clear the noise.
            SubtitleSyncVote.objects.filter(**vote_filter).delete()
            summary['resolved'] += 1
            continue

        rebaked = rebake_track_timing(tracks[index], shift=-consensus)
        if rebaked is None:
            summary['skipped'] += 1
            continue
        tracks[index] = rebaked
        target.subtitle_tracks = normalize_subtitle_tracks(tracks)
        try:
            target.save(update_fields=['subtitle_tracks', 'updated_at'])
        except Exception:  # noqa: BLE001
            logger.warning(
                'subtitle-sync: failed saving %s#%s after re-time',
                group['content_type'], group['object_id'], exc_info=True,
            )
            summary['skipped'] += 1
            continue
        SubtitleSyncVote.objects.filter(**vote_filter).delete()
        summary['baked'] += 1
        logger.info(
            'subtitle-sync: baked %+.2fs into %s#%s track=%s (%d votes)',
            -consensus, group['content_type'], group['object_id'],
            group['track_id'], len(offsets),
        )
    return summary


def prune_stale_votes(*, max_age_days: int = 30) -> int:
    """Drop votes that never reached consensus, to keep the table bounded."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.catalog.models import SubtitleSyncVote

    cutoff = timezone.now() - timedelta(days=max_age_days)
    deleted, _ = SubtitleSyncVote.objects.filter(updated_at__lt=cutoff).delete()
    return deleted

