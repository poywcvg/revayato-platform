#!/usr/bin/env python3
"""Permanent, self-healing subtitle backfill crawler for online playback.

Revolves through the catalog forever, finding every published movie / series
episode that still lacks a synced WebVTT subtitle track and handing it to the
dedicated ``softsub`` Celery worker. That worker does the smart, per-title work
already implemented elsewhere in the codebase:

  1. demux an embedded Persian subtitle straight out of the film's own stream
     (ffmpeg, for Soft-encoded CDN sources), else
  2. match the title by its exact name / year / IMDb id against the configured
     public sources (SubtitleStar, then Subzone.ir) and import the best result,
  3. convert whatever it finds to WebVTT and store it on the shared
     ``subtitle_tracks`` DB field — the single field both the web player and the
     Android app read, so the two stay in sync automatically.

Design mirrors ``run_myf2m_catalog_loop.py``: each unit of work runs as a child
process, so a crash in one round can never kill the loop, and ``restart:
unless-stopped`` on the compose service restarts the whole thing if the
container itself dies. SubtitleStar keeps a 24 h negative cache and a circuit
breaker, so revolving forever never hammers a source for a title that has no
subtitle available.

Round layout:

  * every round  — fast lane: hot-ordered ``--missing-only`` sweep (this
    week's trending titles, then the newest releases), so what people are
    watching right now gets subtitles first;
  * deep rounds  — random-ordered sweep with larger limits, so coverage rotates
    fairly across the *entire* back catalogue rather than re-probing the head;
  * every round  — drain stale viewer-reported playback gaps (belt-and-braces
    with the Celery beat task).
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


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def _stop(_signum, _frame) -> None:
    STOP.set()
    child = CHILD
    if child is not None and child.poll() is None:
        child.terminate()


def _run(label: str, command: list[str]) -> int:
    global CHILD
    if STOP.is_set():
        return 0
    print(f'SUBTITLE_LOOP_START job={label}', flush=True)
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
    print(f'SUBTITLE_LOOP_END job={label} exit={code}', flush=True)
    return int(code)


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        os.nice(_integer('SUBTITLE_CRAWLER_NICE', 10, minimum=0))
    except OSError:
        pass

    interval = _number('SUBTITLE_CRAWL_INTERVAL_SECONDS', 900, minimum=60)
    timeout = _integer('SUBTITLE_EXTRACT_TIMEOUT_SECONDS', 240, minimum=30)
    episode_limit = _integer('SUBTITLE_EPISODE_LIMIT', 24, minimum=1)
    # Fast lane — most-watched / newest titles first, every round.
    fast_movie_limit = _integer('SUBTITLE_FAST_MOVIE_LIMIT', 40, minimum=0)
    fast_series_limit = _integer('SUBTITLE_FAST_SERIES_LIMIT', 20, minimum=0)
    # Deep lane — random rotation over the whole back catalogue, every N rounds.
    deep_every = _integer('SUBTITLE_DEEP_EVERY_ROUNDS', 4, minimum=1)
    deep_movie_limit = _integer('SUBTITLE_DEEP_MOVIE_LIMIT', 120, minimum=0)
    deep_series_limit = _integer('SUBTITLE_DEEP_SERIES_LIMIT', 60, minimum=0)
    drain_gaps = _flag('SUBTITLE_DRAIN_GAPS', True)

    def sweep(*, order: str, movie_limit: int, series_limit: int) -> list[str]:
        return [
            sys.executable,
            str(MANAGE),
            'extract_softsub_tracks',
            '--missing-only',
            '--queue',
            '--order', order,
            '--limit', str(max(movie_limit, series_limit, 1)),
            '--movie-limit', str(movie_limit),
            '--series-limit', str(series_limit),
            '--episode-limit', str(episode_limit),
            '--timeout', str(timeout),
        ]

    gap_drain = [sys.executable, str(MANAGE), 'drain_playback_gaps']

    round_number = 0
    while not STOP.is_set():
        round_number += 1
        deep_round = round_number % deep_every == 0
        print(
            f'SUBTITLE_LOOP_ROUND round={round_number} deep={int(deep_round)}',
            flush=True,
        )

        if fast_movie_limit or fast_series_limit:
            _run('fast-missing', sweep(
                order='hot',
                movie_limit=fast_movie_limit,
                series_limit=fast_series_limit,
            ))

        if deep_round and not STOP.is_set() and (deep_movie_limit or deep_series_limit):
            _run('deep-rotate', sweep(
                order='random',
                movie_limit=deep_movie_limit,
                series_limit=deep_series_limit,
            ))

        if drain_gaps and not STOP.is_set():
            _run('gap-drain', gap_drain)

        if not STOP.is_set():
            print(f'SUBTITLE_LOOP_SLEEP seconds={int(interval)}', flush=True)
            STOP.wait(interval)

    print('SUBTITLE_LOOP_STOPPED', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
