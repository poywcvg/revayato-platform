from urllib.parse import urlsplit

from django.db import migrations, models
import config.public_urls


MEDIA_FIELDS = {
    'Actor': ('photo',),
    'Director': ('photo',),
    'Movie': ('video_url', 'trailer_url'),
    'Series': ('trailer_url',),
    'Episode': ('video_url', 'trailer_url'),
}

MEDIA_FIELDS['Movie'] += ('poster', 'backdrop')
MEDIA_FIELDS['Series'] += ('poster', 'backdrop')
MEDIA_FIELDS['Season'] = ('poster',)
MEDIA_FIELDS['Episode'] += ('poster',)


def as_object_key(value):
    value = (value or '').strip()
    if not value:
        return ''
    parsed = urlsplit(value)
    was_absolute = bool(parsed.scheme or parsed.netloc)
    if was_absolute:
        value = parsed.path
    key = value.split('?', 1)[0].lstrip('/')
    if was_absolute and key.startswith('media/'):
        key = key[len('media/'):]
    return key


def normalize_catalog_media_keys(apps, schema_editor):
    for model_name, fields in MEDIA_FIELDS.items():
        model = apps.get_model('catalog', model_name)
        for obj in model.objects.all().only('pk', *fields):
            updates = {field: as_object_key(getattr(obj, field)) for field in fields}
            if any(getattr(obj, field) != value for field, value in updates.items()):
                model.objects.filter(pk=obj.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [('catalog', '0004_seed_complete_genres')]

    operations = [
        migrations.AlterField(
            model_name='movie', name='trailer_url',
            field=models.CharField(blank=True, max_length=500, validators=[config.public_urls.validate_object_key], verbose_name='Trailer object key'),
        ),
        migrations.AlterField(
            model_name='movie', name='video_url',
            field=models.CharField(blank=True, max_length=500, validators=[config.public_urls.validate_object_key], verbose_name='HLS manifest object key'),
        ),
        migrations.AlterField(
            model_name='series', name='trailer_url',
            field=models.CharField(blank=True, max_length=500, validators=[config.public_urls.validate_object_key], verbose_name='Trailer object key'),
        ),
        migrations.AlterField(
            model_name='episode', name='video_url',
            field=models.CharField(blank=True, max_length=500, validators=[config.public_urls.validate_object_key], verbose_name='HLS manifest object key'),
        ),
        migrations.AlterField(
            model_name='episode', name='trailer_url',
            field=models.CharField(blank=True, max_length=500, validators=[config.public_urls.validate_object_key], verbose_name='Trailer object key'),
        ),
        migrations.RunPython(normalize_catalog_media_keys, migrations.RunPython.noop),
    ]
