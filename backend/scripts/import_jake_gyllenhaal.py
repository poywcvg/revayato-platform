#!/usr/bin/env python
"""Import Jake Gyllenhaal filmography (TMDB person 131) with full download boxes."""

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

    PERSON_TMDB_ID = 131
    ACTOR_PK = 1340

    # Skip talk/variety/reality and tiny cameos.
    TV_SKIP_TITLE_FRAGMENTS = (
        'tonight', 'late night', 'late show', 'daily show', 'saturday night live',
        'graham norton', 'conan', 'jimmy kimmel', 'ellen', 'oprah', 'awards',
        'academy awards', 'oscar', 'explained', 'man vs. wild', 'jimmy fallon',
    )

    client = configured_tmdb_client()
    importer = get_importer_settings()
    actor = Actor.objects.filter(pk=ACTOR_PK).first()
    if actor is None:
        actor = Actor.objects.filter(tmdb_id=PERSON_TMDB_ID).first()
    if actor is None:
        print('ERROR: Jake Gyllenhaal actor row missing', file=sys.stderr)
        return 1

    print(f'Actor: {actor.pk} {actor.name} / {actor.original_name} tmdb={actor.tmdb_id}')
    credits = client._request(f'person/{PERSON_TMDB_ID}/combined_credits', language='en-US')
    cast = credits.get('cast') or []

    def is_noise(item: dict) -> bool:
        media = item.get('media_type')
        char = str(item.get('character') or '').strip().lower()
        title = str(item.get('title') or item.get('name') or '').lower()
        votes = int(item.get('vote_count') or 0)
        if media == 'tv':
            if any(frag in title for frag in TV_SKIP_TITLE_FRAGMENTS):
                return True
            if char.startswith('self') or char in {'', 'himself', 'narrator', 'narrator (voice)'}:
                return True
            return False
        if media == 'movie':
            if char.startswith('self') and votes < 400:
                return True
            # Tiny uncredited blips / shorts without traction.
            if votes < 30 and not str(item.get('release_date') or '').startswith(('2024', '2025', '2026')):
                return True
            return False
        return True

    movies = [x for x in cast if x.get('media_type') == 'movie' and not is_noise(x)]
    series_raw = [x for x in cast if x.get('media_type') == 'tv' and not is_noise(x)]
    seen_tv: set[int] = set()
    series = []
    for item in series_raw:
        tid = int(item['id'])
        if tid in seen_tv:
            continue
        seen_tv.add(tid)
        series.append(item)

    movies.sort(key=lambda x: (-int(x.get('vote_count') or 0), str(x.get('release_date') or '')))
    series.sort(key=lambda x: (-int(x.get('vote_count') or 0), str(x.get('first_air_date') or '')))

    print(f'Filmography targets: movies={len(movies)} series={len(series)}')

    try:
        connector = get_connector('myf2m')
    except Exception as exc:
        print(f'ERROR: myf2m connector unavailable: {exc}', file=sys.stderr)
        return 1

    stats = {
        'movies_imported': 0,
        'movies_existing': 0,
        'movies_published': 0,
        'movies_linked': 0,
        'movies_crawled': 0,
        'movies_crawl_failed': 0,
        'series_imported': 0,
        'series_existing': 0,
        'series_published': 0,
        'series_linked': 0,
        'series_crawled': 0,
        'series_crawl_failed': 0,
        'softsub_queued': 0,
        'errors': [],
    }

    def ensure_movie_actor(movie: Movie, role: str = '') -> bool:
        _, created = MovieActor.objects.get_or_create(
            movie=movie,
            actor=actor,
            defaults={'role': (role or '')[:255], 'order': 0, 'is_lead': True},
        )
        return created

    def ensure_series_actor(series_obj: Series, role: str = '') -> bool:
        _, created = SeriesActor.objects.get_or_create(
            series=series_obj,
            actor=actor,
            defaults={'role': (role or '')[:255], 'order': 0, 'is_lead': True},
        )
        return created

    def crawl_movie(movie: Movie) -> dict:
        replace = not _has_download_links(movie)
        result = _crawl_movie_links(movie, connector, replace=replace or True, resolve_english=True)
        movie.refresh_from_db(fields=['download_links', 'is_dubbed', 'has_subtitle', 'updated_at'])
        result = {**result, 'version_coverage': _version_coverage(movie)}
        return result

    def crawl_series(series_obj: Series) -> dict:
        result = _crawl_series_links(series_obj, connector, replace=True, resolve_english=True)
        series_obj.refresh_from_db(fields=['download_links', 'is_dubbed', 'has_subtitle', 'updated_at'])
        result = {**result, 'version_coverage': _version_coverage(series_obj)}
        return result

    # --- Movies ---
    for idx, item in enumerate(movies, start=1):
        tmdb_id = int(item['id'])
        title = item.get('title') or item.get('original_title') or tmdb_id
        print(f'\n[{idx}/{len(movies)}] MOVIE tmdb={tmdb_id} {title}', flush=True)
        try:
            details = client.movie_details(tmdb_id)
            movie, created, _, _ = upsert_tmdb_movie(details, importer=importer)
            if created:
                stats['movies_imported'] += 1
            else:
                stats['movies_existing'] += 1
            if ensure_movie_actor(movie, str(item.get('character') or '')):
                stats['movies_linked'] += 1
            if _publish_movie(movie):
                stats['movies_published'] += 1
            crawl = crawl_movie(movie)
            cov = crawl.get('version_coverage') or _version_coverage(movie)
            nlinks = len(movie.download_links or [])
            print(
                f'  -> pk={movie.pk} created={created} links={nlinks} '
                f"dub={cov.get('has_dub')} sub={cov.get('has_sub')} crawl={crawl.get('status')}",
                flush=True,
            )
            if crawl.get('status') == 'ok' and crawl.get('imported_count', 0) > 0:
                stats['movies_crawled'] += 1
            elif nlinks == 0:
                stats['movies_crawl_failed'] += 1
                stats['errors'].append({'movie': movie.pk, 'title': str(title), **crawl})
            # SoftSub queue when subtitle encodes exist.
            try:
                from apps.catalog.tasks import enqueue_movie_softsub
                from apps.catalog.subtitle_extract import download_links_imply_softsub
                if download_links_imply_softsub(movie.download_links or []) and not movie.subtitle_tracks:
                    if enqueue_movie_softsub(movie.pk, force=False):
                        stats['softsub_queued'] += 1
            except Exception:
                pass
            time.sleep(0.35)
        except Exception as exc:  # noqa: BLE001
            print(f'  !! ERROR {exc}', flush=True)
            stats['errors'].append({'movie_tmdb': tmdb_id, 'title': str(title), 'error': str(exc)[:240]})

    # --- Series ---
    for idx, item in enumerate(series, start=1):
        tmdb_id = int(item['id'])
        title = item.get('name') or item.get('original_name') or tmdb_id
        print(f'\n[{idx}/{len(series)}] SERIES tmdb={tmdb_id} {title}', flush=True)
        try:
            details = client.tv_details(tmdb_id)
            series_obj, created = upsert_tmdb_series(details, importer=importer)
            if created:
                stats['series_imported'] += 1
            else:
                stats['series_existing'] += 1
            if ensure_series_actor(series_obj, str(item.get('character') or '')):
                stats['series_linked'] += 1
            if _publish_series(series_obj):
                stats['series_published'] += 1
            crawl = crawl_series(series_obj)
            cov = crawl.get('version_coverage') or _version_coverage(series_obj)
            nlinks = len(series_obj.download_links or [])
            print(
                f'  -> pk={series_obj.pk} created={created} links={nlinks} '
                f"dub={cov.get('has_dub')} sub={cov.get('has_sub')} crawl={crawl.get('status')}",
                flush=True,
            )
            if crawl.get('status') == 'ok' and crawl.get('imported_count', 0) > 0:
                stats['series_crawled'] += 1
            elif nlinks == 0:
                stats['series_crawl_failed'] += 1
                stats['errors'].append({'series': series_obj.pk, 'title': str(title), **crawl})
            try:
                from apps.catalog.tasks import enqueue_series_softsub
                from apps.catalog.subtitle_extract import download_links_imply_softsub
                if download_links_imply_softsub(series_obj.download_links or []):
                    if enqueue_series_softsub(series_obj.pk, force=False, episode_limit=24):
                        stats['softsub_queued'] += 1
            except Exception:
                pass
            time.sleep(0.5)
        except Exception as exc:  # noqa: BLE001
            print(f'  !! ERROR {exc}', flush=True)
            stats['errors'].append({'series_tmdb': tmdb_id, 'title': str(title), 'error': str(exc)[:240]})

    print('\n==== SUMMARY ====', flush=True)
    for key, value in stats.items():
        if key == 'errors':
            print(f'errors={len(value)}', flush=True)
            for err in value[:25]:
                print(f'  {err}', flush=True)
        else:
            print(f'{key}={value}', flush=True)

    # Final actor page coverage
    m_roles = MovieActor.objects.filter(actor=actor).select_related('movie')
    s_roles = SeriesActor.objects.filter(actor=actor).select_related('series')
    print(f'\nActor now linked to movies={m_roles.count()} series={s_roles.count()}', flush=True)
    with_links = sum(1 for ma in m_roles if _has_download_links(ma.movie))
    print(f'Movies with download box: {with_links}/{m_roles.count()}', flush=True)
    s_with = sum(1 for sa in s_roles if _has_download_links(sa.series))
    print(f'Series with download box: {s_with}/{s_roles.count()}', flush=True)
    return 0


if __name__ == '__main__':
    # Fix mistaken import at top of try block for softsub
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('FATAL', exc, file=sys.stderr)
        raise
