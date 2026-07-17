from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APITestCase


User = get_user_model()


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AuthenticationApiTests(APITestCase):
    password = 'SafeCinema42!'

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email='viewer@example.com',
            username='viewer',
            password=self.password,
        )

    def login(self, password=None):
        return self.client.post('/api/auth/token/', {
            'email': self.user.email,
            'password': password or self.password,
        }, format='json')

    def test_login_returns_tokens_and_safe_user_payload(self):
        response = self.login()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['email'], self.user.email)
        self.assertNotIn('password', response.data['user'])

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        me_response = self.client.get('/api/accounts/me/')
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data['username'], self.user.username)

    def test_unauthenticated_error_explains_what_user_should_do(self):
        response = self.client.get('/api/accounts/me/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('detail', response.data)
        self.assertIn('hint', response.data)

    def test_invalid_login_has_explainable_error_and_temporarily_locks_account(self):
        first_response = self.login('WrongPassword42!')
        self.assertEqual(first_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(first_response.data['code'], 'invalid_credentials')
        self.assertIn('detail', first_response.data)
        self.assertIn('hint', first_response.data)

        for _attempt in range(4):
            self.login('WrongPassword42!')
        locked_response = self.login('WrongPassword42!')

        self.assertEqual(locked_response.status_code, status.HTTP_423_LOCKED)
        self.assertEqual(locked_response.data['code'], 'account_locked')

    def test_registration_validates_password_and_starts_session(self):
        weak_response = self.client.post('/api/auth/register/', {
            'email': 'new@example.com',
            'username': 'newviewer',
            'password': '12345678',
        }, format='json')
        self.assertEqual(weak_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', weak_response.data)

        response = self.client.post('/api/auth/register/', {
            'email': 'new@example.com',
            'username': 'newviewer',
            'password': 'AnotherSafe42!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', response.data)
        self.assertEqual(response.data['user']['username'], 'newviewer')

    def test_logout_blacklists_refresh_token(self):
        login_response = self.login()
        refresh = login_response.data['refresh']

        response = self.client.post('/api/auth/logout/', {'refresh': refresh}, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        refresh_response = self.client.post('/api/auth/token/refresh/', {'refresh': refresh}, format='json')
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_password_reset_request_does_not_reveal_account_existence(self):
        known = self.client.post('/api/auth/password-reset/', {'email': self.user.email}, format='json')
        unknown = self.client.post('/api/auth/password-reset/', {'email': 'missing@example.com'}, format='json')

        self.assertEqual(known.status_code, status.HTTP_200_OK)
        self.assertEqual(unknown.status_code, status.HTTP_200_OK)
        self.assertEqual(known.data['detail'], unknown.data['detail'])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/auth/reset-password?uid=', mail.outbox[0].body)

    def test_valid_reset_token_changes_password_and_clears_lock(self):
        self.user.failed_login_attempts = 5
        self.user.save(update_fields=['failed_login_attempts'])
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        response = self.client.post('/api/auth/password-reset/confirm/', {
            'uid': uid,
            'token': token,
            'password': 'FreshCinema42!',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('FreshCinema42!'))
        self.assertEqual(self.user.failed_login_attempts, 0)
        self.assertIsNone(self.user.locked_until)

    def test_invalid_reset_token_explains_next_step(self):
        response = self.client.post('/api/auth/password-reset/confirm/', {
            'uid': urlsafe_base64_encode(force_bytes(self.user.pk)),
            'token': 'invalid-token',
            'password': 'FreshCinema42!',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'invalid_reset_link')
        self.assertIn('hint', response.data)
