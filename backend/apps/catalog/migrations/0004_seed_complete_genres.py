from django.db import migrations

from apps.catalog.genres import GENRES


def seed_complete_genres(apps, schema_editor):
    Genre = apps.get_model('catalog', 'Genre')
    for slug, title, description, is_featured in GENRES:
        Genre.objects.update_or_create(
            slug=slug,
            defaults={
                'title': title,
                'description': description,
                'is_featured': is_featured,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('catalog', '0003_movie_content_format_movie_content_warnings_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_complete_genres, migrations.RunPython.noop),
    ]
