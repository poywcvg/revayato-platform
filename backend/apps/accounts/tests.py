from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from config.client_ip import client_ip


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

    def login(self, password=None, *, login=None):
        return self.client.post('/api/auth/token/', {
            'login': login or self.user.email,
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

    def test_login_accepts_username_as_well_as_email(self):
        by_username = self.login(login=self.user.username)
        self.assertEqual(by_username.status_code, status.HTTP_200_OK)
        self.assertEqual(by_username.data['user']['username'], self.user.username)

        missing = self.login(login='nobody-here')
        self.assertEqual(missing.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(missing.data['code'], 'user_not_found')

    def test_unauthenticated_error_explains_what_user_should_do(self):
        response = self.client.get('/api/accounts/me/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('detail', response.data)
        self.assertIn('hint', response.data)

    def test_authenticated_user_can_update_profile(self):
        login_response = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}")

        response = self.client.patch('/api/accounts/me/', {
            'bio': 'علاقه‌مند به سینمای مستقل و داستان‌های شخصیت‌محور',
            'preferred_language': 'fa',
            'avatar': None,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['profile']['preferred_language'], 'fa')
        self.assertIn('سینمای مستقل', response.data['profile']['bio'])
        self.assertIsNone(response.data['profile']['avatar'])

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

    def test_registration_rejects_non_english_or_spaced_username(self):
        persian = self.client.post('/api/auth/register/', {
            'email': 'fa@example.com',
            'username': 'کاربرجدید',
            'password': 'AnotherSafe42!',
        }, format='json')
        self.assertEqual(persian.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', persian.data)

        spaced = self.client.post('/api/auth/register/', {
            'email': 'space@example.com',
            'username': 'new viewer',
            'password': 'AnotherSafe42!',
        }, format='json')
        self.assertEqual(spaced.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', spaced.data)

    def test_registration_keeps_exact_username_and_rejects_taken_name(self):
        exact = self.client.post('/api/auth/register/', {
            'email': 'exact@example.com',
            'username': 'My_User-01',
            'password': 'AnotherSafe42!',
        }, format='json')
        self.assertEqual(exact.status_code, status.HTTP_201_CREATED)
        self.assertEqual(exact.data['user']['username'], 'My_User-01')

        duplicate = self.client.post('/api/auth/register/', {
            'email': 'other@example.com',
            'username': 'my_user-01',
            'password': 'AnotherSafe42!',
        }, format='json')
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', duplicate.data)
        self.assertIn('گرفته شده', str(duplicate.data['username']))

    def test_logout_blacklists_refresh_token(self):
        login_response = self.login()
        refresh = login_response.data['refresh']

        response = self.client.post('/api/auth/logout/', {'refresh': refresh}, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        refresh_response = self.client.post('/api/auth/token/refresh/', {'refresh': refresh}, format='json')
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_with_invalid_token_returns_401_not_500(self):
        """A malformed or revoked refresh token must never crash as a 500.

        Regression for the missing TokenRefreshView import: previously the
        lenient refresh view raised NameError → the server returned 500, which
        the native/web clients treat as transient and retry forever instead of
        clearing the dead session.
        """
        for bad in [
            # Well-formed JWT with a bogus signature/payload.
            'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6OTk5OTk5OTk5OX0.not-a-real-signature',
            # Garbage that is not a JWT at all.
            'definitely-invalid',
        ]:
            response = self.client.post('/api/auth/token/refresh/', {'refresh': bad}, format='json')
            self.assertNotEqual(
                response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR,
                f'expected non-500 for refresh {bad!r}, got {response.status_code}',
            )
            self.assertEqual(
                response.status_code, status.HTTP_401_UNAUTHORIZED,
                f'expected 401 for refresh {bad!r}, got {response.status_code}',
            )

    def test_refresh_token_has_persistent_rotating_lifetime(self):
        login_response = self.login()
        refresh = login_response.data['refresh']
        token = RefreshToken(refresh)

        self.assertGreaterEqual(token['exp'] - token['iat'], 399 * 24 * 60 * 60)

        rotated = self.client.post('/api/auth/token/refresh/', {'refresh': refresh}, format='json')
        self.assertEqual(rotated.status_code, status.HTTP_200_OK)
        self.assertIn('refresh', rotated.data)
        self.assertNotEqual(rotated.data['refresh'], refresh)

        replay = self.client.post('/api/auth/token/refresh/', {'refresh': refresh}, format='json')
        self.assertEqual(replay.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_password_reset_request_does_not_reveal_account_existence(self):
        known = self.client.post('/api/auth/password-reset/', {'email': self.user.email}, format='json')
        unknown = self.client.post('/api/auth/password-reset/', {'email': 'missing@example.com'}, format='json')

        self.assertEqual(known.status_code, status.HTTP_200_OK)
        self.assertEqual(unknown.status_code, status.HTTP_200_OK)
        self.assertEqual(known.data['detail'], unknown.data['detail'])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/auth/reset-password?uid=', mail.outbox[0].body)

    def test_valid_reset_token_changes_password_and_clears_lock(self):
        refresh = self.login().data['refresh']
        self.user.refresh_from_db()
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

        refresh_response = self.client.post('/api/auth/token/refresh/', {'refresh': refresh}, format='json')
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_reset_token_explains_next_step(self):
        response = self.client.post('/api/auth/password-reset/confirm/', {
            'uid': urlsafe_base64_encode(force_bytes(self.user.pk)),
            'token': 'invalid-token',
            'password': 'FreshCinema42!',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'invalid_reset_link')
        self.assertIn('hint', response.data)

    def test_client_ip_uses_cloudflare_connecting_ip_over_spoofed_header(self):
        """A client cannot spoof its IP to bypass throttling."""
        request = type('R', (), {
            'META': {
                'REMOTE_ADDR': '172.64.99.5',  # Cloudflare edge
                'HTTP_TRUE_CLIENT_IP': '1.2.3.4',  # forged by client
                'HTTP_CF_CONNECTING_IP': '89.161.100.5',  # set by Cloudflare
            },
        })()
        self.assertEqual(client_ip(request), '89.161.100.5')

    def test_client_ip_falls_back_to_rewritten_remote_addr(self):
        """uvicorn may rewrite REMOTE_ADDR when the peer is a trusted proxy."""
        request = type('R', (), {'META': {'REMOTE_ADDR': '89.161.100.5'}})()
        self.assertEqual(client_ip(request), '89.161.100.5')

    def test_login_throttle_is_keyed_per_client_ip_not_proxy(self):
        """Repeated login failures from distinct IPs never exhaust one bucket."""
        # The same account still locks after 5 failures (account lockout), so
        # use a fresh user for each batch and stay under the lock threshold to
        # isolate the IP-keyed throttle from the account lock.
        User.all_objects.filter(email__startswith='throttle').delete()
        for attempt in range(15):
            user = User.objects.create_user(
                email=f'throttle{attempt}@example.com',
                username=f'throttle{attempt}',
                password=self.password,
            )
            response = self.client.post(
                '/api/auth/token/',
                {'login': user.email, 'password': 'WrongPassword42!'},
                format='json',
                REMOTE_ADDR='172.64.99.5',
                HTTP_CF_CONNECTING_IP=f'89.161.100.{attempt + 1}',
            )
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED,
                             f'attempt {attempt + 1} was throttled')

    def test_register_throttle_fires_per_client_ip(self):
        """Registration is rate limited per trusted client IP (5/hour)."""
        # The same IP must be throttled to 429 after the allowed number of
        # registrations.
        statuses = []
        for attempt in range(6):
            response = self.client.post(
                '/api/auth/register/',
                {
                    'email': f'throttled-register{attempt}@example.com',
                    'username': f'throttled-register{attempt}',
                    'password': 'AnotherSafe42!',
                },
                format='json',
                REMOTE_ADDR='172.64.99.5',
                HTTP_CF_CONNECTING_IP='89.161.100.77',
            )
            statuses.append(response.status_code)
        # The extra request past the 5/hour allowance must be throttled.
        self.assertEqual(statuses[-1], status.HTTP_429_TOO_MANY_REQUESTS,
                         f'register throttle did not fire: {statuses}')

    def test_login_throttle_still_triggers_for_single_client(self):
        """The same client IP is still rate limited (spoofed XFF cannot help)."""
        # 5 account failures lock the account (423) before 10/min throttle (429)
        # fires, so expect the 423 lockout which is itself a valid abuse stop.
        statuses = []
        for attempt in range(12):
            response = self.client.post(
                '/api/auth/token/',
                {'login': self.user.email, 'password': 'WrongPassword42!'},
                format='json',
                REMOTE_ADDR='172.64.99.5',
                HTTP_CF_CONNECTING_IP='89.161.100.5',
                HTTP_X_FORWARDED_FOR='6.6.6.6',
            )
            statuses.append(response.status_code)
        # Layered defense: 401 (wrong password) → 423 (account lock after 5
        # fails) → finally 429 (per-IP login throttle). The final status is
        # throttle (429), which proves the throttle fires on the trusted IP and
        # that a spoofed XFF header does not reset the bucket between attempts.
        self.assertEqual(statuses[-1], status.HTTP_429_TOO_MANY_REQUESTS,
                         f'expected throttle after lock; got {statuses}')
        self.assertIn(status.HTTP_423_LOCKED, statuses, f'account never locked: {statuses}')
