"""Staff user-management API tests."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()


class AdminUsersApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            email='users-staff@example.com',
            username='users-staff',
            password='test-pass-123',
            is_staff=True,
            is_superuser=True,
        )
        self.member = User.objects.create_user(
            email='users-member@example.com',
            username='users-member',
            password='test-pass-123',
            is_staff=False,
        )

    def test_non_staff_denied(self):
        self.client.force_authenticate(self.member)
        response = self.client.get('/api/admin/users/')
        self.assertEqual(response.status_code, 403)

    def test_list_and_create_and_update(self):
        self.client.force_authenticate(self.staff)
        listed = self.client.get('/api/admin/users/', {'q': 'users-member'})
        self.assertEqual(listed.status_code, 200)
        self.assertGreaterEqual(listed.data['count'], 1)

        created = self.client.post(
            '/api/admin/users/',
            {
                'email': 'new-admin@example.com',
                'username': 'new-admin',
                'password': 'secure-pass-123',
                'is_staff': True,
                'is_active': True,
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201)
        user_id = created.data['id']
        self.assertTrue(created.data['is_staff'])

        updated = self.client.patch(
            f'/api/admin/users/{user_id}/',
            {'is_active': False},
            format='json',
        )
        self.assertEqual(updated.status_code, 200)
        self.assertFalse(updated.data['is_active'])

    def test_cannot_demote_self(self):
        self.client.force_authenticate(self.staff)
        response = self.client.patch(
            f'/api/admin/users/{self.staff.id}/',
            {'is_staff': False},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'cannot_demote_self')

    def test_create_rejects_non_english_username(self):
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            '/api/admin/users/',
            {
                'email': 'fa-admin@example.com',
                'username': 'ادمین',
                'password': 'secure-pass-123',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('username', response.data)
