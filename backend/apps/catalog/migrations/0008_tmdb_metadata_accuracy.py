# Generated for the staff movie/TMDb workflow.

import apps.catalog.models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0007_admin_movie_workflow'),
    ]

    operations = [
        migrations.AddField(
            model_name='movie',
            name='backdrop_path',
            field=models.CharField(blank=True, max_length=255, verbose_name='TMDb backdrop path'),
        ),
        migrations.AddField(
            model_name='movie',
            name='original_language',
            field=models.CharField(blank=True, db_index=True, max_length=20, verbose_name='Original language'),
        ),
        migrations.AddField(
            model_name='movie',
            name='poster_path',
            field=models.CharField(blank=True, max_length=255, verbose_name='TMDb poster path'),
        ),
        migrations.AddField(
            model_name='movie',
            name='rating_average',
            field=models.DecimalField(
                blank=True,
                decimal_places=1,
                max_digits=3,
                null=True,
                validators=[MinValueValidator(0), MaxValueValidator(10)],
                verbose_name='TMDb rating average',
            ),
        ),
        migrations.AlterField(
            model_name='movie',
            name='backdrop',
            field=models.ImageField(blank=True, null=True, upload_to=apps.catalog.models.movie_backdrop_upload_path, verbose_name='Backdrop'),
        ),
        migrations.AlterField(
            model_name='movie',
            name='media_status',
            field=models.CharField(
                choices=[
                    ('missing', 'Media missing'),
                    ('processing', 'Media processing'),
                    ('ready', 'Media ready'),
                    ('error', 'Media error'),
                    ('failed', 'Media failed'),
                ],
                db_index=True,
                default='missing',
                max_length=20,
                verbose_name='Media status',
            ),
        ),
        migrations.AlterField(
            model_name='movie',
            name='poster',
            field=models.ImageField(blank=True, null=True, upload_to=apps.catalog.models.movie_poster_upload_path, verbose_name='Poster'),
        ),
    ]
