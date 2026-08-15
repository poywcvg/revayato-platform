from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.catalog.models import Series
from apps.catalog.serializers import AdminSeriesSerializer


class AdminSeriesAvailabilitySyncTests(TestCase):
    def setUp(self):
        self.series = Series.objects.create(
            title='Test Series',
            slug='test-series',
            is_dubbed=False,
            has_subtitle=False,
        )

    def test_admin_serializer_derives_flags_from_download_links(self):
        serializer = AdminSeriesSerializer(
            self.series,
            data={
                'download_links': [
                    {'label': '1080p Dub', 'url': 'https://cdn.example/d.mp4', 'kind': 'dubbed'},
                    {'label': '720 SoftSub', 'url': 'https://cdn.example/s.mp4', 'kind': 'softsub'},
                ],
            },
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        series = serializer.save()
        self.assertTrue(series.is_dubbed)
        self.assertTrue(series.has_subtitle)
        self.assertTrue(series.has_downloads)
        self.assertEqual(len(series.download_qualities), 2)

    def test_series_save_keeps_flags_honest(self):
        self.series.download_links = [
            {'label': 'دوبله', 'url': 'https://cdn.example/dub.mp4', 'kind': 'dubbed'},
        ]
        self.series.save()
        self.series.refresh_from_db()
        self.assertTrue(self.series.is_dubbed)
        self.assertFalse(self.series.has_subtitle)


class AdminSeriesApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            username='series-admin',
            email='series-admin@example.com',
            password='pass12345',
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        self.series = Series.objects.create(
            title='Public Series',
            slug='public-series',
            is_published=True,
            download_links=[
                {'label': 'SoftSub 1080', 'url': 'https://cdn.example/soft.mp4', 'kind': 'softsub'},
            ],
        )
        # Ensure flags match links after create.
        self.series.save()

    def test_admin_series_list_includes_availability_flags(self):
        response = self.client.get('/api/admin/series/')
        self.assertEqual(response.status_code, 200)
        results = response.data['results']
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertTrue(row['has_subtitle'])
        self.assertFalse(row['is_dubbed'])
        self.assertTrue(row['has_downloads'])

    def test_admin_series_patch_updates_links_and_flags(self):
        response = self.client.patch(
            f'/api/admin/series/{self.series.id}/',
            {
                'download_links': [
                    {'label': 'Dub 720', 'url': 'https://cdn.example/dub.mp4', 'kind': 'dubbed'},
                ],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['is_dubbed'])
        self.assertFalse(response.data['has_subtitle'])
        self.series.refresh_from_db()
        self.assertTrue(self.series.is_dubbed)
