from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0018_movie_download_links'),
    ]

    operations = [
        migrations.AddField(
            model_name='actor',
            name='original_name',
            field=models.CharField(blank=True, db_index=True, max_length=255, verbose_name='Original name'),
        ),
        migrations.AddField(
            model_name='director',
            name='original_name',
            field=models.CharField(blank=True, db_index=True, max_length=255, verbose_name='Original name'),
        ),
    ]
