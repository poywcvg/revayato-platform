from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('catalog', '0027_catalog_trigram_search_indexes'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='movie',
            index=models.Index(
                fields=['is_published', '-view_count', '-like_count', '-popularity'],
                name='catalog_mov_pub_pop_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='movie',
            index=models.Index(
                fields=['is_published', '-created_at', '-id'],
                name='catalog_mov_pub_new_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='movie',
            index=models.Index(
                fields=['is_published', 'id'],
                name='catalog_mov_pub_dl_idx',
                condition=(
                    models.Q(download_links__isnull=False)
                    & ~models.Q(download_links=[])
                ) | (
                    models.Q(download_key__isnull=False)
                    & ~models.Q(download_key='')
                ),
            ),
        ),
        migrations.AddIndex(
            model_name='series',
            index=models.Index(
                fields=['is_published', '-view_count', '-like_count', '-popularity'],
                name='catalog_ser_pub_pop_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='series',
            index=models.Index(
                fields=['is_published', '-created_at', '-id'],
                name='catalog_ser_pub_new_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='series',
            index=models.Index(
                fields=['is_published', 'id'],
                name='catalog_ser_pub_dl_idx',
                condition=(
                    models.Q(download_links__isnull=False)
                    & ~models.Q(download_links=[])
                ),
            ),
        ),
    ]
