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

    importer = [
        sys.executable,
        str(IMPORT_SCRIPT),
        '--target', '0',
        '--max-movie-pages', '500',
        '--max-series-pages', '200',
        '--delay', str(request_delay),
        '--new-only',
        '--require-playback',
        '--no-queue-softsub',
        '--no-dornatv-enrich',
    ]
    sizes = [
        sys.executable,
        str(SIZE_SCRIPT),
        '--source', 'myf2m',
        '--workers', str(size_workers),
        '--timeout', str(size_timeout),
        '--probe-batch-size', '300',
    ]

    round_number = 0
    while not STOP.is_set():
        round_number += 1
        print(f'MYF2M_LOOP_ROUND round={round_number}', flush=True)
        _run('catalog', importer)
        if not STOP.is_set():
            _run('sizes', sizes)
        if not STOP.is_set():
            print(f'MYF2M_LOOP_SLEEP seconds={int(interval)}', flush=True)
            STOP.wait(interval)
    print('MYF2M_LOOP_STOPPED', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
