"""Audit all movies and series for download/playback link health.

Reports:
  - Total published content with/without download links
  - Content with expired/dead CDN signatures
  - Content missing video_url for online playback
  - Series episodes without video_url or download links

Options:
  --fix          Re-crawl broken titles and delete unrecoverable ones
  --dry-run      Show what --fix would do without modifying anything
  --movies-only  Only audit movies
  --series-only  Only audit series
  --verbose      Show individual title details
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.catalog.models import Episode, Movie, Season, Series


class Command(BaseCommand):
    help = 'Audit catalog playback links and optionally fix broken content.'

    def add_arguments(self, parser):
        parser.add_argument('--fix', action='store_true', help='Re-crawl broken titles and delete unrecoverable ones')
        parser.add_argument('--dry-run', action='store_true', help='Show what --fix would do without modifying')
        parser.add_argument('--movies-only', action='store_true', help='Only audit movies')
        parser.add_argument('--series-only', action='store_true', help='Only audit series')
        parser.add_argument('--verbose', action='store_true', help='Show individual title details')
        parser.add_argument('--limit', type=int, default=0, help='Max titles to fix (0 = all)')

    def handle(self, *args, **options):
        verbose = options['verbose']
        movies_only = options['movies_only']
        series_only = options['series_only']

        self.stdout.write(self.style.WARNING('=' * 60))
        self.stdout.write(self.style.WARNING('CATALOG PLAYBACK AUDIT'))
        self.stdout.write(self.style.WARNING('=' * 60))

        # --- Movies ---
        if not series_only:
            self._audit_movies(verbose)

        # --- Series ---
        if not movies_only:
            self._audit_series(verbose)

        # --- Fix mode ---
        if options['fix'] or options['dry_run']:
            self._fix_broken(
                dry_run=options['dry_run'],
                movies_only=movies_only,
                series_only=series_only,
                limit=options['limit'],
            )

    def _audit_movies(self, verbose: bool):
        self.stdout.write('\n' + self.style.WARNING('--- MOVIES ---'))
        qs = Movie.objects.filter(is_published=True)
        total = qs.count()
        with_downloads = qs.exclude(download_links=[]).exclude(download_links__isnull=True).count()
        with_video_url = qs.exclude(video_url='').exclude(video_url__isnull=True).count()
        with_any = qs.filter(
            models_q_download_links | models_q_video_url
        ).count()
        missing_all = total - with_any

        self.stdout.write(f'  Total published: {total}')
        self.stdout.write(f'  With download_links: {with_downloads}')
        self.stdout.write(f'  With video_url (HLS): {with_video_url}')
        self.stdout.write(f'  With any playback: {with_any}')
        self.stdout.write(f'  MISSING ALL links: {self.style.ERROR(str(missing_all))}')

        if missing_all > 0 and verbose:
            self.stdout.write('\n  Titles missing ALL links:')
            missing_qs = qs.exclude(
                models_q_download_links | models_q_video_url
            ).order_by('-created_at')[:50]
            for m in missing_qs:
                self.stdout.write(f'    [{m.id}] {m.title} ({m.original_title}) - {m.release_year}')

        # Check for expired links
        from apps.catalog.playback_refresh import is_broken, has_playable
        broken_count = 0
        broken_ids = []
        for m in qs.only('id', 'title', 'original_title', 'download_links').iterator(chunk_size=200):
            if is_broken(m):
                broken_count += 1
                broken_ids.append(m.id)
                if verbose and len(broken_ids) <= 30:
                    self.stdout.write(f'    EXPIRED [{m.id}] {m.title} ({m.original_title})')

        self.stdout.write(f'  Expired/dead links: {self.style.ERROR(str(broken_count))}')

    def _audit_series(self, verbose: bool):
        self.stdout.write('\n' + self.style.WARNING('--- SERIES ---'))
        qs = Series.objects.filter(is_published=True)
        total = qs.count()
        with_downloads = qs.exclude(download_links=[]).exclude(download_links__isnull=True).count()
        missing_all = total - with_downloads

        self.stdout.write(f'  Total published: {total}')
        self.stdout.write(f'  With download_links: {with_downloads}')
        self.stdout.write(f'  MISSING download_links: {self.style.ERROR(str(missing_all))}')

        if missing_all > 0 and verbose:
            self.stdout.write('\n  Series missing download_links:')
            missing_qs = qs.filter(download_links=[]).order_by('-created_at')[:30]
            for s in missing_qs:
                episode_count = Episode.objects.filter(
                    season__series=s, is_published=True
                ).count()
                ep_with_hls = Episode.objects.filter(
                    season__series=s, is_published=True
                ).exclude(video_url='').exclude(video_url__isnull=True).count()
                self.stdout.write(
                    f'    [{s.id}] {s.title} ({s.original_title}) - '
                    f'{episode_count} episodes, {ep_with_hls} with HLS'
                )

        # Check series expired links
        from apps.catalog.playback_refresh import is_broken
        broken_count = 0
        for s in qs.only('id', 'title', 'original_title', 'download_links').iterator(chunk_size=200):
            if is_broken(s):
                broken_count += 1
                if verbose and broken_count <= 20:
                    self.stdout.write(f'    EXPIRED [{s.id}] {s.title} ({s.original_title})')

        self.stdout.write(f'  Expired/dead links: {self.style.ERROR(str(broken_count))}')

        # Episode audit
        self.stdout.write('\n' + self.style.WARNING('--- EPISODES ---'))
        ep_qs = Episode.objects.filter(is_published=True, season__series__is_published=True)
        ep_total = ep_qs.count()
        ep_with_video = ep_qs.exclude(video_url='').exclude(video_url__isnull=True).count()
        ep_missing = ep_total - ep_with_video

        self.stdout.write(f'  Total published episodes: {ep_total}')
        self.stdout.write(f'  With video_url (HLS): {ep_with_video}')
        self.stdout.write(f'  MISSING video_url: {self.style.ERROR(str(ep_missing))}')

    def _fix_broken(self, *, dry_run: bool, movies_only: bool, series_only: bool, limit: int):
        from apps.catalog.playback_refresh import refresh_broken_playback

        self.stdout.write('\n' + self.style.WARNING('=' * 60))
        mode = 'DRY RUN' if dry_run else 'FIX MODE'
        self.stdout.write(self.style.WARNING(f'PLAYBACK REFRESH ({mode})'))
        self.stdout.write(self.style.WARNING('=' * 60))

        def report(index, total, outcome, content_type, pk, label, before, after, codes):
            icon = {
                'refreshed': self.style.SUCCESS('✓'),
                'deleted': self.style.ERROR('✗'),
                'keep_no_playable': self.style.WARNING('?'),
                'keep_transient': self.style.WARNING('⏳'),
                'skipped': '-',
                'dry_run': self.style.WARNING('DRY'),
            }.get(outcome, '?')
            self.stdout.write(
                f'  [{index}/{total}] {icon} {content_type} {pk} {label} '
                f'links={before}->{after} -> {outcome}'
            )

        stats = refresh_broken_playback(
            max_batch=limit,
            delete=not dry_run,
            delay=0.3,
            movies_only=movies_only,
            series_only=series_only,
            dry_run=dry_run,
            on_progress=report,
        )

        self.stdout.write('\n' + self.style.WARNING('SUMMARY:'))
        self.stdout.write(f'  Total processed: {stats["total"]}')
        self.stdout.write(f'  Refreshed: {self.style.SUCCESS(str(stats["refreshed"]))}')
        self.stdout.write(f'  Deleted: {self.style.ERROR(str(stats["deleted"]))}')
        self.stdout.write(f'  Kept (still broken): {stats["kept_still_broken"]}')
        self.stdout.write(f'  Failed (transient): {stats["failed"]}')


# Pre-built Q objects for common queries
from django.db.models import Q  # noqa: E402

models_q_download_links = Q(download_links__isnull=False) & ~Q(download_links=[])
models_q_video_url = Q(video_url__isnull=False) & ~Q(video_url='')
