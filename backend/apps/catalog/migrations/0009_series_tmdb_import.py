from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0008_tmdb_metadata_accuracy'),
    ]

    operations = [
        migrations.AddField(
            model_name='season',
            name='poster_external_url',
            field=models.URLField(blank=True, max_length=500, verbose_name='External poster URL'),
        ),
        migrations.AddField(
            model_name='season',
            name='tmdb_id',
            field=models.PositiveIntegerField(blank=True, null=True, unique=True, verbose_name='TMDb ID'),
        ),
        migrations.AddField(
            model_name='series',
            name='backdrop_external_url',
            field=models.URLField(blank=True, max_length=500, verbose_name='External backdrop URL'),
        ),
        migrations.AddField(
            model_name='series',
            name='imdb_id',
            field=models.CharField(blank=True, max_length=20, null=True, unique=True, verbose_name='IMDb ID'),
        ),
        migrations.AddField(
            model_name='series',
            name='last_tmdb_sync_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Last TMDb sync'),
        ),
        migrations.AddField(
            model_name='series',
            name='metadata_source',
            field=models.CharField(blank=True, default='manual', max_length=40, verbose_name='Metadata source'),
        ),
        migrations.AddField(
            model_name='series',
            name='metadata_synced_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Metadata synced at'),
        ),
        migrations.AddField(
            model_name='series',
            name='original_language',
            field=models.CharField(blank=True, db_index=True, max_length=20, verbose_name='Original language'),
        ),
        migrations.AddField(
            model_name='series',
            name='popularity',
            field=models.FloatField(db_index=True, default=0.0, verbose_name='TMDb popularity'),
        ),
        migrations.AddField(
            model_name='series',
            name='poster_external_url',
            field=models.URLField(blank=True, max_length=500, verbose_name='External poster URL'),
        ),
        migrations.AddField(
            model_name='series',
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
        migrations.AddField(
            model_name='series',
            name='source_metadata',
            field=models.JSONField(blank=True, default=dict, verbose_name='Source metadata'),
        ),
        migrations.AddField(
            model_name='series',
            name='tmdb_id',
            field=models.PositiveIntegerField(blank=True, null=True, unique=True, verbose_name='TMDb ID'),
        ),
        migrations.AddField(
            model_name='series',
            name='trailer_external_url',
            field=models.URLField(blank=True, max_length=500, verbose_name='External trailer URL'),
        ),
        migrations.AddField(
            model_name='series',
            name='vote_count',
            field=models.PositiveBigIntegerField(default=0, verbose_name='TMDb vote count'),
        ),
    ]
