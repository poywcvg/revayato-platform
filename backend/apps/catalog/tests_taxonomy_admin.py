"""Tests for the staff taxonomy CRUD endpoints (apps.catalog.taxonomy_api)."""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Actor, Country, Director, Genre, Tag

User = get_user_model()


class TaxonomyAdminApiTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username='taxonomy-staff',
            email='taxonomy-staff@example.com',
            password='pass12345',
            is_staff=True,
        )
        self.member = User.objects.create_user(
            username='taxonomy-member',
            email='taxonomy-member@example.com',
            password='pass12345',
        )
        # Migration 0004 seeds the standard genre list; use unique test-only rows.
        self.genre_action, _ = Genre.objects.get_or_create(
            title='اکشن تستی', defaults={'slug': 'test-action'},
        )
        Genre.objects.get_or_create(title='درام تستی', defaults={'slug': 'test-drama'})
        Country.objects.create(name='کشور تستی', code='XT')
        Tag.objects.create(name='برچسب تستی', slug='test-tag')
        Actor.objects.create(name='بازیگر نمونه', slug='sample-actor')
        Director.objects.create(name='کارگردان نمونه', slug='sample-director')

    def test_requires_staff(self):
        self.client.force_authenticate(self.member)
        response = self.client.get('/api/admin/genres/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_without_ordering_does_not_crash(self):
        """Regression: default '-updated_at' ordering broke models lacking that field."""
        for url in ['/api/admin/genres/', '/api/admin/countries/', '/api/admin/tags/', '/api/admin/actors/', '/api/admin/directors/']:
            with self.subTest(url=url):
                self.client.force_authenticate(self.staff)
                response = self.client.get(url)
                self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)

    def test_genre_create_update_delete_roundtrip(self):
        self.client.force_authenticate(self.staff)

        created = self.client.post('/api/admin/genres/', {'title': 'کمدی تستی'}, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.content)
        genre_id = created.json()['id']
        self.assertTrue(created.json()['slug'])

        updated = self.client.patch(
            f'/api/admin/genres/{genre_id}/',
            {'description': 'فیلم‌های خنده‌دار'},
            format='json',
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(updated.json()['description'], 'فیلم‌های خنده‌دار')

        deleted = self.client.delete(f'/api/admin/genres/{genre_id}/')
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)

    def test_actor_multipart_create(self):
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            '/api/admin/actors/',
            {'name': 'بازیگر تازه', 'original_name': 'New Actor'},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        body = response.json()
        self.assertEqual(body['name'], 'بازیگر تازه')
        self.assertTrue(Actor.objects.filter(slug=body['slug']).exists())

    def test_delete_blocked_when_referenced(self):
        from apps.catalog.models import Movie

        movie = Movie.objects.create(title='فیلم متصل', slug='linked-movie')
        movie.genres.add(self.genre_action)

        self.client.force_authenticate(self.staff)
        response = self.client.delete(f'/api/admin/genres/{self.genre_action.pk}/')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
