"""Seed catalog view counters from already-tracked view events.

Historically ``Movie.view_count`` / ``Series.view_count`` were never written, so
every title read as 0 in the admin analytics. Detail-view tracking events
(``view_movie`` / ``view_series``) *were* recorded from day one, so this command
replays them once to backfill a real starting value. Going forward the counter
is kept live by ``_bump_view_count`` in the activity serializer.

Idempotency: pass ``--reset`` to set each counter to exactly the tracked-view
total (safe to re-run); without it the command only fills titles still at 0 so a
re-run never double-counts live traffic accumulated after the first backfill.
"""

from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.catalog.models import Movie, Series
from apps.engagement.models import UserActivityEvent


ACTION_FOR = {'movie': 'view_movie', 'series': 'view_series'}


class Command(BaseCommand):
    help = 'Backfill Movie/Series.view_count from tracked view_movie/view_series events.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Overwrite view_count with the exact tracked total (else only fill zeros).',
        )

    def handle(self, *args, **options):
        reset = options['reset']
        for content_type, model in (('movie', Movie), ('series', Series)):
            counts = {
                row['object_id']: row['n']
                for row in (
                    UserActivityEvent.objects.filter(
                        action=ACTION_FOR[content_type],
                        object_id__isnull=False,
                    )
                    .values('object_id')
                    .annotate(n=Count('id'))
                )
            }
            updated = 0
            for pk, tracked in counts.items():
                qs = model.objects.filter(pk=pk)
                if not reset:
                    qs = qs.filter(view_count=0)
                updated += qs.update(view_count=tracked)
            self.stdout.write(self.style.SUCCESS(
                f'{content_type}: {len(counts)} titles with tracked views, {updated} counters written.'
            ))
