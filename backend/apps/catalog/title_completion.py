"""«تکمیل کامل»: one title, every repair the importer knows, from the admin desk.

The desk used to offer «جستجوی دوباره» as a myf2m-only discovery job on the
default ``celery`` queue — the lane a 30-minute playback-refresh crawl holds
most of the time — so a click routinely sat unrun for half an hour, series
stopped at «awaiting review», and nothing else (metadata, sizes, verification,
subtitles) followed. This runs the whole importer pipeline for one row, on its
own lane, and records each step so the desk can show progress as it happens:

    metadata → titles → sources (all providers) → sizes → verify → publish → problems → subtitles

``problems`` is the reason the title was on «سلامت محتوا» in the first place:
whatever the health queues held against it when the run started (no browser-safe
source, a subtitle gap, a failed check, a viewer report, missing fields, an
approximate score) gets its own repair, and the run records what was fixed, what
was queued and what is still open. See :mod:`.title_problems`.

Every step is the same function the importer lanes call, so a title completed
here is indistinguishable from one the importer completed on its own: manual
overrides are respected, links pass the identity guard, and publishing goes
through the same gates.

``mode='rebuild'`` («بازسازی کامل از صفر») re-extracts the title as if it were
imported today: it backs the title up, re-reads TMDB and IMDb's score, asks
every provider again past the page cache, keeps only the links they answered
with and the episodes those links back, chooses the online player source again
among the fresh links (``playback``), and re-hunts subtitles with ``force``.
See :mod:`.title_rebuild`.

``mode='staged'`` («بازسازی تست‌شده») is the same rebuild done safely: the
providers crawl onto a shadow copy, the staged set is probed, and only a set
that passes replaces the title's links (backed up first). A rejected set leaves
the title exactly as it was and says why. See :mod:`.title_staging`.
"""

from __future__ import annotations

import logging
import time
from types import SimpleNamespace

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Dedicated lane (see CELERY_TASK_ROUTES / the support worker's -Q list).
DESK_QUEUE = 'admin-ops'
#: Bulk selections go to the imports worker's lowest-priority lane, so fifty
#: titles never hold up a single desk click, and discovery/hot lanes (listed
#: first in that worker's -Q) still get picked between them.
BULK_QUEUE = 'imports'

STATE_TTL = 24 * 60 * 60
#: A run older than this without finishing is treated as dead (worker restart).
#: Just above the task's hard time limit.
STALE_AFTER = 40 * 60

STEPS = ('metadata', 'titles', 'sources', 'sizes', 'verify', 'publish', 'problems', 'subtitles')
REBUILD_STEPS = (
    'backup', 'metadata', 'titles', 'sources', 'episodes', 'playback', 'sizes', 'verify', 'publish',
    'problems', 'subtitles',
)
STAGED_STEPS = (
    'metadata', 'titles', 'stage', 'test', 'backup', 'apply', 'sizes', 'verify', 'publish', 'problems',
    'subtitles',
)
MODES = {'complete': STEPS, 'rebuild': REBUILD_STEPS, 'staged': STAGED_STEPS}
#: Steps that only make sense once a staged set has been applied.
_AFTER_APPLY = {'sizes', 'verify', 'publish', 'subtitles'}


def _steps(mode: str) -> tuple:
    return MODES.get(mode, STEPS)


def _key(kind: str, pk: int) -> str:
    return f'admin:complete:{kind}:{pk}'


def _kind(obj) -> str:
    from .models import Series

    return 'series' if isinstance(obj, Series) else 'movie'


def completion_state(obj) -> dict | None:
    """The last/current run for ``obj`` as the desk shows it, or ``None``."""
    return cache.get(_key(_kind(obj), obj.pk))


def is_running(obj) -> bool:
    return _is_active(completion_state(obj))


def _is_active(state: dict | None) -> bool:
    if not state or state.get('state') not in {'queued', 'running'}:
        return False
    started = float(state.get('started_ts') or 0)
    return time.time() - started < STALE_AFTER


def request_completion(
    obj, *, user_id: int | None, publish: bool = True, bulk: bool = False, mode: str = 'complete',
) -> dict:
    """Queue a completion run for ``obj``; a run already in flight is returned as is."""
    from .tasks import complete_title_task

    kind = _kind(obj)
    current = cache.get(_key(kind, obj.pk))
    if _is_active(current):
        return {**current, 'already_running': True}
    state = {
        'state': 'queued',
        'kind': kind,
        'id': obj.pk,
        'mode': mode if mode in MODES else 'complete',
        'publish': bool(publish),
        'started_at': timezone.now().isoformat(),
        'started_ts': time.time(),
        'finished_at': None,
        'steps': [{'key': step, 'status': 'pending', 'detail': ''} for step in _steps(mode)],
    }
    cache.set(_key(kind, obj.pk), state, STATE_TTL)
    try:
        complete_title_task.apply_async(
            args=(kind, obj.pk),
            kwargs={'user_id': user_id, 'publish': bool(publish), 'mode': state['mode']},
            queue=BULK_QUEUE if bulk else DESK_QUEUE,
        )
    except Exception:
        logger.exception('title completion: could not queue %s %s', kind, obj.pk)
        cache.delete(_key(kind, obj.pk))
        return {'error': 'queue_failed'}
    return state


class _Run:
    """Writes step progress to the cache as it goes, so the desk can poll it."""

    def __init__(self, kind: str, pk: int, publish: bool, mode: str = 'complete'):
        self.key = _key(kind, pk)
        state = cache.get(self.key)
        if not state or state.get('mode', 'complete') != mode:
            state = {
                'kind': kind, 'id': pk, 'mode': mode, 'publish': publish,
                'started_at': timezone.now().isoformat(), 'started_ts': time.time(),
                'steps': [{'key': step, 'status': 'pending', 'detail': ''} for step in _steps(mode)],
            }
        self.state = state
        self.state['state'] = 'running'
        self._save()

    def _save(self):
        cache.set(self.key, self.state, STATE_TTL)

    def step(self, key: str, status: str, detail: str = '', **extra):
        for row in self.state['steps']:
            if row['key'] == key:
                row.update({'status': status, 'detail': str(detail)[:300], **extra})
        self._save()

    def finish(self, state: str = 'done', **extra):
        self.state.update({'state': state, 'finished_at': timezone.now().isoformat(), **extra})
        self._save()


def _link_count(obj) -> int:
    return len([
        item for item in (obj.download_links or [])
        if isinstance(item, dict) and (str(item.get('url') or '').strip() or str(item.get('key') or '').strip())
    ])


def run_completion(
    kind: str, pk: int, *, user_id: int | None = None, publish: bool = True, mode: str = 'complete',
) -> dict:
    """Body of :func:`apps.catalog.tasks.complete_title_task`. Each step fails alone.

    In ``rebuild`` mode the backup step is the exception: without a backup
    nothing else runs.
    """
    from celery.exceptions import SoftTimeLimitExceeded
    from django.contrib.auth import get_user_model

    from .models import Movie, Series

    model = Series if kind == 'series' else Movie
    obj = model.objects.filter(pk=pk).first()
    mode = mode if mode in MODES else 'complete'
    rebuild = mode == 'rebuild'
    staged_mode = mode == 'staged'
    run = _Run(kind, pk, publish, mode)
    if obj is None:
        run.finish('failed', error='not_found')
        return run.state
    user = get_user_model().objects.filter(pk=user_id).first() if user_id else None
    request = SimpleNamespace(user=user)
    #: What the sources step learned, for the episodes step after it.
    found: dict = {}
    # What the health queues held against the title before anything ran, so a
    # problem the rebuild itself fixed is reported as fixed.
    try:
        from .title_problems import open_problems

        found['problems'] = open_problems(obj)
    except Exception:
        logger.exception('title completion: problem scan failed for %s %s', kind, pk)
        found['problems'] = {}

    def backup():
        from .title_rebuild import save_backup

        if staged_mode and not found.get('approved'):
            return 'skipped', 'مجموعهٔ تازه رد شد؛ چیزی تغییر نمی‌کند', {}
        entry = save_backup(obj, user=user)
        return 'ok', f'{_link_count(obj)} لینک ذخیره شد', {'backup_id': entry.pk}

    def metadata():
        # The same TMDB upsert the importer runs; manual fields are kept.
        if not obj.tmdb_id:
            return 'skipped', 'missing_tmdb_id', {}
        from .admin_ops import _resync_tmdb

        result = _resync_tmdb(obj)
        if result.get('error'):
            return 'error', result['error'], {}
        if not rebuild:
            return 'ok', '', {}
        # From scratch includes the score: IMDb's own, unless a person typed one.
        from .imdb_dataset import sync_title_rating

        rating = sync_title_rating(obj)
        return 'ok', f'نمره: {rating}', {'rating': rating}

    def titles():
        # fa from Wikidata/stored/MT, en Latin — the title-truth chain.
        from .title_repair import repair_titles

        changes = repair_titles(obj).get('changed') or {}
        return 'ok', '، '.join(sorted(changes)) if changes else 'بدون تغییر', {}

    def sources():
        # Every configured provider, from scratch for a rebuild, merge for complete.
        from .provider_import.source_fill import fill_title, wanted_providers

        providers, blocker = wanted_providers()
        before = _link_count(obj)
        extra = {}
        if rebuild:
            # Every provider, even ones the title already has, crawled off to
            # the side past the page cache, then swapped in atomically: only
            # what they answered with survives (plus manual/uploads and
            # providers that could not be reached). See title_rebuild.
            from .title_rebuild import crawl_fresh, prune_stale

            if providers:
                crawled = crawl_fresh(obj, providers)
                if len(crawled) == 3:
                    verdicts, fresh, fresh_rows = crawled
                else:  # pragma: no cover - backward compat for patched doubles
                    verdicts, fresh = crawled
                    fresh_rows = []
            else:
                verdicts, fresh, fresh_rows = {}, set(), []
            obj.refresh_from_db()
            pruned = prune_stale(obj, verdicts, fresh, fresh_rows)
            found.update(pruned=True, fresh=len(fresh))
            extra = {'fresh': len(fresh), 'removed': pruned.get('removed', 0), 'added': pruned.get('added', 0)}
        else:
            verdicts = fill_title(obj, providers) if providers else {}
        obj.refresh_from_db()
        after = _link_count(obj)
        if after != before:
            found['links_changed'] = True
        parts = [f'{name}: {verdict}' for name, verdict in verdicts.items()]
        if blocker:
            parts.append(f'kargadan: {blocker}')
        if rebuild and not extra['fresh']:
            # Nothing came back, so nothing was removed: the old links stand.
            parts.append('لینک تازه‌ای پیدا نشد؛ لینک‌های قبلی دست نخوردند')
            return 'empty', '، '.join(parts), {'links_before': before, 'links_after': after, **extra}
        status = 'ok' if after else 'empty'
        return status, '، '.join(parts), {'links_before': before, 'links_after': after, **extra}

    def stage():
        # Every provider, crawled onto a shadow: the live title is not touched.
        from .provider_import.source_fill import wanted_providers
        from .title_staging import stage as stage_title, staged_links

        providers, blocker = wanted_providers()
        staged = stage_title(obj, providers) if providers else {'verdicts': {}, 'rows': {}}
        links = staged_links(staged)
        found.update(staged=staged, links=links)
        parts = [f'{name}: {verdict}' for name, verdict in staged['verdicts'].items()]
        if blocker:
            parts.append(f'kargadan: {blocker}')
        status = 'ok' if links else 'empty'
        return status, '، '.join(parts) or 'منبعی در دسترس نبود', {
            'staged_links': len(links), 'links_before': _link_count(obj),
        }

    def test():
        from .title_staging import VERDICT_LABELS, judge, probe_staged

        links = found.get('links') or []
        tally = probe_staged(obj, links) if links else {'live': 0, 'dead': 0, 'unknown': 0, 'probed': 0}
        verdict = judge(obj, links, tally)
        found.update(tally=tally, verdict=verdict, approved=verdict['ok'])
        summary = f"{tally['probed']} تست: {tally['live']} سالم، {tally['dead']} مرده، {tally['unknown']} بی‌پاسخ"
        extra = {
            'live': tally['live'], 'dead': tally['dead'], 'unknown': tally['unknown'],
            'verdict': 'pass' if verdict['ok'] else verdict['reason'],
        }
        if verdict['ok']:
            return 'ok', summary, extra
        return 'blocked', f"{VERDICT_LABELS.get(verdict['reason'], verdict['reason'])} — {summary}", extra

    def apply_step():
        if not found.get('approved'):
            return 'skipped', 'تست قبول نشد؛ عنوان دست نخورد', {}
        from .title_staging import apply

        result = apply(obj, found['staged'], found['links'], found['tally'])
        found['applied'] = True
        detail = f"{result['added']} لینک تازه، {result['removed']} لینک قدیمی برداشته شد"
        if result.get('unpublished'):
            detail += f"، {result['unpublished']} قسمت بی‌لینک پنهان شد"
        return 'ok', detail, result

    def episodes():
        if not isinstance(obj, Series):
            return 'skipped', 'فقط برای سریال', {}
        if not found.get('fresh'):
            return 'skipped', 'منابع تازه‌ای نبود', {}
        from .title_rebuild import reconcile_episodes

        result = reconcile_episodes(obj)
        if result.get('skipped'):
            return 'skipped', result['skipped'], {}
        return 'ok', (
            f"{result['episodes']} قسمت با لینک، {result['unpublished']} قسمت بی‌لینک پنهان شد"
        ), {'unpublished': result['unpublished'], 'seasons_hidden': result['seasons_hidden']}

    def playback():
        # The importer keeps a working player link across re-crawls on purpose;
        # a rebuild picks it again among the fresh links, with fresh probes.
        if not found.get('fresh'):
            return 'skipped', 'لینک تازه‌ای نبود؛ پخش قبلی دست نخورد', {}
        from .title_rebuild import replay_playback

        result = replay_playback(obj)
        found['replayed'] = True
        detail = (
            f"{result['tested']} پخش دوباره انتخاب شد ({result['direct']} مستقیم، "
            f"{result['gateway']} با مبدل، {result['unverified']} بی‌پاسخ)"
        )
        if result['deferred']:
            detail += f"، {result['deferred']} قسمت به صف تست پخش رفت"
        if not result['browser_safe']:
            detail += '، نسخهٔ مناسب مرورگر در منابع نبود'
        return ('ok' if result['browser_safe'] else 'warn'), detail, {
            key: result[key] for key in ('tested', 'direct', 'gateway', 'unverified', 'deferred')
        }

    def sizes():
        # Measured, so the download table is not a column of dashes.
        from .link_sizes import size_title

        result = size_title(obj, budget_seconds=120)
        return 'ok', f"{result.get('sized', 0)} اندازه‌گیری شد، {max(result.get('left', 0), 0)} مانده", {}

    def verify():
        # A fresh MediaCheck — what the publish gate reads. A dead or
        # unreachable title is a finding, not a failed step.
        from .media_verification import verify_target

        verdict = verify_target(obj, use_cache=False)
        found['verified'] = True
        outcome = {'passed': 'ok', 'failed': 'blocked'}.get(verdict.get('status'), 'warn')
        return outcome, verdict.get('reason') or verdict.get('status') or '', {}

    def publish_step():
        # Archived stays archived: that was a person's decision, not a gap.
        archived = getattr(obj, 'publication_status', '') == 'archived'
        if obj.is_published:
            return 'skipped', 'منتشر شده', {}
        if archived:
            return 'skipped', 'بایگانی', {}
        if not publish:
            return 'skipped', 'درخواست نشد', {}
        from .admin_ops import _set_publication

        result = _set_publication(obj, 'published', request=request)
        if result.get('error'):
            blockers = result.get('blockers') or []
            return 'blocked', '، '.join(blockers or [result['error']]), {'blockers': blockers}
        return 'ok', '', {}

    def problems():
        # The staged rebuild's test is the gate on links: nothing here re-crawls
        # them with ``replace`` behind it.
        from .title_problems import fix_problems, summary

        before = found.get('problems') or {}
        if not before:
            return 'skipped', 'مشکلی ثبت نشده بود', {}
        result = fix_problems(
            obj, before, touch_links=not staged_mode, verified=bool(found.get('verified')),
            recrawled=bool(found.get('replayed')), queue_subtitles=not rebuild,
        )
        found['problem_result'] = result
        status = 'warn' if result['left'] else 'ok'
        return status, summary(result), {
            'fixed': result['fixed'], 'queued': result['queued'], 'left': result['left'],
        }

    def subtitles():
        # The urgent lane — the regular one can be thousands deep. Both
        # subtitle workers only read published rows.
        if not obj.is_published:
            return 'skipped', 'فقط برای عنوان منتشرشده', {}
        if not rebuild and 'subtitle_gap' in (found.get('problem_result') or {}).get('queued', []):
            return 'skipped', 'جستجوی اجباری در مرحلهٔ رفع مشکل‌ها در صف رفت', {}
        from .tasks import enqueue_movie_softsub_urgent, extract_series_softsub_task

        # A rebuild re-extracts from the new files: old tracks were timed to
        # encodes that may be gone.
        if isinstance(obj, Series):
            extract_series_softsub_task.apply_async(
                args=(obj.pk,), kwargs={'force': rebuild, 'episode_limit': 60 if rebuild else 24},
                queue='softsub-urgent',
            )
        else:
            enqueue_movie_softsub_urgent(obj.pk, force=rebuild or not bool(obj.subtitle_tracks))
        return 'ok', 'استخراج دوباره در صف فوری' if rebuild else 'در صف فوری', {}

    steps = {
        'backup': backup, 'episodes': episodes, 'playback': playback, 'stage': stage, 'test': test, 'apply': apply_step,
        'metadata': metadata, 'titles': titles, 'sources': sources, 'sizes': sizes,
        'verify': verify, 'publish': publish_step, 'problems': problems, 'subtitles': subtitles,
    }
    for key in _steps(mode):
        if staged_mode and key in _AFTER_APPLY and not found.get('applied'):
            run.step(key, 'skipped', 'بازسازی اعمال نشد')
            continue
        run.step(key, 'running')
        try:
            status, detail, extra = steps[key]()
        except SoftTimeLimitExceeded:
            run.step(key, 'error', 'time_limit')
            run.finish('failed', error='time_limit')
            raise
        except Exception as exc:
            logger.exception('title completion: step %s failed for %s %s', key, kind, pk)
            run.step(key, 'error', exc)
            if key == 'backup':
                run.finish('failed', error='backup_failed', failed_steps=['backup'])
                return run.state
        else:
            run.step(key, status, detail, **extra)
        obj.refresh_from_db()

    failed = [row['key'] for row in run.state['steps'] if row['status'] == 'error']
    outcome = {}
    if 'problem_result' in found:
        result = found['problem_result']
        outcome.update(
            problems_fixed=result['fixed'], problems_queued=result['queued'], problems_left=result['left'],
        )
    if staged_mode:
        # The one line the problem list shows per title: applied, or why not.
        verdict = found.get('verdict') or {}
        outcome.update({
            'verdict': 'applied' if found.get('applied') else 'rejected',
            'verdict_reason': '' if found.get('applied') else (
                verdict.get('reason') or ('apply_failed' if found.get('approved') else 'stage_failed')
            ),
        })
    if rebuild or found.get('applied') or found.get('links_changed'):
        # The site serves versioned catalog payloads; show the new links now,
        # not after the next coalesced bump. Complete mode also merges fresh
        # encodes, so it bumps too once the link count actually moved.
        try:
            from .cache import bump_catalog_cache_version

            bump_catalog_cache_version(force=True)
        except Exception:
            logger.exception('title completion: cache bump failed for %s %s', kind, pk)
    run.finish('done', failed_steps=failed, links=_link_count(obj), is_published=obj.is_published, **outcome)
    if user is not None:
        try:
            from .admin_api import _audit
            from .models import MovieSyncAudit

            _audit(
                request, MovieSyncAudit.Action.MANUAL_UPDATE,
                movie=obj if isinstance(obj, Movie) else None, tmdb_id=obj.tmdb_id,
                details={
                    'kind': kind, 'object_id': obj.pk, 'title': obj.title,
                    'reason': (
                        'staged_rebuild' if staged_mode else 'rebuild_title' if rebuild else 'complete_title'
                    ),
                    'failed_steps': failed, **outcome,
                    'links': run.state.get('links'), 'is_published': obj.is_published,
                },
            )
        except Exception:
            logger.exception('title completion: audit failed for %s %s', kind, pk)
    return run.state
