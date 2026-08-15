from django.core.management.base import BaseCommand

from apps.catalog.models import Movie, Series
from apps.catalog.subtitle_extract import apply_availability_flags


class Command(BaseCommand):
    help = 'Recompute is_dubbed / has_subtitle from download_links so public badges match real data.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        movie_changed = 0
        series_changed = 0

        for movie in Movie.objects.all().only('id', 'title', 'download_links', 'subtitle_tracks', 'is_dubbed', 'has_subtitle').iterator():
            changed = apply_availability_flags(movie, movie.download_links or [])
            if not changed:
                continue
            movie_changed += 1
            self.stdout.write(
                f"movie#{movie.id} {movie.title}: {', '.join(changed)} "
                f"-> dubbed={movie.is_dubbed} subtitle={movie.has_subtitle}"
            )
            if not dry_run:
                movie.save(update_fields=[*changed, 'updated_at'])

        for series in Series.objects.all().only('id', 'title', 'download_links', 'is_dubbed', 'has_subtitle').iterator():
            # Series model may not have subtitle_tracks; apply_availability_flags handles missing attrs.
            changed = apply_availability_flags(series, getattr(series, 'download_links', None) or [])
            if not changed:
                continue
            series_changed += 1
            self.stdout.write(
                f"series#{series.id} {series.title}: {', '.join(changed)} "
                f"-> dubbed={series.is_dubbed} subtitle={series.has_subtitle}"
            )
            if not dry_run:
                series.save(update_fields=[*changed, 'updated_at'])

        mode = 'dry-run' if dry_run else 'updated'
        self.stdout.write(self.style.SUCCESS(
            f'{mode}: movies={movie_changed} series={series_changed}'
        ))
