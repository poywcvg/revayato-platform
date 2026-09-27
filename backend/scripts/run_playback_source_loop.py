#!/usr/bin/env python3
"""Permanent, self-healing crawler for browser-unplayable titles.

Revolves through the catalog forever, finding every published movie / series
whose *only* live sources are ones a browser ``<video>`` cannot decode — a
progressive MKV/AVI/WMV container, or a HEVC/x265/10-bit / AV1 codec — so
iOS/Safari/Firefox viewers hit "پخش ویدیو ممکن نشد" while the download still
works. It re-crawls the configured providers (myf2m + dornatv) to pull a
browser-safe (HLS/MP4 + H.264) mirror, which providers frequently list alongside
the x265 encode but the first crawl did not import.

Design mirrors ``run_subtitle_backfill_loop.py``: each unit of work runs as a
child ``manage.py crawl_playback_sources`` process, so a crash in one round can
never kill the loop, and ``restart: unless-stopped`` on the compose service
restarts the whole thing if the container itself dies. A ``PlaybackSourceGap``
row per title gives backoff (titles no provider can fix are marked
``unavailable`` and only retried after a long window) so revolving forever never
hammers a provider for a title that has no browser-safe encode.

Round layout (kept deliberately light so it never slows the live site):

  * every round  — gate lane: re-test the playback link of a bounded batch of
    published titles (``verify_playback_links``), oldest check first, so a link
    that stopped being playable is found by us rather than by a viewer. It is
    the *detection* half of this container's own work: what it marks ``gateway``
    or ``none`` becomes a gap the fix lanes below then re-crawl;
  * every round  — confirm lane: re-test only the titles the gate already found
    nothing playable for. Blanking a link needs a second verdict from a separate
    run (``verify_playback_links`` will not delete on one sighting), and without
    this lane that second run would be a whole catalogue-pass away — the repair
    would keep being queued and the broken link would keep being served;
  * every round  — expired lane: re-crawl a small, popularity-ordered batch of
    titles whose every download link is an expired signed URL (or dead host), so
    self-expiring provider signatures never leave the online player dark;
  * every round  — fast lane: hot-ordered scan (this week's trending, then the
    newest releases),
    then remediate a small batch of the recorded gaps;
  * deep rounds  — random-ordered scan over the whole back catalogue so coverage
    rotates fairly instead of re-probing the head.

The expired lane is the durable replacement for the ``refresh_expired_playback``
Celery beat task, which was perpetually starved behind an unrelated backlog on
the default queue. Running it here — off Celery, in a dedicated container that
nothing else shares — means expiry refresh can no longer be crowded out.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
MANAGE = APP_ROOT / 'manage.py'
STOP = threading.Event()
CHILD: subprocess.Popen | None = None


def _number(name: str, default: float, *, minimum: float) -> float:
    try:
        return max(minimum, float(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def _integer(name: str, default: int, *, minimum: int) -> int:
    try:
        return max(minimum, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def _stop(_signum, _frame) -> None:
    STOP.set()
    child = CHILD
    if child is not None and child.poll() is None:
        child.terminate()


def _run(label: str, command: list[str]) -> int:
    global CHILD
    if STOP.is_set():
        return 0
    print(f'PLAYBACK_SOURCE_LOOP_START job={label}', flush=True)
    CHILD = subprocess.Popen(command)
    while CHILD.poll() is None and not STOP.wait(1):
        pass
    if STOP.is_set() and CHILD.poll() is None:
        CHILD.terminate()
    try:
        code = CHILD.wait(timeout=30)
    except subprocess.TimeoutExpired:
        CHILD.kill()
        code = CHILD.wait()
    finally:
        CHILD = None
    print(f'PLAYBACK_SOURCE_LOOP_END job={label} exit={code}', flush=True)
    return int(code)


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        os.nice(_integer('PLAYBACK_SOURCE_CRAWLER_NICE', 10, minimum=0))
    except OSError:
        pass

    interval = _number('PLAYBACK_SOURCE_INTERVAL_SECONDS', 1800, minimum=60)
    # Gate lane — re-test published playback links, oldest check first. Sized so
    # a round stays well inside the interval: every target costs a ranged GET and
    # at most two ffprobes, and this container must never be the reason the site
    # feels slow. The initial full backfill is a deliberate one-off run; this
    # lane is what keeps the answer true afterwards.
    gate_movie_limit = _integer('PLAYBACK_GATE_MOVIE_LIMIT', 80, minimum=0)
    gate_episode_limit = _integer('PLAYBACK_GATE_EPISODE_LIMIT', 80, minimum=0)
    gate_every = _integer('PLAYBACK_GATE_EVERY_ROUNDS', 1, minimum=1)
    gate_recheck_hours = _integer('PLAYBACK_GATE_RECHECK_HOURS', 168, minimum=0)
    gate_delay = _number('PLAYBACK_GATE_DELAY_SECONDS', 0.5, minimum=0)
    confirm_limit = _integer('PLAYBACK_GATE_CONFIRM_LIMIT', 60, minimum=0)
    confirm_hours = _integer('PLAYBACK_GATE_CONFIRM_HOURS', 24, minimum=0)
    # Expired lane — refresh titles whose only links are expired signed URLs.
    # A bounded, popularity-ordered batch per round; --no-delete so the crawler
    # never destroys catalog rows (deletion stays a separate, deliberate pass).
    expired_limit = _integer('PLAYBACK_EXPIRED_REFRESH_LIMIT', 60, minimum=0)
    expired_every = _integer('PLAYBACK_EXPIRED_REFRESH_EVERY_ROUNDS', 1, minimum=1)
    expired_delay = _number('PLAYBACK_EXPIRED_REFRESH_DELAY_SECONDS', 1.0, minimum=0)
    # Fast lane — hot-ordered scan (trending this week, then newest), every round.
    fast_scan_limit = _integer('PLAYBACK_SOURCE_FAST_SCAN_LIMIT', 400, minimum=0)
    fast_fix_limit = _integer('PLAYBACK_SOURCE_FAST_FIX_LIMIT', 8, minimum=0)
    # Deep lane — random rotation over the whole back catalogue, every N rounds.
    deep_every = _integer('PLAYBACK_SOURCE_DEEP_EVERY_ROUNDS', 6, minimum=1)
    deep_scan_limit = _integer('PLAYBACK_SOURCE_DEEP_SCAN_LIMIT', 1500, minimum=0)
    deep_fix_limit = _integer('PLAYBACK_SOURCE_DEEP_FIX_LIMIT', 12, minimum=0)
    retry_hours = _number('PLAYBACK_SOURCE_RETRY_UNAVAILABLE_HOURS', 72, minimum=1)
    delay = _number('PLAYBACK_SOURCE_RECRAWL_DELAY_SECONDS', 3, minimum=0)

    def sweep(*, order: str, scan_limit: int, fix_limit: int) -> list[str]:
        command = [
            sys.executable, str(MANAGE), 'crawl_playback_sources',
            '--order', order,
            '--scan-limit', str(scan_limit),
            '--retry-unavailable-hours', str(retry_hours),
            '--delay', str(delay),
        ]
        if fix_limit:
            command += ['--fix', '--fix-limit', str(fix_limit)]
        return command

    def gate_sweep(kind: str, limit: int, *, mode: str = '', hours: int | None = None) -> list[str]:
        return [
            sys.executable, str(MANAGE), 'verify_playback_links',
            f'--{kind}',
            '--limit', str(limit),
            '--order', 'stale',
            '--recheck-hours', str(gate_recheck_hours if hours is None else hours),
            '--delay', str(gate_delay),
            '--quiet',
            *(['--mode', mode] if mode else []),
        ]

    def expired_sweep(limit: int) -> list[str]:
        # Re-crawls providers to refresh expired signatures; heals the most-watched
        # dead titles first (collect_broken defaults to popularity order).
        return [
            sys.executable, str(APP_ROOT / 'scripts' / 'refresh_expired_playback.py'),
            '--limit', str(limit),
            '--delay', str(expired_delay),
            '--no-delete',
        ]

    round_number = 0
    while not STOP.is_set():
        round_number += 1
        deep_round = round_number % deep_every == 0
        print(
            f'PLAYBACK_SOURCE_LOOP_ROUND round={round_number} deep={int(deep_round)}',
            flush=True,
        )

        if round_number % gate_every == 0:
            # Detection before repair: a link demoted to gateway/none this round
            # is already a gap by the time the fix lanes run below.
            if gate_movie_limit and not STOP.is_set():
                _run('gate-movies', gate_sweep('movies', gate_movie_limit))
            if gate_episode_limit and not STOP.is_set():
                _run('gate-episodes', gate_sweep('episodes', gate_episode_limit))

        # Second opinion on yesterday's failures, before the fix lanes run: a
        # title the providers have since healed leaves the queue here, and one
        # they have not is finally allowed to stop pointing at a 404.
        if confirm_limit and not STOP.is_set():
            _run('gate-confirm-movies', gate_sweep(
                'movies', confirm_limit, mode='none', hours=confirm_hours,
            ))
            if not STOP.is_set():
                _run('gate-confirm-episodes', gate_sweep(
                    'episodes', confirm_limit, mode='none', hours=confirm_hours,
                ))

        if expired_limit and round_number % expired_every == 0 and not STOP.is_set():
            _run('expired', expired_sweep(expired_limit))

        if fast_scan_limit or fast_fix_limit:
            _run('fast', sweep(
                order='hot',
                scan_limit=fast_scan_limit,
                fix_limit=fast_fix_limit,
            ))

        if deep_round and not STOP.is_set() and (deep_scan_limit or deep_fix_limit):
            _run('deep', sweep(
                order='random',
                scan_limit=deep_scan_limit,
                fix_limit=deep_fix_limit,
            ))

        if not STOP.is_set():
            print(f'PLAYBACK_SOURCE_LOOP_SLEEP seconds={int(interval)}', flush=True)
            STOP.wait(interval)

    print('PLAYBACK_SOURCE_LOOP_STOPPED', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
