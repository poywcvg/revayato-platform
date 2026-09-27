"""Backfill Season/Episode metadata from TMDB.

Episodes materialised from provider download links carry a stub «قسمت N» title
and nothing else. This command fills them in bulk; the recurring Celery beat
task handles the trickle afterwards.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.episode_metadata import (
    complete_missing_episode_metadata,
    complete_series_episode_metadata,
    series_needing_episode_metadata,
)
from apps.catalog.models import Series


class Command(BaseCommand):
    help = 'Complete season/episode metadata (titles, overviews, air dates, runtimes) from TMDB.'

    def add_arguments(self, parser):
        parser.add_argument('--series-id', type=int, default=0, help='Process a single series by pk.')
        parser.add_argument('--slug', type=str, default='', help='Process a single series by slug.')
        parser.add_argument(
            '--limit', type=int, default=0,
            help='Maximum number of series to process (0 = every series that needs it).',
        )
        parser.add_argument('--stills', action='store_true', help='Also download per-episode still images.')
        parser.add_argument('--delay', type=float, default=0.15, help='Seconds to sleep between TMDB calls.')
        parser.add_argument(
            '--force', action='store_true',
            help='Ignore the completion stamp and re-check recently processed series.',
        )
        parser.add_argument('--dry-run', action='store_true', help='Only report how many series need work.')

    def handle(self, *args, **options):
        series_id = int(options['series_id'] or 0)
        slug = str(options['slug'] or '').strip()

        if series_id or slug:
            lookup = {'pk': series_id} if series_id else {'slug': slug}
            series = Series.objects.filter(**lookup).first()
            if series is None:
                raise CommandError(f'Series not found: {lookup}')
            if options['dry_run']:
                self.stdout.write(f'would process {series.slug} (tmdb_id={series.tmdb_id})')
                return
            result = complete_series_episode_metadata(
                series, stills=options['stills'], delay=options['delay'],
            )
            self.stdout.write(self.style.SUCCESS(str(result)))
            return

        if options['dry_run']:
            pending = series_needing_episode_metadata(force=options['force']).count()
            self.stdout.write(f'{pending} series need episode metadata')
            return

        def on_progress(stats, series):
            self.stdout.write(
                f"[{stats['series_considered']}] {series.slug}: "
                f"seasons={stats['seasons_updated']} episodes={stats['episodes_updated']} "
                f"missing={stats['episodes_missing']} errors={stats['errors']}",
            )

        stats = complete_missing_episode_metadata(
            # 0 means "every series that needs it"; None would fall back to the
            # small per-beat-tick default, which is not what a backfill wants.
            series_limit=int(options['limit'] or 0),
            stills=options['stills'],
            delay=options['delay'],
            force=options['force'],
            on_progress=on_progress,
        )
        self.stdout.write(self.style.SUCCESS(str(stats)))
