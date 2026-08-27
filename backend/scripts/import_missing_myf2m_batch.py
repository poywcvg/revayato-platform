#!/usr/bin/env python3
"""Import NEW Film2Media movies/series that are missing from our catalog.

Walks myf2m /movies/ and /series/ listings, skips anything already in the DB
(by TMDB, IMDb, or provider page path), keeps titles that expose Persian dub
and/or subtitle encodes when possible, publishes them, and queues SoftSub /
SubtitleStar extraction for online playback.
"""

from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import html
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

_APP_ROOT = Path(__file__).resolve().parents[1]
# When copied to /tmp inside the container, force the Django app root.
if not (_APP_ROOT / 'config').is_dir():
    _APP_ROOT = Path('/app')
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

LISTING_MOVIE_RE = re.compile(
    r'href="(?:https?://(?:www\.)?myf2m\.info)?/(?P<id>\d+)/(?P<slug>[^"/]+)/"',
    re.I,
)
SERIES_SLUG_RE = re.compile(
    r'href="(?:https?://(?:www\.)?myf2m\.info)?/series/(?P<slug>[a-z0-9\-]+)/"',
    re.I,
)
IMDB_RE = re.compile(r'(tt\d{7,10})', re.I)
H1_RE = re.compile(r'<h1[^>]*>(?P<title>.*?)</h1>', re.I | re.S)
TITLE_SERIES_RE = re.compile(
    r'دانلود\s+سریال\s+(.+?)(?:\s+بدون|\s+با\s+زیرنویس|\s+با\s+دوبله|\s*\||$)',
    re.I,
)


def _clean_html(value: str) -> str:
    # WordPress occasionally double-escapes apostrophes (for example
    # ``&amp;#8217;``), which makes an otherwise exact TMDB search miss.
    text = re.sub(r'<[^>]+>', '', value or '')
    for _ in range(2):
        text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


def _identity_title(value: object) -> str:
    """Comparable Latin title used only for conservative TMDB fallback matching."""
    text = html.unescape(str(value or '')).casefold().replace('&', ' and ')
    text = re.sub(r'\b(?:19|20)\d{2}\b', ' ', text)
    return ' '.join(re.findall(r'[a-z0-9]+', text))


def _select_tmdb_result(results, *, titles: list[str], year: int | None, content_type: str):
    """Return a strong title/year match; never trust TMDB's first fuzzy hit.

    Provider pages without IMDb are the dangerous path: a loose TMDB search can
    otherwise attach an unrelated catalog row to a provider page permanently.
    """
    wanted = [value for value in (_identity_title(title) for title in titles) if value]
    if not wanted:
        return None
    name_fields = ('name', 'original_name') if content_type == 'series' else ('title', 'original_title')
    date_field = 'first_air_date' if content_type == 'series' else 'release_date'
    best = None
    best_score = 0.0
    for row in list(results or [])[:12]:
        if not isinstance(row, dict) or not row.get('id'):
            continue
        candidate_year = str(row.get(date_field) or '')[:4]
        if year and candidate_year.isdigit() and abs(int(candidate_year) - int(year)) > 1:
            continue
        candidate_names = [
            value for value in (_identity_title(row.get(field)) for field in name_fields) if value
        ]
        for left in wanted:
            left_tokens = set(left.split())
            for right in candidate_names:
                right_tokens = set(right.split())
                if left == right:
                    score = 1.0
                else:
                    ratio = SequenceMatcher(None, left, right).ratio()
                    overlap = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
                    score = max(ratio, overlap)
                if score > best_score:
                    best, best_score = row, score
    # High threshold is intentional: an unmatched title is safer than corrupt
    # metadata/download bindings. IMDb-resolved rows bypass this fallback.
    return best if best_score >= 0.86 else None


def _has_exact_tmdb_artwork(details: object) -> bool:
    """Require artwork returned by the matched TMDB record itself."""
    if not isinstance(details, dict):
        return False
    return bool(
        str(details.get('poster_path') or '').strip()
        and str(details.get('backdrop_path') or '').strip()
    )


def _coverage_ok(links, *, require_both: bool) -> tuple[bool, dict]:
    from apps.catalog.subtitle_extract import download_links_imply_dub, download_links_imply_subtitle

    has_links = False
    for item in links or []:
        if not isinstance(item, dict):
            continue
        if str(item.get('url') or '').strip() or str(item.get('key') or '').strip():
            has_links = True
            break
    has_dub = download_links_imply_dub(links)
    has_sub = download_links_imply_subtitle(links)
    cov = {
        'has_links': has_links,
        'has_dub': has_dub,
        'has_sub': has_sub,
        'has_both': has_dub and has_sub,
        'link_count': sum(
            1 for item in (links or [])
            if isinstance(item, dict) and (
                str(item.get('url') or '').strip() or str(item.get('key') or '').strip()
            )
        ),
    }
    if not has_links:
        return False, cov
    if require_both:
        return cov['has_both'], cov
    # Import the complete provider catalog. Dub/subtitle are retained and
    # reported when available, but their absence must not hide a playable title.
    return True, cov


def _probe_link_sizes(links, *, workers: int = 6, timeout: int = 12) -> None:
    """Fill ``size_label`` for direct CDN links that still lack a size.

    Inline HEAD/Range probing so every freshly imported title exposes an
    accurate per-episode/per-quality size in the download box from day one.
    Skips subtitle tracks (WebVTT) and un-parseable URLs; uses a short timeout
    and bounded worker pool so it never stalls a slow provider crawl.
    """
    try:
        from apps.catalog.provider_import.providers.myf2m import enrich_download_link_metadata
    except Exception:
        enrich_download_link_metadata = None

    probe_rows = []
    for item in (links or []):
        if not isinstance(item, dict):
            continue
        if str(item.get('size_label') or '').strip():
            continue
        url = str(item.get('url') or '').strip()
        if not url.lower().startswith(('http://', 'https://')):
            continue
        if url.lower().rsplit('.', 1)[-1] in {'vtt', 'srt', 'ass'}:
            continue
        probe_rows.append(item)

    if not probe_rows:
        return

    if enrich_download_link_metadata is not None:
        try:
            result = enrich_download_link_metadata(
                probe_rows,
                timeout_seconds=timeout,
                max_workers=workers,
                min_size_bytes=1,
            )
            enriched = result.get('links') or []
            by_url = {str(row.get('url') or ''): row for row in enriched}
            for item in probe_rows:
                found = by_url.get(str(item.get('url') or ''))
                if found and found.get('size_label'):
                    item['size_label'] = found['size_label']
            return
        except Exception:
            pass

    # Lightweight fallback: shared backfill prober.
    from urllib.request import Request, urlopen
    from urllib.parse import urlsplit
    from concurrent.futures import ThreadPoolExecutor

    def _human(bytes_):
        if not bytes_ or bytes_ <= 0:
            return ''
        if bytes_ >= 1024 ** 3:
            return f'{bytes_ / 1024 ** 3:.1f} GB'
        if bytes_ >= 1024 ** 2:
            return f'{bytes_ / 1024 ** 2:.0f} MB'
        return f'{bytes_ // 1024} KB'

    def _probe(url_):
        headers = {'User-Agent': 'RevayatoCatalogCrawler/1.0 (+https://revayato.com)'}
        try:
            req = Request(url_, headers=headers, method='HEAD')
            with urlopen(req, timeout=timeout) as resp:
                value = resp.headers.get('Content-Length')
                if value and value.isdigit():
                    return int(value)
        except Exception:
            pass
        try:
            req = Request(url_, headers=dict(headers, Range='bytes=0-0'))
            with urlopen(req, timeout=timeout) as resp:
                cr = resp.headers.get('Content-Range') or ''
                m = re.search(r'/(\d+)\s*$', cr)
                if m:
                    return int(m.group(1))
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        sizes = list(pool.map(_probe, [item.get('url') for item in probe_rows]))
    for item, size in zip(probe_rows, sizes):
        label = _human(size)
        if label:
            item['size_label'] = label


def _merge_dornatv(obj, *, content_type: str) -> dict:
    """Pull extra qualities/kinds from Dornatv without wiping Film2Media rows."""
    try:
        from apps.catalog.provider_import.multi_provider_crawl import enrich_with_other_providers
        return enrich_with_other_providers(
            obj,
            already_used='myf2m',
            queue_softsub_extract=False,
        ) or {}
    except Exception as exc:
        return {'status': 'error', 'detail': str(exc)[:200]}


def main() -> int:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from django.conf import settings
    from django.core.cache import cache
    from django.db import transaction

    from apps.catalog.ingestion import upsert_tmdb_movie, upsert_tmdb_series
    from apps.catalog.iranian import is_iranian_catalog_item, is_iranian_tmdb_details
    from apps.catalog.models import Episode, Movie, Series
    from apps.catalog.provider_import.catalog_lookup import (
        _prefer_streamable_download,
        crawl_myf2m_downloads_for_series,
    )
    from apps.catalog.provider_import.exceptions import ProviderImportError, ProviderRateLimited
    from apps.catalog.provider_import.registry import get_connector
    from apps.catalog.provider_import.providers.myf2m_parser import parse_download_links
    from apps.catalog.subtitle_extract import (
        apply_availability_flags,
        coalesce_download_links,
        download_links_imply_softsub,
    )
    from apps.catalog.tasks import enqueue_movie_softsub, enqueue_series_softsub
    from apps.catalog.top_catalog import (
        _has_download_links,
        _publish_movie,
        _publish_series,
        _suppress_provider_publish_signals,
        _version_coverage,
    )
    from apps.catalog.tmdb import configured_tmdb_client
    from config.public_urls import normalize_download_links

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--target',
        type=int,
        default=0,
        help='Total new titles to keep (0 = unlimited until listings end)',
    )
    parser.add_argument(
        '--movies-target',
        type=int,
        default=0,
        help='Movie quota (0 with --target 0 = unlimited movies)',
    )
    parser.add_argument(
        '--series-target',
        type=int,
        default=0,
        help='Series quota (0 with --target 0 = unlimited series)',
    )
    parser.add_argument('--max-movie-pages', type=int, default=500)
    parser.add_argument('--max-series-pages', type=int, default=200)
    parser.add_argument('--start-movie-page', type=int, default=1)
    parser.add_argument('--start-series-page', type=int, default=1)
    parser.add_argument('--delay', type=float, default=0.45)
    parser.add_argument(
        '--require-both',
        action='store_true',
        help='Only keep titles that expose both dub and subtitle encodes',
    )
    parser.add_argument('--skip-movies', action='store_true')
    parser.add_argument('--skip-series', action='store_true')
    parser.add_argument('--queue-softsub', action='store_true', default=True)
    parser.add_argument('--no-queue-softsub', action='store_false', dest='queue_softsub')
    parser.add_argument(
        '--no-dornatv-enrich',
        action='store_true',
        help='Skip merging Dornatv qualities after Film2Media crawl',
    )
    parser.add_argument(
        '--new-only',
        action='store_true',
        help='Never update, activate, or merge a title already present in the catalog.',
    )
    parser.add_argument(
        '--require-playback',
        action='store_true',
        help='Only publish movies with a direct stream URL and series with playable episodes.',
    )
    parser.add_argument(
        '--probe-sizes',
        action='store_true',
        default=False,
        help='Probe CDN Content-Length for freshly imported links to record accurate size_label per episode/quality.',
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=int(os.environ.get('MYF2M_CRAWL_WORKERS', '4')),
        help='Number of parallel worker threads for per-title import (default 4).',
    )
    parser.add_argument(
        '--listing-delay',
        type=float,
        default=float(os.environ.get('MYF2M_LISTING_DELAY', '0.15')),
        help='Delay between listing-page requests (cheap page walk; separate from --delay).',
    )
    parser.add_argument(
        '--checkpoint',
        default=os.environ.get('MYF2M_CRAWL_CHECKPOINT', ''),
        help='Path to a JSON resume/checkpoint file for the listing walk.',
    )
    parser.add_argument(
        '--resume',
        action='store_true',
        help='When --checkpoint is set, continue from the last saved listing page instead of page 1.',
    )
    args = parser.parse_args()

    target = max(0, int(args.target))
    unlimited = target == 0 and int(args.movies_target) == 0 and int(args.series_target) == 0
    if args.movies_target or args.series_target:
        movies_target = max(0, int(args.movies_target))
        series_target = max(0, int(args.series_target))
        if unlimited is False and target == 0:
            unlimited = movies_target == 0 or series_target == 0
    elif unlimited:
        movies_target = 10**9
        series_target = 10**9
    else:
        movies_target = int(round(target * 0.65))
        series_target = max(0, target - movies_target)
    if args.skip_movies:
        movies_target = 0
        if not unlimited and not args.series_target:
            series_target = target
    if args.skip_series:
        series_target = 0
        if not unlimited and not args.movies_target:
            movies_target = target

    delay = max(0.0, float(args.delay))
    listing_delay = max(0.0, float(args.listing_delay))
    workers = max(1, int(args.workers))
    require_both = bool(args.require_both)
    enrich_dornatv = not bool(args.no_dornatv_enrich)
    new_only = bool(args.new_only)
    require_playback = bool(args.require_playback)
    probe_sizes = bool(args.probe_sizes)
    checkpoint_path = (args.checkpoint or '').strip() or None
    resume = bool(args.resume)
    tmdb_miss_ttl = max(3600, int(os.environ.get('MYF2M_TMDB_MISS_CACHE_SECONDS', str(7 * 86400))))

    def _tmdb_miss_key(content_type: str, page_path: str) -> str:
        import hashlib
        digest = hashlib.sha1(page_path.encode('utf-8')).hexdigest()
        return f'catalog:myf2m:tmdb-miss:{content_type}:{digest}'

    # --- resume / checkpoint state -------------------------------------
    check_state = {
        'movie_page': 1,
        'series_page': 1,
        'movies_kept': 0,
        'series_kept': 0,
    }
    if checkpoint_path:
        ck = Path(checkpoint_path)
        if resume and ck.exists() and ck.is_file():
            try:
                loaded = json.loads(ck.read_text(encoding='utf-8'))
                if isinstance(loaded, dict):
                    check_state['movie_page'] = max(1, int(loaded.get('movie_page') or 1))
                    check_state['series_page'] = max(1, int(loaded.get('series_page') or 1))
                    check_state['movies_kept'] = int(loaded.get('movies_kept') or 0)
                    check_state['series_kept'] = int(loaded.get('series_kept') or 0)
            except Exception as exc:
                print(f'  -> checkpoint load failed ({exc}); starting from page 1', flush=True)
        if check_state['movie_page'] > 1:
            print(f'  -> resume movie listing from page {check_state["movie_page"]}', flush=True)
        if check_state['series_page'] > 1:
            print(f'  -> resume series listing from page {check_state["series_page"]}', flush=True)

    def _save_checkpoint(*, also=False):
        if not checkpoint_path:
            return
        try:
            ck = Path(checkpoint_path)
            ck.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                'movie_page': stats.get('last_movie_page', check_state['movie_page']),
                'series_page': stats.get('last_series_page', check_state['series_page']),
                'movies_kept': stats.get('movies_kept', 0),
                'series_kept': stats.get('series_kept', 0),
                'updated_at': time.time(),
            }
            tmp = ck.with_suffix('.tmp')
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
            tmp.replace(ck)
        except Exception as exc:  # pragma: no cover - best effort
            print(f'  -> checkpoint save failed: {exc}', flush=True)

    def tmdb_details_with_retry(call, *, label: str, attempts: int = 3):
        """Retry the complete TMDB details call, including client-level retries."""
        for attempt in range(1, attempts + 1):
            try:
                return call()
            except Exception as exc:
                if attempt >= attempts:
                    raise
                wait = min(20.0, 3.0 * attempt)
                print(
                    f'  -> transient TMDB details error {label} '
                    f'attempt={attempt}/{attempts}: {exc}; sleep {wait:.0f}s',
                    flush=True,
                )
                time.sleep(wait)

    existing_movie_tmdb = set(
        Movie.objects.exclude(tmdb_id__isnull=True).values_list('tmdb_id', flat=True),
    )
    existing_series_tmdb = set(
        Series.objects.exclude(tmdb_id__isnull=True).values_list('tmdb_id', flat=True),
    )
    existing_movie_imdb = {
        str(v).strip().lower()
        for v in Movie.objects.exclude(imdb_id__isnull=True).exclude(imdb_id='').values_list('imdb_id', flat=True)
    }
    existing_series_imdb = {
        str(v).strip().lower()
        for v in Series.objects.exclude(imdb_id__isnull=True).exclude(imdb_id='').values_list('imdb_id', flat=True)
    }

    existing_movie_paths: set[str] = set()
    for links in (
        Movie.objects.all()
        .exclude(download_links=[])
        .exclude(download_links__isnull=True)
        .values_list('download_links', flat=True)
        .iterator(chunk_size=200)
    ):
        for item in links or []:
            if isinstance(item, dict):
                path = str(item.get('page_path') or '').strip()
                if path:
                    existing_movie_paths.add('/' + path.strip('/') + '/')

    existing_series_paths: set[str] = set()
    for links in (
        Series.objects.all()
        .exclude(download_links=[])
        .exclude(download_links__isnull=True)
        .values_list('download_links', flat=True)
        .iterator(chunk_size=100)
    ):
        for item in links or []:
            if not isinstance(item, dict):
                continue
            path = str(item.get('page_path') or '').strip()
            if path:
                existing_series_paths.add('/' + path.strip('/') + '/')
                continue
            url = str(item.get('page_url') or item.get('url') or '')
            if '/series/' in url:
                try:
                    p = urlparse(url).path
                except Exception:
                    p = ''
                if p.startswith('/series/'):
                    existing_series_paths.add(p.rstrip('/') + '/')

    print(
        f'target={target or "unlimited"} movies_target={movies_target if movies_target < 10**8 else "unlimited"} '
        f'series_target={series_target if series_target < 10**8 else "unlimited"} '
        f'require_both={require_both} require_playback={require_playback} '
        f'new_only={new_only} enrich_dornatv={enrich_dornatv} '
        f'draft_or_all_movies_tmdb={len(existing_movie_tmdb)} '
        f'draft_or_all_series_tmdb={len(existing_series_tmdb)} '
        f'published_movies={Movie.objects.filter(is_published=True).count()} '
        f'published_series={Series.objects.filter(is_published=True).count()}',
        flush=True,
    )

    client = configured_tmdb_client()
    connector = get_connector('myf2m')
    connector.authenticate()

    # --- parallel worker infrastructure -------------------------------
    # MyF2MConnector is stateful (throttle clock + httpx client) and NOT
    # thread-safe, so each worker thread gets its own connector instance. A
    # shared lock keeps the aggregate request rate to myf2m within the
    # configured per-minute budget regardless of worker count, so parallel
    # crawling cannot trip the provider WAF / 429s.
    provider_request_lock = threading.Lock()
    provider_min_interval = max(0.0, 60.0 / max(1, int(getattr(settings, 'MYF2M_RATE_LIMIT_PER_MINUTE', 30))))
    _provider_last_request = [0.0]

    def _provider_throttle():
        now = time.monotonic()
        with provider_request_lock:
            wait = provider_min_interval - (now - _provider_last_request[0])
            if wait > 0:
                time.sleep(wait)
            _provider_last_request[0] = time.monotonic()

    def _new_connector():
        conn = get_connector('myf2m')
        conn.authenticate()
        return conn

    def _fetch_detail(conn, path: str, *, label: str, retries: int = 5):
        """Fetch a myf2m detail page honoring the shared provider rate budget."""
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            _provider_throttle()
            try:
                response = conn._request('GET', path)
            except ProviderRateLimited as exc:
                last_exc = exc
                print(f'  -> {label} rate limited: {exc}; sleep 25s', flush=True)
                time.sleep(25)
                continue
            except Exception as exc:
                last_exc = exc
                wait = min(30.0, 2.0 * attempt)
                print(f'  -> {label} fetch error attempt={attempt}/{retries} {type(exc).__name__}: {exc}; sleep {wait:.0f}s', flush=True)
                time.sleep(wait)
                continue
            code = int(getattr(response, 'status_code', 200) or 200)
            if code in {429, 500, 502, 503, 504} or code >= 520:
                wait = min(45.0, 3.0 * attempt)
                print(f'  -> {label} http={code} attempt={attempt}/{retries}; sleep {wait:.0f}s', flush=True)
                time.sleep(wait)
                continue
            return response
        print(f'  -> {label} gave up after {retries} retries last={last_exc}', flush=True)
        return None

    stats = {
        'movies_kept': 0,
        'series_kept': 0,
        'movies_created': 0,
        'movies_activated': 0,
        'series_created': 0,
        'series_activated': 0,
        'movies_tried': 0,
        'series_tried': 0,
        'skipped_existing': 0,
        'skipped_tmdb_miss': 0,
        'skipped_no_av': 0,
        'skipped_missing_artwork': 0,
        'no_links': 0,
        'iranian': 0,
        'errors': 0,
        'softsub_queued': 0,
        'dornatv_enriched': 0,
        'with_dub': 0,
        'with_sub': 0,
        'with_both': 0,
        'last_movie_page': 1,
        'last_series_page': 1,
        'movies_submitted': 0,
        'series_submitted': 0,
        'kept_movie_ids': [],
        'kept_series_ids': [],
    }

    published_movie_tmdb = set(
        Movie.objects.filter(is_published=True).exclude(tmdb_id__isnull=True).values_list('tmdb_id', flat=True),
    )
    published_series_tmdb = set(
        Series.objects.filter(is_published=True).exclude(tmdb_id__isnull=True).values_list('tmdb_id', flat=True),
    )
    # Only skip IMDb when that title is already public with playback links.
    published_movie_imdb = {
        str(v).strip().lower()
        for v in (
            Movie.objects.filter(is_published=True)
            .exclude(imdb_id__isnull=True)
            .exclude(imdb_id='')
            .values_list('imdb_id', flat=True)
        )
    }
    published_series_imdb = {
        str(v).strip().lower()
        for v in (
            Series.objects.filter(is_published=True)
            .exclude(imdb_id__isnull=True)
            .exclude(imdb_id='')
            .values_list('imdb_id', flat=True)
        )
    }

    def _listing_get(path: str, *, label: str, page: int, retries: int = 8):
        """Fetch a listing page; retry transient gateway/rate errors instead of aborting."""
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                response = connector._request('GET', path)
            except Exception as exc:
                last_exc = exc
                wait = min(60.0, 2.0 * attempt)
                print(
                    f'{label} listing fail page={page} attempt={attempt}/{retries}: {exc}; sleep {wait:.0f}s',
                    flush=True,
                )
                time.sleep(wait)
                continue
            code = int(getattr(response, 'status_code', 0) or 0)
            if code in {429, 500, 502, 503, 504} or code >= 520:
                wait = min(90.0, 3.0 * attempt)
                print(
                    f'{label} listing http={code} page={page} attempt={attempt}/{retries}; sleep {wait:.0f}s',
                    flush=True,
                )
                time.sleep(wait)
                continue
            if code >= 400:
                print(f'{label} listing http={code} page={page} (fatal)', flush=True)
                return None
            return response
        print(f'{label} listing gave up page={page} after {retries} retries last={last_exc}', flush=True)
        return None

    def iter_movie_paths():
        seen: set[str] = set()
        empty_streak = 0
        first_page = max(1, int(check_state['movie_page']), int(args.start_movie_page))
        for page in range(first_page, max(first_page, int(args.max_movie_pages)) + 1):
            path = '/movies/' if page == 1 else f'/movies/page/{page}/'
            if listing_delay:
                time.sleep(listing_delay)
            response = _listing_get(path, label='movie', page=page)
            if response is None:
                # Soft skip this page and keep walking; Film2Media often flaps 502.
                empty_streak += 1
                stats['last_movie_page'] = page
                _save_checkpoint()
                if empty_streak >= 5:
                    print(f'movie listing abort after {empty_streak} consecutive failures', flush=True)
                    break
                continue
            html = response.text or ''
            found = 0
            for match in LISTING_MOVIE_RE.finditer(html):
                item_path = f'/{match.group("id")}/{match.group("slug")}/'
                if item_path in seen:
                    continue
                seen.add(item_path)
                found += 1
                yield item_path, match.group('slug')
            stats['last_movie_page'] = page
            print(f'movie listing page={page} items={found} unique_total={len(seen)}', flush=True)
            _save_checkpoint()
            if found == 0:
                empty_streak += 1
                if empty_streak >= 3:
                    break
            else:
                empty_streak = 0

    def iter_series_slugs():
        seen: set[str] = set()
        empty_streak = 0
        first_page = max(1, int(check_state['series_page']), int(args.start_series_page))
        for page in range(first_page, max(first_page, int(args.max_series_pages)) + 1):
            path = '/series/' if page == 1 else f'/series/page/{page}/'
            response = _listing_get(path, label='series', page=page)
            if response is None:
                empty_streak += 1
                stats['last_series_page'] = page
                _save_checkpoint()
                if empty_streak >= 5:
                    print(f'series listing abort after {empty_streak} consecutive failures', flush=True)
                    break
                continue
            html = response.text or ''
            found = 0
            for match in SERIES_SLUG_RE.finditer(html):
                slug = match.group('slug')
                if slug in {'page'} or slug.isdigit() or slug in seen:
                    continue
                seen.add(slug)
                found += 1
                yield slug
            print(f'series listing page={page} items={found} unique_total={len(seen)}', flush=True)
            stats['last_series_page'] = page
            _save_checkpoint()
            if found == 0 and page > 1:
                empty_streak += 1
                if empty_streak >= 3:
                    break
            else:
                empty_streak = 0
            if delay:
                time.sleep(delay)

    def stamp_page_path(links, page_path: str) -> list[dict]:
        stamped = []
        for item in links or []:
            if isinstance(item, dict):
                row = dict(item)
                row.setdefault('page_path', page_path)
                stamped.append(row)
        return stamped

    try:
        with _suppress_provider_publish_signals():
            # --- Movies ---
            if movies_target > 0:
                for page_path, slug in iter_movie_paths():
                    if stats['movies_kept'] >= movies_target:
                        break
                    if page_path in existing_movie_paths:
                        stats['skipped_existing'] += 1
                        continue
                    miss_key = _tmdb_miss_key('movie', page_path)
                    if cache.get(miss_key):
                        stats['skipped_tmdb_miss'] += 1
                        continue

                    stats['movies_tried'] += 1
                    print(
                        f'[movie {stats["movies_kept"]}/{movies_target}] try={stats["movies_tried"]} {page_path}',
                        flush=True,
                    )
                    detail = None
                    for attempt in range(1, 6):
                        try:
                            detail = connector._request('GET', page_path)
                        except ProviderRateLimited as exc:
                            stats['errors'] += 1
                            print(f'  -> rate limited: {exc}; sleep 25s', flush=True)
                            time.sleep(25)
                            detail = None
                            continue
                        except Exception as exc:
                            wait = min(30.0, 2.0 * attempt)
                            print(
                                f'  -> fetch error attempt={attempt}/5 {type(exc).__name__}: {exc}; sleep {wait:.0f}s',
                                flush=True,
                            )
                            time.sleep(wait)
                            detail = None
                            continue
                        code = int(getattr(detail, 'status_code', 200) or 200)
                        if code in {429, 500, 502, 503, 504} or code >= 520:
                            wait = min(45.0, 3.0 * attempt)
                            print(f'  -> detail http={code} attempt={attempt}/5; sleep {wait:.0f}s', flush=True)
                            time.sleep(wait)
                            detail = None
                            continue
                        break
                    if detail is None:
                        stats['errors'] += 1
                        print('  -> detail fetch gave up', flush=True)
                        if delay:
                            time.sleep(delay)
                        continue
                    if getattr(detail, 'status_code', 200) >= 400:
                        stats['no_links'] += 1
                        print(f'  -> bad detail status={detail.status_code}', flush=True)
                        if delay:
                            time.sleep(delay)
                        continue

                    html = detail.text or ''
                    imdb_ids = IMDB_RE.findall(html)
                    imdb_id = (imdb_ids[0] if imdb_ids else '').lower()
                    h1 = H1_RE.search(html)
                    page_title = _clean_html(h1.group('title')) if h1 else slug.replace('-', ' ')
                    year_match = re.search(r'\b((?:19|20)\d{2})\b', page_title) or re.search(
                        r'\b((?:19|20)\d{2})\b', slug,
                    )
                    year = int(year_match.group(1)) if year_match else None

                    if new_only and imdb_id and imdb_id in existing_movie_imdb:
                        stats['skipped_existing'] += 1
                        existing_movie_paths.add(page_path)
                        print(f'  -> skip existing imdb={imdb_id}', flush=True)
                        if delay:
                            time.sleep(delay)
                        continue

                    if imdb_id and imdb_id in published_movie_imdb:
                        existing_by_imdb = Movie.objects.filter(imdb_id__iexact=imdb_id).first()
                        if (
                            existing_by_imdb
                            and existing_by_imdb.is_published
                            and _has_download_links(existing_by_imdb)
                        ):
                            # Fall through to TMDB identity + merge path below using this row.
                            movie = existing_by_imdb
                            if existing_by_imdb.tmdb_id:
                                # Jump into merge via normal flow after tmdb resolve.
                                pass
                            else:
                                stats['skipped_existing'] += 1
                                existing_movie_paths.add(page_path)
                                print(f'  -> skip published imdb={imdb_id} (no tmdb)', flush=True)
                                if delay:
                                    time.sleep(delay)
                                continue

                    # Cheap provider preflight before any TMDB search/details,
                    # translation or artwork work. Dead/archive-only pages are
                    # common in old listing pages and must not consume the
                    # expensive metadata lane.
                    crawled = parse_download_links(html, page_path=page_path)
                    available = crawled.get('available_links') or []
                    if not available:
                        stats['no_links'] += 1
                        print('  -> preflight skip: no playable provider links', flush=True)
                        continue
                    if require_playback and not _prefer_streamable_download(list(available)):
                        stats['skipped_no_av'] += 1
                        print('  -> preflight skip: no direct online playback URL', flush=True)
                        continue

                    tmdb_summary = None
                    if imdb_id:
                        tmdb_summary = client.resolve_imdb_to_tmdb(imdb_id, content_type='movie')
                    if tmdb_summary is None:
                        query = re.sub(r'\b(19|20)\d{2}\b', '', page_title).strip(' -_')
                        try:
                            payload = client.search_movies(query, page=1) or {}
                        except Exception:
                            payload = {}
                        results = payload.get('results') if isinstance(payload, dict) else (payload or [])
                        results = list(results or [])
                        tmdb_summary = _select_tmdb_result(
                            results,
                            titles=[query, slug.replace('-', ' ')],
                            year=year,
                            content_type='movie',
                        )
                        if tmdb_summary is None:
                            slug_query = re.sub(r'\s+', ' ', slug.replace('-', ' ')).strip()
                            if slug_query and slug_query.lower() != query.lower():
                                try:
                                    payload = client.search_movies(slug_query, page=1) or {}
                                except Exception:
                                    payload = {}
                                slug_results = (
                                    payload.get('results') if isinstance(payload, dict) else (payload or [])
                                )
                                tmdb_summary = _select_tmdb_result(
                                    slug_results,
                                    titles=[slug_query, query],
                                    year=year,
                                    content_type='movie',
                                )

                    if not tmdb_summary or not tmdb_summary.get('id'):
                        stats['skipped_tmdb_miss'] += 1
                        cache.set(miss_key, True, timeout=tmdb_miss_ttl)
                        print(f'  -> tmdb miss title={page_title!r} imdb={imdb_id}', flush=True)
                        if delay:
                            time.sleep(delay)
                        continue

                    tmdb_id = int(tmdb_summary['id'])
                    if new_only and tmdb_id in existing_movie_tmdb:
                        stats['skipped_existing'] += 1
                        existing_movie_paths.add(page_path)
                        print(f'  -> skip existing tmdb={tmdb_id}', flush=True)
                        if delay:
                            time.sleep(delay)
                        continue
                    movie = Movie.objects.filter(tmdb_id=tmdb_id).first()
                    # Already on site: merge any Film2Media qualities we don't have yet.
                    if movie and movie.is_published and _has_download_links(movie):
                        if available:
                            normalized = normalize_download_links(available)
                            before = len(movie.download_links or [])
                            movie.download_links = stamp_page_path(
                                coalesce_download_links(
                                    movie.download_links or [], normalized, replace=False,
                                ),
                                crawled.get('page_path') or page_path,
                            )
                            preferred = _prefer_streamable_download(list(movie.download_links or []))
                            update_fields = ['download_links', 'updated_at']
                            update_fields.extend(
                                apply_availability_flags(movie, movie.download_links),
                            )
                            if preferred and preferred != (movie.video_url or ''):
                                movie.video_url = preferred
                                update_fields.append('video_url')
                            if imdb_id and not movie.imdb_id:
                                movie.imdb_id = imdb_id
                                update_fields.append('imdb_id')
                            movie.save(update_fields=list(dict.fromkeys(update_fields)))
                            after = len(movie.download_links or [])
                            if after > before:
                                stats['movies_activated'] += 1
                                stats['movies_kept'] += 1
                                stats['kept_movie_ids'].append(movie.pk)
                                cov = _version_coverage(movie)
                                if cov['has_dub']:
                                    stats['with_dub'] += 1
                                if cov['has_sub']:
                                    stats['with_sub'] += 1
                                if cov['has_both']:
                                    stats['with_both'] += 1
                                print(
                                    f'  -> MERGED movie id={movie.pk} {movie.title} '
                                    f'links {before}->{after} '
                                    f'dub={cov["has_dub"]} sub={cov["has_sub"]}',
                                    flush=True,
                                )
                                if args.queue_softsub and enqueue_movie_softsub(movie.pk):
                                    stats['softsub_queued'] += 1
                            else:
                                stats['skipped_existing'] += 1
                                print(
                                    f'  -> skip published tmdb={tmdb_id} (already complete)',
                                    flush=True,
                                )
                        else:
                            stats['skipped_existing'] += 1
                            print(f'  -> skip published tmdb={tmdb_id}', flush=True)
                        published_movie_tmdb.add(tmdb_id)
                        existing_movie_paths.add(page_path)
                        if delay:
                            time.sleep(delay)
                        continue

                    ok, cov = _coverage_ok(available, require_both=require_both)
                    if not available:
                        stats['no_links'] += 1
                        print('  -> empty links', flush=True)
                        if delay:
                            time.sleep(delay)
                        continue
                    if not ok:
                        stats['skipped_no_av'] += 1
                        print(f'  -> skip insufficient coverage {cov}', flush=True)
                        if delay:
                            time.sleep(delay)
                        continue

                    created = False
                    try:
                        details = tmdb_details_with_retry(
                            lambda: client.movie_details(tmdb_id),
                            label=f'movie/{tmdb_id}',
                        )
                        if not _has_exact_tmdb_artwork(details):
                            stats['skipped_missing_artwork'] += 1
                            print('  -> skip: matched TMDB record has no poster/backdrop', flush=True)
                            continue
                        if is_iranian_tmdb_details(details):
                            stats['iranian'] += 1
                            print('  -> skip iranian', flush=True)
                            continue
                        with transaction.atomic():
                            movie, created, _pub, _skip = upsert_tmdb_movie(details, auto_publish=False)
                    except Exception as exc:
                        stats['errors'] += 1
                        print(f'  -> import error {type(exc).__name__}: {exc}', flush=True)
                        continue

                    if movie.is_published and _has_download_links(movie) and not created:
                        normalized = normalize_download_links(available)
                        movie.download_links = stamp_page_path(
                            coalesce_download_links(
                                movie.download_links or [], normalized, replace=False,
                            ),
                            crawled.get('page_path') or page_path,
                        )
                        preferred = _prefer_streamable_download(list(movie.download_links or []))
                        update_fields = ['download_links', 'updated_at']
                        update_fields.extend(
                            apply_availability_flags(movie, movie.download_links),
                        )
                        if preferred:
                            movie.video_url = preferred
                            update_fields.append('video_url')
                        movie.save(update_fields=list(dict.fromkeys(update_fields)))
                        stats['skipped_existing'] += 1
                        published_movie_tmdb.add(tmdb_id)
                        print(f'  -> race-merged published id={movie.pk}', flush=True)
                        continue

                    normalized = normalize_download_links(available)
                    movie.download_links = stamp_page_path(
                        coalesce_download_links(movie.download_links or [], normalized, replace=True),
                        crawled.get('page_path') or page_path,
                    )
                    # Record accurate per-quality sizes before the row is saved so
                    # the download box reflects real file sizes from day one.
                    if args.probe_sizes:
                        _probe_link_sizes(movie.download_links, workers=workers)
                    if imdb_id and not movie.imdb_id:
                        movie.imdb_id = imdb_id
                    flag_fields = apply_availability_flags(movie, movie.download_links)
                    preferred = _prefer_streamable_download(list(movie.download_links or []))
                    if preferred:
                        movie.video_url = preferred
                    elif not (movie.video_url or '').strip():
                        for item in movie.download_links:
                            url = str(item.get('url') or '')
                            if url.startswith('http') and not url.lower().endswith(('.vtt', '.srt', '.ass')):
                                movie.video_url = url
                                break
                    update_fields = ['download_links', 'updated_at', *flag_fields]
                    if movie.imdb_id:
                        update_fields.append('imdb_id')
                    if movie.video_url:
                        update_fields.append('video_url')
                    movie.save(update_fields=list(dict.fromkeys(update_fields)))

                    if enrich_dornatv:
                        enriched = _merge_dornatv(movie, content_type='movie')
                        if enriched.get('code') == 'ok' or (enriched.get('providers') or {}).get('dornatv', {}).get('status') == 'ok':
                            stats['dornatv_enriched'] += 1
                        movie.refresh_from_db()
                        preferred = _prefer_streamable_download(list(movie.download_links or []))
                        if preferred and preferred != (movie.video_url or ''):
                            movie.video_url = preferred
                            movie.save(update_fields=['video_url', 'updated_at'])

                    if is_iranian_catalog_item(movie) or not _has_download_links(movie):
                        if created:
                            movie.delete()
                        stats['no_links' if not _has_download_links(movie) else 'iranian'] += 1
                        print('  -> drop (iranian/no links)', flush=True)
                        continue

                    preferred = _prefer_streamable_download(list(movie.download_links or []))
                    if require_playback and not preferred:
                        if created:
                            movie.delete()
                        stats['skipped_no_av'] += 1
                        print('  -> drop: no direct online playback URL after enrichment', flush=True)
                        continue
                    if preferred and preferred != (movie.video_url or ''):
                        movie.video_url = preferred
                        movie.save(update_fields=['video_url', 'updated_at'])

                    # Re-check that at least one real link remains after normalization.
                    ok_after, cov_after = _coverage_ok(movie.download_links or [], require_both=require_both)
                    if not ok_after:
                        if created:
                            movie.delete()
                        stats['skipped_no_av'] += 1
                        print(f'  -> drop insufficient coverage after enrich {cov_after}', flush=True)
                        continue

                    _publish_movie(movie)
                    cov = _version_coverage(movie)
                    stats['movies_kept'] += 1
                    if created:
                        stats['movies_created'] += 1
                    else:
                        stats['movies_activated'] += 1
                    stats['kept_movie_ids'].append(movie.pk)
                    published_movie_tmdb.add(tmdb_id)
                    existing_movie_tmdb.add(tmdb_id)
                    existing_movie_paths.add(page_path)
                    if imdb_id:
                        published_movie_imdb.add(imdb_id)
                        existing_movie_imdb.add(imdb_id)
                    if cov['has_dub']:
                        stats['with_dub'] += 1
                    if cov['has_sub']:
                        stats['with_sub'] += 1
                    if cov['has_both']:
                        stats['with_both'] += 1
                    print(
                        f'  -> KEPT movie id={movie.pk} {"new" if created else "activated"} {movie.title} '
                        f'tmdb={tmdb_id} links={len(movie.download_links or [])} '
                        f'dub={cov["has_dub"]} sub={cov["has_sub"]} video={bool(movie.video_url)}',
                        flush=True,
                    )
                    if args.queue_softsub and enqueue_movie_softsub(movie.pk):
                        stats['softsub_queued'] += 1
                    if delay:
                        time.sleep(delay)

            # --- Series ---
            if series_target > 0:
                for slug in iter_series_slugs():
                    if stats['series_kept'] >= series_target:
                        break
                    page_path = f'/series/{slug}/'
                    if page_path in existing_series_paths:
                        stats['skipped_existing'] += 1
                        continue
                    miss_key = _tmdb_miss_key('series', page_path)
                    if cache.get(miss_key):
                        stats['skipped_tmdb_miss'] += 1
                        continue

                    stats['series_tried'] += 1
                    print(
                        f'[series {stats["series_kept"]}/{series_target}] try={stats["series_tried"]} {page_path}',
                        flush=True,
                    )
                    detail = None
                    for attempt in range(1, 6):
                        try:
                            detail = connector._request('GET', page_path)
                        except ProviderRateLimited as exc:
                            stats['errors'] += 1
                            print(f'  -> rate limited: {exc}; sleep 25s', flush=True)
                            time.sleep(25)
                            detail = None
                            continue
                        except Exception as exc:
                            wait = min(30.0, 2.0 * attempt)
                            print(
                                f'  -> fetch error attempt={attempt}/5 {type(exc).__name__}: {exc}; sleep {wait:.0f}s',
                                flush=True,
                            )
                            time.sleep(wait)
                            detail = None
                            continue
                        code = int(getattr(detail, 'status_code', 200) or 200)
                        if code in {429, 500, 502, 503, 504} or code >= 520:
                            wait = min(45.0, 3.0 * attempt)
                            print(f'  -> detail http={code} attempt={attempt}/5; sleep {wait:.0f}s', flush=True)
                            time.sleep(wait)
                            detail = None
                            continue
                        break
                    if detail is None:
                        stats['errors'] += 1
                        print('  -> detail fetch gave up', flush=True)
                        if delay:
                            time.sleep(delay)
                        continue
                    if detail.status_code >= 400 or '/profile/' in str(getattr(detail, 'url', '') or ''):
                        stats['no_links'] += 1
                        print(f'  -> bad detail status={detail.status_code}', flush=True)
                        if delay:
                            time.sleep(delay)
                        continue

                    html = detail.text or ''
                    imdb_ids = IMDB_RE.findall(html)
                    imdb_id = (imdb_ids[0] if imdb_ids else '').lower()
                    if new_only and imdb_id and imdb_id in existing_series_imdb:
                        stats['skipped_existing'] += 1
                        existing_series_paths.add(page_path)
                        print(f'  -> skip existing imdb={imdb_id}', flush=True)
                        if delay:
                            time.sleep(delay)
                        continue
                    if imdb_id and imdb_id in published_series_imdb:
                        existing_by_imdb = Series.objects.filter(imdb_id__iexact=imdb_id).first()
                        if existing_by_imdb and existing_by_imdb.is_published and _has_download_links(existing_by_imdb):
                            stats['skipped_existing'] += 1
                            existing_series_paths.add(page_path)
                            print(f'  -> skip published imdb={imdb_id}', flush=True)
                            if delay:
                                time.sleep(delay)
                            continue

                    # Reject empty/dead series pages before TMDB resolution and
                    # Persian localization. This is the dominant cost on deep
                    # historical sweeps and has no effect on import accuracy.
                    preflight = parse_download_links(html, page_path=page_path)
                    preflight_links = preflight.get('available_links') or []
                    if not preflight_links:
                        stats['no_links'] += 1
                        print('  -> preflight skip: no provider episode links', flush=True)
                        continue
                    if require_playback and not _prefer_streamable_download(list(preflight_links)):
                        stats['skipped_no_av'] += 1
                        print('  -> preflight skip: no directly playable episodes', flush=True)
                        continue

                    title_tag = re.search(r'<title>([^<]+)</title>', html, re.I)
                    series_alias_queries: list[str] = []
                    page_title = slug.replace('-', ' ')
                    if title_tag:
                        raw = _clean_html(title_tag.group(1))
                        tm = TITLE_SERIES_RE.search(raw)
                        page_title = (tm.group(1) if tm else raw).strip(' -|')
                        page_title = re.sub(r'^دانلود\s+(?:سریال|انیمه)\s+', '', page_title, flags=re.I)
                        page_title = re.sub(r'\s+(بدون|با).*$', '', page_title).strip(' -|') or page_title
                        # Prefer Latin title when Persian + English are mixed in the <title>.
                        latin = re.findall(r'[A-Za-z][A-Za-z0-9\'’.:&\- ]{2,}', page_title)
                        if latin:
                            series_alias_queries = list(dict.fromkeys(
                                part.strip(' -|/') for part in latin if part.strip(' -|/')
                            ))
                            page_title = max(series_alias_queries, key=len)
                    years = [int(y) for y in re.findall(r'\b(19\d{2}|20\d{2})\b', html) if 1970 <= int(y) <= 2030]
                    year = years[0] if years else None

                    # WordPress titles frequently append the release year to the
                    # searchable name (for example ``Ratched 2020``). TMDB's TV
                    # search already receives the year separately, so keeping it
                    # in the query can turn an exact match into an empty result.
                    series_query = re.sub(r'\b(?:19|20)\d{2}\b', ' ', page_title)
                    series_query = re.sub(r'\s+', ' ', series_query).strip(' -_|/') or page_title

                    tmdb_summary = None
                    if imdb_id:
                        tmdb_summary = client.resolve_imdb_to_tmdb(imdb_id, content_type='series')
                    if tmdb_summary is None:
                        try:
                            payload = client._request(
                                'search/tv',
                                {
                                    'query': series_query,
                                    'include_adult': 'false',
                                    **({'first_air_date_year': int(year)} if year else {}),
                                },
                                language='en-US',
                            )
                        except Exception:
                            payload = {}
                        results = list(payload.get('results') or [])
                        identity_titles = [series_query, slug.replace('-', ' '), *series_alias_queries]
                        tmdb_summary = _select_tmdb_result(
                            results,
                            titles=identity_titles,
                            year=year,
                            content_type='series',
                        )
                        if tmdb_summary is None:
                            simple = re.sub(r'[^A-Za-z0-9 ]+', ' ', series_query)
                            simple = re.sub(r'\s+', ' ', simple).strip()
                            if simple:
                                try:
                                    payload = client._request(
                                        'search/tv',
                                        {'query': simple, 'include_adult': 'false'},
                                        language='en-US',
                                    )
                                    results = list(payload.get('results') or [])
                                    tmdb_summary = _select_tmdb_result(
                                        results,
                                        titles=[simple, *identity_titles],
                                        year=year,
                                        content_type='series',
                                    )
                                except Exception:
                                    tmdb_summary = None
                        if tmdb_summary is None:
                            # Film2Media often publishes an English alias and a
                            # transliterated original title separated by '/'.
                            # Trying both prevents exact aliases such as
                            # ``Cranberry Sorbet/Kizilcik Serbeti`` from being
                            # lost when only the latter exists in TMDB.
                            for alias in series_alias_queries:
                                alias_query = re.sub(r'\b(?:19|20)\d{2}\b', ' ', alias)
                                alias_query = re.sub(r'\s+', ' ', alias_query).strip(' -_|/')
                                if not alias_query or alias_query.lower() == series_query.lower():
                                    continue
                                try:
                                    payload = client._request(
                                        'search/tv',
                                        {'query': alias_query, 'include_adult': 'false'},
                                        language='en-US',
                                    )
                                    results = list(payload.get('results') or [])
                                    tmdb_summary = _select_tmdb_result(
                                        results,
                                        titles=[alias_query, *identity_titles],
                                        year=year,
                                        content_type='series',
                                    )
                                except Exception:
                                    tmdb_summary = None
                                if tmdb_summary is not None:
                                    break
                        if tmdb_summary is None:
                            # A few WordPress <title> values are clipped before
                            # the provider suffix. The canonical listing slug is
                            # then the most complete English search query.
                            slug_query = re.sub(r'\b(?:19|20)\d{2}\b', ' ', slug.replace('-', ' '))
                            slug_query = re.sub(r'\b(?:tv|series)\b', ' ', slug_query, flags=re.I)
                            slug_query = re.sub(r'\s+', ' ', slug_query).strip()
                            if slug_query and slug_query.lower() != series_query.lower():
                                try:
                                    payload = client._request(
                                        'search/tv',
                                        {'query': slug_query, 'include_adult': 'false'},
                                        language='en-US',
                                    )
                                    results = list(payload.get('results') or [])
                                    tmdb_summary = _select_tmdb_result(
                                        results,
                                        titles=[slug_query, *identity_titles],
                                        year=year,
                                        content_type='series',
                                    )
                                except Exception:
                                    tmdb_summary = None

                    if not tmdb_summary or not tmdb_summary.get('id'):
                        stats['skipped_tmdb_miss'] += 1
                        cache.set(miss_key, True, timeout=tmdb_miss_ttl)
                        print(f'  -> tmdb miss title={page_title!r} imdb={imdb_id}', flush=True)
                        if delay:
                            time.sleep(delay)
                        continue

                    tmdb_id = int(tmdb_summary['id'])
                    if new_only and tmdb_id in existing_series_tmdb:
                        stats['skipped_existing'] += 1
                        existing_series_paths.add(page_path)
                        print(f'  -> skip existing tmdb={tmdb_id}', flush=True)
                        if delay:
                            time.sleep(delay)
                        continue
                    series = Series.objects.filter(tmdb_id=tmdb_id).first()
                    created = False
                    if series and series.is_published and _has_download_links(series):
                        before = len(series.download_links or [])
                        try:
                            crawl_myf2m_downloads_for_series(
                                series=series,
                                provider_item_id=page_path,
                                replace=False,
                                queue_softsub_extract=False,
                            )
                            series.refresh_from_db()
                        except Exception as exc:
                            print(f'  -> merge skip {type(exc).__name__}: {exc}', flush=True)
                            stats['skipped_existing'] += 1
                            existing_series_paths.add(page_path)
                            if delay:
                                time.sleep(delay)
                            continue
                        after = len(series.download_links or [])
                        if after > before:
                            stats['series_activated'] += 1
                            stats['series_kept'] += 1
                            stats['kept_series_ids'].append(series.pk)
                            cov = _version_coverage(series)
                            if cov['has_dub']:
                                stats['with_dub'] += 1
                            if cov['has_sub']:
                                stats['with_sub'] += 1
                            if cov['has_both']:
                                stats['with_both'] += 1
                            print(
                                f'  -> MERGED series id={series.pk} {series.title} '
                                f'links {before}->{after} dub={cov["has_dub"]} sub={cov["has_sub"]}',
                                flush=True,
                            )
                            if args.queue_softsub and (
                                download_links_imply_softsub(series.download_links or []) or series.imdb_id
                            ):
                                if enqueue_series_softsub(series.pk, force=False, episode_limit=60):
                                    stats['softsub_queued'] += 1
                        else:
                            stats['skipped_existing'] += 1
                            print(f'  -> skip published tmdb={tmdb_id} (already complete)', flush=True)
                        published_series_tmdb.add(tmdb_id)
                        existing_series_paths.add(page_path)
                        if delay:
                            time.sleep(delay)
                        continue

                    try:
                        details = tmdb_details_with_retry(
                            lambda: client.tv_details(tmdb_id),
                            label=f'tv/{tmdb_id}',
                        )
                        if not _has_exact_tmdb_artwork(details):
                            stats['skipped_missing_artwork'] += 1
                            print('  -> skip: matched TMDB record has no poster/backdrop', flush=True)
                            continue
                        if is_iranian_tmdb_details(details):
                            stats['iranian'] += 1
                            print('  -> skip iranian', flush=True)
                            continue
                        with transaction.atomic():
                            series, created = upsert_tmdb_series(details)
                    except Exception as exc:
                        stats['errors'] += 1
                        print(f'  -> import error {type(exc).__name__}: {exc}', flush=True)
                        continue

                    if series.is_published and _has_download_links(series) and not created:
                        stats['skipped_existing'] += 1
                        published_series_tmdb.add(tmdb_id)
                        print(f'  -> skip raced published id={series.pk}', flush=True)
                        continue

                    if imdb_id and not series.imdb_id:
                        series.imdb_id = imdb_id
                        series.save(update_fields=['imdb_id', 'updated_at'])

                    try:
                        crawl_myf2m_downloads_for_series(
                            series=series,
                            provider_item_id=page_path,
                            replace=True,
                            queue_softsub_extract=False,
                        )
                    except ProviderImportError as exc:
                        stats['no_links'] += 1
                        print(f'  -> crawl skip {getattr(exc, "code", "")}: {exc}', flush=True)
                        if created:
                            series.delete()
                        if delay:
                            time.sleep(delay)
                        continue
                    except Exception as exc:
                        stats['errors'] += 1
                        print(f'  -> crawl error {type(exc).__name__}: {exc}', flush=True)
                        if created:
                            series.delete()
                        if delay:
                            time.sleep(delay)
                        continue

                    series.refresh_from_db()
                    if enrich_dornatv:
                        enriched = _merge_dornatv(series, content_type='series')
                        if enriched.get('code') == 'ok' or (enriched.get('providers') or {}).get('dornatv', {}).get('status') == 'ok':
                            stats['dornatv_enriched'] += 1
                        series.refresh_from_db()

                    playable_episode_count = Episode.objects.filter(
                        season__series_id=series.pk,
                        is_published=True,
                    ).exclude(video_url='').exclude(video_url__isnull=True).count()
                    if require_playback and playable_episode_count == 0:
                        if created:
                            series.delete()
                        stats['skipped_no_av'] += 1
                        print('  -> drop: no playable online episodes', flush=True)
                        if delay:
                            time.sleep(delay)
                        continue

                    ok, cov = _coverage_ok(series.download_links or [], require_both=require_both)
                    if not ok or not _has_download_links(series) or is_iranian_catalog_item(series):
                        reason = 'iranian' if is_iranian_catalog_item(series) else (
                            'no_av' if _has_download_links(series) else 'no_links'
                        )
                        if created:
                            series.delete()
                        elif not _has_download_links(series):
                            series.is_published = False
                            series.save(update_fields=['is_published', 'updated_at'])
                        if reason == 'iranian':
                            stats['iranian'] += 1
                        elif reason == 'no_av':
                            stats['skipped_no_av'] += 1
                        else:
                            stats['no_links'] += 1
                        print(f'  -> drop ({reason})', flush=True)
                        if delay:
                            time.sleep(delay)
                        continue

                    # Record accurate per-episode/per-quality sizes so the download
                    # box reflects real file sizes from the moment the series ships.
                    if probe_sizes:
                        _probe_link_sizes(series.download_links or [], workers=workers)

                    _publish_series(series)
                    cov = _version_coverage(series)
                    stats['series_kept'] += 1
                    if created:
                        stats['series_created'] += 1
                    else:
                        stats['series_activated'] += 1
                    stats['kept_series_ids'].append(series.pk)
                    published_series_tmdb.add(tmdb_id)
                    existing_series_tmdb.add(tmdb_id)
                    existing_series_paths.add(page_path)
                    if imdb_id:
                        published_series_imdb.add(imdb_id)
                        existing_series_imdb.add(imdb_id)
                    if cov['has_dub']:
                        stats['with_dub'] += 1
                    if cov['has_sub']:
                        stats['with_sub'] += 1
                    if cov['has_both']:
                        stats['with_both'] += 1
                    print(
                        f'  -> KEPT series id={series.pk} {"new" if created else "activated"} {series.title} '
                        f'tmdb={tmdb_id} links={len(series.download_links or [])} '
                        f'episodes={playable_episode_count} dub={cov["has_dub"]} sub={cov["has_sub"]}',
                        flush=True,
                    )
                    if args.queue_softsub:
                        if download_links_imply_softsub(series.download_links or []) or series.imdb_id:
                            if enqueue_series_softsub(series.pk, force=False, episode_limit=60):
                                stats['softsub_queued'] += 1
                    if delay:
                        time.sleep(delay)
    finally:
        close = getattr(connector, 'close', None)
        if callable(close):
            close()

    try:
        from apps.catalog.cache import bump_catalog_cache_version
        bump_catalog_cache_version()
    except Exception:
        pass

    summary = {k: v for k, v in stats.items() if k not in {'kept_movie_ids', 'kept_series_ids'}}
    summary['total_kept'] = stats['movies_kept'] + stats['series_kept']
    print('IMPORT_MISSING_MYF2M_BATCH_DONE', summary, flush=True)
    print('kept_movie_ids_sample', stats['kept_movie_ids'][:30], flush=True)
    print('kept_series_ids_sample', stats['kept_series_ids'][:30], flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
