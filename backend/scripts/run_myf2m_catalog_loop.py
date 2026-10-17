#!/usr/bin/env python3
"""Permanent catalog ingestion loop: grow the archive and keep it accurate.

One round is the whole chain, in dependency order, so a title that arrives at the
top of a round can be live by the bottom of it:

  1. ``catalog-recent`` / ``catalog-deep`` — import titles Film2Media lists that
     we do not have yet (the only lane that creates rows);
  2. ``series-refresh`` / ``movie-refresh`` — re-crawl titles we already publish
     so new episodes and qualities land automatically;
  3. ``sizes`` — backfill download sizes;
  4. ``meta-complete-*`` — fill missing TMDB metadata and artwork;
  5. ``imdb-ratings`` — replace approximated scores with IMDb's own published
     numbers (its dataset is republished daily, so this is a standing job, not a
     one-off backfill);
  6. ``drafts`` — hunt real download sources for unpublished titles that have
     none at all, which is what actually completes the back archive;
  7. ``publish`` — publish whatever is now ready.

Lanes 5-7 live here rather than on Celery beat deliberately. They were queued on
the ``imports`` lane, which runs at concurrency 1 and was ~900 messages deep, so
they effectively never ran. This container is always on, shares its budget with
nothing, and is the one place that already owns provider crawling.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
IMPORT_SCRIPT = APP_ROOT / 'scripts' / 'import_missing_myf2m_batch.py'
SIZE_SCRIPT = APP_ROOT / 'scripts' / 'backfill_download_sizes.py'
SERIES_REFRESH_SCRIPT = APP_ROOT / 'scripts' / 'refresh_series_new_episodes.py'
MOVIE_REFRESH_SCRIPT = APP_ROOT / 'scripts' / 'refresh_movie_download_links.py'
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


# Hang-breaker for a single lane, not a schedule. ``restart: unless-stopped``
# only recovers a crawler that *exits*; a child blocked forever on a socket read
# leaves the loop waiting on it with the container still reporting healthy and no
# error in the log, which is indistinguishable from "the import just stopped".
# Any lane still running after this long is presumed wedged: it is killed, the
# exit is logged, and the loop moves on to the next lane instead of stalling for
# good. The default is deliberately far above the slowest legitimate lane (a full
# deep sweep) so it only ever fires on a genuine hang. 0 disables it.
JOB_TIMEOUT_SECONDS = _number('MYF2M_JOB_TIMEOUT_SECONDS', 4 * 60 * 60, minimum=0.0)


def _run(label: str, command: list[str]) -> int:
    global CHILD
    if STOP.is_set():
        return 0
    print(f'MYF2M_LOOP_START job={label}', flush=True)
    CHILD = subprocess.Popen(command)
    started = time.monotonic()
    timed_out = False
    while CHILD.poll() is None and not STOP.wait(1):
        if JOB_TIMEOUT_SECONDS and time.monotonic() - started > JOB_TIMEOUT_SECONDS:
            timed_out = True
            print(
                f'MYF2M_LOOP_TIMEOUT job={label} after={int(time.monotonic() - started)}s '
                f'limit={int(JOB_TIMEOUT_SECONDS)}s — killing a wedged lane',
                flush=True,
            )
            CHILD.terminate()
            break
    if (STOP.is_set() or timed_out) and CHILD.poll() is None:
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

    # Floor at 5 minutes: a round is already ~30+ minutes of work, and the floor
    # used to be 15 — which silently turned the configured 600 s into 900 s.
    interval = _number('MYF2M_CRAWL_INTERVAL_SECONDS', 21600, minimum=300)
    request_delay = _number('MYF2M_BULK_CRAWL_DELAY_SECONDS', 1.2, minimum=0.3)
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
    checkpoint = Path(os.environ.get(
        'MYF2M_CRAWL_CHECKPOINT',
        '/var/lib/revayato-crawler/myf2m-listings.json',
    ))

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
            '--checkpoint', str(checkpoint),
            '--resume',
            '--new-only',
            '--require-playback',
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
        '--delay', str(max(refresh_delay, request_delay)),
        '--limit', str(series_refresh_limit),
        '--workers', str(crawl_workers),
        *(('--year-min', str(series_refresh_year_min)) if series_refresh_year_min else ()),
    ]
    movie_refresh = [
        sys.executable,
        str(MOVIE_REFRESH_SCRIPT),
        '--delay', str(refresh_delay),
        '--limit', str(movie_refresh_limit),
        '--order', os.environ.get('MYF2M_MOVIE_REFRESH_ORDER', 'hot').strip().lower(),
    ]

    # Backfill missing TMDB metadata (age rating, trailer, cast/crew, artwork) on
    # titles that were imported before enrichment completed. --stale-days rotates
    # coverage so titles TMDB cannot fill are not re-fetched every round.
    meta_enabled = str(os.environ.get('MYF2M_META_COMPLETE_ENABLED', '1')).strip().lower() in {'1', 'true', 'yes', 'on'}
    meta_movie_limit = _integer('MYF2M_META_COMPLETE_MOVIE_LIMIT', 80, minimum=0)
    meta_series_limit = _integer('MYF2M_META_COMPLETE_SERIES_LIMIT', 40, minimum=0)
    meta_stale_days = _integer('MYF2M_META_COMPLETE_STALE_DAYS', 21, minimum=0)
    meta_sleep = _number('MYF2M_META_COMPLETE_SLEEP', 0.25, minimum=0.0)

    def meta_complete(*, movies: bool, limit: int) -> list[str]:
        return [
            sys.executable, str(MANAGE), 'complete_catalog_metadata',
            '--movies-only' if movies else '--series-only',
            '--limit', str(limit),
            '--stale-days', str(meta_stale_days),
            '--sleep', str(meta_sleep),
            # Drafts that already have links are one metadata pass away from the
            # publish gate; without this they were never filled at all.
            '--include-sourced-drafts',
        ]

    # Titles lane — every movie and series must carry a Persian title and an
    # English one. Fixes rows missing either (published first), then upgrades
    # machine-translated Persian titles to TMDB / Persian-Wikipedia names. Each
    # checked row is stamped, so a title no source can name yet is retried
    # every few hours instead of every round.
    titles_enabled = str(os.environ.get('CATALOG_TITLE_REPAIR_ENABLED', '1')).strip().lower() in {
        '1', 'true', 'yes', 'on',
    }
    titles_limit = _integer('CATALOG_TITLE_REPAIR_LIMIT', 150, minimum=0)
    titles_repair = [
        sys.executable, str(MANAGE), 'repair_catalog_titles',
        '--limit', str(titles_limit), '--sleep', '0.3', '--show', '5',
    ]

    # Draft-source lane — the archive completion pass. Thousands of drafts came
    # from the metadata crawlers with no download links at all; `diagnose()` calls
    # a title with zero sources "playable" (nothing is broken for the player), so
    # the playback crawler never owned them. This enrols them under the
    # `no_source` reason and spends a bounded provider budget per round hunting
    # real links. Deliberately small: the provider rate limit is shared with the
    # import lanes above, which serve titles viewers are waiting for.
    drafts_enabled = str(os.environ.get('CATALOG_DRAFT_SOURCE_ENABLED', '1')).strip().lower() in {
        '1', 'true', 'yes', 'on',
    }
    draft_scan_limit = _integer('CATALOG_DRAFT_SCAN_LIMIT', 600, minimum=0)
    draft_fix_limit = _integer('CATALOG_DRAFT_FIX_LIMIT', 40, minimum=0)
    draft_deep_scan_limit = _integer('CATALOG_DRAFT_DEEP_SCAN_LIMIT', 4000, minimum=0)
    draft_deep_fix_limit = _integer('CATALOG_DRAFT_DEEP_FIX_LIMIT', 80, minimum=0)
    draft_retry_hours = _number('CATALOG_DRAFT_RETRY_HOURS', 168, minimum=1)
    draft_delay = _number('CATALOG_DRAFT_DELAY_SECONDS', 1.4, minimum=0.0)
    # IMDb ratings lane — IMDb republishes its ratings file once a day, so run
    # this a few times a day and no more. One ~8 MB download, one sequential
    # scan, and a bulk_update of only the rows whose number actually moved.
    imdb_every = _integer('CATALOG_IMDB_SYNC_EVERY_ROUNDS', 6, minimum=1)
    imdb_enabled = str(os.environ.get('CATALOG_IMDB_SYNC_ENABLED', '1')).strip().lower() in {
        '1', 'true', 'yes', 'on',
    }
    # Publish lane — bounded, because every candidate costs a live media probe.
    # `publish_ready_catalog` is a no-op unless CATALOG_AUTO_PUBLISH is on, so the
    # switch stays the single place that decides whether drafts go live.
    publish_batch = _integer('CATALOG_PUBLISH_BATCH', 200, minimum=0)
    # Drafts the source hunter filled, re-asked at the gate every round (their
    # metadata is usually completed after the links landed).
    sourced_publish_limit = _integer('CATALOG_SOURCED_DRAFT_PUBLISH_LIMIT', 60, minimum=0)
    # IMDb Top 250 is deliberately NOT a lane of this loop any more. Here it only
    # ran after the ~17-minute listing walk, 20 positions a round, so the most
    # visible shelf waited behind everything else. It is now its own Celery lane
    # (`complete_top250_task` on `imports-top250`, every 10 minutes, restarted by
    # `import_watchdog_task` when it goes quiet). One driver only: two would crawl
    # the same positions twice.

    def draft_hunt(*, deep: bool) -> list[str]:
        return [
            sys.executable, str(MANAGE), 'hunt_draft_sources',
            # Hot first on a normal round (this week's trending, then the newest
            # releases) so what people are looking for right now is filled
            # first; a deep round rotates fairly over the whole tail.
            '--order', 'random' if deep else 'hot',
            '--scan-limit', str(draft_deep_scan_limit if deep else draft_scan_limit),
            '--fix',
            '--fix-limit', str(draft_deep_fix_limit if deep else draft_fix_limit),
            '--retry-hours', str(draft_retry_hours),
            '--delay', str(draft_delay),
        ]

    imdb_ratings = [sys.executable, str(MANAGE), 'sync_imdb_ratings']
    publish_ready = [
        sys.executable, str(MANAGE), 'publish_ready_catalog', '--limit', str(publish_batch),
        '--sourced-drafts-limit', str(sourced_publish_limit),
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
            import_code = _run('catalog-deep', importer(deep=True))
        else:
            import_code = _run('catalog-recent', importer(deep=False))
        # A checkpoint is only for an interrupted listing walk. Once a complete
        # pass succeeds, remove it so the next round starts at the newest pages.
        # If the process/container dies mid-pass, the durable file survives and
        # --resume continues from the last completed listing page.
        if import_code == 0:
            try:
                checkpoint.unlink(missing_ok=True)
            except OSError as exc:
                print(f'MYF2M_CHECKPOINT_CLEANUP_FAILED {exc}', flush=True)
        if not STOP.is_set():
            _run('series-refresh', series_refresh)
        if not STOP.is_set():
            _run('movie-refresh', movie_refresh)
        if not STOP.is_set():
            _run('sizes', sizes)
        if meta_enabled and not STOP.is_set() and meta_movie_limit:
            _run('meta-complete-movies', meta_complete(movies=True, limit=meta_movie_limit))
        if meta_enabled and not STOP.is_set() and meta_series_limit:
            _run('meta-complete-series', meta_complete(movies=False, limit=meta_series_limit))
        if titles_enabled and not STOP.is_set() and titles_limit:
            _run('titles', titles_repair)
        # Ratings before publishing: the publish gate refuses a title whose IMDb
        # score is still an approximation, so syncing first is what lets the
        # titles completed above actually go live in the same round.
        if imdb_enabled and not STOP.is_set() and round_number % imdb_every == 0:
            _run('imdb-ratings', imdb_ratings)
        if drafts_enabled and not STOP.is_set() and (draft_scan_limit or draft_fix_limit):
            _run('drafts', draft_hunt(deep=deep_round))
        if publish_batch and not STOP.is_set():
            _run('publish', publish_ready)
        if not STOP.is_set():
            print(f'MYF2M_LOOP_SLEEP seconds={int(interval)}', flush=True)
            STOP.wait(interval)
    print('MYF2M_LOOP_STOPPED', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
