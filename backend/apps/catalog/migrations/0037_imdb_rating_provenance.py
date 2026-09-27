"""Make it possible to tell a real IMDb score from a stand-in.

``imdb_rating`` has always been written without recording where it came from,
and with ``OMDB_API_KEY`` unset the only source that ever ran was TMDB's
``vote_average``. Measured against IMDb's own published file on 2026-09-24,
that left 9% of 20,168 rated titles correct and 3,898 off by a point or more —
and nothing on the row said so.

``imdb_rating_source`` is the missing fact: ``imdb`` (exact, from IMDb's daily
dataset), ``omdb``, ``manual`` (an admin typed it, and it outranks everything),
or ``tmdb`` (an approximation the sync is allowed to replace). ``imdb_votes``
carries the vote count behind the score and ``imdb_rating_synced_at`` says when
it was last checked.

All three are nullable/blank, so every existing row keeps its current rating
untouched; the sync fills them in afterwards.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0036_playback_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='movie',
            name='imdb_votes',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Vote count behind imdb_rating, from the same source.',
                null=True,
                verbose_name='IMDb votes',
            ),
        ),
        migrations.AddField(
            model_name='movie',
            name='imdb_rating_source',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text=(
                    'Where imdb_rating came from: imdb (exact, from IMDb’s own dataset), '
                    'omdb, manual (an admin typed it, wins over everything), or tmdb (an '
                    'approximation kept only until the real score is available).'
                ),
                max_length=12,
                verbose_name='IMDb rating source',
            ),
        ),
        migrations.AddField(
            model_name='movie',
            name='imdb_rating_synced_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='IMDb rating synced at'),
        ),
        migrations.AddField(
            model_name='series',
            name='imdb_votes',
            field=models.PositiveIntegerField(
                blank=True,
                help_text='Vote count behind imdb_rating, from the same source.',
                null=True,
                verbose_name='IMDb votes',
            ),
        ),
        migrations.AddField(
            model_name='series',
            name='imdb_rating_source',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text=(
                    'Where imdb_rating came from: imdb (exact, from IMDb’s own dataset), '
                    'omdb, manual (an admin typed it, wins over everything), or tmdb (an '
                    'approximation kept only until the real score is available).'
                ),
                max_length=12,
                verbose_name='IMDb rating source',
            ),
        ),
        migrations.AddField(
            model_name='series',
            name='imdb_rating_synced_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='IMDb rating synced at'),
        ),
    ]
