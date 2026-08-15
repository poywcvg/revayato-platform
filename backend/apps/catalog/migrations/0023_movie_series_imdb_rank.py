# Generated manually for IMDb Top 250 rank badges.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0022_list_updated_at_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='movie',
            name='imdb_rank',
            field=models.PositiveSmallIntegerField(
                blank=True,
                db_index=True,
                help_text='1–250 when this title is on the IMDb Top 250 chart; null otherwise.',
                null=True,
                verbose_name='IMDb Top 250 rank',
            ),
        ),
        migrations.AddField(
            model_name='series',
            name='imdb_rank',
            field=models.PositiveSmallIntegerField(
                blank=True,
                db_index=True,
                help_text='1–250 when this title is on the IMDb Top 250 TV chart; null otherwise.',
                null=True,
                verbose_name='IMDb Top 250 rank',
            ),
        ),
        migrations.AddIndex(
            model_name='movie',
            index=models.Index(fields=['is_published', 'imdb_rank'], name='catalog_mov_is_publ_imdb_rk_idx'),
        ),
        migrations.AddIndex(
            model_name='series',
            index=models.Index(fields=['is_published', 'imdb_rank'], name='catalog_ser_is_publ_imdb_rk_idx'),
        ),
    ]
