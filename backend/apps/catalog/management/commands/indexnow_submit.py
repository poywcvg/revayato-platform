"""Send title URLs to IndexNow now.

    manage.py indexnow_submit            # flush what the save signal queued
    manage.py indexnow_submit --all      # every published movie/series (one-off backfill)
    manage.py indexnow_submit --all --dry-run
"""

from django.core.management.base import BaseCommand

from apps.catalog import indexnow
from apps.catalog.models import Movie, Series


class Command(BaseCommand):
    help = 'Submit title URLs to IndexNow (Bing, Yandex, Seznam, Naver).'

    def add_arguments(self, parser):
        parser.add_argument('--all', action='store_true', help='Submit every published movie and series.')
        parser.add_argument('--dry-run', action='store_true', help='Count the URLs, send nothing.')

    def handle(self, *args, **options):
        if not indexnow.enabled():
            self.stdout.write('IndexNow is disabled (INDEXNOW_ENABLED / INDEXNOW_KEY / SITE_BASE_URL).')
            return
        if not options['all']:
            self.stdout.write(str(indexnow.flush_pending()))
            return
        site = indexnow.site_url()
        urls = [
            f'{site}/movies/{slug}'
            for slug in Movie.objects.filter(is_published=True).exclude(slug='').order_by('-id').values_list('slug', flat=True)
        ] + [
            f'{site}/series/{slug}'
            for slug in Series.objects.filter(is_published=True).exclude(slug='').order_by('-id').values_list('slug', flat=True)
        ]
        self.stdout.write(f'{len(urls)} URLs')
        if options['dry_run']:
            return
        self.stdout.write(str(indexnow.submit(urls, timeout=60)))
