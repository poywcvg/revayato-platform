"""Intake for viewer content-issue reports from the in-player «گزارش خطا».

:func:`record_content_issue_report` is the single write path used by the REST
endpoint. It resolves the reported title, upserts a deduped
:class:`~apps.catalog.models.ContentIssueReport`, mirrors it into the staff
support inbox (so nothing is ever invisible to a human), and — for the problem
types the engine can fix — kicks a short, best-effort remediation inline so a
popular breakage often heals before the viewer even reloads. The long tail is
finished by the ``remediate_content_reports`` drain.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

# Labels, accepted values and legacy aliases all come from the button catalogue,
# so the player, the ticket subject and the admin read the same wording and an
# older app's coarse type still lands on a button that has a repair behind it.
from apps.catalog.report_catalog import (
    PROBLEM_LABELS, VALID_PROBLEMS, normalize as normalize_problem,
)

VALID_CONTENT = frozenset({'movie', 'series'})

logger = logging.getLogger(__name__)


def reporter_key(request) -> str:
    """Stable per-viewer id for anon dedup: user id, else hashed session+IP+UA."""
    user = getattr(request, 'user', None)
    if user is not None and getattr(user, 'is_authenticated', False):
        return f'u{user.pk}'
    meta = getattr(request, 'META', {}) or {}
    forwarded = (meta.get('HTTP_X_FORWARDED_FOR') or '').split(',')[0].strip()
    ip = forwarded or meta.get('REMOTE_ADDR') or ''
    session_key = getattr(getattr(request, 'session', None), 'session_key', '') or ''
    seed = f'{session_key}|{ip}|{meta.get("HTTP_USER_AGENT", "")}'
    return 'a' + hashlib.sha1(seed.encode('utf-8')).hexdigest()[:32]


def _resolve(content_type: str, *, object_id: int, slug: str, episode_id: int):
    """Resolve to ``(obj, episode)``; either may be ``None`` if not found."""
    from apps.catalog.models import Episode, Movie, Series

    model = Movie if content_type == 'movie' else Series
    obj = None
    if object_id:
        obj = model.objects.filter(pk=object_id).first()
    if obj is None and slug:
        from apps.catalog.slugs import canonical_slug

        obj = model.objects.filter(slug=canonical_slug(model, slug)).first()

    episode = None
    if content_type == 'series' and episode_id:
        episode = (
            Episode.objects.select_related('season__series')
            .filter(pk=episode_id)
            .first()
        )
    return obj, episode


def _mirror_to_inbox(report, obj, episode, detail: str, *, reopened: bool = False):
    """File the report as a support ticket so staff always have eyes on it.

    Only for signed-in reporters (a ticket requires an owner). Idempotent per
    report row — a repeat report bumps the counter but never spams the inbox.
    """
    from apps.engagement.models import SupportTicket
    from apps.engagement import services as engagement_services

    if report.support_ticket_id:
        ticket = report.support_ticket
        if reopened and ticket.status in {
            SupportTicket.Status.RESOLVED, SupportTicket.Status.CLOSED,
            SupportTicket.Status.WAITING_USER,
        }:
            # The viewer says it is still broken: put the ticket back in the queue
            # (reply_support_ticket flips it to OPEN + unread for the engine).
            engagement_services.reply_support_ticket(
                ticket=ticket, author=ticket.user, is_staff_reply=False,
                body='این مشکل هنوز برطرف نشده و دوباره از پلیر گزارش شد.',
                auto_process=False,
            )
        return ticket
    reporter = report.reporter
    if reporter is None:
        return None

    label = PROBLEM_LABELS.get(report.problem_type, report.problem_type)
    where = report.title or getattr(obj, 'title', '') or report.slug
    if episode is not None:
        where = f'{where} — قسمت {report.episode_number or episode.episode_number}'
    body_lines = [f'گزارش خودکار از پلیر: «{label}».', f'عنوان: {where}']
    if report.playback_version:
        body_lines.append(f'نسخه پخش: {report.playback_version}')
    if detail.strip():
        body_lines.append(f'توضیح کاربر: {detail.strip()}')
    body_lines.append(f'کد گزارش داخلی: CIR-{report.pk}')

    ticket = engagement_services.create_support_ticket(
        user=reporter,
        category=(
            SupportTicket.Category.CONTENT_FIX
            if report.problem_type in {'wrong_title', 'wrong_episode'}
            else SupportTicket.Category.BUG
        ),
        subject=f'گزارش پلیر: {label} — {where}'[:200],
        body='\n'.join(body_lines),
        related_title=where[:255],
        related_year=getattr(obj, 'release_year', None) if report.content_type == 'movie' else None,
        # The report's own task remediates first and then lets the ticket speak, so
        # the ticket engine must not race it (two crawls, two replies).
        auto_process=False,
    )
    report.support_ticket = ticket
    report.save(update_fields=['support_ticket', 'updated_at'])
    return ticket


def _kick_remediation(report) -> bool:
    """Heal instantly when already fixed; otherwise hand the crawl to the worker.

    The provider re-crawl is slow (seconds to minutes) and must never run inside
    the viewer's HTTP request. A network-free recheck answers the common "a mirror
    already landed" case immediately; everything else is queued on the dedicated
    support lane right after the row commits. If the broker is unreachable the
    periodic drain (``drain_content_reports_task``) still picks the row up.
    """
    from apps.catalog.content_remediation import recheck_report

    try:
        if recheck_report(report):
            _wake_ticket(report)
            return True
    except Exception:  # noqa: BLE001 — recheck is an optimisation, never fatal
        logger.exception('instant recheck of content report %s failed', report.pk)

    def _send():
        try:
            from apps.catalog.tasks import handle_content_report_task

            handle_content_report_task.delay(report.pk)
        except Exception:  # noqa: BLE001 — broker down: the beat drain is the safety net
            logger.warning('could not queue remediation for content report %s', report.pk, exc_info=True)

    transaction.on_commit(_send)
    return True


def _wake_ticket(report) -> None:
    """Let the linked support ticket report the (already-known) outcome."""
    if not report.support_ticket_id:
        return
    from apps.engagement.tasks import enqueue_ticket_processing

    enqueue_ticket_processing(report.support_ticket_id)


def record_content_issue_report(
    request,
    *,
    content_type: str,
    problem_type: str,
    object_id: int = 0,
    slug: str = '',
    episode_id: int = 0,
    playback_version: str = '',
    source_url: str = '',
    detail: str = '',
    auto_remediate: bool = True,
) -> dict[str, Any]:
    """Validate, upsert (dedup), mirror to inbox, and best-effort remediate.

    Returns a small dict the player shows: ``{ ok, report_id, status,
    problem_type, auto }``. Never raises for player input — an invalid payload
    comes back as ``{ ok: False, error: ... }``.
    """
    from apps.catalog.models import ContentIssueReport

    content_type = (content_type or '').strip().lower()
    problem_type = (problem_type or '').strip().lower()
    if content_type not in VALID_CONTENT or problem_type not in VALID_PROBLEMS:
        return {'ok': False, 'error': 'invalid_payload'}
    # An older app still sends the coarse «مشکل زیرنویس»/«مشکل صدا»; store the
    # precise button it meant so the report routes to a real repair.
    problem_type = normalize_problem(problem_type)
    # A series-only problem needs an episode; a movie can't carry one.
    if content_type == 'movie':
        episode_id = 0
    if problem_type == 'wrong_episode' and (content_type != 'series' or not episode_id):
        return {'ok': False, 'error': 'episode_required'}

    obj, episode = _resolve(
        content_type, object_id=int(object_id or 0), slug=slug, episode_id=int(episode_id or 0),
    )
    if obj is None:
        return {'ok': False, 'error': 'content_not_found'}

    season_number = episode_number = 0
    if episode is not None:
        episode_number = episode.episode_number or 0
        season_number = getattr(getattr(episode, 'season', None), 'season_number', 0) or 0

    key = reporter_key(request)
    reporter = request.user if getattr(request.user, 'is_authenticated', False) else None
    detail = (detail or '').strip()[:5000]

    reopened = False
    with transaction.atomic():
        report, created = ContentIssueReport.objects.select_for_update().get_or_create(
            content_type=content_type,
            object_id=obj.pk,
            episode_id=episode.pk if episode is not None else 0,
            problem_type=problem_type,
            defaults={
                'slug': (slug or getattr(obj, 'slug', ''))[:255],
                'title': getattr(obj, 'title', '')[:300],
                'season_number': season_number,
                'episode_number': episode_number,
                'playback_version': playback_version[:32],
                'source_url': source_url[:1000],
                'detail': detail,
                'reporter': reporter,
                'reporter_key': key,
                'status': ContentIssueReport.Status.OPEN,
            },
        )
        if not created:
            # Repeat report: bump the signal, keep the freshest context, and
            # re-open a row we thought resolved but a viewer still sees broken.
            report.report_count = (report.report_count or 1) + 1
            reopen = report.status in {
                ContentIssueReport.Status.RESOLVED, ContentIssueReport.Status.UNAVAILABLE,
            } or (
                # Auto-retries gave up or crashed: a fresh viewer signal is a reason to try again.
                report.status == ContentIssueReport.Status.NEEDS_REVIEW
                and report.remediation_action in {'error', 'auto_exhausted'}
            )
            if reopen:
                reopened = True
                report.status = ContentIssueReport.Status.OPEN
                report.attempts = 0
            if playback_version:
                report.playback_version = playback_version[:32]
            if source_url:
                report.source_url = source_url[:1000]
            if detail and not report.detail:
                report.detail = detail
            if reporter is not None and report.reporter_id is None:
                report.reporter = reporter
            report.save(update_fields=[
                'report_count', 'status', 'attempts', 'playback_version',
                'source_url', 'detail', 'reporter', 'updated_at',
            ])

    # Always visible to staff (best-effort — inbox failure must not fail intake).
    try:
        _mirror_to_inbox(report, obj, episode, detail, reopened=reopened)
    except Exception:  # noqa: BLE001
        logger.warning('could not mirror content report %s to the inbox', report.pk, exc_info=True)

    auto_ran = False
    if auto_remediate and problem_type in ContentIssueReport.AUTO_PROBLEMS:
        auto_ran = _kick_remediation(report)

    report.refresh_from_db(fields=['status', 'report_count'])
    return {
        'ok': True,
        'report_id': report.pk,
        'status': report.status,
        'problem_type': problem_type,
        'report_count': report.report_count,
        'auto': auto_ran,
        'created': created,
    }


def read_report_status(report_id: int) -> dict[str, Any]:
    """Lightweight player poll for a filed report's remediation status."""
    from apps.catalog.models import ContentIssueReport

    report = ContentIssueReport.objects.filter(pk=report_id).only(
        'status', 'problem_type', 'remediation_action', 'last_result', 'report_count',
    ).first()
    if report is None:
        return {'ok': False, 'error': 'not_found'}
    return {
        'ok': True,
        'report_id': report_id,
        'status': report.status,
        'problem_type': report.problem_type,
        'action': report.remediation_action,
        'resolved': report.status == ContentIssueReport.Status.RESOLVED,
    }
