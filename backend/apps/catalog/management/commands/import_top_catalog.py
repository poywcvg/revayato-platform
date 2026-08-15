from django.core.management.base import BaseCommand, CommandError

from apps.catalog.top_catalog import import_top_catalog
from apps.catalog.tmdb import TMDBError


class Command(BaseCommand):
    help = 'Import TMDB popular/top-rated movies/series, publish them, and crawl provider download links (dub + softsub when available).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100, help='How many titles per content type (default: 100).')
        parser.add_argument(
            '--source',
            choices=['popular', 'top_rated', 'imdb_top'],
            default='popular',
            help='List source: TMDB popular/top_rated or IMDb Top 250 (default: popular).',
        )
        parser.add_argument('--movies-only', action='store_true')
        parser.add_argument('--series-only', action='store_true')
        parser.add_argument('--no-publish', action='store_true')
        parser.add_argument('--no-crawl', action='store_true')
        parser.add_argument('--crawl-only', action='store_true', help='Only crawl Film2Media links for published titles.')
        parser.add_argument('--replace-links', action='store_true', help='Overwrite existing download links.')
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Do not touch titles that already exist in the catalog (by TMDB id).',
        )
        parser.add_argument(
            '--require-links',
            action='store_true',
            help='Delete newly created titles that never received Film2Media download links.',
        )
        parser.add_argument('--crawl-delay', type=float, default=0.0, help='Optional delay between provider crawls.')

    def handle(self, *args, **options):
        import_movies = not options['series_only']
        import_series = not options['movies_only']
        if not import_movies and not import_series:
            raise CommandError('Choose at least one of movies or series.')

        def on_progress(phase, label, stats):
            self.stdout.write(f'[{phase}] {label}')

        try:
            stats = import_top_catalog(
                limit=max(1, int(options['limit'])),
                import_movies=import_movies,
                import_series=import_series,
                publish=not options['no_publish'],
                crawl=not options['no_crawl'],
                crawl_only=bool(options['crawl_only']),
                replace_links=bool(options['replace_links']),
                skip_existing_links=not bool(options['replace_links']),
                skip_existing_titles=bool(options['skip_existing']),
                require_provider_links=bool(options['require_links']),
                crawl_delay_seconds=max(0.0, float(options['crawl_delay'] or 0)),
                source=str(options.get('source') or 'popular'),
                on_progress=on_progress,
            )
        except TMDBError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(
            'Top catalog import complete: '
            f'source={stats.get("source", "popular")} '
            f'movies={stats["movies_discovered"]} '
            f'(+{stats["movies_created"]}/~{stats["movies_updated"]}, '
            f'skip_existing={stats.get("movies_skipped_existing", 0)}, '
            f'published={stats["movies_published"]}, '
            f'links_ok={stats["movies_crawled_ok"]}, '
            f'links_skipped={stats["movies_crawl_skipped"]}, '
            f'links_failed={stats["movies_crawl_failed"]}, '
            f'dub={stats.get("movies_with_dub", 0)}, '
            f'sub={stats.get("movies_with_sub", 0)}, '
            f'both={stats.get("movies_with_both", 0)}, '
            f'removed_no_links={stats.get("movies_removed_no_links", 0)}); '
            f'series={stats["series_discovered"]} '
            f'(+{stats["series_created"]}/~{stats["series_updated"]}, '
            f'skip_existing={stats.get("series_skipped_existing", 0)}, '
            f'published={stats["series_published"]}, '
            f'links_ok={stats["series_crawled_ok"]}, '
            f'links_skipped={stats["series_crawl_skipped"]}, '
            f'links_failed={stats["series_crawl_failed"]}, '
            f'dub={stats.get("series_with_dub", 0)}, '
            f'sub={stats.get("series_with_sub", 0)}, '
            f'both={stats.get("series_with_both", 0)}, '
            f'removed_no_links={stats.get("series_removed_no_links", 0)}); '
            f'errors={len(stats["errors"])}'
        ))
        if stats['errors']:
            for row in stats['errors'][:20]:
                self.stdout.write(self.style.WARNING(str(row)))
            if len(stats['errors']) > 20:
                self.stdout.write(self.style.WARNING(f'... and {len(stats["errors"]) - 20} more errors'))
