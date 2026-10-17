"""Live fix broadcast for failed online playback inside a watch-party room.

A group room is the place a broken source hurts most: one dead mirror freezes
every member at once, and each member's player would otherwise file its own
report and run its own repair. This module is the fan-out half of
``POST /api/catalog/playback-failure/`` — after the catalog repair runs, the
outcome is pushed to ``watchparty.<invite_code>`` so:

* the host (and every guest) sees a Persian notice without reloading,
* a fixed URL is applied by clients that are still on the dead source,
* duplicate per-member reports collapse onto the same ``report_id``.

Best-effort by design: a missing channel layer, an ended room, or an unknown
code never fails the report itself.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def notify_room_of_fix(
    invite_code: str,
    *,
    report_id=None,
    problem_type: str = '',
    status: str = '',
    fixed_url: str = '',
    playback_mode: str = '',
    message_fa: str = '',
) -> bool:
    """Broadcast a playback-fix event to a room. Returns True when sent."""
    code = str(invite_code or '').strip()
    if not code:
        return False
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        from apps.watchparty.models import WatchRoom

        room = WatchRoom.objects.filter(invite_code=code).only('id', 'status').first()
        if room is None or room.status != WatchRoom.Status.ACTIVE:
            return False

        channel_layer = get_channel_layer()
        if channel_layer is None:
            return False

        payload = {
            'type': 'playback.fix',
            'report_id': report_id,
            'problem_type': str(problem_type or ''),
            'status': str(status or ''),
            'resolved': str(status or '') == 'resolved',
            'fixed_url': str(fixed_url or ''),
            'playback_mode': str(playback_mode or ''),
            'message_fa': str(message_fa or 'پخش در حال ترمیم است…'),
        }
        async_to_sync(channel_layer.group_send)(
            f'watchparty.{code}',
            {'type': 'watchparty.event', 'payload': payload},
        )
        return True
    except Exception:  # noqa: BLE001 — notify must never break remediation
        logger.warning('watchparty fix broadcast failed for room %s', code, exc_info=True)
        return False
