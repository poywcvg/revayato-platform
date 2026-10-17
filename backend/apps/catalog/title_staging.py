"""«بازسازی تست‌شده»: rebuild a broken title off to the side, test it, then swap it in.

«بازسازی کامل از صفر» (:mod:`.title_rebuild`) crawls *into* the live title and
prunes afterwards, so for the minutes the crawl takes — and forever, if the new
answer turns out worse — viewers see whatever the providers happened to return.
This mode never lets an untested answer near the title:

1. **Stage.** Each provider crawls onto a *shadow* of the title: a copy whose
   ``save()`` does nothing, while :func:`staging` tells the two side effects a
   crawl has beyond the row itself (episode creation, Dornatv's VTT ingest) to
   stand down. The crawl still runs every guard it runs at import — identity,
   contamination, dead-host screen — so the staged set is exactly what an import
   would have stored, and nothing about the live title has changed.
2. **Test.** The staged links are probed: the best candidates for a film, a
   spread of episodes (first, last, and evenly between) for a series.
3. **Judge.** Applied only if the files answer live, most of what was probed is
   live, and a series does not lose a large share of the episodes it plays
   today unless today's set has already failed its own check. Every rejection
   has a reason the desk shows, and the title stays exactly as it was.
4. **Apply.** Backed up first (:func:`.title_rebuild.save_backup`, so «بازگردانی»
   works), then each provider that answered has its rows *replaced* by its
   staged rows, minus anything the test found dead. Hand-added (``source:
   manual``) and uploaded (``key``-only) rows are never touched, and a provider
   that could not be reached keeps its rows: no answer is not "the title is
   gone". Episodes then follow the links (create what the new set backs,
   unpublish what it no longer does).
"""

from __future__ import annotations

import copy
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

logger = logging.getLogger(__name__)

_staging: ContextVar[bool] = ContextVar('title_staging', default=False)

#: Probes spent testing one staged set. A film's few best encodes, or a spread
#: of a series' episodes — enough to tell a working set from a dead one without
#: holding the admin lane for minutes.
MOVIE_TEST_PROBES = 6
SERIES_TEST_PROBES = 10
#: A series' staged set must still back this share of the episodes it plays
#: today, unless today's set has already failed its check.
MIN_EPISODE_COVERAGE = 0.7

#: Verdict codes, shown on the desk as the reason a staged rebuild was or was not applied.
REJECT_NO_LINKS = 'no_fresh_links'
REJECT_DEAD = 'fresh_dead'
REJECT_MOSTLY_DEAD = 'fresh_mostly_dead'
REJECT_INCONCLUSIVE = 'test_inconclusive'
REJECT_COVERAGE = 'episode_coverage_drop'

VERDICT_LABELS = {
    REJECT_NO_LINKS: 'هیچ منبعی لینک تازه نداد',
    REJECT_DEAD: 'همهٔ لینک‌های تازهٔ تست‌شده مرده بودند',
    REJECT_MOSTLY_DEAD: 'بیشتر لینک‌های تازه مرده بودند',
    REJECT_INCONCLUSIVE: 'میزبان‌ها به تست جواب ندادند؛ چیزی تغییر نکرد',
    REJECT_COVERAGE: 'مجموعهٔ تازه قسمت‌های کمتری از وضعیت فعلی پوشش می‌داد',
}


@contextmanager
def staging() -> Iterator[None]:
    """Crawls inside this block must not touch anything but the object passed in."""
    token = _staging.set(True)
    try:
        yield
    finally:
        _staging.reset(token)


def is_staging() -> bool:
    return _staging.get()


def _rows(links) -> list[dict]:
    return [item for item in (links or []) if isinstance(item, dict)]


def _shadow(obj):
    """A copy of ``obj`` a crawl can write to freely: no save, no reload, no links yet."""
    shadow = copy.copy(obj)
    shadow.download_links = []
    if hasattr(obj, 'subtitle_tracks'):
        shadow.subtitle_tracks = list(getattr(obj, 'subtitle_tracks', None) or [])
    shadow.save = lambda *args, **kwargs: None
    shadow.refresh_from_db = lambda *args, **kwargs: None
    return shadow


# --------------------------------------------------------------------------
# 1. Stage
# --------------------------------------------------------------------------

def stage(obj, providers: list[str]) -> dict:
    """Crawl every provider onto a shadow of ``obj``. Nothing is written to ``obj``.

    Returns ``{'verdicts': {slug: filled|not_found|error}, 'rows': {slug: [...]}}``.
    """
    from .models import Movie
    from .provider_import.exceptions import ProviderImportError
    from .provider_import.multi_provider_crawl import _crawl_one_movie, _crawl_one_series
    from .provider_import.source_fill import _verdict_for

    crawl = _crawl_one_movie if isinstance(obj, Movie) else _crawl_one_series
    verdicts: dict[str, str] = {}
    rows: dict[str, list[dict]] = {}
    for slug in providers:
        shadow = _shadow(obj)
        try:
            with staging():
                result = crawl(slug, shadow, replace=True, queue_softsub=False)
        except ProviderImportError as exc:
            verdicts[slug] = _verdict_for(exc)
            logger.info('staged rebuild %s %s via %s: %s', type(obj).__name__, obj.pk, slug, exc)
        except Exception:
            verdicts[slug] = 'error'
            logger.exception('staged rebuild %s %s via %s failed', type(obj).__name__, obj.pk, slug)
        else:
            found = _rows((result or {}).get('download_links'))
            verdicts[slug] = 'filled' if found else 'not_found'
            if found:
                rows[slug] = found
    return {'verdicts': verdicts, 'rows': rows}


def staged_links(staged: dict) -> list[dict]:
    from .subtitle_extract import canonicalize_download_links

    merged: list[dict] = []
    for found in (staged.get('rows') or {}).values():
        merged.extend(found)
    canonical, _ = canonicalize_download_links(merged)
    return _dedupe(canonical)


def _dedupe(rows: list[dict]) -> list[dict]:
    from .subtitle_extract import _download_link_identity

    seen: set[str] = set()
    out = []
    for row in rows:
        key = _download_link_identity(row)
        if key and not key.startswith('|'):
            if key in seen:
                continue
            seen.add(key)
        out.append(row)
    return out


# --------------------------------------------------------------------------
# 2. Test
# --------------------------------------------------------------------------

def _episode_keys(links: list[dict]) -> set[tuple[int, int]]:
    """Episodes ``links`` can actually play (a stream URL, not just a parsed name)."""
    from .subtitle_extract import _links_for_episode, _pack_episode_keys, _prefer_episode_stream_url

    return {
        key for key in {k for k in _pack_episode_keys(links) if k}
        if _prefer_episode_stream_url(_links_for_episode(links, key[0], key[1]))
    }


def _spread(items: list, count: int) -> list:
    """``count`` items from ``items``: first, last, and evenly between."""
    if len(items) <= count:
        return list(items)
    if count <= 1:
        return [items[0]]
    step = (len(items) - 1) / (count - 1)
    picked = []
    for index in range(count):
        item = items[round(index * step)]
        if item not in picked:
            picked.append(item)
    return picked


def probe_targets(obj, links: list[dict]) -> list[str]:
    """The staged URLs worth probing, most telling first."""
    from .models import Series

    if isinstance(obj, Series):
        from .subtitle_extract import _links_for_episode, _prefer_episode_stream_url

        urls = []
        for season, episode in _spread(sorted(_episode_keys(links)), SERIES_TEST_PROBES):
            url = _prefer_episode_stream_url(_links_for_episode(links, season, episode))
            if url and url not in urls:
                urls.append(url)
        if urls:
            return urls
        # A pack nobody can key to episodes: still worth knowing if it is alive.
        candidates = links
        limit = SERIES_TEST_PROBES
    else:
        candidates = links
        limit = MOVIE_TEST_PROBES
    from .playback_gate import rank_candidates

    ranked = [str(item.get('url') or '').strip() for item in rank_candidates(candidates)]
    if not ranked:
        ranked = [str(item.get('url') or '').strip() for item in candidates]
    return list(dict.fromkeys(url for url in ranked if url.startswith(('http://', 'https://'))))[:limit]


def probe_staged(obj, links: list[dict]) -> dict:
    """Probe the staged set. ``{'live', 'dead', 'unknown', 'probed', 'dead_urls'}``."""
    from .media_verification import _probe

    tally = {'live': 0, 'dead': 0, 'unknown': 0, 'probed': 0, 'dead_urls': []}
    for url in probe_targets(obj, links):
        try:
            verdict = _probe(url, use_cache=False).verdict
        except Exception:
            logger.exception('staged rebuild: probe failed for %s', url[:120])
            verdict = 'unknown'
        tally['probed'] += 1
        tally[verdict if verdict in {'live', 'dead'} else 'unknown'] += 1
        if verdict == 'dead':
            tally['dead_urls'].append(url)
    return tally


# --------------------------------------------------------------------------
# 3. Judge
# --------------------------------------------------------------------------

def _current_check_failed(obj) -> bool:
    from .models import MediaCheck

    kind = 'series' if type(obj).__name__ == 'Series' else 'movie'
    latest = (
        MediaCheck.objects.filter(content_type=kind, object_id=obj.pk, episode_id=0)
        .order_by('-checked_at').values_list('status', flat=True).first()
    )
    return latest == MediaCheck.Status.FAILED


def judge(obj, links: list[dict], tally: dict) -> dict:
    """Should the staged set replace the live one? ``{'ok', 'reason', ...}``."""
    from .models import Series

    if not links:
        return {'ok': False, 'reason': REJECT_NO_LINKS}
    live, dead = tally.get('live', 0), tally.get('dead', 0)
    if not live:
        # Dead everywhere we looked, or nobody answered: either way no evidence
        # the new set is better, and replacing on no evidence is a gamble.
        return {'ok': False, 'reason': REJECT_DEAD if dead else REJECT_INCONCLUSIVE}
    if dead > live:
        return {'ok': False, 'reason': REJECT_MOSTLY_DEAD}
    detail: dict = {}
    if isinstance(obj, Series):
        today = _episode_keys(_rows(obj.download_links))
        staged = _episode_keys(links)
        detail = {'episodes_now': len(today), 'episodes_staged': len(staged)}
        if (
            today
            and len(staged) < MIN_EPISODE_COVERAGE * len(today)
            and not _current_check_failed(obj)
        ):
            return {'ok': False, 'reason': REJECT_COVERAGE, **detail}
    return {'ok': True, 'reason': '', **detail}


# --------------------------------------------------------------------------
# 4. Apply
# --------------------------------------------------------------------------

def _is_protected(row: dict) -> bool:
    """Rows no crawl can vouch for or against: a person's work."""
    return (
        str(row.get('source') or '').strip().lower() == 'manual'
        or not str(row.get('url') or '').strip()
    )


def apply(obj, staged: dict, links: list[dict], tally: dict) -> dict:
    """Swap the staged set in. The caller has already backed the title up."""
    from . import playback_gate
    from .models import Movie, PlaybackMode, Series
    from .provider_import.source_fill import link_provider
    from .subtitle_extract import (
        _download_link_identity,
        apply_availability_flags,
        canonicalize_download_links,
        ensure_episodes_from_download_links,
    )
    from .title_rebuild import reconcile_episodes

    answered = {
        slug for slug, verdict in (staged.get('verdicts') or {}).items()
        if verdict in {'filled', 'not_found'}
    }
    dead = set(tally.get('dead_urls') or [])
    fresh = [row for row in links if str(row.get('url') or '').strip() not in dead]

    current, _ = canonicalize_download_links(_rows(obj.download_links))
    kept = [row for row in current if _is_protected(row) or link_provider(row) not in answered]
    new_set = _dedupe([*kept, *fresh])

    before = {_download_link_identity(row) for row in current}
    after = {_download_link_identity(row) for row in new_set}
    previous_urls = {str(row.get('url') or '').strip() for row in current}

    obj.download_links = new_set
    fields = ['download_links', 'updated_at']
    if isinstance(obj, Movie):
        current_video = (obj.video_url or '').strip()
        hand_set = current_video and current_video not in previous_urls
        if not hand_set:
            # Decided by testing the sources, as at import; if none could be
            # tested, the best-named survivor goes in unverified rather than the
            # old file staying on a title that no longer lists it.
            _choice, gate_fields = playback_gate.gate_links(obj, new_set)
            fields += gate_fields
            live_urls = {str(row.get('url') or '').strip() for row in new_set}
            if (obj.video_url or '').strip() not in live_urls:
                from .provider_import.link_apply import _prefer_streamable_download

                replacement = _prefer_streamable_download(new_set)
                if replacement:
                    obj.video_url = replacement
                    obj.playback_mode = PlaybackMode.UNVERIFIED
                    obj.playback_checked_at = None
                    fields += ['video_url', 'playback_mode', 'playback_checked_at']
    fields += apply_availability_flags(obj, obj.download_links)
    obj.save(update_fields=list(dict.fromkeys(fields)))

    result = {
        'links': len(new_set),
        'added': len(after - before),
        'removed': len(before - after),
        'kept_protected': len(kept),
        'dropped_dead': len(dead),
    }
    if isinstance(obj, Series):
        try:
            result['episodes_created'] = ensure_episodes_from_download_links(obj)
        except Exception:
            logger.exception('staged rebuild: episode sync failed for series %s', obj.pk)
        episodes = reconcile_episodes(obj)
        result.update({
            'unpublished': episodes.get('unpublished', 0),
            'seasons_hidden': episodes.get('seasons_hidden', 0),
        })
    return result
