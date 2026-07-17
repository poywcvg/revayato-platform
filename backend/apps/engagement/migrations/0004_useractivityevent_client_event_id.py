from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('engagement', '0003_alter_useractivityevent_action'),
    ]

    operations = [
        migrations.AddField(
            model_name='useractivityevent',
            name='client_event_id',
            field=models.CharField(blank=True, max_length=100, null=True, unique=True),
        ),
    ]
