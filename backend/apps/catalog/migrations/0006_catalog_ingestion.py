import config.public_urls
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('catalog', '0005_media_object_keys')]

    operations = [
        migrations.CreateModel(
            name='CatalogSyncRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider', models.CharField(default='tmdb', max_length=40, verbose_name='Provider')),
                ('status', models.CharField(choices=[('running', 'Running'), ('succeeded', 'Succeeded'), ('failed', 'Failed')], default='running', max_length=20, verbose_name='Status')),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('discovered_count', models.PositiveIntegerField(default=0)),
                ('created_count', models.PositiveIntegerField(default=0)),
                ('updated_count', models.PositiveIntegerField(default=0)),
                ('published_count', models.PositiveIntegerField(default=0)),
                ('error_count', models.PositiveIntegerField(default=0)),
                ('errors', models.JSONField(blank=True, default=list)),
            ],
            options={
                'verbose_name': 'Catalog sync run',
                'verbose_name_plural': 'Catalog sync runs',
                'ordering': ['-started_at'],
            },
        ),
        migrations.AddField(
            model_name='movie', name='release_date',
            field=models.DateField(blank=True, db_index=True, null=True, verbose_name='Release Date'),
        ),
        migrations.AddField(
            model_name='movie', name='download_key',
            field=models.CharField(blank=True, max_length=500, validators=[config.public_urls.validate_object_key], verbose_name='Download object key'),
        ),
        migrations.AddField(
            model_name='movie', name='subtitle_tracks',
            field=models.JSONField(blank=True, default=list, validators=[config.public_urls.validate_subtitle_tracks], verbose_name='Subtitle tracks'),
        ),
        migrations.AddField(
            model_name='movie', name='media_status',
            field=models.CharField(choices=[('missing', 'Media missing'), ('ready', 'Media ready'), ('error', 'Media error')], db_index=True, default='missing', max_length=20, verbose_name='Media status'),
        ),
        migrations.AddField(
            model_name='movie', name='rights_verified',
            field=models.BooleanField(db_index=True, default=False, verbose_name='Rights verified'),
        ),
        migrations.AddField(
            model_name='movie', name='auto_publish',
            field=models.BooleanField(db_index=True, default=False, verbose_name='Auto publish when ready'),
        ),
        migrations.AddField(
            model_name='movie', name='scheduled_publish_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True, verbose_name='Scheduled publish time'),
        ),
        migrations.AddField(
            model_name='movie', name='metadata_source',
            field=models.CharField(blank=True, default='manual', max_length=40, verbose_name='Metadata source'),
        ),
        migrations.AddField(
            model_name='movie', name='metadata_synced_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Metadata synced at'),
        ),
        migrations.AddField(
            model_name='movie', name='source_metadata',
            field=models.JSONField(blank=True, default=dict, verbose_name='Source metadata'),
        ),
        migrations.AddField(
            model_name='episode', name='download_key',
            field=models.CharField(blank=True, max_length=500, validators=[config.public_urls.validate_object_key], verbose_name='Download object key'),
        ),
        migrations.AddField(
            model_name='episode', name='subtitle_tracks',
            field=models.JSONField(blank=True, default=list, validators=[config.public_urls.validate_subtitle_tracks], verbose_name='Subtitle tracks'),
        ),
    ]
