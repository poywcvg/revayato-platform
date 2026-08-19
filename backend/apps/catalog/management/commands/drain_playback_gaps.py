"""Re-enqueue stale viewer-reported playback subtitle gaps.

Safety valve for reports a dead urgent worker may have dropped: stale
OPEN/QUEUED gaps get re-queued (respecting the 2h SoftSub queue lock and the
per-gap ``meta['drain_count']`` attempt cap). Pure enqueue + track check —
never probes providers, never clears circuit/miss caches (a fresh probe is
the worker's job).

Run manually::

    python manage.py drain_playback_gaps --dry-run
    python manage.py drain_playback_gaps --batch 50 --min-age 300
    python manage.py drain_playback_gaps --reset-drain-count
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.catalog.tasks import drain_playback_subtitle_gaps


class Command(BaseCommand):
    help = 'Re-enqueue stale OPEN/QUEUED playback subtitle gaps.'

    def add_arguments(self, parser):
        parser.add_argument('--batch', type=int, default=None, help='Max rows to process (default from settings)')
        parser.add_argument('--min-age', type=int, default=None, help='Only gaps older than this many seconds')
        parser.add_argument('--dry-run', action='store_true', help='Report what would be done without enqueueing')
        parser.add_argument(
            '--reset-drain-count',
            action='store_true',
            help='Ignore and reset meta["drain_count"] so capped gaps retry',
        )

    def handle(self, *args, **options):
        from django.conf import settings as django_settings

        kwargs = {
            'max_batch': int(
                options.get('batch') or getattr(django_settings, 'PLAYBACK_GAP_DRAIN_MAX_PER_BATCH', 20)
            ),
            'min_age_seconds': int(
                options.get('min_age') or getattr(django_settings, 'PLAYBACK_GAP_DRAIN_MIN_AGE_SECONDS', 600)
            ),
            'max_attempts': int(getattr(django_settings, 'PLAYBACK_GAP_DRAIN_MAX_ATTEMPTS', 3)),
            'reset_drain_count': bool(options.get('reset_drain_count')),
        }
        if options.get('dry_run'):
            stats = drain_playback_subtitle_gaps(dry_run=True, **kwargs)
            self.stdout.write(
                'DRY RUN: {processed} stale gap(s) found, {resolved} would resolve, '
                '{re_enqueued} would re-enqueue, {skipped} would be skipped.'.format_map(stats)
            )
            return
        stats = drain_playback_subtitle_gaps(**kwargs)
        self.stdout.write(
            'drained {processed} stale gap(s): {resolved} resolved, {re_enqueued} re-enqueued, '
            '{skipped} skipped.'.format_map(stats)
        )
