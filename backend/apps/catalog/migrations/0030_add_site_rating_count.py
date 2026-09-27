from django.db import migrations, models
from django.db.models import Avg, Count


def backfill_site_rating_counts(apps, schema_editor):
    """Seed the denormalised vote counts (and refresh averages) from any user
    ratings that already exist so the confidence-weighted «محبوب‌ترین» sort is
    correct the moment this ships."""
    Rating = apps.get_model('engagement', 'Rating')
    models_by_type = {
        'movie': apps.get_model('catalog', 'Movie'),
        'series': apps.get_model('catalog', 'Series'),
    }
    for content_type, model in models_by_type.items():
        stats = (
            Rating.objects.filter(content_type=content_type)
            .values('object_id')
            .annotate(avg=Avg('score'), votes=Count('id'))
        )
        for row in stats:
            model.objects.filter(pk=row['object_id']).update(
                site_rating=round(row['avg'], 1) if row['avg'] is not None else None,
                site_rating_count=int(row['votes'] or 0),
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0029_add_collections'),
        ('engagement', '0005_support_inbox_and_review_moderation'),
    ]

    operations = [
        migrations.AddField(
            model_name='movie',
            name='site_rating_count',
            field=models.PositiveIntegerField(default=0, db_index=True, verbose_name='Site rating votes'),
        ),
        migrations.AddField(
            model_name='series',
            name='site_rating_count',
            field=models.PositiveIntegerField(default=0, db_index=True, verbose_name='Site rating votes'),
        ),
        migrations.RunPython(backfill_site_rating_counts, noop),
    ]
