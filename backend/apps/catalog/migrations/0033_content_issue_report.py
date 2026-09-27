from django.conf import settings
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0032_subtitlesyncvote'),
        ('engagement', '0005_support_inbox_and_review_moderation'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ContentIssueReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content_type', models.CharField(choices=[('movie', 'Movie'), ('series', 'Series')], db_index=True, max_length=16)),
                ('object_id', models.PositiveIntegerField(db_index=True)),
                ('episode_id', models.PositiveIntegerField(db_index=True, default=0)),
                ('season_number', models.PositiveSmallIntegerField(default=0)),
                ('episode_number', models.PositiveSmallIntegerField(default=0)),
                ('slug', models.SlugField(blank=True, max_length=255)),
                ('title', models.CharField(blank=True, max_length=300)),
                ('problem_type', models.CharField(choices=[('subtitle', 'Subtitle problem'), ('wrong_title', 'Wrong film / mismatched title'), ('wrong_episode', 'Wrong episode placed'), ('playback', 'Will not play'), ('audio', 'Audio / dubbing problem'), ('other', 'Other')], db_index=True, max_length=20)),
                ('playback_version', models.CharField(blank=True, max_length=32)),
                ('source_url', models.URLField(blank=True, max_length=1000)),
                ('detail', models.TextField(blank=True)),
                ('reporter_key', models.CharField(blank=True, db_index=True, max_length=64)),
                ('status', models.CharField(choices=[('open', 'Open'), ('queued', 'Queued'), ('remediating', 'Remediating'), ('resolved', 'Resolved'), ('needs_review', 'Needs review'), ('rejected', 'Rejected'), ('unavailable', 'Unavailable')], db_index=True, default='open', max_length=16)),
                ('report_count', models.PositiveIntegerField(default=1)),
                ('remediation_action', models.CharField(blank=True, max_length=64)),
                ('last_result', models.CharField(blank=True, max_length=200)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('meta', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('remediated_at', models.DateTimeField(blank=True, null=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('reporter', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='content_issue_reports', to=settings.AUTH_USER_MODEL)),
                ('support_ticket', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='content_issue_reports', to='engagement.supportticket')),
            ],
            options={
                'verbose_name': 'Content issue report',
                'verbose_name_plural': 'Content issue reports',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.AddIndex(
            model_name='contentissuereport',
            index=models.Index(fields=['content_type', 'object_id', 'status'], name='catalog_con_content_de8798_idx'),
        ),
        migrations.AddIndex(
            model_name='contentissuereport',
            index=models.Index(fields=['status', '-updated_at'], name='catalog_con_status_bb3020_idx'),
        ),
        migrations.AddIndex(
            model_name='contentissuereport',
            index=models.Index(fields=['problem_type', 'status'], name='catalog_con_problem_71015b_idx'),
        ),
        migrations.AddConstraint(
            model_name='contentissuereport',
            constraint=models.UniqueConstraint(fields=('content_type', 'object_id', 'episode_id', 'problem_type'), name='uniq_content_issue_report_target'),
        ),
    ]
