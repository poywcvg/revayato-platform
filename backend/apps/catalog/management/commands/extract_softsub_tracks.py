"""Backfill SoftSub tracks into WebVTT for HTML5 playback (movies + series episodes)."""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.catalog.models import Movie, Series
from apps.catalog.subtitle_extract import (
    attach_extracted_subtitle,
    attach_series_softsub_tracks,
    _ranked_movie_stream_urls,
    download_links_imply_dub,
    download_links_imply_softsub,
    download_links_imply_subtitle,
    looks_like_hardsub_link,
    url_implies_softsub,
)


class Command(BaseCommand):
    help = 'Attach Persian WebVTT tracks from SoftSub streams or SubtitleStar fallback.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=20, help='Max movies/series to process')
        parser.add_argument('--movie-limit', type=int, default=None, help='Override movie queue limit')
        parser.add_argument('--series-limit', type=int, default=None, help='Override series queue limit')
        parser.add_argument('--force', action='store_true')
        parser.add_argument('--timeout', type=int, default=300)
        parser.add_argument('--movies-only', action='store_true')
        parser.add_argument('--series-only', action='store_true')
        parser.add_argument('--episode-limit', type=int, default=40, help='Max episodes per series')
        parser.add_argument(
            '--missing-only',
            action='store_true',
            help='Prefer titles that still lack SoftSub WebVTT tracks',
        )
        parser.add_argument(
            '--soft-only',
            action='store_true',
            help='Only Soft encodes without HardSub (embedded demux path)',
        )
        parser.add_argument(
            '--queue',
            action='store_true',
            help='Enqueue Celery extract tasks instead of running inline',
        )

    def handle(self, *args, **options):
        limit = max(1, int(options['limit'] or 20))
        movie_limit = max(0, int(options['movie_limit'])) if options['movie_limit'] is not None else limit
        series_limit = max(0, int(options['series_limit'])) if options['series_limit'] is not None else limit
        force = bool(options['force'])
        timeout = max(30, int(options['timeout'] or 120))
        episode_limit = max(1, int(options['episode_limit'] or 40))
        missing_only = bool(options['missing_only'])
        soft_only = bool(options.get('soft_only'))
        queue = bool(options['queue'])
        do_movies = not options['series_only']
        do_series = not options['movies_only']

        def _is_soft_only(links) -> bool:
            rows = [item for item in (links or []) if isinstance(item, dict)]
            has_soft = (
                any(url_implies_softsub(item) for item in rows)
                or download_links_imply_softsub(rows)
            )
            has_hard = any(looks_like_hardsub_link(item) for item in rows)
            return bool(has_soft and not has_hard)

        movie_stats = {'processed': 0, 'extracted': 0, 'marked': 0, 'queued': 0}
        series_stats = {'processed': 0, 'extracted': 0, 'queued': 0}

        if do_movies:
            qs = Movie.objects.filter(is_published=True).order_by('-popularity', '-updated_at', '-id')
            for movie in qs.iterator(chunk_size=50):
                if movie_stats['processed'] >= movie_limit:
                    break
                links = movie.download_links or []
                has_tracks = bool(movie.subtitle_tracks)
                if missing_only and has_tracks and not force:
                    continue
                if soft_only and not _is_soft_only(links):
                    continue
                subtitlestar_eligible = bool(
                    getattr(settings, 'SUBTITLESTAR_ENABLED', True)
                    and movie.imdb_id
                    and _ranked_movie_stream_urls(links)
                )
                if missing_only:
                    if not download_links_imply_softsub(links) and not subtitlestar_eligible:
                        continue
                elif (
                    not download_links_imply_subtitle(links)
                    and not download_links_imply_dub(links)
                    and not subtitlestar_eligible
                ):
                    continue
                if download_links_imply_dub(links) and not movie.is_dubbed:
                    movie.is_dubbed = True
                    movie.save(update_fields=['is_dubbed', 'updated_at'])
                if queue:
                    from apps.catalog.tasks import enqueue_movie_softsub
                    if enqueue_movie_softsub(movie.pk, force=force):
                        movie_stats['processed'] += 1
                        movie_stats['queued'] += 1
                        self.stdout.write(f'queued movie={movie.pk} {movie.title}')
                    else:
                        self.stdout.write(f'already queued movie={movie.pk} {movie.title}')
                    continue
                movie_stats['processed'] += 1
                before = bool(movie.subtitle_tracks)
                changed = attach_extracted_subtitle(
                    movie,
                    force=force,
                    timeout_seconds=timeout,
                    allow_ffmpeg=True,
                    prefer_embedded=_is_soft_only(links),
                )
                movie.refresh_from_db(fields=['subtitle_tracks', 'has_subtitle', 'is_dubbed'])
                if changed:
                    movie_stats['extracted'] += 1
                    self.stdout.write(self.style.SUCCESS(f'extracted movie={movie.pk} {movie.title}'))
                elif movie.has_subtitle and not before:
                    movie_stats['marked'] += 1
                    self.stdout.write(f'marked has_subtitle movie={movie.pk} {movie.title}')
                else:
                    self.stdout.write(f'skipped movie={movie.pk} {movie.title}')

        if do_series:
            qs = Series.objects.filter(is_published=True).order_by('-popularity', '-updated_at', '-id')
            for series in qs.iterator(chunk_size=25):
                if series_stats['processed'] >= series_limit:
                    break
                links = series.download_links or []
                if soft_only and not _is_soft_only(links):
                    continue
                subtitlestar_eligible = bool(
                    getattr(settings, 'SUBTITLESTAR_ENABLED', True)
                    and series.imdb_id
                )
                if (
                    not download_links_imply_subtitle(links)
                    and not download_links_imply_softsub(links)
                    and not subtitlestar_eligible
                ):
                    continue
                if missing_only:
                    from apps.catalog.models import Episode
                    has_any = Episode.objects.filter(
                        season__series_id=series.pk,
                        is_published=True,
                    ).exclude(subtitle_tracks=[]).exclude(subtitle_tracks__isnull=True).exists()
                    if has_any and not force:
                        # Still process series that have Soft links but many missing episode tracks,
                        # or IMDb-backed titles that can still fill gaps via SubtitleStar.
                        soft = download_links_imply_softsub(links)
                        if not soft and not subtitlestar_eligible:
                            continue
                        total = Episode.objects.filter(season__series_id=series.pk, is_published=True).count()
                        with_tracks = Episode.objects.filter(
                            season__series_id=series.pk,
                            is_published=True,
                        ).exclude(subtitle_tracks=[]).exclude(subtitle_tracks__isnull=True).count()
                        if total and with_tracks >= total:
                            continue
                if queue:
                    from apps.catalog.tasks import enqueue_series_softsub
                    if enqueue_series_softsub(series.pk, force=force, episode_limit=episode_limit):
                        series_stats['processed'] += 1
                        series_stats['queued'] += 1
                        self.stdout.write(f'queued series={series.pk} {series.title}')
                    else:
                        self.stdout.write(f'already queued series={series.pk} {series.title}')
                    continue
                series_stats['processed'] += 1
                result = attach_series_softsub_tracks(
                    series,
                    force=force,
                    timeout_seconds=timeout,
                    limit=episode_limit,
                    allow_ffmpeg=True,
                    prefer_embedded=_is_soft_only(links),
                )
                series_stats['extracted'] += int(result.get('extracted') or 0)
                self.stdout.write(
                    f"series={series.pk} {series.title} "
                    f"processed_eps={result.get('processed')} extracted={result.get('extracted')} "
                    f"subtitlestar={result.get('subtitlestar_attached')} "
                    f"refreshed={result.get('refreshed')}",
                )

        self.stdout.write(self.style.SUCCESS(
            'done '
            f"movies processed={movie_stats['processed']} extracted={movie_stats['extracted']} "
            f"marked={movie_stats['marked']} queued={movie_stats['queued']} "
            f"series processed={series_stats['processed']} extracted_eps={series_stats['extracted']} "
            f"queued={series_stats['queued']}",
        ))
