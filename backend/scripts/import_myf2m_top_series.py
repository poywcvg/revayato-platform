#!/usr/bin/env python
"""Import series from myf2m /series/ listing until N published titles have download boxes."""

from __future__ import annotations

import os
import re
import sys
import time
from urllib.parse import urlparse

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

import httpx
from django.conf import settings

from apps.catalog.ingestion import upsert_tmdb_series
from apps.catalog.iranian import is_iranian_tmdb_details
from apps.catalog.models import Series
from apps.catalog.provider_import.catalog_lookup import crawl_myf2m_downloads_for_series
from apps.catalog.provider_import.exceptions import ProviderImportError
from apps.catalog.subtitle_extract import download_links_imply_softsub
from apps.catalog.tasks import enqueue_series_softsub
from apps.catalog.top_catalog import _has_download_links, _version_coverage, _publish_series
from apps.catalog.tmdb import configured_tmdb_client

TARGET = int(os.environ.get('SERIES_WITH_LINKS_TARGET', '250'))
MAX_PAGES = int(os.environ.get('MYF2M_SERIES_MAX_PAGES', '40'))  # ~960 candidates
TITLE_RE = re.compile(
    r'دانلود\s+سریال\s+(.+?)(?:\s+بدون|\s+با\s+زیرنویس|\s+با\s+دوبله|\s*\||$)',
    re.I,
)
SLUG_RE = re.compile(r'https://www\.myf2m\.info/series/([a-z0-9\-]+)/', re.I)


def _published_with_links() -> int:
    return sum(1 for s in Series.objects.filter(is_published=True).iterator() if _has_download_links(s))


def _existing_paths() -> set[str]:
    paths: set[str] = set()
    for s in Series.objects.exclude(download_links=[]).iterator():
        for item in s.download_links or []:
            if not isinstance(item, dict):
                continue
            path = str(item.get('page_path') or '').strip()
            if path:
                paths.add(path.rstrip('/') + '/')
                continue
            url = str(item.get('page_url') or item.get('url') or '')
            if '/series/' in url:
                try:
                    p = urlparse(url).path
                except Exception:
                    p = ''
                if p.startswith('/series/'):
                    paths.add(p.rstrip('/') + '/')
    return paths


def _list_myf2m_slugs(client: httpx.Client, *, max_pages: int) -> list[str]:
    seen: list[str] = []
    known: set[str] = set()
    base = getattr(settings, 'MYF2M_BASE_URL', 'https://www.myf2m.info').rstrip('/')
    for page in range(1, max_pages + 1):
        path = '/series/' if page == 1 else f'/series/page/{page}/'
        r = client.get(base + path)
        if r.status_code != 200:
            break
        gained = 0
        for slug in SLUG_RE.findall(r.text):
            if slug in {'page'} or slug.isdigit():
                continue
            if slug in known:
                continue
            known.add(slug)
            seen.append(slug)
            gained += 1
        print(f'[list] page={page} gained={gained} total={len(seen)}', flush=True)
        if gained == 0 and page > 1:
            break
        time.sleep(0.2)
    return seen


def _title_from_detail(html: str, slug: str) -> str:
    m = re.search(r'<title>([^<]+)</title>', html or '', re.I)
    if m:
        raw = re.sub(r'\s+', ' ', m.group(1)).strip()
        tm = TITLE_RE.search(raw)
        if tm:
            return tm.group(1).strip(' -|')
        # Fallback: strip common Persian prefixes/suffixes.
        cleaned = re.sub(r'^دانلود\s+سریال\s+', '', raw, flags=re.I)
        cleaned = re.sub(r'\s+(بدون|با).*$', '', cleaned)
        cleaned = cleaned.strip(' -|')
        if cleaned and len(cleaned) > 1:
            return cleaned
    return slug.replace('-', ' ').strip()


def _search_tmdb_tv(client, title: str, year: int | None = None) -> dict | None:
    title = (title or '').strip()
    if not title:
        return None
    payload = client._request(
        'search/tv',
        {
            'query': title,
            'include_adult': 'false',
            **({'first_air_date_year': int(year)} if year else {}),
        },
        language='en-US',
    )
    results = payload.get('results') or []
    if not results:
        # Retry without year / with slug-ish simplification.
        simple = re.sub(r'[^A-Za-z0-9 ]+', ' ', title)
        simple = re.sub(r'\s+', ' ', simple).strip()
        if simple and simple.lower() != title.lower():
            payload = client._request(
                'search/tv',
                {'query': simple, 'include_adult': 'false'},
                language='en-US',
            )
            results = payload.get('results') or []
    if not results:
        return None
    return results[0]


def _guess_year(html: str) -> int | None:
    years = [int(y) for y in re.findall(r'\b(19\d{2}|20\d{2})\b', html or '')]
    years = [y for y in years if 1970 <= y <= 2027]
    return years[0] if years else None


def main() -> int:
    started = time.time()
    current = _published_with_links()
    print(f'target={TARGET} current_with_links={current}', flush=True)
    if current >= TARGET:
        print('already at target', flush=True)
        return 0

    tmdb = configured_tmdb_client()
    exclude_iranian = bool(getattr(settings, 'CATALOG_EXCLUDE_IRANIAN', True))
    base = getattr(settings, 'MYF2M_BASE_URL', 'https://www.myf2m.info').rstrip('/')
    headers = {
        'User-Agent': getattr(settings, 'MYF2M_USER_AGENT', 'RevayatoCatalogCrawler/1.0'),
        'Accept-Language': 'fa-IR,fa;q=0.9,en;q=0.8',
    }
    http = httpx.Client(timeout=30, follow_redirects=True, headers=headers, verify=True)
    existing_paths = _existing_paths()
    print(f'existing_provider_paths={len(existing_paths)}', flush=True)

    slugs = _list_myf2m_slugs(http, max_pages=MAX_PAGES)
    created = updated = crawled = skipped = failed = 0
    with_links = current

    for idx, slug in enumerate(slugs, start=1):
        if with_links >= TARGET:
            print(f'reached target at idx={idx}', flush=True)
            break
        path = f'/series/{slug}/'
        if path in existing_paths:
            skipped += 1
            continue

        print(f'[{idx}/{len(slugs)}] fetch {path}', flush=True)
        try:
            detail = http.get(base + path)
        except Exception as exc:
            failed += 1
            print(f'  fetch_error {exc}', flush=True)
            continue
        if detail.status_code != 200 or '/profile/' in str(detail.url):
            failed += 1
            print(f'  bad_detail status={detail.status_code} url={detail.url}', flush=True)
            continue

        title = _title_from_detail(detail.text, slug)
        year = _guess_year(detail.text)
        hit = _search_tmdb_tv(tmdb, title, year)
        if not hit:
            # Try slug words.
            hit = _search_tmdb_tv(tmdb, slug.replace('-', ' '))
        if not hit or not hit.get('id'):
            failed += 1
            print(f'  tmdb_miss title={title!r}', flush=True)
            time.sleep(0.25)
            continue

        tmdb_id = int(hit['id'])
        try:
            details = tmdb.tv_details(tmdb_id)
            if exclude_iranian and is_iranian_tmdb_details(details):
                skipped += 1
                print(f'  skip_iranian tmdb={tmdb_id}', flush=True)
                continue
            series, was_created = upsert_tmdb_series(details)
            created += int(was_created)
            updated += int(not was_created)
            _publish_series(series)
            result = crawl_myf2m_downloads_for_series(
                series=series,
                provider_item_id=path,
                replace=True,
                queue_softsub_extract=False,
            )
            series.refresh_from_db()
            if _has_download_links(series):
                crawled += 1
                if path not in existing_paths:
                    existing_paths.add(path)
                    # Only bump when this path was newly linked into the published set.
                    if series.is_published:
                        with_links += 1
                cov = _version_coverage(series)
                print(
                    f'  ok {series.original_title or series.title} links={result.get("imported_count")} '
                    f'dub={cov["has_dub"]} soft={download_links_imply_softsub(series.download_links or [])} '
                    f'with_links_total~={with_links}',
                    flush=True,
                )
                if download_links_imply_softsub(series.download_links or []):
                    enqueue_series_softsub(series.pk, force=False, episode_limit=60)
            else:
                failed += 1
                series.is_published = False
                series.save(update_fields=['is_published', 'updated_at'])
                print(f'  no_links_after_crawl tmdb={tmdb_id}', flush=True)
        except ProviderImportError as exc:
            failed += 1
            print(f'  crawl_error {exc}', flush=True)
        except Exception as exc:
            failed += 1
            print(f'  error {exc}', flush=True)
        time.sleep(0.3)

    http.close()
    final = _published_with_links()
    # Coverage snapshot
    pub = list(Series.objects.filter(is_published=True))
    dub = sub = both = soft = 0
    for s in pub:
        cov = _version_coverage(s)
        dub += int(cov['has_dub'])
        sub += int(cov['has_sub'])
        both += int(cov['has_both'])
        soft += int(download_links_imply_softsub(s.download_links or []))
    print(
        f'DONE created={created} updated={updated} crawled={crawled} skipped={skipped} failed={failed} '
        f'published={len(pub)} with_links={final} dub={dub} sub={sub} both={both} soft={soft} '
        f'elapsed_s={int(time.time()-started)}',
        flush=True,
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
