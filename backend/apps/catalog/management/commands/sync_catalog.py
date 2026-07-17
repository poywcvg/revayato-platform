from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test.utils import override_settings

from apps.catalog.ingestion import load_media_manifest, sync_recent_tmdb_movies


class Command(BaseCommand):
    help = 'Sync newly released movie metadata from TMDB and attach licensed media keys.'

    def add_arguments(self, parser):
        parser.add_argument('--pages', type=int, default=None)
        parser.add_argument('--lookback-days', type=int, default=None)
        parser.add_argument('--lookahead-days', type=int, default=None)
        parser.add_argument('--manifest', default=None)
        parser.add_argument('--no-publish', action='store_true')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        manifest_path = options['manifest']
        manifest = None
        if manifest_path is not None:
            try:
                manifest = load_media_manifest(manifest_path)
            except (OSError, ValueError) as exc:
                raise CommandError(f'Unable to load media manifest: {exc}') from exc

        try:
            with override_settings(
                CATALOG_AUTO_PUBLISH=False
                if options['no_publish'] or options['dry_run']
                else getattr(settings, 'CATALOG_AUTO_PUBLISH', False),
            ):
                with transaction.atomic():
                    stats = sync_recent_tmdb_movies(
                        manifest=manifest,
                        max_pages=options['pages'],
                        lookback_days=options['lookback_days'],
                        lookahead_days=options['lookahead_days'],
                    )
                    if options['dry_run']:
                        transaction.set_rollback(True)
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        label = 'Dry run' if options['dry_run'] else 'Catalog sync'
        self.stdout.write(self.style.SUCCESS(
            f'{label}: discovered={stats["discovered"]}, created={stats["created"]}, '
            f'updated={stats["updated"]}, published={stats["published"]}, errors={stats["errors"]}'
        ))
