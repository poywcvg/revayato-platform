"""Dry provider probe for playback subtitle gaps: search, never persist.

Runs the same SubtitleStar → SubDL → Subzone lookups the SoftSub worker would for a
gap's exact movie / episode and prints what each provider returned, without
storing a VTT or touching the title. Run it with ``-e CACHE_URL=`` so provider
miss/circuit keys live in process memory and never leak into production Redis.

    python manage.py subtitle_gap_probe 130 677 412
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Dry-run provider lookups for PlaybackSubtitleGap ids (no writes).'

    def add_arguments(self, parser):
        parser.add_argument('gap_ids', type=int, nargs='+')
        parser.add_argument('--timeout', type=int, default=40)

    def handle(self, *args, **options):
        from apps.catalog.models import Episode, Movie, PlaybackSubtitleGap, Series

        for gap in PlaybackSubtitleGap.objects.filter(pk__in=options['gap_ids']):
            self.stdout.write(f'\n=== gap #{gap.pk} {gap.content_type} {gap.slug}')
            if gap.content_type == 'movie':
                movie = Movie.objects.filter(pk=gap.object_id).first()
                if movie is not None:
                    self._probe_movie(movie, options['timeout'])
                continue
            series = Series.objects.filter(pk=gap.object_id).first()
            episode = Episode.objects.filter(pk=gap.episode_id).select_related('season').first()
            if series is not None and episode is not None:
                self._probe_episode(series, episode, options['timeout'])

    def _report(self, provider, started, match):
        took = time.monotonic() - started
        if match is None:
            self.stdout.write(f'  {provider:<12} miss ({took:.1f}s)')
            return
        rows = match if isinstance(match, list) else [match]
        self.stdout.write(f'  {provider:<12} {len(rows)} match(es) ({took:.1f}s)')
        for row in rows[:6]:
            se = ''
            if hasattr(row, 'season_number'):
                se = f's{row.season_number}e{row.episode_number} '
            self.stdout.write(
                f'    {se}{row.release_name[:70]} | {row.page_url[:90]} | bytes={len(row.payload)} '
                f'| bound={len(row.source_urls)}'
            )

    def _probe_movie(self, movie, timeout):
        from apps.catalog import subdl, subtitle_star, subzone
        from apps.catalog.subtitle_extract import _ranked_movie_stream_urls, _ranked_subtitlestar_stream_urls

        links = [row for row in (movie.download_links or []) if isinstance(row, dict)]
        urls = _ranked_subtitlestar_stream_urls(links) or _ranked_movie_stream_urls(links)
        self.stdout.write(
            f'  title={movie.original_title!r} y={movie.release_year} imdb={movie.imdb_id} urls={len(urls)}'
        )
        for url in urls[:3]:
            self.stdout.write(f'    url: {url.rsplit("/", 1)[-1][:110]}')
        if not urls:
            return
        started = time.monotonic()
        self._report('subtitlestar', started, subtitle_star.find_movie_subtitle(
            movie, video_urls=urls, timeout_seconds=timeout,
        ))
        started = time.monotonic()
        self._report('subdl', started, subdl.find_movie_subtitle(
            movie, video_urls=urls, timeout_seconds=timeout,
        ))
        started = time.monotonic()
        self._report('subzone', started, subzone.find_movie_subtitle(
            movie, video_urls=urls, timeout_seconds=timeout,
        ))

    def _probe_episode(self, series, episode, timeout):
        from apps.catalog import subdl, subtitle_star, subzone
        from apps.catalog.subtitle_extract import _episode_video_map, _links_for_episode

        links = [row for row in (series.download_links or []) if isinstance(row, dict)]
        season_no = int(episode.season.season_number or 1)
        ep_no = int(episode.episode_number or 0)
        key = (season_no, ep_no)
        videos = _episode_video_map(series, _links_for_episode(links, season_no, ep_no) or links)
        if key not in videos:
            videos = _episode_video_map(series, links)
        if key not in videos and episode.video_url:
            videos[key] = [episode.video_url]
        seasons = sorted({s for s, _e in _episode_video_map(series, links)})
        self.stdout.write(
            f'  title={series.original_title!r} y={series.start_year} imdb={series.imdb_id} '
            f'target=s{season_no}e{ep_no} mapped_seasons={seasons[:12]} has_target={key in videos}'
        )
        for url in videos.get(key, [])[:2]:
            self.stdout.write(f'    url: {url.rsplit("/", 1)[-1][:110]}')
        if key not in videos:
            return
        wanted = {key: videos[key]}
        started = time.monotonic()
        self._report('subtitlestar', started, subtitle_star.find_series_episode_subtitles(
            series, episode_videos=wanted, timeout_seconds=timeout,
        ) or None)
        started = time.monotonic()
        self._report('subdl', started, subdl.find_series_episode_subtitles(
            series, episode_videos=wanted, timeout_seconds=timeout,
        ) or None)
        started = time.monotonic()
        self._report('subzone', started, subzone.find_series_episode_subtitles(
            series, episode_videos=wanted, timeout_seconds=timeout,
        ) or None)
