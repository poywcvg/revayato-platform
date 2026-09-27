"""Detect and remediate browser-unplayable titles (MKV/AVI or HEVC/AV1 only).

Some catalog rows only carry sources a browser ``<video>`` cannot decode, so
iOS/Safari/Firefox viewers hit "پخش ویدیو ممکن نشد" while the download works.
This command scans published titles, records a ``PlaybackSourceGap`` for each one
with no browser-safe source, and (with ``--fix``) re-crawls the providers to pull
a browser-safe (HLS/MP4 + H.264) mirror.

Examples::

    # Detect only (no provider calls) — record/refresh gaps for the top titles.
    python manage.py crawl_playback_sources --scan-limit 300

    # Detect, then remediate up to 15 recorded gaps this pass.
    python manage.py crawl_playback_sources --scan-limit 300 --fix --fix-limit 15

    # Remediate recorded gaps only, no fresh scan.
    python manage.py crawl_playback_sources --no-scan --fix --fix-limit 25
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.catalog import playback_sources


class Command(BaseCommand):
    help = 'Detect and fix titles no browser can play (MKV/AVI or HEVC/AV1 only).'

    def add_arguments(self, parser):
        parser.add_argument('--order', choices=['hot', 'popularity', 'random', 'stale'], default='hot',
                            help='Scan order: hot (default: trending this week, then newest), popularity, '
                                 'random (fair rotation), stale (oldest first).')
        parser.add_argument('--scan-limit', type=int, default=0,
                            help='Max published titles to examine this pass (0 = all).')
        parser.add_argument('--no-scan', action='store_true', help='Skip detection; only remediate recorded gaps.')
        parser.add_argument('--fix', action='store_true', help='Re-crawl providers to fix recorded gaps.')
        parser.add_argument('--fix-limit', type=int, default=20, help='Max gaps to remediate this pass.')
        parser.add_argument('--retry-unavailable-hours', type=float, default=72.0,
                            help='Re-attempt "unavailable" gaps only after this many hours.')
        parser.add_argument('--delay', type=float, default=0.0, help='Seconds to sleep between provider re-crawls.')
        parser.add_argument('--movies-only', action='store_true')
        parser.add_argument('--series-only', action='store_true')
        parser.add_argument('--dry-run', action='store_true', help='Report actions without crawling providers.')

    def handle(self, *args, **options):
        movies = not options['series_only']
        series = not options['movies_only']

        if not options['no_scan']:
            scan_stats = playback_sources.scan(
                order=options['order'],
                scan_limit=max(0, int(options['scan_limit'] or 0)),
                movies=movies,
                series=series,
                record=not options['dry_run'],
            )
            self.stdout.write(
                'SCAN scanned={scanned} unplayable={unplayable} recorded={recorded} '
                'self_healed={self_healed}'.format(**scan_stats)
            )

        if options['fix'] or options['no_scan']:
            def _progress(index, total, outcome, gap):
                self.stdout.write(
                    f'  [{index}/{total}] {gap.content_type}:{gap.object_id} '
                    f'({gap.reason or "?"}) -> {outcome} · {gap.title[:60]}'
                )

            fix_stats = playback_sources.remediate_open_gaps(
                fix_limit=max(1, int(options['fix_limit'] or 1)),
                retry_unavailable_hours=max(0.0, float(options['retry_unavailable_hours'] or 0)),
                delay=max(0.0, float(options['delay'] or 0)),
                dry_run=options['dry_run'],
                on_progress=_progress,
            )
            self.stdout.write(
                'FIX candidates={candidates} refreshed={refreshed} unavailable={unavailable} '
                'provider_error={provider_error} vanished={vanished} skipped={skipped}'.format(**fix_stats)
            )
