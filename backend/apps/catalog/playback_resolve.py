"""Re-sign a title's playback URL at the moment a viewer asks to watch it.

Nearly every link in this catalog is time-limited. The providers hand out
``…?md5=<token>&expires=<unix>`` and the token lapses in about thirteen hours;
after that the CDN answers ``410 Gone`` and the player is left with «پخش ویدیو
ممکن نشد» on a film that is perfectly fine and still sitting on the origin.

The existing answer to that was a beat task
(:func:`tasks.refresh_expired_playback_task`) re-crawling 120 titles every
thirty minutes. That is 240 an hour against 6,956 movies and 19,688 episodes
whose tokens all lapse twice a day: a full pass takes days, so by construction
it can never catch up, and the titles people actually open are stale most of
the time. Sweeping harder is not the fix either — it is tens of thousands of
provider page fetches a day to re-sign links that nobody is going to watch.

So the refresh moves to where the demand is. A viewer opening a title is the
only reliable signal that *this* link needs to be valid *now*, and there are a
few hundred of those an hour, not tens of thousands. On that signal:

* if the stored URL's token is still good, this costs one string parse and
  returns — the overwhelmingly common case, and it must stay free;
* if it has lapsed, the title is re-crawled through the same providers the
  importer uses, re-tested through :mod:`playback_gate`, and the fresh URL is
  written back before the player is answered.

The scheduled sweep stays, demoted to what it is actually good at: healing
titles nobody has opened recently, in the background, at its own pace.

**Never fail closed.** Every failure here — a provider that is down, a crawl
that finds nothing, a lock held by another request — falls back to handing over
the stale URL with a reason attached. A lapsed link that probably will not play
is still strictly better than refusing to try, and the client already knows how
to report a failure (:mod:`support` «گزارش خطا»), which is the path that gets a
human involved when this one cannot help.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: How long one title's refresh may hold its lock. A provider page fetch is
#: seconds; this is the ceiling for a crawl that hangs, after which another
#: viewer is allowed to try again rather than inheriting a stuck lock.
LOCK_TTL_SECONDS = 90

#: How long a requester without the lock waits for the holder's result before
#: giving up and taking the stale URL. Sized to the player's own patience, not
#: to the crawl's: whoever holds the lock keeps going and the next viewer
#: benefits, so waiting longer here buys nothing.
WAIT_FOR_HOLDER_SECONDS = 12.0
_POLL_INTERVAL = 0.4

#: Minimum gap between two crawls of the same title. A provider that has stopped
#: carrying a film returns nothing no matter how often it is asked, and a
#: popular broken title must not turn into a crawl loop against the provider.
COOLDOWN_SECONDS = 900

#: Wall-clock ceiling on one refresh, because a viewer is watching a spinner for
#: every second of it. Measured on a real lapsed title, crawling both providers
#: and then codec-probing the winner took 68 seconds — most of it spent on work
#: this path does not need: a second provider after the first had already
#: produced a fresh link, and an ffprobe that timed out. Both are now skipped,
#: and this is the backstop for whatever else runs long. On expiry the stale URL
#: is handed over, which is where the viewer would have been anyway.
DEADLINE_SECONDS = 25.0

#: How long the lock survives a hand-off. Once the viewer has been answered the
#: crawl keeps running, and nothing must start a second one on the same title
#: while it does. Deliberately finite: if the thread dies without releasing, the
#: title becomes refreshable again in two minutes rather than never.
HANDOFF_LOCK_TTL_SECONDS = 120

#: Run the crawl on its own thread. Off for tests and management commands: a
#: second thread gets a second DB connection, which cannot see the open
#: transaction a ``TestCase`` wraps around itself, and a command has no viewer
#: waiting on it to be quick.
THREADED = os.environ.get('PLAYBACK_RESOLVE_THREADED', '1') != '0'

#: Ceiling on the crawl itself, which is a different question from what the
#: viewer waits for. Once handed off the crawl is working for the *next* viewer
#: and may run past :data:`DEADLINE_SECONDS`, but not forever: past this it is
#: no longer refreshing anything anybody is still waiting on.
CRAWL_CEILING_SECONDS = 90.0

_LOCK_PREFIX = 'catalog:playback-resolve:lock:'
_COOLDOWN_PREFIX = 'catalog:playback-resolve:cooled:'


@dataclass(frozen=True)
class Resolution:
    """What the viewer should be given, and what it took to get there."""

    url: str = ''
    mode: str = ''
    reason: str = ''
    refreshed: bool = False
    stale: bool = False
    elapsed_ms: int = 0
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            'video_url': self.url,
            'playback_mode': self.mode,
            'reason': self.reason,
            'refreshed': self.refreshed,
            'stale': self.stale,
            'elapsed_ms': self.elapsed_ms,
        }


def _key(owner, episode=None) -> str:
    """One lock per *crawled unit*, which is the series, not the episode.

    A season's episodes share one ``download_links`` list and one provider page,
    so twenty viewers opening twenty episodes of the same series must produce
    one crawl. Keying on the episode would produce twenty.
    """
    return f'{owner.__class__.__name__}:{owner.pk}'


def needs_refresh(target) -> bool:
    """Has this target's playback URL stopped being usable? Pure string test."""
    from apps.catalog.media_probe import signature_expired

    url = (getattr(target, 'video_url', '') or '').strip()
    if not url:
        return True
    return signature_expired(url)


def resolve_playback(owner, episode=None, *, allow_refresh: bool = True) -> Resolution:
    """The URL this viewer should be handed, re-signed if the stored one lapsed.

    ``owner`` is the Movie or Series that holds ``download_links``; ``episode``
    names which of them is wanted. Never raises.
    """
    from django.core.cache import cache

    started = time.monotonic()
    target = episode if episode is not None else owner
    current = (getattr(target, 'video_url', '') or '').strip()
    mode = getattr(target, 'playback_mode', '') or ''

    def done(url, reason, *, refreshed=False, stale=False, **detail) -> Resolution:
        return Resolution(
            url=url, mode=getattr(target, 'playback_mode', '') or mode, reason=reason,
            refreshed=refreshed, stale=stale,
            elapsed_ms=int((time.monotonic() - started) * 1000), detail=detail,
        )

    if not needs_refresh(target):
        return done(current, 'fresh')
    if not allow_refresh:
        return done(current, 'expired', stale=True)

    key = _key(owner, episode)
    if cache.get(_COOLDOWN_PREFIX + key):
        # Asked recently and it did not help. Do not queue behind a crawl that
        # is known not to fix this title.
        return done(current, 'cooldown', stale=True)

    if not cache.add(_LOCK_PREFIX + key, 'running', LOCK_TTL_SECONDS):
        return _await_holder(owner, target, key, started, mode)

    try:
        # The lock belongs to _refresh_now from here. It releases it inline when
        # the crawl finishes in time and hands it to the background thread when
        # it does not, so a handed-off crawl is never raced by the next viewer.
        return _refresh_now(owner, episode, target, key, started, mode)
    except Exception as exc:  # noqa: BLE001 — a viewer never sees a traceback
        cache.delete(_LOCK_PREFIX + key)
        logger.warning('playback_resolve: %s failed: %s', key, exc, exc_info=True)
        return done(current, 'refresh_failed', stale=True, error=type(exc).__name__)


def _await_holder(owner, target, key, started, mode) -> Resolution:
    """Another request is already re-crawling this title. Wait for its answer.

    Polls the row rather than the lock: the holder writes the fresh URL before
    it releases, so a changed ``video_url`` is the result arriving.
    """
    from django.core.cache import cache

    original = (getattr(target, 'video_url', '') or '').strip()
    deadline = time.monotonic() + WAIT_FOR_HOLDER_SECONDS
    while time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL)
        if cache.get(_LOCK_PREFIX + key) is None:
            break
    try:
        target.refresh_from_db(fields=['video_url', 'playback_mode'])
    except Exception:  # noqa: BLE001 — row vanished mid-wait
        pass
    url = (getattr(target, 'video_url', '') or '').strip()
    refreshed = bool(url) and url != original
    return Resolution(
        url=url or original,
        mode=getattr(target, 'playback_mode', '') or mode,
        reason='shared_refresh' if refreshed else 'shared_refresh_timeout',
        refreshed=refreshed,
        stale=not refreshed,
        elapsed_ms=int((time.monotonic() - started) * 1000),
    )


def _has_fresh_link(owner, episode) -> bool:
    """Does this title now carry any candidate whose token has not lapsed?

    Deliberately a string test over the freshly crawled rows — the point is to
    stop crawling, and paying for a probe to decide whether to stop would defeat
    that.
    """
    from apps.catalog import playback_gate
    from apps.catalog.media_probe import signature_expired

    try:
        owner.refresh_from_db(fields=['download_links'])
    except Exception:  # noqa: BLE001
        return False
    for item in playback_gate.candidate_links(owner, episode):
        url = str(item.get('url') or '').strip()
        if url and not signature_expired(url):
            return True
    return False


def _refresh_now(owner, episode, target, key, started, mode) -> Resolution:
    """Bound what the viewer waits for, without throwing the crawl away.

    The work below is not interruptible. One provider fetch can hang for as long
    as its socket timeout and the gate then probes every candidate, so the
    deadline that was checked *between* providers bounded nothing that actually
    took the time: measured on three real lapsed titles this ran 18s, 50s and
    68s against a 25s budget.

    Cutting the work into smaller interruptible pieces would only move the
    ceiling. Instead it runs on its own thread and the viewer waits
    :data:`DEADLINE_SECONDS` for it. Past that the viewer is handed the stale URL
    — which is where they would have been anyway — and the crawl *keeps going*:
    it still re-signs the links and still writes them back. The wait is paid
    once, by one viewer, and whoever asks next gets the fresh link. The lock
    travels with the thread so the hand-off is not raced.
    """
    from django.core.cache import cache

    if not THREADED:
        try:
            return _refresh_blocking(owner, episode, target, key, started, mode)
        finally:
            cache.delete(_LOCK_PREFIX + key)

    previous = (getattr(target, 'video_url', '') or '').strip()
    box: dict = {}
    finished = threading.Event()

    def work() -> None:
        try:
            box['value'] = _refresh_blocking(owner, episode, target, key, started, mode)
        except Exception as exc:  # noqa: BLE001
            box['error'] = exc
            logger.warning('playback_resolve: %s crawl failed: %s', key, exc, exc_info=True)
        finally:
            from django.db import connection
            try:
                # This thread opened a connection of its own; a request thread
                # would have had one closed for it.
                connection.close()
            except Exception:  # noqa: BLE001
                pass
            cache.delete(_LOCK_PREFIX + key)
            finished.set()

    threading.Thread(target=work, name=f'playback-resolve:{key}', daemon=True).start()

    if finished.wait(timeout=DEADLINE_SECONDS):
        error = box.get('error')
        if error is not None:
            raise error
        return box['value']

    # Still crawling. Keep the lock alive past this request so the next viewer
    # waits on this crawl rather than starting a second one.
    cache.set(_LOCK_PREFIX + key, 'running', HANDOFF_LOCK_TTL_SECONDS)
    if finished.is_set():
        # It landed in the gap between the timeout and the line above, which
        # would otherwise leave the lock held over a crawl that is already done.
        cache.delete(_LOCK_PREFIX + key)
        value = box.get('value')
        if value is not None:
            return value

    logger.info('playback_resolve: %s exceeded %.0fs, handed off', key, DEADLINE_SECONDS)
    return Resolution(
        url=previous, mode=mode, reason='refresh_in_progress', stale=True,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        detail={'handed_off': True},
    )


def _refresh_blocking(owner, episode, target, key, started, mode) -> Resolution:
    """Re-crawl this title's providers, re-test the links, write the winner back."""
    from django.core.cache import cache
    from django.utils import timezone

    from apps.catalog import playback_gate
    from apps.catalog.playback_refresh import _crawl_one
    from apps.catalog.provider_import.exceptions import ProviderImportError
    from apps.catalog.provider_import.multi_provider_crawl import catalog_link_providers

    previous = (getattr(target, 'video_url', '') or '').strip()
    codes: dict[str, str] = {}
    crawled = False
    deadline = started + CRAWL_CEILING_SECONDS

    for slug in catalog_link_providers():
        if time.monotonic() > deadline:
            codes[slug] = 'deadline'
            break
        try:
            # ``replace=False`` after the first success: a later provider adding
            # its mirrors must not drop the ones an earlier one just re-signed.
            _crawl_one(slug, owner, replace=not crawled, queue_softsub=False)
            codes[slug] = 'ok'
            crawled = True
        except ProviderImportError as exc:
            codes[slug] = getattr(exc, 'code', '') or 'provider_import_error'
        except Exception as exc:  # noqa: BLE001
            codes[slug] = type(exc).__name__
        if crawled and _has_fresh_link(owner, episode):
            # The question was "is there a link that has not lapsed", and there
            # is. Asking the next provider the same question costs the viewer
            # another crawl to learn nothing.
            break

    if not crawled:
        # Nothing was refreshed, so nothing downstream can be. Cool the title
        # down so the next viewer is answered instantly instead of waiting
        # through the same failing crawl.
        cache.set(_COOLDOWN_PREFIX + key, 1, COOLDOWN_SECONDS)
        return Resolution(
            url=previous, mode=mode, reason='provider_unavailable', stale=True,
            elapsed_ms=int((time.monotonic() - started) * 1000), detail={'providers': codes},
        )

    owner.refresh_from_db(fields=['download_links'])
    if episode is not None:
        episode.refresh_from_db(fields=['video_url', 'playback_mode'])

    # Fresh probes, no cache: the cached answers describe the URLs that just
    # got replaced.
    links = playback_gate.candidate_links(owner, episode)
    # ``max_tech=0``: no codec probe with a viewer waiting. A stalling host costs
    # the full ffprobe timeout, which was half of the 68 seconds this used to
    # take, and the answer it buys — direct versus gateway — is one the player
    # can discover for itself in a fraction of the time. The sweep still runs
    # the full test on this row later.
    choice = playback_gate.choose_playback_link(
        links, current=previous, use_cache=False, max_tech=0,
    )

    # Never clear here. This path runs while someone is waiting to watch, on one
    # crawl, against providers that may simply be having a bad minute — it is
    # the least qualified caller in the codebase to decide a film is gone.
    fields = playback_gate.apply_choice(target, choice, allow_clear=False)
    if fields:
        target.updated_at = timezone.now()
        target.save(update_fields=[*dict.fromkeys([*fields, 'updated_at'])])

    url = (getattr(target, 'video_url', '') or '').strip()
    still_stale = needs_refresh(target)
    if still_stale:
        cache.set(_COOLDOWN_PREFIX + key, 1, COOLDOWN_SECONDS)

    logger.info(
        'playback_resolve: %s %s -> %s (%s) refreshed=%s',
        key, previous[:60], url[:60], choice.reason or choice.mode, not still_stale,
    )
    return Resolution(
        url=url or previous,
        mode=getattr(target, 'playback_mode', '') or choice.mode,
        reason=choice.reason or ('refreshed' if not still_stale else 'still_expired'),
        refreshed=not still_stale and bool(url),
        stale=still_stale,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        detail={'providers': codes, 'tested': choice.tested},
    )
