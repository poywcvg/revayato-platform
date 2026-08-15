#!/usr/bin/env python3
"""Safely complete IMDb Top 250 movies/series with playback and AV coverage.

Existing catalog rows are matched by stable IMDb/TMDB ids and never deleted.
Missing chart titles are created only when a provider crawl yields playable
links; retries are idempotent.  Existing chart rows missing either Persian dub
or subtitle encodes are re-crawled additively.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

for _candidate in (Path('/app'), Path(__file__).resolve().parents[1]):
    if (_candidate / 'config' / 'settings.py').exists():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        break

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from apps.catalog.imdb_charts import imdb_top_movies, imdb_top_series, sync_imdb_top_ranks
from apps.catalog.models import Episode, Movie, Series
from apps.catalog.subtitle_extract import download_links_imply_softsub
from apps.catalog.tasks import enqueue_movie_softsub, enqueue_series_softsub
from apps.catalog.top_catalog import (
    _crawl_movie_links,
    _crawl_series_links,
    _has_download_links,
    _publish_movie,
    _publish_series,
    _suppress_provider_publish_signals,
    _version_coverage,
    import_top_catalog,
)

LIMIT = max(1, min(250, int(os.environ.get('IMDB_TOP_LIMIT', '250'))))
DELAY = max(0.0, float(os.environ.get('IMDB_TOP_CRAWL_DELAY', '0.35')))


def _episode_track_coverage(series: Series) -> tuple[int, int]:
    episodes = Episode.objects.filter(season__series=series, is_published=True)
    return (
        episodes.count(),
        episodes.exclude(subtitle_tracks=[]).exclude(subtitle_tracks__isnull=True).count(),
    )


def main() -> int:
    started = time.time()
    print(
        f'=== safely complete IMDb Top {LIMIT}: metadata + playback + dub/sub ===',
        flush=True,
    )

    def on_progress(phase, label, stats):
        print(
            f'[{phase}] {label} | '
            f'm={stats.get("movies_discovered")}/+{stats.get("movies_created")} '
            f's={stats.get("series_discovered")}/+{stats.get("series_created")}',
            flush=True,
        )

    # This stage only touches missing TMDB ids.  With provider links required,
    # a brand-new title that cannot play is removed again; existing rows are
    # skipped and therefore can never be removed by this stage.
    imported = import_top_catalog(
        limit=LIMIT,
        import_movies=True,
        import_series=True,
        publish=True,
        crawl=True,
        crawl_only=False,
        replace_links=False,
        skip_existing_links=True,
        skip_existing_titles=True,
        require_provider_links=True,
        crawl_delay_seconds=DELAY,
        source='imdb_top',
        on_progress=on_progress,
    )
    print(
        'MISSING_IMPORT',
        {key: value for key, value in imported.items() if key != 'errors'},
        flush=True,
    )
    if imported.get('errors'):
        print('MISSING_IMPORT_ERRORS', imported['errors'][:40], flush=True)

    movies_chart = imdb_top_movies(limit=LIMIT)
    series_chart = imdb_top_series(limit=LIMIT)
    stats = {
        'movie_chart': len(movies_chart),
        'series_chart': len(series_chart),
        'movie_missing_db': 0,
        'series_missing_db': 0,
        'movie_recrawled': 0,
        'series_recrawled': 0,
        'movie_crawl_ok': 0,
        'series_crawl_ok': 0,
        'movie_published': 0,
        'series_published': 0,
        'movie_softsub_queued': 0,
        'series_softsub_queued': 0,
        'errors': [],
    }

    with _suppress_provider_publish_signals():
        for index, chart in enumerate(movies_chart, start=1):
            movie = Movie.objects.filter(imdb_id__iexact=chart.imdb_id).first()
            if movie is None:
                stats['movie_missing_db'] += 1
                continue
            coverage = _version_coverage(movie)
            if not coverage['has_both']:
                print(
                    f'[movie recrawl {index}/{len(movies_chart)}] '
                    f'#{chart.rank} {chart.primary_title}',
                    flush=True,
                )
                result = _crawl_movie_links(movie, replace=True, resolve_english=True)
                stats['movie_recrawled'] += 1
                movie.refresh_from_db()
                if result.get('status') == 'ok' and _has_download_links(movie):
                    stats['movie_crawl_ok'] += 1
                else:
                    stats['errors'].append({
                        'type': 'movie',
                        'imdb_id': chart.imdb_id,
                        'title': chart.primary_title,
                        'result': result,
                    })
                if DELAY:
                    time.sleep(DELAY)
            if _has_download_links(movie) and _publish_movie(movie):
                stats['movie_published'] += 1
            movie.refresh_from_db(fields=['download_links', 'subtitle_tracks'])
            if (
                download_links_imply_softsub(movie.download_links or [])
                and not movie.subtitle_tracks
                and enqueue_movie_softsub(movie.pk, force=False)
            ):
                stats['movie_softsub_queued'] += 1

        for index, chart in enumerate(series_chart, start=1):
            series = Series.objects.filter(imdb_id__iexact=chart.imdb_id).first()
            if series is None:
                stats['series_missing_db'] += 1
                continue
            coverage = _version_coverage(series)
            if not coverage['has_both']:
                print(
                    f'[series recrawl {index}/{len(series_chart)}] '
                    f'#{chart.rank} {chart.primary_title}',
                    flush=True,
                )
                result = _crawl_series_links(series, replace=True, resolve_english=True)
                stats['series_recrawled'] += 1
                series.refresh_from_db()
                if result.get('status') == 'ok' and _has_download_links(series):
                    stats['series_crawl_ok'] += 1
                else:
                    stats['errors'].append({
                        'type': 'series',
                        'imdb_id': chart.imdb_id,
                        'title': chart.primary_title,
                        'result': result,
                    })
                if DELAY:
                    time.sleep(DELAY)
            if _has_download_links(series) and _publish_series(series):
                stats['series_published'] += 1
            series.refresh_from_db(fields=['download_links'])
            total, with_tracks = _episode_track_coverage(series)
            if (
                download_links_imply_softsub(series.download_links or [])
                and total > with_tracks
                and enqueue_series_softsub(series.pk, force=False, episode_limit=60)
            ):
                stats['series_softsub_queued'] += 1

    ranks = sync_imdb_top_ranks(limit=LIMIT)
    print('RECRAWL', {key: value for key, value in stats.items() if key != 'errors'}, flush=True)
    if stats['errors']:
        print('RECRAWL_ERRORS', stats['errors'][:60], flush=True)
    print(
        'RANKS',
        {
            'movies': f'{ranks["movies_ranked"]}/{ranks["movies_chart"]}',
            'series': f'{ranks["series_ranked"]}/{ranks["series_chart"]}',
            'movies_missing': len(ranks['movies_missing']),
            'series_missing': len(ranks['series_missing']),
        },
        flush=True,
    )
    print(f'DONE elapsed_s={int(time.time() - started)}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
