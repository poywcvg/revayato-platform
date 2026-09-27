"""Give every movie and series an English page address.

Dry run by default: prints what would change. ``--apply`` renames the slugs; each
old (Persian) slug is kept as a :class:`CatalogSlugAlias`, so existing links,
bookmarks and search-engine results keep resolving (the web app 301s them).
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Movie, Series
from apps.catalog.slugs import english_slug_for, is_english_slug


class Command(BaseCommand):
    help = 'Convert non-English movie/series slugs to English ones (old slugs keep working).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Write the changes (default: dry run).')
        parser.add_argument('--kind', choices=['movie', 'series', 'all'], default='all')
        parser.add_argument('--limit', type=int, default=0, help='Stop after this many rows per kind.')
        parser.add_argument('--show', type=int, default=15, help='Sample rows to print per kind.')

    def handle(self, *args, apply=False, kind='all', limit=0, show=15, **options):
        targets = []
        if kind in {'movie', 'all'}:
            targets.append((Movie, 'release_year'))
        if kind in {'series', 'all'}:
            targets.append((Series, 'start_year'))
        total_changed = 0
        for model, year_field in targets:
            changed = skipped = 0
            rows = model.objects.order_by('pk').only('pk', 'slug', 'title', 'original_title', 'tmdb_id', year_field)
            for obj in rows.iterator(chunk_size=500):
                if is_english_slug(obj.slug):
                    skipped += 1
                    continue
                if limit and changed >= limit:
                    break
                with transaction.atomic():
                    new_slug = english_slug_for(
                        model, title=obj.title, original_title=obj.original_title,
                        year=getattr(obj, year_field), tmdb_id=obj.tmdb_id, current_pk=obj.pk,
                    )
                    if changed < show:
                        self.stdout.write(f'  {model.__name__} #{obj.pk}: {obj.slug} → {new_slug}')
                    if apply:
                        obj.slug = new_slug
                        obj.save(update_fields=['slug'])
                changed += 1
            total_changed += changed
            self.stdout.write(
                f'{model.__name__}: {changed} {"renamed" if apply else "to rename"}, {skipped} already English',
            )
        if apply and total_changed:
            from apps.catalog.cache import bump_catalog_cache_version

            bump_catalog_cache_version()
        if not apply:
            self.stdout.write('Dry run — nothing written. Re-run with --apply.')
