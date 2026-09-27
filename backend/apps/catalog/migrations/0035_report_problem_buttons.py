"""Split the coarse «گزارش خطا» problem types into the precise buttons.

``subtitle`` meant "missing", "out of sync" and "mojibake" at once — three
unrelated repairs behind one word — and ``audio`` had no repair at all. The new
values each name exactly one fix in ``apps.catalog.content_remediation``.

Choices-only, so no data migration: the retired spellings stay valid choices and
existing rows keep validating, while intake normalizes new reports off them.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0034_mediacheck'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contentissuereport',
            name='problem_type',
            field=models.CharField(
                choices=[
                    ('playback', 'Will not play at all'),
                    ('buffering', 'Stalls / buffers constantly'),
                    ('audio_silent', 'Picture but no sound'),
                    ('audio_desync', 'Audio out of sync with picture'),
                    ('subtitle_missing', 'No subtitle available'),
                    ('subtitle_sync', 'Subtitle out of sync'),
                    ('subtitle_garbled', 'Subtitle garbled / wrong text'),
                    ('wrong_title', 'Wrong film / mismatched title'),
                    ('wrong_episode', 'Wrong episode placed'),
                    ('quality', 'Picture quality far below the label'),
                    ('download_dead', 'Download link does not work'),
                    ('other', 'Other'),
                    ('subtitle', 'Subtitle problem (legacy)'),
                    ('audio', 'Audio problem (legacy)'),
                ],
                db_index=True,
                max_length=20,
            ),
        ),
    ]
