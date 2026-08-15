from django.db import migrations, models

import config.public_urls


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0020_catalogsyncrun_legacy_defaults'),
    ]

    operations = [
        migrations.AddField(
            model_name='series',
            name='download_links',
            field=models.JSONField(
                blank=True,
                default=list,
                validators=[config.public_urls.validate_download_links],
                verbose_name='Download links',
            ),
        ),
    ]
