from django.db import migrations, models

import config.public_urls


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0017_bamabin_provider_m1'),
    ]

    operations = [
        migrations.AddField(
            model_name='movie',
            name='download_links',
            field=models.JSONField(
                blank=True,
                default=list,
                validators=[config.public_urls.validate_download_links],
                verbose_name='Download links',
            ),
        ),
    ]
