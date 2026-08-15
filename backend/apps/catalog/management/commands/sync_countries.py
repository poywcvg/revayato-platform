"""Normalize Country rows to Persian names and keep them aligned with catalog titles."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from apps.catalog.cache import bump_catalog_cache_version
from apps.catalog.countries import COUNTRY_NAME_BY_CODE, persian_country_name
from apps.catalog.models import Country


class Command(BaseCommand):
    help = (
        'Normalize country display names to Persian, report published coverage, '
        'and optionally prune countries with no published movies/series.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--prune-orphans',
            action='store_true',
            help='Delete countries that are not linked to any published movie or series.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show planned changes without writing.',
        )

    def handle(self, *args, **options):
        dry_run = bool(options['dry_run'])
        prune = bool(options['prune_orphans'])
        renamed = 0
        pruned = 0

        countries = Country.objects.annotate(
            movie_count=Count('movies', filter=Q(movies__is_published=True), distinct=True),
            series_count=Count('series', filter=Q(series__is_published=True), distinct=True),
        ).order_by('code')

        for country in countries:
            desired = persian_country_name(country.code, country.name)
            if desired and desired != country.name:
                conflict = Country.objects.filter(name=desired).exclude(pk=country.pk).exists()
                if conflict:
                    self.stdout.write(
                        self.style.WARNING(
                            f'skip rename {country.code}: name {desired!r} already used',
                        ),
                    )
                    continue
                self.stdout.write(f'rename {country.code}: {country.name!r} -> {desired!r}')
                if not dry_run:
                    country.name = desired
                    country.save(update_fields=['name'])
                renamed += 1

        if prune:
            orphans = [
                country for country in countries
                if country.movie_count == 0 and country.series_count == 0
            ]
            for country in orphans:
                self.stdout.write(
                    f'prune orphan {country.code} name={country.name!r}',
                )
                if not dry_run:
                    country.delete()
                pruned += 1

        mapped = sum(1 for code in {c.code for c in countries} if code in COUNTRY_NAME_BY_CODE)
        with_content = sum(1 for c in countries if c.movie_count or c.series_count)

        if not dry_run and (renamed or pruned):
            bump_catalog_cache_version()

        self.stdout.write(
            self.style.SUCCESS(
                f'done renamed={renamed} pruned={pruned} '
                f'with_published={with_content} mapped={mapped}/{countries.count()} dry_run={dry_run}',
            ),
        )
