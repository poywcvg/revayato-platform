#!/usr/bin/env python3
"""Continuously run low-priority Film2Media delta sweeps and size backfills."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
IMPORT_SCRIPT = APP_ROOT / 'scripts' / 'import_missing_myf2m_batch.py'
SIZE_SCRIPT = APP_ROOT / 'scripts' / 'backfill_download_sizes.py'
SERIES_REFRESH_SCRIPT = APP_ROOT / 'scripts' / 'refresh_series_new_episodes.py'
MOVIE_REFRESH_SCRIPT = APP_ROOT / 'scripts' / 'refresh_movie_download_links.py'
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
    print(f'MYF2M_LOOP_START job={label}', flush=True)
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
    print(f'MYF2M_LOOP_END job={label} exit={code}', flush=True)
    return int(code)


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        os.nice(_integer('MYF2M_CRAWLER_NICE', 10, minimum=0))
    except OSError:
        pass

    interval = _number('MYF2M_CRAWL_INTERVAL_SECONDS', 21600, minimum=900)
    request_delay = _number('MYF2M_BULK_CRAWL_DELAY_SECONDS', 3.0, minimum=1.0)
    size_workers = _integer('MYF2M_SIZE_WORKERS', 4, minimum=1)
    size_timeout = _integer('MYF2M_SIZE_TIMEOUT_SECONDS', 10, minimum=5)
    size_probe_batch = _integer('MYF2M_SIZE_PROBE_BATCH', 600, minimum=50)
    size_limit = _integer('MYF2M_SIZE_LIMIT', 0, minimum=0)
    probe_sizes = str(os.environ.get('MYF2M_PROBE_SIZES', '1')).strip().lower() in {'1', 'true', 'yes', 'on'}
    refresh_delay = _number('MYF2M_REFRESH_DELAY_SECONDS', 0.7, minimum=0.1)
    series_refresh_limit = _integer('MYF2M_SERIES_REFRESH_LIMIT', 150, minimum=1)
    series_refresh_year_min = _integer('MYF2M_SERIES_REFRESH_YEAR_MIN', 2023, minimum=0)
    movie_refresh_limit = _integer('MYF2M_MOVIE_REFRESH_LIMIT', 200, minimum=1)
    crawl_workers = _integer('MYF2M_CRAWL_WORKERS', 6, minimum=1)
    listing_delay = _number('MYF2M_LISTING_DELAY', 0.08, minimum=0.0)
    recent_movie_pages = _integer('MYF2M_RECENT_MOVIE_PAGES', 16, minimum=1)
    recent_series_pages = _integer('MYF2M_RECENT_SERIES_PAGES', 10, minimum=1)
    deep_sweep_every = _integer('MYF2M_DEEP_SWEEP_EVERY_ROUNDS', 12, minimum=1)

    def importer(*, deep: bool) -> list[str]:
        return [
            sys.executable,
            str(IMPORT_SCRIPT),
            '--target', '0',
            '--max-movie-pages', '500' if deep else str(recent_movie_pages),
            '--max-series-pages', '200' if deep else str(recent_series_pages),
            '--delay', str(request_delay),
            '--listing-delay', str(listing_delay),
            '--workers', str(crawl_workers),
            '--new-only',
            '--require-playback',
            '--no-queue-softsub',
            '--no-dornatv-enrich',
            *(('--probe-sizes',) if probe_sizes else ()),
        ]
    sizes = [
        sys.executable,
        str(SIZE_SCRIPT),
        '--workers', str(size_workers),
        '--timeout', str(size_timeout),
        '--probe-batch-size', str(size_probe_batch),
        '--limit', str(size_limit),
    ]
    # Re-crawl pages of EXISTING published titles so a new episode or quality
    # that Film2Media adds after the first import also lands automatically.
    series_refresh = [
        sys.executable,
        str(SERIES_REFRESH_SCRIPT),
        '--delay', str(refresh_delay),
        '--limit', str(series_refresh_limit),
        *(('--year-min', str(series_refresh_year_min)) if series_refresh_year_min else ()),
    ]
    movie_refresh = [
        sys.executable,
        str(MOVIE_REFRESH_SCRIPT),
        '--delay', str(refresh_delay),
        '--limit', str(movie_refresh_limit),
        '--order', os.environ.get('MYF2M_MOVIE_REFRESH_ORDER', 'stale').strip().lower(),
    ]

    round_number = 0
    while not STOP.is_set():
        round_number += 1
        print(f'MYF2M_LOOP_ROUND round={round_number}', flush=True)
        deep_round = round_number % deep_sweep_every == 0
        # Avoid reading the first listing pages twice on a deep round. During
        # initial coverage (deep every round), start the full missing-title
        # sweep immediately; later configurations retain the fast delta lane.
        if deep_round:
            _run('catalog-deep', importer(deep=True))
        else:
            _run('catalog-recent', importer(deep=False))
        if not STOP.is_set():
            _run('series-refresh', series_refresh)
        if not STOP.is_set():
            _run('movie-refresh', movie_refresh)
        if not STOP.is_set():
            _run('sizes', sizes)
        if not STOP.is_set():
            print(f'MYF2M_LOOP_SLEEP seconds={int(interval)}', flush=True)
            STOP.wait(interval)
    print('MYF2M_LOOP_STOPPED', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
