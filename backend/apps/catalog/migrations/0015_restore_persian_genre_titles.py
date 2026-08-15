from django.db import migrations

from apps.catalog.genres import GENRES


def restore_persian_genre_titles(apps, schema_editor):
    Genre = apps.get_model('catalog', 'Genre')
    for slug, title, description, is_featured in GENRES:
        genre, created = Genre.objects.get_or_create(
            slug=slug,
            defaults={
                'title': title,
                'description': description,
                'is_featured': is_featured,
            },
        )
        updates = []
        if genre.title != title:
            # Avoid unique collisions while renaming English leftovers.
            if Genre.objects.filter(title=title).exclude(pk=genre.pk).exists():
                conflict = Genre.objects.filter(title=title).exclude(pk=genre.pk).first()
                if conflict and conflict.slug.startswith('tmdb-'):
                    conflict.title = f'{title} ({conflict.slug})'
                    conflict.save(update_fields=['title'])
                elif conflict:
                    continue
            genre.title = title
            updates.append('title')
        if description and genre.description != description:
            genre.description = description
            updates.append('description')
        if genre.is_featured != is_featured:
            genre.is_featured = is_featured
            updates.append('is_featured')
        if updates:
            genre.save(update_fields=updates)

    # Rename leftover English TMDB compound slugs if present.
    aliases = {
        'action-adventure': 'اکشن و ماجراجویی',
        'sci-fi-fantasy': 'علمی‌تخیلی و فانتزی',
        'reality': 'رئالیتی‌شو',
        'war-politics': 'جنگ و سیاست',
        'tv-movie': 'فیلم تلویزیونی',
        'Science Fiction': None,  # title collision guard; ignored
    }
    for slug, title in aliases.items():
        if not title:
            continue
        Genre.objects.filter(slug=slug).exclude(title=title).update(title=title)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0014_movie_archive_asset'),
    ]

    operations = [
        migrations.RunPython(restore_persian_genre_titles, noop_reverse),
    ]
