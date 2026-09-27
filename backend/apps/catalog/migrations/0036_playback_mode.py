"""Record what testing a title's playback source actually proved.

``video_url`` has always been chosen by reading the file name, so the catalog
could never distinguish "this plays" from "this was the best-looking name in
the list". These two fields hold the answer :mod:`apps.catalog.playback_gate`
measures, and let the API tell the player up front when a source needs the
gateway's HLS rewrap instead of letting it find out by failing.

Both default to ``unverified``, so every existing row keeps behaving exactly as
it does today until the sweep reaches it. ``playback_checked_at`` is the
sweep's resume cursor — oldest first over ~76,000 targets.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0035_report_problem_buttons'),
    ]

    operations = [
        migrations.AddField(
            model_name='movie',
            name='playback_mode',
            field=models.CharField(
                choices=[
                    ('direct', 'Plays directly'),
                    ('gateway', 'Needs gateway'),
                    ('unverified', 'Not verified'),
                    ('none', 'No playable source'),
                ],
                db_index=True, default='unverified', max_length=16,
                verbose_name='Playback mode',
            ),
        ),
        migrations.AddField(
            model_name='movie',
            name='playback_checked_at',
            field=models.DateTimeField(
                blank=True, db_index=True, null=True, verbose_name='Playback checked at',
            ),
        ),
        migrations.AddField(
            model_name='episode',
            name='playback_mode',
            field=models.CharField(
                choices=[
                    ('direct', 'Plays directly'),
                    ('gateway', 'Needs gateway'),
                    ('unverified', 'Not verified'),
                    ('none', 'No playable source'),
                ],
                db_index=True, default='unverified', max_length=16,
                verbose_name='Playback mode',
            ),
        ),
        migrations.AddField(
            model_name='episode',
            name='playback_checked_at',
            field=models.DateTimeField(
                blank=True, db_index=True, null=True, verbose_name='Playback checked at',
            ),
        ),
    ]
