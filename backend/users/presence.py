"""Realtime presence tracking backed by Redis sorted sets.

Scores are unix timestamps. Members older than PRESENCE_WINDOW_SECONDS are
pruned on every read/write so counts reflect actual live clients.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

PRESENCE_WINDOW_SECONDS = 90
USERS_KEY = 'analytics:presence:users'
ANON_KEY = 'analytics:presence:anon'
_SESSION_RE = re.compile(r'^[A-Za-z0-9_.:-]{8,80}$')

_redis_client = None


def _redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis
    except ImportError:  # pragma: no cover
        return None
    url = getattr(settings, 'CACHE_URL', None) or getattr(settings, 'REDIS_URL', None)
    if not url:
        return None
    try:
        _redis_client = redis.from_url(url, decode_responses=True, socket_connect_timeout=1.5, socket_timeout=1.5)
    except Exception:  # noqa: BLE001
        logger.exception('presence redis connect failed')
        return None
    return _redis_client


def _cutoff(now: float | None = None) -> float:
    return (now or time.time()) - PRESENCE_WINDOW_SECONDS


def touch_presence(*, user_id: int | None = None, anonymous_session_id: str | None = None) -> None:
    client = _redis()
    if client is None:
        return
    now = time.time()
    cutoff = _cutoff(now)
    try:
        pipe = client.pipeline()
        if user_id:
            pipe.zadd(USERS_KEY, {str(int(user_id)): now})
            pipe.zremrangebyscore(USERS_KEY, 0, cutoff)
        anon = (anonymous_session_id or '').strip()
        if anon and _SESSION_RE.match(anon):
            # Authenticated users also send a session id; keep guest set for guests only
            # when user_id is absent.
            if not user_id:
                pipe.zadd(ANON_KEY, {anon: now})
                pipe.zremrangebyscore(ANON_KEY, 0, cutoff)
        pipe.execute()
    except Exception:  # noqa: BLE001
        logger.exception('presence touch failed')


def presence_counts() -> dict[str, Any]:
    client = _redis()
    if client is None:
        return {
            'authenticated': 0,
            'guests': 0,
            'user_ids': set(),
            'available': False,
            'window_seconds': PRESENCE_WINDOW_SECONDS,
        }
    now = time.time()
    cutoff = _cutoff(now)
    try:
        pipe = client.pipeline()
        pipe.zremrangebyscore(USERS_KEY, 0, cutoff)
        pipe.zremrangebyscore(ANON_KEY, 0, cutoff)
        pipe.zrangebyscore(USERS_KEY, cutoff, '+inf')
        pipe.zcard(ANON_KEY)
        _, _, user_ids_raw, guests = pipe.execute()
        user_ids = {int(item) for item in user_ids_raw if str(item).isdigit()}
        return {
            'authenticated': len(user_ids),
            'guests': int(guests or 0),
            'user_ids': user_ids,
            'available': True,
            'window_seconds': PRESENCE_WINDOW_SECONDS,
        }
    except Exception:  # noqa: BLE001
        logger.exception('presence count failed')
        return {
            'authenticated': 0,
            'guests': 0,
            'user_ids': set(),
            'available': False,
            'window_seconds': PRESENCE_WINDOW_SECONDS,
        }
