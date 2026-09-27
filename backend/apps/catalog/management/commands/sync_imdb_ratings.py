"""Replace approximated IMDb scores with IMDb's own published numbers.

Run it with no arguments to bring the whole catalog onto the real ratings:

    python manage.py sync_imdb_ratings

``--dry-run`` reports exactly what would change without writing, which is the
honest way to see how far the current numbers have drifted.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.catalog import imdb_dataset


class Command(BaseCommand):
    help = "Sync imdb_rating/imdb_votes from IMDb's official daily dataset."

    def add_arguments(self, parser):
        parser.add_argument('--movies-only', action='store_true')
        parser.add_argument('--series-only', action='store_true')
        parser.add_argument(
            '--limit', type=int, default=0,
            help='Cap the number of titles inspected per model (newest first). 0 = all.',
        )
        parser.add_argument(
            '--only-missing', action='store_true',
            help='Touch only titles with no usable rating, leaving existing ones alone.',
        )
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--force-download', action='store_true',
            help='Re-fetch the dataset even when the cached copy is still fresh.',
        )
        parser.add_argument('--batch-size', type=int, default=500)

    def handle(self, *args, **options):
        if options['force_download']:
            self.stdout.write('Downloading IMDb ratings dataset…')
            imdb_dataset.ensure_dataset(force=True)

        movies = not options['series_only']
        series = not options['movies_only']
        result = imdb_dataset.sync_catalog_ratings(
            movies=movies,
            series=series,
            limit=options['limit'],
            only_missing=options['only_missing'],
            dry_run=options['dry_run'],
            batch_size=options['batch_size'],
        )

        prefix = 'WOULD UPDATE' if result['dry_run'] else 'UPDATED'
        self.stdout.write(
            f"checked={result['checked']} {prefix}={result['updated']} "
            f"(movies={result['movies']} series={result['series']})"
        )
        self.stdout.write(
            f"  newly rated       : {result['filled']}\n"
            f"  corrected         : {result['corrected']}\n"
            f"  unrated by IMDb   : {result['unrated_by_imdb']}\n"
            f"  manual, untouched : {result['skipped_manual']}"
        )
        self.stdout.write(self.style.SUCCESS('done'))
