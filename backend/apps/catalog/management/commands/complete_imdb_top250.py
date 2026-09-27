"""Keep both IMDb Top 250 shelves complete: every position imported and watchable.

Runs as a lane of the permanent crawler loop. Each pass refreshes the stored
chart when it is stale, then works through a bounded number of positions that
are not yet watchable — best rank first — and records *why* each one is still
missing, so ``coverage`` is a number anyone can check instead of a hope.
"""

from django.core.management.base import BaseCommand

from apps.catalog.top250 import complete_chart, coverage, refresh_chart


class Command(BaseCommand):
    help = 'Refresh the IMDb Top 250 chart and import/crawl/publish the positions still missing.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=20, help='Positions to work on this pass.')
        parser.add_argument('--retry-hours', type=float, default=24, help='Wait before retrying a failed position.')
        parser.add_argument('--delay', type=float, default=1.0, help='Pause between positions (provider courtesy).')
        parser.add_argument('--refresh-max-age-hours', type=float, default=20, help='Re-download the chart when older.')
        parser.add_argument('--force-refresh', action='store_true', help='Re-download the chart regardless of age.')
        parser.add_argument('--kind', choices=['movie', 'series', 'both'], default='both')
        parser.add_argument('--report', action='store_true', help='Only print coverage; change nothing.')
        parser.add_argument(
            '--detail', action='store_true',
            help='With --report: also list every position that is not watchable and why.',
        )

    def handle(self, *args, **options):
        if options['report']:
            self._print_coverage(coverage())
            if options['detail']:
                self._print_detail()
            return
        try:
            chart = refresh_chart(
                max_age_hours=options['refresh_max_age_hours'],
                force=options['force_refresh'],
            )
            self.stdout.write(f'TOP250_CHART {chart}')
        except Exception as exc:  # a failed download must not stop completion of the stored chart
            self.stderr.write(self.style.WARNING(f'TOP250_CHART_REFRESH_FAILED {exc}'))
        kinds = ('movie', 'series') if options['kind'] == 'both' else (options['kind'],)
        stats = complete_chart(
            limit=max(0, options['limit']),
            retry_hours=options['retry_hours'],
            delay=max(0.0, options['delay']),
            kinds=kinds,
        )
        self.stdout.write(
            f'TOP250_PASS attempted={stats["attempted"]} imported={stats["imported"]} '
            f'crawled={stats["crawled"]} published={stats["published"]} gaps={stats["gaps"]}'
        )
        for line in stats.get('errors', [])[:10]:
            self.stderr.write(self.style.WARNING(f'  {line}'))
        self._print_coverage(stats['coverage'])

    def _print_coverage(self, data):
        for kind, row in data.items():
            self.stdout.write(self.style.SUCCESS(
                f'TOP250_COVERAGE kind={kind} total={row["total"]} '
                f'in_catalog={row["in_catalog"]} published={row["published"]}'
            ))

    def _print_detail(self):
        """One line per unwatchable position: the row it points at and its state."""
        from apps.catalog.models import ImdbChartEntry, Movie, Series
        from apps.catalog.top_catalog import _has_download_links

        for kind, model in (('movie', Movie), ('series', Series)):
            entries = ImdbChartEntry.objects.filter(kind=kind).select_related(kind).order_by('rank')
            for entry in entries:
                obj = getattr(entry, kind)
                if obj is not None and obj.is_published:
                    continue
                twins = model.objects.filter(imdb_id__iexact=entry.imdb_id).count()
                state = 'absent'
                if obj is not None:
                    state = (
                        f'pk={obj.pk} status={getattr(obj, "publication_status", "-")} '
                        f'links={_has_download_links(obj)} updated={obj.updated_at:%m-%d %H:%M}'
                    )
                attempted = f'{entry.attempted_at:%m-%d %H:%M}' if entry.attempted_at else '-'
                self.stdout.write(
                    f'TOP250_MISSING kind={kind} rank={entry.rank} imdb={entry.imdb_id} '
                    f'{state} twins={twins} attempts={entry.attempts} attempted={attempted} '
                    f'gap={entry.gap_reason or "-"} title={entry.primary_title!r}'
                )
