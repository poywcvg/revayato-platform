from django.db import migrations


DEPRECATED_PROVIDER_SLUGS = ('donyayeserial', 'serialblog')


def deactivate_removed_providers(apps, schema_editor):
    ProviderSource = apps.get_model('catalog', 'ProviderSource')
    ProviderSource.objects.filter(slug__in=DEPRECATED_PROVIDER_SLUGS).update(is_active=False)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0024_playback_subtitle_gap'),
    ]

    operations = [
        migrations.RunPython(deactivate_removed_providers, noop_reverse),
    ]
