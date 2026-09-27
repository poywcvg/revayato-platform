from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0038_imdb_chart_entry'),
    ]

    operations = [
        migrations.CreateModel(
            name='CatalogSlugAlias',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('movie', 'Movie'), ('series', 'Series')], max_length=16)),
                ('old_slug', models.SlugField(allow_unicode=True, max_length=280)),
                ('object_id', models.PositiveIntegerField(db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Catalog slug alias',
                'verbose_name_plural': 'Catalog slug aliases',
                'constraints': [models.UniqueConstraint(fields=('kind', 'old_slug'), name='uniq_catalog_slug_alias')],
            },
        ),
    ]
