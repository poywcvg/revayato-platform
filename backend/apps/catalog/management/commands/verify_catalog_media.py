"""Test that catalog media really plays and downloads.

Runs the same pre-publish check the importer runs, on demand: it asks each host
for the first two kilobytes of the file and reports whether the title is
playable in a browser, merely downloadable, or gone. Nothing is published or
unpublished here unless ``--sweep`` is used.

Examples::

    python manage.py verify_catalog_media --movie 1234
    python manage.py verify_catalog_media --series 88 --episodes 5
    python manage.py verify_catalog_media --published --limit 50
    python manage.py verify_catalog_media --sweep --limit 40
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Verify that catalog playback/download sources are actually served.'

    def add_arguments(self, parser):
        parser.add_argument('--movie', type=int, default=None, help='Verify one movie by id')
        parser.add_argument('--series', type=int, default=None, help='Verify one series by id')
        parser.add_argument('--episodes', type=int, default=0, help='Also verify N episodes of that series')
        parser.add_argument('--published', action='store_true', help='Verify a batch of published titles')
        parser.add_argument('--limit', type=int, default=25, help='Batch size')
        parser.add_argument('--force', action='store_true', help='Re-probe even when the stored check is fresh')
        parser.add_argument(
            '--sweep', action='store_true',
            help='Run the periodic sweep: re-crawl broken titles, draft the empty ones',
        )

    def handle(self, *args, **options):
        from apps.catalog.media_verification import (
            sweep_published_media, verify_series_episodes, verify_target,
        )
        from apps.catalog.models import Movie, Series

        if options.get('sweep'):
            stats = sweep_published_media(limit=int(options.get('limit') or 40))
            self.stdout.write(
                'swept {checked}: {passed} ok, {failed} broken, {unknown} unreachable · '
                '{recrawled} re-crawled, {unpublished} drafted'.format_map(
                    {'recrawled': 0, 'unpublished': 0, **stats},
                )
            )
            return

        if options.get('movie'):
            self._one(Movie, options['movie'], options)
            return
        if options.get('series'):
            series = self._one(Series, options['series'], options)
            episodes = int(options.get('episodes') or 0)
            if episodes:
                stats = verify_series_episodes(series, limit=episodes)
                self.stdout.write(
                    '  episodes: {checked} checked · {passed} ok, {failed} broken, '
                    '{unknown} unreachable'.format_map(stats)
                )
            return

        if not options.get('published'):
            raise CommandError('Pass --movie, --series, --published or --sweep.')

        limit = int(options.get('limit') or 25)
        checked = 0
        for model in (Movie, Series):
            for obj in model.objects.filter(is_published=True).order_by('-updated_at')[:limit]:
                self._report(obj, verify_target(obj))
                checked += 1
        self.stdout.write(f'verified {checked} published title(s).')

    def _one(self, model, pk: int, options):
        from apps.catalog.media_verification import ensure_verified

        obj = model.objects.filter(pk=pk).first()
        if obj is None:
            raise CommandError(f'No {model.__name__} with id={pk}')
        self._report(obj, ensure_verified(obj, force=bool(options.get('force'))))
        return obj

    def _report(self, obj, verdict: dict):
        marks = []
        if verdict.get('playable'):
            marks.append('plays in browser')
        if verdict.get('downloadable'):
            marks.append('downloadable')
        detail = ', '.join(marks) or verdict.get('reason') or 'no usable source'
        line = (
            f'{obj.__class__.__name__} #{obj.pk} {obj.title[:48]} → '
            f'{verdict["status"]}: {detail} '
            f'({verdict.get("checked", 0)} probed, {verdict.get("dead", 0)} dead)'
        )
        style = {
            'passed': self.style.SUCCESS,
            'failed': self.style.ERROR,
        }.get(verdict.get('status'), self.style.WARNING)
        self.stdout.write(style(line))
