from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from .models import Movie, Series


class EnsurePersianDescriptionsCommandTests(TestCase):
    def test_updates_movie_and_series_description_fields(self):
        movie = Movie.objects.create(
            title='فیلم', original_title='Movie', slug='movie-description-fix',
            description='An English movie plot.', short_description='Old',
        )
        series = Series.objects.create(
            title='سریال', original_title='Series', slug='series-description-fix',
            description='An English series plot.', short_description='Old',
        )

        with mock.patch(
            'apps.catalog.management.commands.ensure_persian_descriptions.translate_to_persian',
            side_effect=['خلاصه فارسی فیلم.', 'خلاصه فارسی سریال.'],
        ):
            call_command('ensure_persian_descriptions', sleep=0)

        movie.refresh_from_db()
        series.refresh_from_db()
        self.assertEqual(movie.description, 'خلاصه فارسی فیلم.')
        self.assertEqual(movie.short_description, 'خلاصه فارسی فیلم.')
        self.assertEqual(series.description, 'خلاصه فارسی سریال.')
        self.assertEqual(series.short_description, 'خلاصه فارسی سریال.')
