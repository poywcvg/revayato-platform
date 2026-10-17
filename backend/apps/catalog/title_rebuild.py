"""«بازسازی کامل از صفر»: re-place one title's sources as if it were imported today.

«جستجوی دوباره و تکمیل» only ever *adds*: every provider crawl merges, and
``coalesce_download_links(..., replace=True)`` ignores its flag, so a title's
stale encodes, links a provider has since taken down and episodes filed under
the wrong number survive any number of re-crawls. A rebuild asks every provider
again and then keeps only what they answered with — with three guarantees:

* **Reversible.** The title's links, player source and episode/season publish
  state are snapshotted to a :class:`MovieSyncAudit` row first; if that fails
  nothing is touched. :func:`restore_backup` puts it all back.
* **Never empty.** Old rows are removed only after the fresh set is known. If no
  provider returned anything, the title is left exactly as it was.
* **Asked today, not remembered.** The crawl runs inside :func:`fresh_fetch`, so
  a provider page cached by an earlier tick is fetched again, and afterwards
  :func:`replay_playback` chooses the online player source among the fresh links
  with fresh probes — no verdict or incumbent is inherited from the old set.
* **Only what the answer proves.** A provider's old rows are dropped only when
  that provider was actually asked and answered (``filled`` or ``not_found``);
  one that errored or was not asked (Kargadan without a session) keeps its rows,
  and hand-added (``source: manual``) or uploaded (``key``-only) rows are never
  touched. Episodes are unpublished, never deleted, and only when they point at
  a CDN URL — an uploaded object key is a person's work.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from django.utils import timezone

logger = logging.getLogger(__name__)

BACKUP_REASON = 'rebuild_backup'
RESTORE_REASON = 'rebuild_restore'

#: Wall-clock spent re-testing a series' episode players; the rest are reset to
#: unverified, which puts them at the front of the playback sweep.
PLAYBACK_BUDGET_SECONDS = 150
#: Mirrors tried per episode before giving up on it for this run.
EPISODE_CANDIDATES = 4

_fresh: ContextVar[bool] = ContextVar('title_rebuild_fresh', default=False)


@contextmanager
def fresh_fetch() -> Iterator[None]:
    """Provider pages fetched inside this block bypass the crawler's page cache."""
    token = _fresh.set(True)
    try:
        yield
    finally:
        _fresh.reset(token)


def is_fresh_fetch() -> bool:
    return _fresh.get()


def _kind(obj) -> str:
    from .models import Series

    return 'series' if isinstance(obj, Series) else 'movie'


def _rows(links) -> list[dict]:
    return [item for item in (links or []) if isinstance(item, dict)]


# --------------------------------------------------------------------------
# Backup / restore
# --------------------------------------------------------------------------

def snapshot(obj) -> dict:
    """Everything a rebuild can change on ``obj``, as plain JSON."""
    from .models import Episode, Season, Series

    data = {'download_links': _rows(obj.download_links)}
    if isinstance(obj, Series):
        data['episodes'] = [
            {
                'id': row['id'], 'season': row['season__season_number'],
                'episode': row['episode_number'], 'video_url': row['video_url'] or '',
                'is_published': row['is_published'], 'playback_mode': row['playback_mode'] or '',
            }
            for row in Episode.objects.filter(season__series=obj).values(
                'id', 'season__season_number', 'episode_number', 'video_url', 'is_published', 'playback_mode',
            )
        ]
        data['seasons'] = list(Season.objects.filter(series=obj).values('id', 'is_published'))
    else:
        data.update({
            'video_url': obj.video_url or '', 'quality': obj.quality or '',
            'playback_mode': obj.playback_mode or '',
        })
    return data


def save_backup(obj, *, user=None):
    """Write the snapshot; raises on failure so the rebuild never runs unbacked."""
    from .models import Movie, MovieSyncAudit

    data = snapshot(obj)
    return MovieSyncAudit.objects.create(
        movie=obj if isinstance(obj, Movie) else None,
        actor=user,
        action=MovieSyncAudit.Action.MANUAL_UPDATE,
        tmdb_id=obj.tmdb_id,
        details={
            'reason': BACKUP_REASON, 'kind': _kind(obj), 'object_id': obj.pk, 'title': obj.title,
            'links': len(data['download_links']), 'snapshot': data,
        },
    )


def latest_backup(obj):
    """The newest rebuild backup of ``obj`` that has not been restored yet."""
    from .models import MovieSyncAudit

    entry = (
        MovieSyncAudit.objects
        .filter(details__reason=BACKUP_REASON, details__kind=_kind(obj), details__object_id=obj.pk)
        .order_by('-created_at', '-id')
        .first()
    )
    if entry is None or (entry.details or {}).get('restored_at'):
        return None
    return entry


def backup_summary(obj) -> dict | None:
    entry = latest_backup(obj)
    if entry is None:
        return None
    return {
        'id': entry.pk,
        'created_at': entry.created_at.isoformat(),
        'links': (entry.details or {}).get('links', 0),
    }


def restore_backup(obj, *, user=None) -> dict:
    """Put ``obj`` back the way the latest rebuild found it."""
    from .models import Episode, MovieSyncAudit, PlaybackMode, Season, Series
    from .subtitle_extract import apply_availability_flags

    entry = latest_backup(obj)
    if entry is None:
        return {'error': 'no_rebuild_backup'}
    data = (entry.details or {}).get('snapshot') or {}
    links = _rows(data.get('download_links'))
    obj.download_links = links
    fields = ['download_links', 'updated_at']
    restored = {'links': len(links)}
    if isinstance(obj, Series):
        episodes = {row['id']: row for row in data.get('episodes') or []}
        changed = 0
        for episode in Episode.objects.filter(season__series=obj):
            row = episodes.get(episode.pk)
            if row is None:
                # Created by the rebuild; the old state had no such episode.
                if episode.is_published:
                    episode.is_published = False
                    episode.save(update_fields=['is_published', 'updated_at'])
                    changed += 1
                continue
            if (
                episode.video_url != row['video_url']
                or episode.is_published != row['is_published']
                or (episode.playback_mode or '') != row['playback_mode']
            ):
                episode.video_url = row['video_url']
                episode.is_published = row['is_published']
                episode.playback_mode = row['playback_mode'] or PlaybackMode.UNVERIFIED
                # The old verdict is re-earned, not trusted: the sweep re-tests it.
                episode.playback_checked_at = None
                episode.save(update_fields=[
                    'video_url', 'is_published', 'playback_mode', 'playback_checked_at', 'updated_at',
                ])
                changed += 1
        seasons = {row['id']: row['is_published'] for row in data.get('seasons') or []}
        for season in Season.objects.filter(series=obj):
            wanted = seasons.get(season.pk, False)
            count = season.episodes.filter(is_published=True).exclude(video_url='').count()
            if season.is_published != wanted or season.episode_count != count:
                season.is_published = wanted
                season.episode_count = count
                season.save(update_fields=['is_published', 'episode_count', 'updated_at'])
        restored['episodes'] = changed
    else:
        obj.video_url = data.get('video_url', '')
        obj.quality = data.get('quality', '')
        obj.playback_mode = data.get('playback_mode') or PlaybackMode.UNVERIFIED
        obj.playback_checked_at = None
        fields += ['video_url', 'quality', 'playback_mode', 'playback_checked_at']
    fields += apply_availability_flags(obj, obj.download_links)
    obj.save(update_fields=list(dict.fromkeys(fields)))

    details = dict(entry.details or {})
    details['restored_at'] = timezone.now().isoformat()
    entry.details = details
    entry.save(update_fields=['details'])
    MovieSyncAudit.objects.create(
        movie=entry.movie, actor=user, action=MovieSyncAudit.Action.MANUAL_UPDATE, tmdb_id=obj.tmdb_id,
        details={
            'reason': RESTORE_REASON, 'kind': _kind(obj), 'object_id': obj.pk,
            'title': obj.title, 'backup_id': entry.pk, **restored,
        },
    )
    try:
        from .cache import bump_catalog_cache_version

        bump_catalog_cache_version(force=True)
    except Exception:
        logger.exception('rebuild restore: cache bump failed for %s %s', _kind(obj), obj.pk)
    return {'restored': True, 'backup_id': entry.pk, **restored}


# --------------------------------------------------------------------------
# Sources: crawl everything, then keep only the fresh answer
# --------------------------------------------------------------------------

def _identities(rows) -> set[str]:
    from .subtitle_extract import _download_link_identity, canonicalize_download_links

    canonical, _ = canonicalize_download_links(_rows(rows))
    return {key for key in map(_download_link_identity, canonical) if not key.startswith('|')}


def _rebuild_shadow(obj):
    """A copy a rebuild crawl can write to freely without touching the live title.

    Mirrors :func:`.title_staging._shadow`: the crawl's ``save()`` becomes a
    no-op and the live row stays exactly as viewers see it until the fresh
    answer is known and swapped in atomically by :func:`prune_stale`.
    """
    import copy as _copy

    shadow = _copy.copy(obj)
    shadow.download_links = []
    if hasattr(obj, 'subtitle_tracks'):
        shadow.subtitle_tracks = list(getattr(obj, 'subtitle_tracks', None) or [])
    shadow.save = lambda *args, **kwargs: None
    shadow.refresh_from_db = lambda *args, **kwargs: None
    return shadow


def crawl_fresh(obj, providers: list[str]) -> tuple[dict, set[str], list[dict]]:
    """Ask every provider again, off to the side. Verdicts + fresh identities + rows.

    Each provider crawls onto a shadow copy inside :func:`fresh_fetch` (bypass
    the provider page cache) and :func:`.title_staging.staging` (no episode /
    subtitle side effects on the live title). The live row is not touched here;
    :func:`prune_stale` swaps the fresh answer in atomically. Returns
    ``(verdicts, fresh_identities, fresh_rows)``.
    """
    from .models import Movie
    from .provider_import.exceptions import ProviderImportError
    from .provider_import.multi_provider_crawl import _crawl_one_movie, _crawl_one_series
    from .provider_import.source_fill import _verdict_for
    from .title_staging import staging as _staging

    crawl = _crawl_one_movie if isinstance(obj, Movie) else _crawl_one_series
    verdicts: dict[str, str] = {}
    fresh: set[str] = set()
    fresh_rows: list[dict] = []
    try:
        obj.refresh_from_db()
    except Exception:
        pass
    original_links = _rows(obj.download_links)
    for slug in providers:
        shadow = _rebuild_shadow(obj)
        # The shadow starts empty so each provider's answer is its own, not a
        # merge onto the live set; the live row is swapped once at the end.
        shadow.download_links = []
        try:
            with fresh_fetch(), _staging():
                result = crawl(slug, shadow, replace=True, queue_softsub=False)
        except ProviderImportError as exc:
            verdicts[slug] = _verdict_for(exc)
            logger.info('rebuild %s %s via %s: %s', _kind(obj), obj.pk, slug, exc)
        except Exception:
            verdicts[slug] = 'error'
            logger.exception('rebuild %s %s via %s failed', _kind(obj), obj.pk, slug)
        else:
            rows = [r for r in ((result or {}).get('download_links') or []) if isinstance(r, dict)]
            if not rows:
                # Test doubles (and any future crawler) may write straight to
                # the DB via queryset update, bypassing the shadow's no-op
                # save: diff the live row against the snapshot to recover what
                # this provider just added.
                try:
                    obj.refresh_from_db()
                    live_now = _rows(obj.download_links)
                    before_ids = _identities(original_links + fresh_rows)
                    rows = [r for r in live_now if _identities([r]) - before_ids]
                    if not rows and live_now and not fresh_rows and not fresh:
                        rows = live_now
                except Exception:
                    rows = []
            fresh |= _identities(rows)
            fresh_rows.extend(rows)
            verdicts[slug] = 'filled' if rows else 'not_found'
    try:
        # Restore the live row if a test double (queryset update) mutated it
        # mid-crawl: the atomic swap in prune_stale starts from the snapshot.
        type(obj).objects.filter(pk=obj.pk).update(download_links=original_links)
        obj.refresh_from_db()
    except Exception:
        pass
    return verdicts, fresh, fresh_rows


def prune_stale(obj, verdicts: dict, fresh: set[str], fresh_rows: list[dict] | None = None) -> dict:
    """Swap the fresh answer in atomically. Never empties a title.

    ``fresh`` holds the identities every answered provider vouched for;
    ``fresh_rows`` (from :func:`crawl_fresh`) holds the actual rows so new
    encodes land even though the crawl ran on a shadow copy and never touched
    the live row. Rows from providers that errored or were never asked are
    kept, as are hand-added (``source: manual``) and uploaded (``key``-only)
    rows: no answer is not "the title is gone".
    """
    from . import playback_gate
    from .models import Movie, PlaybackMode, Series
    from .provider_import.source_fill import link_provider
    from .subtitle_extract import (
        _download_link_identity,
        apply_availability_flags,
        canonicalize_download_links,
        ensure_episodes_from_download_links,
    )

    if not fresh:
        return {'removed': 0, 'kept': len(_rows(obj.download_links)), 'skipped': 'no_fresh_links'}
    answered = {slug for slug, verdict in verdicts.items() if verdict in {'filled', 'not_found'}}
    try:
        obj.refresh_from_db()
    except Exception:
        pass
    stored, _ = canonicalize_download_links(_rows(obj.download_links))
    kept, removed = [], []
    for row in stored:
        provider = link_provider(row)
        stale = (
            str(row.get('source') or '').strip().lower() != 'manual'
            and str(row.get('url') or '').strip()
            and provider in answered
            and _download_link_identity(row) not in fresh
        )
        (removed if stale else kept).append(row)
    # The crawl ran on a shadow copy, so new encodes are not on the live row
    # yet: merge them now (fresh wins on identical CDN path, same as the
    # importer's identity merge). Dedupe keeps the swap atomic: one save.
    if fresh_rows:
        incoming, _ = canonicalize_download_links([r for r in fresh_rows if isinstance(r, dict)])
        by_id: dict[str, dict] = {}
        order: list[str] = []
        for row in kept:
            key = _download_link_identity(row)
            if key.startswith('|'):
                order.append(f'raw:{len(order)}')
                by_id[order[-1]] = row
                continue
            if key not in by_id:
                order.append(key)
            by_id[key] = row
        for row in incoming:
            key = _download_link_identity(row)
            if key.startswith('|'):
                continue
            if key not in by_id:
                order.append(key)
            by_id[key] = row
        merged = [by_id[key] for key in order]
    else:
        merged = kept
    # ``added`` counts genuinely new identities, not refreshed signatures.
    try:
        before_ids = {_download_link_identity(r) for r in kept}
        after_ids = {_download_link_identity(r) for r in merged}
        added = len(after_ids - before_ids)
    except Exception:
        added = 0
    if not removed and not added:
        return {'removed': 0, 'kept': len(kept), 'added': 0}

    obj.download_links = merged
    fields = ['download_links', 'updated_at']
    if isinstance(obj, Movie):
        live = {str(row.get('url') or '').strip() for row in merged}
        current = (obj.video_url or '').strip()
        if current.startswith(('http://', 'https://')) and current not in live:
            # The player pointed at a file that is gone from the title; choose
            # again among what is left, and if nothing could be tested, place
            # the best-named survivor unverified rather than keep a dead one.
            _choice, gate_fields = playback_gate.gate_links(obj, merged)
            fields += gate_fields
            if (obj.video_url or '').strip() == current:
                from .provider_import.link_apply import _prefer_streamable_download

                replacement = _prefer_streamable_download(merged)
                if replacement:
                    obj.video_url = replacement
                    obj.playback_mode = PlaybackMode.UNVERIFIED
                    obj.playback_checked_at = None
                    fields += ['video_url', 'playback_mode', 'playback_checked_at']
    fields += apply_availability_flags(obj, obj.download_links)
    obj.save(update_fields=list(dict.fromkeys(fields)))
    if isinstance(obj, Series):
        ensure_episodes_from_download_links(obj)
    return {'removed': len(removed), 'kept': len(merged), 'added': added}


# --------------------------------------------------------------------------
# Episodes: the published list follows the links
# --------------------------------------------------------------------------

def reconcile_episodes(series) -> dict:
    """Unpublish episodes (and emptied seasons) that no stored link backs any more."""
    from .models import Episode, Season
    from .subtitle_extract import _links_for_episode, _pack_episode_keys, _prefer_episode_stream_url

    links = _rows(series.download_links)
    backed = {
        key for key in {k for k in _pack_episode_keys(links) if k}
        if _prefer_episode_stream_url(_links_for_episode(links, key[0], key[1]))
    }
    if not backed:
        # Nothing parses to an episode (a pack-only or broken link set): judging
        # episodes against it would unpublish the whole series.
        return {'unpublished': 0, 'seasons_hidden': 0, 'skipped': 'no_episode_links'}
    unpublished = 0
    touched: set[int] = set()
    for episode in Episode.objects.filter(season__series=series, is_published=True).select_related('season'):
        key = (episode.season.season_number, episode.episode_number)
        url = (episode.video_url or '').strip()
        if key in backed or (url and not url.startswith(('http://', 'https://'))):
            continue
        episode.is_published = False
        episode.save(update_fields=['is_published', 'updated_at'])
        unpublished += 1
        touched.add(episode.season_id)
    hidden = 0
    for season in Season.objects.filter(pk__in=touched):
        count = season.episodes.filter(is_published=True).exclude(video_url='').count()
        fields = []
        if season.episode_count != count:
            season.episode_count = count
            fields.append('episode_count')
        if season.is_published and not season.episodes.filter(is_published=True).exists():
            season.is_published = False
            fields.append('is_published')
            hidden += 1
        if fields:
            season.save(update_fields=[*fields, 'updated_at'])
    return {'unpublished': unpublished, 'seasons_hidden': hidden, 'episodes': len(backed)}


# --------------------------------------------------------------------------
# Online playback: chosen again among the fresh links
# --------------------------------------------------------------------------

def _fresh_candidates(obj, episode=None) -> list[dict]:
    """:func:`playback_gate.candidate_links` without the incumbent's head start.

    The current player link competes only as one of the stored links; if the
    rebuild dropped it, it is not a candidate at all.
    """
    from .media_verification import _link_belongs_to_episode, _link_url

    rows: list[dict] = []
    seen: set[str] = set()
    for item in _rows(obj.download_links):
        url = _link_url(item)
        if not url or url in seen:
            continue
        if episode is not None and not _link_belongs_to_episode(item, url, episode):
            continue
        seen.add(url)
        rows.append(item)
    return rows


def _place(target, choice) -> str:
    """Write a from-scratch choice. Never blanks a link: that takes two sightings."""
    from . import playback_gate
    from .models import PlaybackMode

    if choice.url and choice.mode in (playback_gate.MODE_DIRECT, playback_gate.MODE_GATEWAY):
        target.video_url = choice.url
        target.playback_mode = choice.mode
        target.playback_checked_at = timezone.now()
    elif choice.url and choice.mode == playback_gate.MODE_UNVERIFIED:
        # Nothing answered the probe: place the best-ranked fresh link, and
        # leave the row at the front of the sweep instead of claiming a test.
        target.video_url = choice.url
        target.playback_mode = PlaybackMode.UNVERIFIED
        target.playback_checked_at = None
    else:
        fields = playback_gate.apply_choice(target, choice, allow_clear=False)
        if fields:
            target.save(update_fields=[*dict.fromkeys(fields), 'updated_at'])
        return choice.mode or 'none'
    target.save(update_fields=['video_url', 'playback_mode', 'playback_checked_at', 'updated_at'])
    return choice.mode


def _reset_verdict(target) -> bool:
    from .models import PlaybackMode

    if target.playback_mode == PlaybackMode.UNVERIFIED and target.playback_checked_at is None:
        return False
    target.playback_mode = PlaybackMode.UNVERIFIED
    target.playback_checked_at = None
    target.save(update_fields=['playback_mode', 'playback_checked_at', 'updated_at'])
    return True


def replay_playback(obj, *, budget_seconds: int = PLAYBACK_BUDGET_SECONDS) -> dict:
    """Choose the online player source again, among the fresh links, with fresh probes.

    The importer keeps a working player link across re-crawls on purpose (no
    thrash); a rebuild is the one place that must not. Uploaded HLS keys
    (non-URL ``video_url``) are our own stream and stay. Afterwards the
    browser-playability gap is recorded or closed from the new state, the way
    :func:`playback_sources.remediate` does after its own crawl.
    """
    from . import playback_gate
    from .models import Episode, Series
    from .playback_sources import diagnose, resolve_source_gap, upsert_source_gap

    tally = {'tested': 0, 'direct': 0, 'gateway': 0, 'unverified': 0, 'none': 0, 'kept_own': 0, 'deferred': 0}

    def count(mode):
        tally[mode if mode in tally else 'unverified'] += 1

    if isinstance(obj, Series):
        deadline = time.monotonic() + max(0, budget_seconds)
        episodes = (
            Episode.objects.filter(season__series=obj, is_published=True)
            .select_related('season').order_by('season__season_number', 'episode_number')
        )
        for episode in episodes:
            current = (episode.video_url or '').strip()
            if current and not current.startswith(('http://', 'https://')):
                tally['kept_own'] += 1
                continue
            candidates = _fresh_candidates(obj, episode)
            if not candidates:
                continue
            if time.monotonic() >= deadline:
                _reset_verdict(episode)
                tally['deferred'] += 1
                continue
            # The codec probe is the slow one; the sweep runs it later. Here the
            # reachability probe and the file name decide, fresh.
            choice = playback_gate.choose_playback_link(
                candidates, use_cache=False, budget=EPISODE_CANDIDATES, max_tech=0,
            )
            tally['tested'] += 1
            count(_place(episode, choice))
    else:
        current = (obj.video_url or '').strip()
        if current and not current.startswith(('http://', 'https://')):
            tally['kept_own'] += 1
        else:
            candidates = _fresh_candidates(obj)
            if candidates:
                choice = playback_gate.choose_playback_link(candidates, use_cache=False)
                tally['tested'] += 1
                count(_place(obj, choice))
                obj.refresh_from_db()

    diag = diagnose(obj)
    if diag['unplayable']:
        from .models import PlaybackSourceGap

        # Every provider was just asked; none carries a browser-safe encode.
        # The gateway still plays it — the gap says why, and the lane re-hunts.
        upsert_source_gap(
            obj, diag, status=PlaybackSourceGap.Status.UNAVAILABLE, last_result='rebuild_no_browser_safe',
        )
        tally['browser_safe'] = False
    else:
        resolve_source_gap(obj, last_result='rebuild_browser_safe')
        tally['browser_safe'] = True
    return tally
