from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0025_deactivate_donyayeserial_serialblog'),
    ]

    operations = [
        migrations.RenameIndex(
            model_name='movie',
            new_name='catalog_mov_is_publ_3081d5_idx',
            old_name='catalog_mov_is_publ_imdb_rk_idx',
        ),
        migrations.RenameIndex(
            model_name='series',
            new_name='catalog_ser_is_publ_71f2b4_idx',
            old_name='catalog_ser_is_publ_imdb_rk_idx',
        ),
        migrations.AlterField(
            model_name='movie',
            name='original_title',
            field=models.CharField(blank=True, max_length=255, verbose_name='English Title'),
        ),
        migrations.AlterField(
            model_name='movie',
            name='title',
            field=models.CharField(db_index=True, max_length=255, verbose_name='Persian Title'),
        ),
        migrations.AlterField(
            model_name='series',
            name='original_title',
            field=models.CharField(blank=True, max_length=255, verbose_name='English Title'),
        ),
        migrations.AlterField(
            model_name='series',
            name='title',
            field=models.CharField(db_index=True, max_length=255, verbose_name='Persian Title'),
        ),
    ]
