from django.core.management.base import BaseCommand, CommandError

from apps.catalog.myf2m_reconcile import (
    import_this_week_with_myf2m,
    purge_iranian_catalog,
    reconcile_catalog_with_myf2m,
)
from apps.catalog.provider_import.exceptions import ProviderImportError, ProviderRateLimited
from apps.catalog.tmdb import TMDBError


class Command(BaseCommand):
    help = (
        'Crawl Film2Media (https://www.myf2m.info/) for Hollywood download/stream links, '
        'sync SoftSub tracks for online playback, purge Iranian titles, delete '
        'catalog rows that myf2m does not carry, and optionally import this week\'s titles.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0, help='Max titles per type (0=all).')
        parser.add_argument('--crawl-delay', type=float, default=0.75)
        parser.add_argument('--movies-only', action='store_true')
        parser.add_argument('--series-only', action='store_true')
        parser.add_argument('--no-delete', action='store_true', help='Keep titles even when myf2m misses.')
        parser.add_argument('--keep-iranian', action='store_true', help='Do not purge Iranian titles.')
        parser.add_argument(
            '--only-missing',
            action='store_true',
            help='Only crawl titles missing links (or incomplete dub+sub).',
        )
        parser.add_argument('--purge-iranian-only', action='store_true', help='Only delete Iranian titles.')
        parser.add_argument('--skip-reconcile', action='store_true', help='Skip catalog backfill reconcile.')
        parser.add_argument('--import-week', action='store_true', help='Import this week\'s TMDB titles via myf2m.')
        parser.add_argument('--week-days', type=int, default=7)
        parser.add_argument('--week-limit', type=int, default=40)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        do_movies = not options['series_only']
        do_series = not options['movies_only']
        if not do_movies and not do_series and not options['purge_iranian_only']:
            raise CommandError('Choose at least one of movies or series.')

        if options['purge_iranian_only']:
            purged = purge_iranian_catalog(dry_run=bool(options['dry_run']))
            self.stdout.write(self.style.SUCCESS(
                f'Iranian purge: movies={purged["iranian_movies_deleted"]} '
                f'series={purged["iranian_series_deleted"]}'
            ))
            return

        limit = int(options['limit'] or 0) or None

        def on_progress(phase, label, stats):
            self.stdout.write(f'[{phase}] {label}')

        try:
            if not options['skip_reconcile']:
                stats = reconcile_catalog_with_myf2m(
                    delete_missing=not options['no_delete'],
                    purge_iranian=not options['keep_iranian'],
                    crawl_delay_seconds=max(0.0, float(options['crawl_delay'] or 0)),
                    limit=limit,
                    movies=do_movies,
                    series=do_series,
                    only_missing_links=bool(options['only_missing']),
                    refresh_incomplete=True,
                    dry_run=bool(options['dry_run']),
                    on_progress=on_progress,
                )
                self.stdout.write(self.style.SUCCESS(
                    'myf2m reconcile done: '
                    f'iranian movies deleted={stats["iranian_movies_deleted"]} '
                    f'series deleted={stats["iranian_series_deleted"]}; '
                    f'movies scanned={stats["movies_scanned"]} ok={stats["movies_crawled_ok"]} '
                    f'deleted={stats["movies_deleted"]} both={stats["movies_with_both"]}; '
                    f'series scanned={stats["series_scanned"]} ok={stats["series_crawled_ok"]} '
                    f'deleted={stats["series_deleted"]} both={stats["series_with_both"]}; '
                    f'errors={len(stats["errors"])}'
                ))
                for row in stats['errors'][:20]:
                    self.stdout.write(self.style.WARNING(str(row)))

            if options['import_week']:
                week = import_this_week_with_myf2m(
                    days=max(1, int(options['week_days'] or 7)),
                    limit=max(1, int(options['week_limit'] or 40)),
                    movies=do_movies,
                    series=do_series,
                    delete_if_missing=not options['no_delete'],
                    crawl_delay_seconds=max(0.0, float(options['crawl_delay'] or 0)),
                    dry_run=bool(options['dry_run']),
                    on_progress=on_progress,
                )
                self.stdout.write(self.style.SUCCESS(
                    'Week import done: '
                    f'movies discovered={week["week_movies_discovered"]} '
                    f'imported={week["week_movies_imported"]} kept={week["week_movies_kept"]} '
                    f'deleted={week["week_movies_deleted"]} '
                    f'skipped_iranian={week["week_movies_skipped_iranian"]}; '
                    f'series discovered={week["week_series_discovered"]} '
                    f'imported={week["week_series_imported"]} kept={week["week_series_kept"]} '
                    f'deleted={week["week_series_deleted"]} '
                    f'skipped_iranian={week["week_series_skipped_iranian"]}'
                ))
                for row in week['errors'][:20]:
                    self.stdout.write(self.style.WARNING(str(row)))
        except TMDBError as exc:
            raise CommandError(str(exc)) from exc
        except ProviderRateLimited as exc:
            raise CommandError(f'myf2m rate limited: {exc}') from exc
        except ProviderImportError as exc:
            raise CommandError(str(exc)) from exc
