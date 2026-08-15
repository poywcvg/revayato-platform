from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0012_reconcile_importer_and_sync_schema'),
    ]

    operations = [
        migrations.AddField(
            model_name='catalogimportersettings',
            name='cast_import_limit',
            field=models.PositiveSmallIntegerField(
                default=15,
                help_text='Maximum number of cast members imported per title (1–50).',
                validators=[MinValueValidator(1), MaxValueValidator(50)],
                verbose_name='Cast import limit',
            ),
        ),
    ]
