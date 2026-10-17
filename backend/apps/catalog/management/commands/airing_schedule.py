"""جدول پخش by hand: sync TMDB release dates, hunt due releases, or show the state.

    python manage.py airing_schedule --status
    python manage.py airing_schedule --sync [--budget 900]
    python manage.py airing_schedule --hunt [--titles 10]
"""

import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Sync the airing schedule from TMDB and/or crawl for releases that are due.'

    def add_arguments(self, parser):
        parser.add_argument('--sync', action='store_true', help='Re-read TMDB dates of tracked titles that are due.')
        parser.add_argument('--hunt', action='store_true', help='Crawl providers for aired releases not on the site.')
        parser.add_argument('--status', action='store_true', help='Print what the schedule holds.')
        parser.add_argument('--budget', type=float, default=None, help='Seconds per phase.')
        parser.add_argument('--titles', type=int, default=None, help='Max titles per phase.')

    def handle(self, *args, **options):
        from apps.catalog import airing

        if not (options['sync'] or options['hunt'] or options['status']):
            options['status'] = True
        if options['sync']:
            self._print('sync', airing.sync_schedule(budget_seconds=options['budget'], limit=options['titles']))
        if options['hunt']:
            self._print('hunt', airing.hunt(budget_seconds=options['budget'], max_titles=options['titles']))
        if options['status']:
            self._print('status', airing.status_summary())

    def _print(self, label, payload):
        self.stdout.write(f'{label}: {json.dumps(payload, ensure_ascii=False, default=str)}')
