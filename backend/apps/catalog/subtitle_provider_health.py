"""Traffic lane + per-pass provider outcome for the subtitle hunt.

Two facts every provider call needs, without threading them through a dozen
signatures:

* **Lane** — ``live`` while a viewer has the player open (the ensure request and
  the ``softsub-urgent`` worker), ``bulk`` for catalog backfill. Providers with a
  shared quota (SubDL) reserve their budget for the live lane: bulk backfill used
  to drain the key into HTTP 429 every quarter hour, so the viewer who actually
  pressed play found the provider closed.

* **Outages** — a provider that could not answer (rate limit, open circuit,
  network failure) is not a provider that answered "no subtitle". A pass that
  ends empty while any provider was down is *deferred*, never recorded as
  exhausted; otherwise one bad quarter hour hid subtitles that existed.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

LIVE = 'live'
BULK = 'bulk'

_lane: ContextVar[str] = ContextVar('subtitle_lane', default=BULK)
_outages: ContextVar[set[str] | None] = ContextVar('subtitle_provider_outages', default=None)


@contextmanager
def subtitle_lane(name: str) -> Iterator[None]:
    token = _lane.set(LIVE if name == LIVE else BULK)
    try:
        yield
    finally:
        _lane.reset(token)


def current_lane() -> str:
    return _lane.get()


def is_live_lane() -> bool:
    return _lane.get() == LIVE


@contextmanager
def track_provider_outages() -> Iterator[set[str]]:
    """Collect the providers that could not answer during this block."""
    seen: set[str] = set()
    token = _outages.set(seen)
    try:
        yield seen
    finally:
        _outages.reset(token)


def note_provider_outage(provider: str) -> None:
    seen = _outages.get()
    if seen is not None:
        seen.add(str(provider or 'unknown'))
