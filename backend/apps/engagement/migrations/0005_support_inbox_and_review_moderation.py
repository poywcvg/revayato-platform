import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('engagement', '0004_useractivityevent_client_event_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='rating',
            name='is_hidden',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.CreateModel(
            name='SupportTicket',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tracking_code', models.CharField(db_index=True, max_length=16, unique=True)),
                ('category', models.CharField(
                    choices=[
                        ('content_request', 'درخواست عنوان'),
                        ('bug', 'گزارش مشکل'),
                        ('content_fix', 'اصلاح محتوا'),
                        ('suggestion', 'پیشنهاد'),
                        ('support', 'پشتیبانی'),
                        ('cooperation', 'همکاری'),
                    ],
                    default='support',
                    max_length=32,
                )),
                ('subject', models.CharField(max_length=200)),
                ('body', models.TextField()),
                ('related_title', models.CharField(blank=True, max_length=255)),
                ('related_year', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('related_url', models.URLField(blank=True, max_length=500)),
                ('status', models.CharField(
                    choices=[
                        ('open', 'باز'),
                        ('in_progress', 'در حال بررسی'),
                        ('waiting_user', 'منتظر پاسخ شما'),
                        ('resolved', 'حل‌شده'),
                        ('closed', 'بسته'),
                    ],
                    db_index=True,
                    default='open',
                    max_length=20,
                )),
                ('staff_note', models.TextField(blank=True)),
                ('unread_by_staff', models.BooleanField(db_index=True, default=True)),
                ('unread_by_user', models.BooleanField(default=False)),
                ('last_message_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='support_tickets',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-last_message_at', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='SupportMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_staff_reply', models.BooleanField(default=False)),
                ('body', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('author', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='support_messages',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('ticket', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='messages',
                    to='engagement.supportticket',
                )),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='supportticket',
            index=models.Index(fields=['status', '-last_message_at'], name='engagement__status_7c0d2a_idx'),
        ),
        migrations.AddIndex(
            model_name='supportticket',
            index=models.Index(fields=['user', '-created_at'], name='engagement__user_id_8f1a4b_idx'),
        ),
    ]
