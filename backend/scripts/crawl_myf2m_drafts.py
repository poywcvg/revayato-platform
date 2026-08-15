"""Crawl myf2m links for titles without links (or with suspicious mismatches), then publish drafts with links."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

if __name__ == '__main__' and 'django' not in sys.modules:
    import os
    import django

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()

from django.conf import settings

from apps.catalog.models import Movie, Series
from apps.catalog.provider_import.providers.myf2m_parser import slugify_title
from apps.catalog.provider_import.registry import get_connector
from apps.catalog.top_catalog import (
    _crawl_movie_links,
    _crawl_series_links,
    _has_download_links,
    _publish_movie,
    _publish_series,
    _suppress_provider_publish_signals,
)


def _log(msg: str):
    print(msg, flush=True)


def _page_paths(obj) -> set[str]:
    out = set()
    for item in (getattr(obj, 'download_links', None) or []):
        if not isinstance(item, dict):
            continue
        path = str(item.get('page_path') or '').strip()
        if path:
            out.add(path)
        url = str(item.get('url') or '')
        if url:
            out.add(url)
    return out


def _tokens(text: str) -> list[str]:
    slug = slugify_title(re.sub(r'\(\d{4}\)', '', text or ''))
    return [t for t in slug.split('-') if len(t) > 2 and t not in {
        'the', 'and', 'for', 'with', 'from', 'film', 'movie', 'season', 'farsi', 'dubbed', 'subbed',
    }]


def _is_myf2m_linked(obj) -> bool:
    blob = ' '.join(_page_paths(obj)).lower()
    return any(marker in blob for marker in ('abrtech.top', 'film2media', 'myf2m.info'))


def _looks_mismatched(obj) -> bool:
    """Heuristic: linked page/CDN path shares almost no tokens with title.

    Only applies to myf2m/Film2Media links so existing catalog rows stay untouched.
    """
    if not _has_download_links(obj):
        return False
    if not _is_myf2m_linked(obj):
        return False
    titles = [getattr(obj, 'original_title', '') or '', getattr(obj, 'title', '') or '']
    title_tokens = []
    for title in titles:
        title_tokens.extend(_tokens(title))
    title_tokens = list(dict.fromkeys(title_tokens))
    if len(title_tokens) < 2:
        return False
    blob = slugify_title(' '.join(_page_paths(obj)))
    if not blob:
        return False
    hits = sum(1 for tok in title_tokens if tok in blob)
    need = 2 if len(title_tokens) >= 3 else 1
    return hits < need


def _clear_links_and_unpublish_movie(movie: Movie):
    movie.download_links = []
    movie.video_url = ''
    movie.is_published = False
    movie.publication_status = Movie.PublicationStatus.DRAFT
    movie.save(update_fields=['download_links', 'video_url', 'is_published', 'publication_status', 'updated_at'])


def _clear_links_and_unpublish_series(series: Series):
    series.download_links = []
    series.is_published = False
    series.save(update_fields=['download_links', 'is_published', 'updated_at'])


def main():
    delay = float(getattr(settings, 'MYF2M_CRAWL_DELAY_SECONDS', 1.0) or 1.0)
    provider = getattr(settings, 'CATALOG_LINK_PROVIDER', 'myf2m')
    _log(f'start provider={provider} delay={delay}s')

    cleared_movies = 0
    cleared_series = 0
    for movie in Movie.objects.order_by('-id'):
        if _looks_mismatched(movie):
            _log(f'clear mismatched movie id={movie.id} {movie.original_title or movie.title}')
            _clear_links_and_unpublish_movie(movie)
            cleared_movies += 1
    for series in Series.objects.order_by('-id'):
        if _looks_mismatched(series):
            _log(f'clear mismatched series id={series.id} {series.original_title or series.title}')
            _clear_links_and_unpublish_series(series)
            cleared_series += 1
    _log(f'cleared mismatched movies={cleared_movies} series={cleared_series}')

    movies = [m for m in Movie.objects.order_by('-id') if not _has_download_links(m)]
    series_list = [s for s in Series.objects.order_by('-id') if not _has_download_links(s)]

    stats = {
        'movies_total': len(movies),
        'series_total': len(series_list),
        'cleared_mismatched_movies': cleared_movies,
        'cleared_mismatched_series': cleared_series,
        'movies_ok': 0,
        'movies_not_found': 0,
        'movies_failed': 0,
        'movies_published': 0,
        'series_ok': 0,
        'series_not_found': 0,
        'series_failed': 0,
        'series_published': 0,
        'errors': [],
    }
    _log(f'queue movies={len(movies)} series={len(series_list)}')

    connector = get_connector('myf2m')
    auth = connector.authenticate()
    _log(f'auth ok={auth.ok} msg={auth.message}')
    if not auth.ok:
        raise SystemExit(f'myf2m auth failed: {auth.message}')

    try:
        with _suppress_provider_publish_signals():
            for index, movie in enumerate(movies, start=1):
                label = movie.original_title or movie.title or str(movie.id)
                _log(f'[movie {index}/{len(movies)}] {label} id={movie.id}')
                try:
                    result = _crawl_movie_links(movie, connector, replace=True)
                except Exception as exc:
                    stats['movies_failed'] += 1
                    stats['errors'].append({'type': 'movie', 'id': movie.id, 'title': label, 'error': str(exc)[:200]})
                    _log(f'  ERROR {exc}')
                    if delay:
                        time.sleep(delay)
                    continue

                movie.refresh_from_db()
                status = result.get('status')
                if status == 'ok' and _has_download_links(movie):
                    if _looks_mismatched(movie):
                        _log(f'  reject mismatched path={result.get("page_path")}')
                        _clear_links_and_unpublish_movie(movie)
                        stats['movies_failed'] += 1
                        stats['errors'].append({
                            'type': 'movie', 'id': movie.id, 'title': label,
                            'status': 'mismatched', 'page_path': result.get('page_path'),
                        })
                    else:
                        stats['movies_ok'] += 1
                        was_draft = not (
                            movie.is_published
                            and movie.publication_status == Movie.PublicationStatus.PUBLISHED
                        )
                        if was_draft and _publish_movie(movie):
                            stats['movies_published'] += 1
                            _log(f'  OK links={result.get("imported_count")} published path={result.get("page_path")}')
                        else:
                            _log(f'  OK links={result.get("imported_count")} path={result.get("page_path")}')
                elif status == 'page_not_found':
                    stats['movies_not_found'] += 1
                    _log('  not found on myf2m')
                else:
                    stats['movies_failed'] += 1
                    stats['errors'].append({'type': 'movie', 'id': movie.id, 'title': label, **result})
                    _log(f'  fail {result}')
                if delay:
                    time.sleep(delay)

            for index, series in enumerate(series_list, start=1):
                label = series.original_title or series.title or str(series.id)
                _log(f'[series {index}/{len(series_list)}] {label} id={series.id}')
                try:
                    result = _crawl_series_links(series, connector, replace=True)
                except Exception as exc:
                    stats['series_failed'] += 1
                    stats['errors'].append({'type': 'series', 'id': series.id, 'title': label, 'error': str(exc)[:200]})
                    _log(f'  ERROR {exc}')
                    if delay:
                        time.sleep(delay)
                    continue

                series.refresh_from_db()
                status = result.get('status')
                if status == 'ok' and _has_download_links(series):
                    if _looks_mismatched(series):
                        _log(f'  reject mismatched path={result.get("page_path")}')
                        _clear_links_and_unpublish_series(series)
                        stats['series_failed'] += 1
                        stats['errors'].append({
                            'type': 'series', 'id': series.id, 'title': label,
                            'status': 'mismatched', 'page_path': result.get('page_path'),
                        })
                    else:
                        stats['series_ok'] += 1
                        was_draft = not series.is_published
                        if was_draft and _publish_series(series):
                            stats['series_published'] += 1
                            _log(f'  OK links={result.get("imported_count")} published path={result.get("page_path")}')
                        else:
                            _log(f'  OK links={result.get("imported_count")} path={result.get("page_path")}')
                elif status == 'page_not_found':
                    stats['series_not_found'] += 1
                    _log('  not found on myf2m')
                else:
                    stats['series_failed'] += 1
                    stats['errors'].append({'type': 'series', 'id': series.id, 'title': label, **result})
                    _log(f'  fail {result}')
                if delay:
                    time.sleep(delay)
    finally:
        close = getattr(connector, 'close', None)
        if callable(close):
            close()

    out = Path('/tmp/myf2m_draft_crawl_stats.json')
    out.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
    _log('DONE ' + json.dumps({k: v for k, v in stats.items() if k != 'errors'}, ensure_ascii=False))
    _log(f'errors={len(stats["errors"])} wrote {out}')
    return stats


if __name__ == '__main__':
    main()
