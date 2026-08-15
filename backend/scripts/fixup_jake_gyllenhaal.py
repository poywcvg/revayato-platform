#!/usr/bin/env python
"""Fixup Jake Gyllenhaal import: link actor, publish, crawl missing download boxes."""

from __future__ import annotations

import os
import sys
import time


def main() -> int:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()

    from apps.catalog.ingestion import upsert_tmdb_movie, upsert_tmdb_series
    from apps.catalog.importer_config import get_importer_settings
    from apps.catalog.models import Actor, Movie, MovieActor, Series, SeriesActor
    from apps.catalog.provider_import.registry import get_connector
    from apps.catalog.tmdb import configured_tmdb_client
    from apps.catalog.top_catalog import (
        _crawl_movie_links,
        _crawl_series_links,
        _has_download_links,
        _publish_movie,
        _publish_series,
        _version_coverage,
    )
    from apps.catalog.tasks import enqueue_movie_softsub, enqueue_series_softsub
    from apps.catalog.subtitle_extract import download_links_imply_softsub

    actor = Actor.objects.get(pk=1340)
    client = configured_tmdb_client()
    importer = get_importer_settings()
    myf2m = get_connector('myf2m')

    # Ensure all Jake movie/series targets exist + linked.
    credits = client._request('person/131/combined_credits', language='en-US')
    cast = credits.get('cast') or []

    TV_SKIP = (
        'tonight', 'late night', 'late show', 'daily show', 'saturday night live',
        'graham norton', 'conan', 'jimmy kimmel', 'ellen', 'explained', 'man vs. wild',
        'jimmy fallon', 'oprah',
    )

    def noise(item):
        media = item.get('media_type')
        char = str(item.get('character') or '').strip().lower()
        title = str(item.get('title') or item.get('name') or '').lower()
        votes = int(item.get('vote_count') or 0)
        if media == 'tv':
            if any(x in title for x in TV_SKIP):
                return True
            if char.startswith('self') or char in {'', 'himself', 'narrator', 'narrator (voice)'}:
                return True
            return False
        if media == 'movie':
            if char.startswith('self') and votes < 400:
                return True
            if votes < 30 and not str(item.get('release_date') or '').startswith(('2024', '2025', '2026')):
                return True
            return False
        return True

    movies = [x for x in cast if x.get('media_type') == 'movie' and not noise(x)]
    series_items = []
    seen = set()
    for x in cast:
        if x.get('media_type') != 'tv' or noise(x):
            continue
        tid = int(x['id'])
        if tid in seen:
            continue
        seen.add(tid)
        series_items.append(x)

    def link_movie(movie, role=''):
        obj, created = MovieActor.objects.get_or_create(
            movie=movie,
            actor=actor,
            defaults={'role': (role or '')[:255], 'order': 0, 'is_lead': True},
        )
        if not created and role and not obj.role:
            obj.role = role[:255]
            obj.save(update_fields=['role'])
        return created

    def link_series(series, role=''):
        obj, created = SeriesActor.objects.get_or_create(
            series=series,
            actor=actor,
            defaults={'role': (role or '')[:255], 'order': 0, 'is_lead': True},
        )
        return created

    print(f'Fixup movies={len(movies)} series={len(series_items)}', flush=True)

    # Import / publish / link movies that failed earlier
    for item in movies:
        tmdb_id = int(item['id'])
        role = str(item.get('character') or '')
        movie = Movie.objects.filter(tmdb_id=tmdb_id).first()
        if movie is None:
            try:
                details = client.movie_details(tmdb_id)
                movie, created, _, _ = upsert_tmdb_movie(details, importer=importer)
                print(f'imported movie tmdb={tmdb_id} pk={movie.pk} created={created}', flush=True)
            except Exception as exc:
                print(f'import fail movie {tmdb_id}: {exc}', flush=True)
                continue
        link_movie(movie, role)
        _publish_movie(movie)

    for item in series_items:
        tmdb_id = int(item['id'])
        role = str(item.get('character') or '')
        series = Series.objects.filter(tmdb_id=tmdb_id).first()
        if series is None:
            try:
                details = client.tv_details(tmdb_id)
                series, created = upsert_tmdb_series(details, importer=importer)
                print(f'imported series tmdb={tmdb_id} pk={series.pk} created={created}', flush=True)
            except Exception as exc:
                print(f'import fail series {tmdb_id}: {exc}', flush=True)
                continue
        else:
            # Refresh metadata if unpublished empty shell
            try:
                details = client.tv_details(tmdb_id)
                series, _ = upsert_tmdb_series(details, importer=importer)
            except Exception as exc:
                print(f'refresh series {tmdb_id}: {exc}', flush=True)
        link_series(series, role)
        _publish_series(series)

    # Crawl missing download boxes for all Jake titles
    missing_movies = []
    for ma in MovieActor.objects.filter(actor=actor).select_related('movie'):
        movie = ma.movie
        if not movie.is_published:
            _publish_movie(movie)
        if not _has_download_links(movie):
            missing_movies.append(movie)

    print(f'\nCrawling {len(missing_movies)} movies without download box…', flush=True)
    crawled = failed = 0
    for movie in missing_movies:
        print(f'  crawl movie pk={movie.pk} {movie.original_title or movie.title}', flush=True)
        try:
            result = _crawl_movie_links(movie, myf2m, replace=True, resolve_english=True)
            movie.refresh_from_db(fields=['download_links', 'is_dubbed', 'has_subtitle'])
            n = len(movie.download_links or [])
            cov = _version_coverage(movie)
            print(f'    -> status={result.get("status")} links={n} dub={cov["has_dub"]} sub={cov["has_sub"]}', flush=True)
            if n:
                crawled += 1
                if download_links_imply_softsub(movie.download_links or []) and not movie.subtitle_tracks:
                    enqueue_movie_softsub(movie.pk, force=False)
            else:
                failed += 1
        except Exception as exc:
            print(f'    !! {exc}', flush=True)
            failed += 1
        time.sleep(0.4)

    # Also refresh boxes that have very few links (<3) — often incomplete
    thin = []
    for ma in MovieActor.objects.filter(actor=actor).select_related('movie'):
        movie = ma.movie
        n = len(movie.download_links or [])
        if 0 < n < 3:
            thin.append(movie)
    print(f'\nRefreshing {len(thin)} thin download boxes…', flush=True)
    for movie in thin:
        try:
            result = _crawl_movie_links(movie, myf2m, replace=True, resolve_english=True)
            movie.refresh_from_db(fields=['download_links'])
            print(f'  refresh m{movie.pk} -> {len(movie.download_links or [])} ({result.get("status")})', flush=True)
        except Exception as exc:
            print(f'  refresh fail m{movie.pk}: {exc}', flush=True)
        time.sleep(0.35)

    print('\nCrawling Jake series…', flush=True)
    for sa in SeriesActor.objects.filter(actor=actor).select_related('series'):
        series = sa.series
        if not series.is_published:
            _publish_series(series)
        print(f'  crawl series pk={series.pk} {series.original_title or series.title}', flush=True)
        try:
            result = _crawl_series_links(series, myf2m, replace=True, resolve_english=True)
            series.refresh_from_db(fields=['download_links', 'is_dubbed', 'has_subtitle'])
            n = len(series.download_links or [])
            cov = _version_coverage(series)
            print(f'    -> status={result.get("status")} links={n} dub={cov["has_dub"]} sub={cov["has_sub"]}', flush=True)
            if download_links_imply_softsub(series.download_links or []):
                enqueue_series_softsub(series.pk, force=False, episode_limit=24)
        except Exception as exc:
            print(f'    !! {exc}', flush=True)
        time.sleep(0.5)

    # Final report
    m_roles = list(MovieActor.objects.filter(actor=actor).select_related('movie'))
    s_roles = list(SeriesActor.objects.filter(actor=actor).select_related('series'))
    m_with = sum(1 for ma in m_roles if _has_download_links(ma.movie) and ma.movie.is_published)
    s_with = sum(1 for sa in s_roles if _has_download_links(sa.series) and sa.series.is_published)
    print('\n==== FINAL ====', flush=True)
    print(f'movies linked={len(m_roles)} published_with_box={m_with}', flush=True)
    print(f'series linked={len(s_roles)} published_with_box={s_with}', flush=True)
    print('Movies still missing box:', flush=True)
    for ma in m_roles:
        if not _has_download_links(ma.movie):
            print(f'  - m{ma.movie.pk} {ma.movie.original_title or ma.movie.title}', flush=True)
    print('Series still missing box:', flush=True)
    for sa in s_roles:
        if not _has_download_links(sa.series):
            print(f'  - s{sa.series.pk} {sa.series.original_title or sa.series.title}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
