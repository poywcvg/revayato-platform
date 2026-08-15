import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('catalog', '0013_cast_import_limit'),
    ]

    operations = [
        migrations.CreateModel(
            name='MovieArchiveAsset',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('storage_provider', models.CharField(default='arvan_s3', max_length=40, verbose_name='Storage provider')),
                ('bucket', models.CharField(max_length=255, verbose_name='Bucket')),
                ('object_key', models.CharField(max_length=1024, unique=True, verbose_name='Object key')),
                ('original_filename', models.CharField(max_length=255, verbose_name='Original filename')),
                ('safe_filename', models.CharField(max_length=255, verbose_name='Safe filename')),
                ('file_extension', models.CharField(max_length=16, verbose_name='File extension')),
                ('content_type', models.CharField(max_length=100, verbose_name='Content type')),
                ('size_bytes', models.PositiveBigIntegerField(verbose_name='Expected size (bytes)')),
                ('actual_size_bytes', models.PositiveBigIntegerField(blank=True, null=True, verbose_name='Actual size (bytes)')),
                ('etag', models.CharField(blank=True, max_length=255, verbose_name='ETag')),
                ('sha256', models.CharField(blank=True, max_length=64, verbose_name='SHA-256')),
                ('upload_id', models.CharField(blank=True, max_length=255, verbose_name='Multipart upload ID')),
                ('part_size_bytes', models.PositiveBigIntegerField(verbose_name='Part size (bytes)')),
                ('total_parts', models.PositiveIntegerField(verbose_name='Total parts')),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('multipart_created', 'Multipart created'),
                        ('uploading', 'Uploading'),
                        ('verifying', 'Verifying'),
                        ('available', 'Available'),
                        ('failed', 'Failed'),
                        ('aborted', 'Aborted'),
                        ('deletion_pending', 'Deletion pending'),
                        ('deleted', 'Deleted'),
                    ],
                    db_index=True,
                    default='pending',
                    max_length=32,
                    verbose_name='Status',
                )),
                ('failure_reason', models.CharField(blank=True, max_length=500, verbose_name='Failure reason')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('aborted_at', models.DateTimeField(blank=True, null=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_archive_assets',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('movie', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='archive_assets',
                    to='catalog.movie',
                )),
                ('uploaded_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='uploaded_archive_assets',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Movie archive asset',
                'verbose_name_plural': 'Movie archive assets',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='moviearchiveasset',
            index=models.Index(fields=['movie', 'status'], name='catalog_mov_movie_i_7c0f1a_idx'),
        ),
        migrations.AddIndex(
            model_name='moviearchiveasset',
            index=models.Index(fields=['status', '-created_at'], name='catalog_mov_status_5e2b9c_idx'),
        ),
    ]
