"""Backfill Actor/Director names: English original_name + Persian/Latin display name only."""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from apps.catalog.localization import (
    contains_disallowed_catalog_script,
    normalize_person_names,
)
from apps.catalog.models import Actor, Director
from apps.catalog.tmdb import TMDBClient, TMDBError, configured_tmdb_client


class Command(BaseCommand):
    help = (
        'Fill original_name (English/Latin) and normalize display name to Persian+English '
        'for actors/directors from TMDB.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0, help='Max people to update (0 = all).')
        parser.add_argument('--sleep', type=float, default=0.12, help='Pause between TMDB calls.')
        parser.add_argument('--force', action='store_true', help='Overwrite existing original_name values.')
        parser.add_argument(
            '--non-latin-only',
            action='store_true',
            help='Only people whose name/original_name still has disallowed scripts.',
        )

    def handle(self, *args, **options):
        client: TMDBClient = configured_tmdb_client()
        limit = max(0, int(options['limit'] or 0))
        sleep = max(0.0, float(options['sleep'] or 0))
        force = bool(options['force'])
        non_latin_only = bool(options['non_latin_only'])

        updated = 0
        skipped = 0
        errors = 0

        for model in (Actor, Director):
            qs = model.objects.exclude(tmdb_id__isnull=True).order_by('id')
            if not force and not non_latin_only:
                qs = qs.filter(original_name='')
            if limit:
                remaining = max(0, limit - updated)
                if remaining <= 0:
                    break
                qs = qs[:remaining]

            for person in qs.iterator(chunk_size=50):
                if non_latin_only and not (
                    contains_disallowed_catalog_script(person.name or '')
                    or contains_disallowed_catalog_script(person.original_name or '')
                ):
                    skipped += 1
                    continue
                try:
                    details = client.person_details(person.tmdb_id, language='en-US')
                except TMDBError as exc:
                    errors += 1
                    self.stderr.write(f'{model.__name__} {person.tmdb_id}: {exc}')
                    continue
                english = (details.get('name') or details.get('original_name') or '').strip()
                if not english:
                    skipped += 1
                    continue
                display, original = normalize_person_names(
                    person.name,
                    person.original_name,
                    english_name=english,
                )
                if person.name == display and person.original_name == original:
                    skipped += 1
                    continue
                person.name = display
                person.original_name = original
                person.save(update_fields=['name', 'original_name', 'updated_at'])
                updated += 1
                if contains_disallowed_catalog_script(english):
                    self.stdout.write(
                        f'{model.__name__}#{person.pk}: kept non-latin english={english!r}',
                    )
                if sleep:
                    time.sleep(sleep)

        self.stdout.write(self.style.SUCCESS(
            f'person name backfill done: updated={updated} skipped={skipped} errors={errors}',
        ))
