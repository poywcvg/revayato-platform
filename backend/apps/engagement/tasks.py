"""Celery tasks for the engagement app.

Everything here runs on the dedicated ``support`` queue (see
``CELERY_TASK_ROUTES``). That lane is served by its own worker so an answer to a
user is never stuck behind the 25-minute playback-refresh crawl that owns the
default ``celery`` lane.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task(name='apps.engagement.tasks.resolve_support_tickets_task')
def resolve_support_tickets_task(limit: int = 50):
    """Safety-net sweep of the support inbox (celery beat).

    Tickets are normally answered the moment they are filed
    (:func:`process_support_ticket_task`); this catches anything the event path
    missed (broker blip, worker restart) and drives the crawl-free retry phase that
    closes parked tickets once their title is genuinely fixed. Idempotent.
    """
    from apps.engagement.support_automation import resolve_open_tickets

    stats = resolve_open_tickets(limit=limit)
    if stats['processed']:
        logger.info(
            'resolve_support_tickets_task: processed=%s resolved=%s in_progress=%s '
            'waiting_user=%s errors=%s',
            stats['processed'], stats['resolved'], stats['in_progress'],
            stats['waiting_user'], stats['errors'],
        )
    return {k: v for k, v in stats.items() if k != 'outcomes'}


@shared_task(
    name='apps.engagement.tasks.process_support_ticket_task',
    time_limit=420, soft_time_limit=400,
)
def process_support_ticket_task(ticket_id: int):
    """Answer/remediate one ticket immediately after it is filed or replied to."""
    from apps.engagement.support_automation import process_ticket

    outcome = process_ticket(ticket_id)
    return {'ticket_id': ticket_id, 'action': outcome.action if outcome else 'skipped'}


def enqueue_ticket_processing(ticket_id: int) -> None:
    """Queue :func:`process_support_ticket_task` once the current transaction commits.

    Never raises: if the broker is unreachable the periodic sweep answers the
    ticket a few minutes later instead of the user's request failing.
    """
    def _send():
        try:
            process_support_ticket_task.delay(ticket_id)
        except Exception:  # noqa: BLE001
            logger.warning('could not queue support ticket %s', ticket_id, exc_info=True)

    transaction.on_commit(_send)
