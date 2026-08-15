from django.core.management.base import BaseCommand

from apps.catalog.imdb_charts import sync_imdb_top_ranks


class Command(BaseCommand):
    help = 'Stamp IMDb Top 250 ranks (movies + TV) onto matching catalog titles.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=250, help='Chart size (default 250).')

    def handle(self, *args, **options):
        stats = sync_imdb_top_ranks(limit=int(options['limit'] or 250))
        self.stdout.write(self.style.SUCCESS(
            'IMDb Top ranks synced: '
            f'movies chart={stats["movies_chart"]} ranked={stats["movies_ranked"]} '
            f'missing={len(stats["movies_missing"])} cleared={stats["movies_cleared"]}; '
            f'series chart={stats["series_chart"]} ranked={stats["series_ranked"]} '
            f'missing={len(stats["series_missing"])} cleared={stats["series_cleared"]}'
        ))
        for row in stats['movies_missing'][:15]:
            self.stdout.write(self.style.WARNING(
                f'  movie missing #{row["rank"]} {row["imdb_id"]} {row["title"]}'
            ))
        for row in stats['series_missing'][:15]:
            self.stdout.write(self.style.WARNING(
                f'  series missing #{row["rank"]} {row["imdb_id"]} {row["title"]}'
            ))
