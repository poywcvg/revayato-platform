from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0030_add_site_rating_count'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlaybackSourceGap',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content_type', models.CharField(choices=[('movie', 'Movie'), ('series', 'Series')], db_index=True, max_length=16)),
                ('object_id', models.PositiveIntegerField(db_index=True)),
                ('episode_id', models.PositiveIntegerField(db_index=True, default=0)),
                ('slug', models.SlugField(blank=True, max_length=255)),
                ('title', models.CharField(blank=True, max_length=300)),
                ('reason', models.CharField(blank=True, max_length=32)),
                ('status', models.CharField(choices=[('open', 'Open'), ('queued', 'Queued'), ('resolved', 'Resolved'), ('unavailable', 'Unavailable')], db_index=True, default='open', max_length=16)),
                ('report_count', models.PositiveIntegerField(default=1)),
                ('last_result', models.CharField(blank=True, max_length=64)),
                ('meta', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Playback source gap',
                'verbose_name_plural': 'Playback source gaps',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.AddIndex(
            model_name='playbacksourcegap',
            index=models.Index(fields=['content_type', 'object_id', 'status'], name='catalog_pla_content_b6da7e_idx'),
        ),
        migrations.AddIndex(
            model_name='playbacksourcegap',
            index=models.Index(fields=['status', '-updated_at'], name='catalog_pla_status_36a16e_idx'),
        ),
        migrations.AddConstraint(
            model_name='playbacksourcegap',
            constraint=models.UniqueConstraint(fields=('content_type', 'object_id', 'episode_id'), name='uniq_playback_source_gap_target'),
        ),
    ]
