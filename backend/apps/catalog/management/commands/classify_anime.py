"""Backfill the `anime` genre onto existing Japanese-animation titles.

New imports are tagged automatically inside ``_upsert_genres`` (see
``looks_like_anime``). This one-shot command applies the same rule to titles
already in the catalog, deriving the signal from stored fields instead of a live
TMDB payload: the Animation content format (or genre) together with a Japanese
origin — ``original_language == 'ja'`` or ``JP`` among the linked countries.

Idempotent: a title that already carries the anime genre is left untouched.
Use ``--dry-run`` to preview counts without writing.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.catalog.ingestion import persian_genre_title
from apps.catalog.models import Genre, Movie, Series


def _japanese_animation_qs(model):
    return (
        model.objects.filter(
            (Q(content_format='animation') | Q(genres__slug='animation'))
            & (Q(original_language__iexact='ja') | Q(countries__code__iexact='JP'))
        )
        .exclude(genres__slug='anime')
        .distinct()
    )


class Command(BaseCommand):
    help = 'Tag existing Japanese-animation movies and series with the anime genre.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be tagged without writing.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        anime_genre, _ = Genre.objects.get_or_create(
            slug='anime', defaults={'title': persian_genre_title('anime')},
        )

        totals = {}
        for label, model in (('movies', Movie), ('series', Series)):
            qs = list(_japanese_animation_qs(model))
            totals[label] = len(qs)
            self.stdout.write(f'{label}: {len(qs)} title(s) match the anime rule')
            if dry_run:
                for obj in qs[:20]:
                    self.stdout.write(f'  • {obj.slug} ({obj.original_language or "?"})')
                continue
            for obj in qs:
                obj.genres.add(anime_genre)

        verb = 'Would tag' if dry_run else 'Tagged'
        self.stdout.write(self.style.SUCCESS(
            f'{verb} {totals.get("movies", 0)} movie(s) and {totals.get("series", 0)} series as anime.'
        ))
