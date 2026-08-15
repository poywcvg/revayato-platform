from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('catalog', '0010_catalog_sync_jobs'),
    ]

    operations = [
        migrations.AlterField(
            model_name='catalogsyncrun',
            name='mode',
            field=models.CharField(
                choices=[
                    ('incremental', 'Incremental'),
                    ('daily', 'Daily releases'),
                    ('trending', 'Trending'),
                    ('full', 'Full catalog'),
                ],
                default='incremental',
                max_length=20,
                verbose_name='Mode',
            ),
        ),
        migrations.AddField(
            model_name='actor',
            name='photo_external_url',
            field=models.URLField(blank=True, max_length=500, verbose_name='External photo URL'),
        ),
        migrations.AddField(
            model_name='director',
            name='photo_external_url',
            field=models.URLField(blank=True, max_length=500, verbose_name='External photo URL'),
        ),
        migrations.CreateModel(
            name='CatalogImporterSettings',
            fields=[
                ('id', models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ('language', models.CharField(default='fa-IR', max_length=10, verbose_name='TMDb language')),
                ('fallback_language', models.CharField(default='en-US', max_length=10, verbose_name='Fallback language')),
                ('region', models.CharField(blank=True, default='IR', max_length=2, verbose_name='TMDb region')),
                ('daily_lookback_days', models.PositiveSmallIntegerField(default=2, validators=[MinValueValidator(1), MaxValueValidator(14)], verbose_name='Daily lookback days')),
                ('daily_lookahead_days', models.PositiveSmallIntegerField(default=7, validators=[MinValueValidator(0), MaxValueValidator(90)], verbose_name='Daily lookahead days')),
                ('daily_max_pages', models.PositiveSmallIntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(100)], verbose_name='Daily maximum pages')),
                ('trending_window', models.CharField(choices=[('day', 'Day'), ('week', 'Week')], default='day', max_length=8, verbose_name='Trending window')),
                ('trending_max_pages', models.PositiveSmallIntegerField(default=3, validators=[MinValueValidator(1), MaxValueValidator(20)], verbose_name='Trending maximum pages')),
                ('import_people_images', models.BooleanField(default=True, verbose_name='Import cast and director images')),
                ('fetch_imdb_ratings', models.BooleanField(default=True, verbose_name='Fetch IMDb ratings')),
                ('feature_trending', models.BooleanField(default=True, verbose_name='Feature trending imports')),
                ('auto_publish', models.BooleanField(default=False, verbose_name='Publish complete imported metadata')),
                ('automation_enabled', models.BooleanField(default=False, verbose_name='Enable scheduled imports')),
                ('automation_mode', models.CharField(choices=[('daily', 'Daily releases'), ('trending', 'Trending')], default='daily', max_length=12, verbose_name='Scheduled import mode')),
                ('automation_interval_hours', models.PositiveSmallIntegerField(default=24, validators=[MinValueValidator(1), MaxValueValidator(168)], verbose_name='Scheduled interval (hours)')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='catalog_importer_settings_updates', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Catalog importer settings',
                'verbose_name_plural': 'Catalog importer settings',
            },
        ),
    ]
