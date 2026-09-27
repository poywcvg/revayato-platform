"""Find download sources for catalog drafts that have none, and complete the archive.

Most unpublished titles were created by the metadata crawlers and never matched to
a provider page, so they carry an empty ``download_links`` and no pipeline ever
looks at them again — see :mod:`apps.catalog.draft_sources` for the measurement.
This command enrols them in ``PlaybackSourceGap`` with ``reason='no_source'`` and
re-crawls the providers for them, on a budget that is separate from the
viewer-facing playback repairs (``crawl_playback_sources``).

Examples::

    # Enrol only — no provider calls. Safe to run over the whole back archive.
    python manage.py hunt_draft_sources --scan-limit 0

    # Enrol the top 500 and hunt sources for 20 of the queue this pass.
    python manage.py hunt_draft_sources --scan-limit 500 --fix --fix-limit 20

    # Work the recorded queue only, 1.5s between provider crawls.
    python manage.py hunt_draft_sources --no-scan --fix --fix-limit 30 --delay 1.5
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.catalog import draft_sources


class Command(BaseCommand):
    help = 'Enrol sourceless drafts and crawl providers to give them download links.'

    def add_arguments(self, parser):
        parser.add_argument('--order', choices=['hot', 'popularity', 'random', 'stale'], default='hot',
                            help='Scan order: hot (default: trending this week, then newest), popularity, '
                                 'random (fair rotation), stale (oldest first).')
        parser.add_argument('--scan-limit', type=int, default=0,
                            help='Max drafts to enrol this pass (0 = all).')
        parser.add_argument('--no-scan', action='store_true', help='Skip enrolment; work the recorded queue only.')
        parser.add_argument('--fix', action='store_true', help='Crawl providers for recorded no-source gaps.')
        parser.add_argument('--fix-limit', type=int, default=20, help='Max drafts to hunt sources for this pass.')
        parser.add_argument('--retry-hours', type=float, default=168.0,
                            help='Re-attempt drafts no provider carried only after this many hours.')
        parser.add_argument('--delay', type=float, default=0.0, help='Seconds to sleep between provider crawls.')
        parser.add_argument('--movies-only', action='store_true')
        parser.add_argument('--series-only', action='store_true')
        parser.add_argument('--dry-run', action='store_true', help='Report without recording or crawling.')

    def handle(self, *args, **options):
        movies = not options['series_only']
        series = not options['movies_only']

        if not options['no_scan']:
            scan_stats = draft_sources.scan(
                order=options['order'],
                limit=max(0, int(options['scan_limit'] or 0)),
                movies=movies,
                series=series,
                record=not options['dry_run'],
            )
            self.stdout.write(
                'SCAN sourceless={scanned} enrolled={recorded} reopened={reopened} '
                'already_enrolled={skipped}'.format(**scan_stats)
            )

        if not options['fix']:
            return

        def _progress(index, total, outcome, gap):
            self.stdout.write(f'  [{index}/{total}] {gap.content_type}:{gap.object_id} {gap.slug} -> {outcome}')

        stats = draft_sources.hunt_open_gaps(
            limit=max(1, int(options['fix_limit'] or 1)),
            retry_hours=float(options['retry_hours']),
            delay=float(options['delay'] or 0),
            dry_run=options['dry_run'],
            on_progress=_progress,
            order=options['order'],
        )
        self.stdout.write(self.style.SUCCESS(
            'HUNT candidates={candidates} sourced={sourced} unplayable={unplayable} '
            'unavailable={unavailable} provider_error={provider_error} published={published} '
            'skipped={skipped} vanished={vanished}'.format(**stats)
        ))
