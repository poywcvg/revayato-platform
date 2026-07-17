from django.conf import settings
from django.core.management.base import BaseCommand

from apps.catalog.ingestion import publish_ready_movies


class Command(BaseCommand):
    help = 'Publish licensed catalog movies whose required metadata and HLS media are ready.'

    def handle(self, *args, **options):
        count = publish_ready_movies(enabled=getattr(settings, 'CATALOG_AUTO_PUBLISH', False))
        self.stdout.write(self.style.SUCCESS(f'Published {count} ready movie(s).'))
