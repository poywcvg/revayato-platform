#!/usr/bin/env python
"""Import IMDb Top 250 movies + Top 250 TV series with provider links and SoftSub queue."""

from __future__ import annotations

import os
import sys
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from apps.catalog.models import Episode, Movie, Series
from apps.catalog.subtitle_extract import download_links_imply_softsub
from apps.catalog.tasks import enqueue_movie_softsub, enqueue_series_softsub
from apps.catalog.top_catalog import (
    _has_download_links,
    _version_coverage,
    import_top_catalog,
)


LIMIT = int(os.environ.get('IMDB_TOP_LIMIT', '250'))
CRAWL_DELAY = float(os.environ.get('IMDB_TOP_CRAWL_DELAY', '0.4'))


def _episode_track_coverage(series: Series) -> tuple[int, int]:
    eps = list(
        Episode.objects.filter(season__series=series, is_published=True).only('subtitle_tracks')
    )
    with_tracks = sum(
        1
        for ep in eps
        if any(
            isinstance(t, dict) and str(t.get('src') or t.get('key') or '').strip()
            for t in (ep.subtitle_tracks or [])
        )
    )
    return len(eps), with_tracks


def _coverage(label: str) -> None:
    movies = list(Movie.objects.filter(is_published=True))
    series_rows = list(Series.objects.filter(is_published=True))
    m_links = m_dub = m_sub = m_both = m_soft = m_tracks = 0
    for movie in movies:
        if _has_download_links(movie):
            m_links += 1
        cov = _version_coverage(movie)
        m_dub += int(cov['has_dub'])
        m_sub += int(cov['has_sub'])
        m_both += int(cov['has_both'])
        m_soft += int(download_links_imply_softsub(movie.download_links or []))
        m_tracks += int(bool(movie.subtitle_tracks))
    s_links = s_dub = s_sub = s_both = s_soft = 0
    for series in series_rows:
        if _has_download_links(series):
            s_links += 1
        cov = _version_coverage(series)
        s_dub += int(cov['has_dub'])
        s_sub += int(cov['has_sub'])
        s_both += int(cov['has_both'])
        s_soft += int(download_links_imply_softsub(series.download_links or []))
    print(
        f'[{label}] movies_pub={len(movies)} links={m_links} dub={m_dub} sub={m_sub} '
        f'both={m_both} soft={m_soft} vtt={m_tracks} | '
        f'series_pub={len(series_rows)} links={s_links} dub={s_dub} sub={s_sub} '
        f'both={s_both} soft={s_soft}',
        flush=True,
    )


def main() -> int:
    started = time.time()
    print(f'=== import IMDb Top {LIMIT} movies + series ===', flush=True)
    _coverage('before')

    def on_progress(phase, label, stats):
        print(
            f'[{phase}] {label} | m={stats.get("movies_discovered")}/'
            f'+{stats.get("movies_created")} links_ok={stats.get("movies_crawled_ok")} '
            f'both={stats.get("movies_with_both")} | '
            f's={stats.get("series_discovered")}/+{stats.get("series_created")} '
            f'links_ok={stats.get("series_crawled_ok")} both={stats.get("series_with_both")}',
            flush=True,
        )

    stats = import_top_catalog(
        limit=LIMIT,
        import_movies=True,
        import_series=True,
        publish=True,
        crawl=True,
        crawl_only=False,
        replace_links=False,
        skip_existing_links=True,
        skip_existing_titles=False,
        require_provider_links=False,
        crawl_delay_seconds=CRAWL_DELAY,
        source='imdb_top',
        on_progress=on_progress,
    )
    print('IMPORT_STATS', {k: v for k, v in stats.items() if k != 'errors'}, flush=True)
    if stats.get('errors'):
        print('ERRORS_SAMPLE', stats['errors'][:40], flush=True)

    # SoftSub queue for player-synced WebVTT.
    movie_queued = series_queued = 0
    for movie in Movie.objects.filter(is_published=True).iterator():
        if not download_links_imply_softsub(movie.download_links or []):
            continue
        if movie.subtitle_tracks:
            continue
        if enqueue_movie_softsub(movie.pk, force=False):
            movie_queued += 1
    for series in Series.objects.filter(is_published=True).iterator():
        if not download_links_imply_softsub(series.download_links or []):
            continue
        total, with_tracks = _episode_track_coverage(series)
        if total and with_tracks >= total:
            continue
        if enqueue_series_softsub(series.pk, force=False, episode_limit=60):
            series_queued += 1
    print(
        f'softsub_queued movies={movie_queued} series={series_queued} '
        f'elapsed_s={int(time.time() - started)}',
        flush=True,
    )

    from apps.catalog.imdb_charts import sync_imdb_top_ranks

    rank_stats = sync_imdb_top_ranks(limit=LIMIT)
    print(
        'IMDB_RANKS '
        f'movies={rank_stats["movies_ranked"]}/{rank_stats["movies_chart"]} '
        f'missing_m={len(rank_stats["movies_missing"])} '
        f'series={rank_stats["series_ranked"]}/{rank_stats["series_chart"]} '
        f'missing_s={len(rank_stats["series_missing"])}',
        flush=True,
    )
    _coverage('after')
    return 0


if __name__ == '__main__':
    sys.exit(main())
