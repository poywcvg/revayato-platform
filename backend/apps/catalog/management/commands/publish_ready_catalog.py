from django.conf import settings
from django.core.management.base import BaseCommand

from apps.catalog.draft_sources import publish_sourced_drafts
from apps.catalog.ingestion import publish_ready_movies


class Command(BaseCommand):
    help = 'Publish licensed catalog movies whose required metadata and HLS media are ready.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0,
                            help='Max movies to publish this pass (0 = no cap). Each one costs a media probe.')
        parser.add_argument('--sourced-drafts-limit', type=int, default=60,
                            help='Max drafts the source hunter filled to put through the gate '
                                 '(0 = skip that pass). Each one may cost a media probe.')

    def handle(self, *args, **options):
        enabled = getattr(settings, 'CATALOG_AUTO_PUBLISH', False)
        count = publish_ready_movies(
            enabled=enabled,
            limit=max(0, int(options['limit'] or 0)),
        )
        self.stdout.write(self.style.SUCCESS(f'Published {count} ready movie(s).'))
        drafts_limit = max(0, int(options['sourced_drafts_limit'] or 0))
        if enabled and drafts_limit:
            stats = publish_sourced_drafts(limit=drafts_limit)
            self.stdout.write(self.style.SUCCESS(
                f'Sourced drafts: published={stats["published"]} blocked={stats["blocked"]} '
                f'resting={stats["resting"]} candidates={stats["candidates"]}',
            ))
