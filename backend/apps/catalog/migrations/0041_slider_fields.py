# Admin-curated home slider: order + per-platform targeting for movies/series.
# Purely additive columns with safe defaults (order 0, platform "all"), so
# every existing featured title keeps showing exactly where it did.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0040_airing_entry'),
    ]

    operations = [
        migrations.AddField(
            model_name='movie',
            name='featured_order',
            field=models.PositiveIntegerField(db_index=True, default=0, help_text='Lower shows first in the home slider; titles with the same order fall back to recency.', verbose_name='Slider order'),
        ),
        migrations.AddField(
            model_name='movie',
            name='slider_platform',
            field=models.CharField(choices=[('all', 'All platforms'), ('web', 'Website'), ('app', 'Application')], db_index=True, default='all', help_text='Which clients show this title in the home slider.', max_length=8, verbose_name='Slider platform'),
        ),
        migrations.AddField(
            model_name='series',
            name='featured_order',
            field=models.PositiveIntegerField(db_index=True, default=0, help_text='Lower shows first in the home slider; titles with the same order fall back to recency.', verbose_name='Slider order'),
        ),
        migrations.AddField(
            model_name='series',
            name='slider_platform',
            field=models.CharField(choices=[('all', 'All platforms'), ('web', 'Website'), ('app', 'Application')], db_index=True, default='all', help_text='Which clients show this title in the home slider.', max_length=8, verbose_name='Slider platform'),
        ),
    ]
