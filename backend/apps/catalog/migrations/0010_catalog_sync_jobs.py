from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def close_duplicate_active_runs(apps, schema_editor):
    CatalogSyncRun = apps.get_model('catalog', 'CatalogSyncRun')
    active = CatalogSyncRun.objects.filter(status='running').order_by('provider', '-started_at')
    seen = set()
    for run in active.iterator():
        if run.provider not in seen:
            seen.add(run.provider)
            continue
        run.status = 'failed'
        run.phase = 'migration_cleanup'
        run.finished_at = django.utils.timezone.now()
        run.errors = [{'error': 'Superseded while enabling exclusive catalog sync jobs.'}]
        run.save(update_fields=['status', 'phase', 'finished_at', 'errors'])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('catalog', '0009_series_tmdb_import'),
    ]

    operations = [
        migrations.AddField(
            model_name='catalogsyncrun',
            name='cancel_requested_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='catalogsyncrun',
            name='current_tmdb_id',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='catalogsyncrun',
            name='heartbeat_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='catalogsyncrun',
            name='mode',
            field=models.CharField(choices=[('incremental', 'Incremental'), ('full', 'Full catalog')], default='incremental', max_length=20, verbose_name='Mode'),
        ),
        migrations.AddField(
            model_name='catalogsyncrun',
            name='parameters',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='catalogsyncrun',
            name='phase',
            field=models.CharField(default='queued', max_length=40, verbose_name='Phase'),
        ),
        migrations.AddField(
            model_name='catalogsyncrun',
            name='processed_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='catalogsyncrun',
            name='requested_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='catalog_sync_runs', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='catalogsyncrun',
            name='skipped_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='catalogsyncrun',
            name='task_id',
            field=models.CharField(blank=True, max_length=255, verbose_name='Celery task ID'),
        ),
        migrations.AddField(
            model_name='catalogsyncrun',
            name='total_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='catalogsyncrun',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name='catalogsyncrun',
            name='status',
            field=models.CharField(choices=[('queued', 'Queued'), ('running', 'Running'), ('cancelling', 'Cancelling'), ('cancelled', 'Cancelled'), ('succeeded', 'Succeeded'), ('failed', 'Failed')], default='queued', max_length=20, verbose_name='Status'),
        ),
        migrations.RunPython(close_duplicate_active_runs, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='catalogsyncrun',
            constraint=models.UniqueConstraint(condition=models.Q(('status__in', ['queued', 'running', 'cancelling'])), fields=('provider',), name='catalog_one_active_sync_per_provider'),
        ),
        migrations.CreateModel(
            name='CatalogSyncCandidate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tmdb_id', models.PositiveIntegerField()),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('succeeded', 'Succeeded'), ('skipped', 'Skipped'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('popularity', models.FloatField(default=0.0)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('error', models.CharField(blank=True, max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('run', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='candidates', to='catalog.catalogsyncrun')),
            ],
            options={'ordering': ['id']},
        ),
        migrations.AddConstraint(
            model_name='catalogsynccandidate',
            constraint=models.UniqueConstraint(fields=('run', 'tmdb_id'), name='catalog_unique_sync_candidate'),
        ),
        migrations.AddIndex(
            model_name='catalogsynccandidate',
            index=models.Index(fields=['run', 'status', 'id'], name='catalog_sync_work_idx'),
        ),
    ]
