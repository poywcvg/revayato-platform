"""What is wrong with one title, and the repair for each — the «سلامت محتوا» list, per row.

The health page lists a title because of something specific: no browser can play
it, a subtitle never arrived, the hosts said its files are gone, a viewer
reported it, it was never verified, it is missing a publish field, or its score
is TMDB's guess rather than IMDb's. A rebuild from scratch replaces the links,
which fixes some of those and none of the others. This module closes the gap:

* :func:`open_problems` reads every problem the health queues would show for the
  title, from the same tables they read;
* :func:`fix_problems` runs the one repair each of those problems has — the same
  functions the background lanes use, never a second implementation — and then
  reads the problems again, so the run reports what it actually fixed, what was
  queued (subtitles are hunted on their own lane) and what is still open.

``touch_links=False`` is the staged rebuild's promise: a set that passed its test
(or was rejected and left the title as it was) is not then re-crawled with
``replace`` behind the test's back.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

#: Order is the order the admin reads them in.
LABELS = {
    'source_gap': 'پخش در مرورگر',
    'sourceless': 'بدون لینک',
    'failed_check': 'تست ناموفق',
    'unverified': 'تأیید نشده',
    'incomplete': 'اطلاعات ناقص',
    'approx_rating': 'نمرهٔ تقریبی',
    'subtitle_gap': 'زیرنویس',
    'reports': 'گزارش کاربر',
}

#: Rating provenance that is IMDb's own number (mirrors the health queue).
EXACT_RATING_SOURCES = ('imdb', 'omdb', 'manual')
#: Report types whose repair re-crawls or strips links.
LINK_REPORTS = frozenset({
    'playback', 'buffering', 'wrong_title', 'wrong_episode', 'quality', 'download_dead',
})
#: Reports repaired per run: each can crawl, and the run has a time limit.
MAX_REPORTS = 4


def _kind(obj) -> str:
    from .models import Series

    return 'series' if isinstance(obj, Series) else 'movie'


def open_problems(obj) -> dict[str, dict]:
    """Every open health-page problem for ``obj``, keyed by code (see :data:`LABELS`)."""
    from .completeness import publish_blockers
    from .media_verification import FRESH_SECONDS
    from .models import ContentIssueReport, MediaCheck, PlaybackSourceGap, PlaybackSubtitleGap
    from .playback_sources import DRAFT_GAP_REASON

    kind = _kind(obj)
    where = {'content_type': kind, 'object_id': obj.pk}
    found: dict[str, dict] = {}

    for reason in (
        PlaybackSourceGap.objects.filter(**where)
        .exclude(status=PlaybackSourceGap.Status.RESOLVED)
        .values_list('reason', flat=True)
    ):
        found['sourceless' if reason == DRAFT_GAP_REASON else 'source_gap'] = {}

    episodes = sorted(set(
        PlaybackSubtitleGap.objects.filter(**where)
        .exclude(status=PlaybackSubtitleGap.Status.RESOLVED)
        .values_list('episode_id', flat=True)[:100]
    ))
    if episodes:
        found['subtitle_gap'] = {'episodes': episodes}

    if MediaCheck.objects.filter(**where, status=MediaCheck.Status.FAILED).exists():
        found['failed_check'] = {}

    reports = list(
        ContentIssueReport.objects.filter(**where)
        .exclude(status__in=[ContentIssueReport.Status.RESOLVED, ContentIssueReport.Status.REJECTED])
        .order_by('-report_count', '-updated_at')
        .values_list('pk', flat=True)[:20]
    )
    if reports:
        found['reports'] = {'ids': reports}

    if obj.is_published:
        cutoff = timezone.now() - timedelta(seconds=FRESH_SECONDS)
        if not MediaCheck.objects.filter(**where, episode_id=0, checked_at__gte=cutoff).exists():
            found['unverified'] = {}

    try:
        blockers = publish_blockers(obj)
    except Exception:
        logger.exception('title problems: blockers failed for %s %s', kind, obj.pk)
        blockers = []
    if blockers:
        found['incomplete'] = {'gaps': blockers}

    imdb_id = (getattr(obj, 'imdb_id', '') or '').strip()
    if imdb_id and (obj.imdb_rating_source or '') not in EXACT_RATING_SOURCES:
        found['approx_rating'] = {}

    return {code: found[code] for code in LABELS if code in found}


def _fix_rating(obj) -> str:
    from .imdb_dataset import sync_title_rating

    return sync_title_rating(obj)


def _fix_persian_description(obj) -> str:
    from .localization import contains_persian, translate_to_persian

    source = (obj.description or '').strip()
    if not source or contains_persian(source):
        return 'skipped'
    translated = translate_to_persian(source)
    if not translated or not contains_persian(translated):
        return 'translation_failed'
    obj.description = translated
    obj.short_description = translated[:500]
    fields = ['description', 'short_description', 'updated_at']
    if any(f.name == 'meta_description' for f in obj._meta.get_fields()):
        obj.meta_description = translated[:500]
        fields.append('meta_description')
    obj.save(update_fields=fields)
    return 'translated'


def _fix_playback(obj, *, recrawled: bool = False) -> str:
    from .playback_sources import diagnose, remediate, resolve_source_gap

    if not diagnose(obj)['unplayable']:
        resolve_source_gap(obj, last_result='browser_safe')
        return 'refreshed'
    if recrawled:
        # The rebuild has just asked every provider; a second crawl would only
        # repeat the same answer (replay_playback recorded the gap).
        return 'unavailable'
    return remediate(obj)['outcome']


def _fix_sourceless(obj) -> str:
    from .playback_sources import has_any_source, resolve_source_gap

    if not has_any_source(obj):
        return 'still_sourceless'
    resolve_source_gap(obj, last_result='rebuild_found_links')
    return 'resolved'


def _queue_subtitles(obj, episodes: list[int]) -> str:
    """A forced hunt on the urgent lane — the gap closes when a track lands."""
    from .models import Series
    from .tasks import enqueue_movie_softsub_urgent, extract_series_softsub_task

    if not obj.is_published:
        # Both subtitle workers only read published rows.
        return 'needs_published'
    if isinstance(obj, Series):
        episode = next((pk for pk in episodes if pk), 0)
        extract_series_softsub_task.apply_async(
            args=(obj.pk,),
            kwargs={'force': True, 'preferred_episode_id': episode, 'episode_limit': 24},
            queue='softsub-urgent',
        )
    else:
        enqueue_movie_softsub_urgent(obj.pk, force=True)
    return 'queued'


def _fix_reports(ids: list[int], *, touch_links: bool) -> dict:
    from .content_remediation import recheck_report, remediate_report
    from .models import ContentIssueReport

    tally = {'resolved': 0, 'attempted': 0, 'held': 0}
    for report in ContentIssueReport.objects.filter(pk__in=ids)[:MAX_REPORTS]:
        if recheck_report(report):
            tally['resolved'] += 1
            continue
        if not touch_links and report.problem_type in LINK_REPORTS:
            tally['held'] += 1
            continue
        tally['attempted'] += 1
        remediate_report(report)
    return tally


def fix_problems(
    obj, before: dict[str, dict], *, touch_links: bool = True, verified: bool = False,
    recrawled: bool = False, queue_subtitles: bool = True,
) -> dict:
    """Run each problem's repair, then read the problems again.

    ``before`` is what :func:`open_problems` said when the run started, so a
    problem the rebuild itself fixed counts as fixed. Each repair fails alone.
    Returns ``fixed`` / ``queued`` / ``left`` (codes) and ``actions`` (what each
    repair answered).

    ``recrawled``: every provider was asked during this run already, so the
    playback repair judges the result instead of crawling again.
    ``queue_subtitles=False``: the caller queues its own (wider) forced hunt;
    an open subtitle gap on a published title then counts as queued.
    """
    actions: dict[str, object] = {}
    queued: list[str] = []
    gaps = set((before.get('incomplete') or {}).get('gaps') or [])

    def attempt(code, repair):
        try:
            actions[code] = repair()
        except Exception as exc:  # noqa: BLE001 - one repair never stops the others
            logger.exception('title problems: %s repair failed for %s %s', code, _kind(obj), obj.pk)
            actions[code] = f'error:{type(exc).__name__}'
        obj.refresh_from_db()

    if 'approx_rating' in before or 'missing_imdb_rating' in gaps:
        attempt('approx_rating', lambda: _fix_rating(obj))
    if 'missing_persian_description' in gaps:
        attempt('incomplete', lambda: _fix_persian_description(obj))
    if 'source_gap' in before:
        if touch_links:
            attempt('source_gap', lambda: _fix_playback(obj, recrawled=recrawled))
        else:
            actions['source_gap'] = 'held_by_test'
    if 'sourceless' in before:
        attempt('sourceless', lambda: _fix_sourceless(obj))
    if ('failed_check' in before or 'unverified' in before) and not verified:
        from .media_verification import verify_target

        attempt('verify', lambda: verify_target(obj, use_cache=False).get('status'))
    if 'reports' in before:
        attempt('reports', lambda: _fix_reports(before['reports']['ids'], touch_links=touch_links))

    after = open_problems(obj)
    if 'subtitle_gap' in after:
        if queue_subtitles:
            attempt('subtitle_gap', lambda: _queue_subtitles(obj, after['subtitle_gap']['episodes']))
        else:
            actions['subtitle_gap'] = 'queued' if obj.is_published else 'needs_published'
        if actions.get('subtitle_gap') == 'queued':
            queued.append('subtitle_gap')

    fixed = [code for code in before if code not in after]
    left = [code for code in after if code not in queued]
    return {'fixed': fixed, 'queued': queued, 'left': left, 'actions': actions}


def summary(result: dict) -> str:
    """One line for the run's step detail, in the admin's words."""
    def names(codes):
        return '، '.join(LABELS.get(code, code) for code in codes)

    parts = []
    if result.get('fixed'):
        parts.append(f"رفع شد: {names(result['fixed'])}")
    if result.get('queued'):
        parts.append(f"در صف: {names(result['queued'])}")
    if result.get('left'):
        parts.append(f"باقی مانده: {names(result['left'])}")
    return ' · '.join(parts) or 'مشکلی ثبت نشده بود'
