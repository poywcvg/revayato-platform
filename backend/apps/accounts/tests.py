from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
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

    def test_rotated_refresh_token_is_labelled_for_client_side_retry(self):
        """A lost rotation race must be distinguishable from a dead session.

        Two tabs (or a retried request) can send the same refresh token; the
        loser gets 401 even though the winner already stored a newer token. The
        ``refresh_token_rotated`` code tells the client to retry with that one
        instead of concluding the user logged out — guessing wrong there is what
        ended live sessions.
        """
        refresh = self.login().data['refresh']
        rotated = self.client.post('/api/auth/token/refresh/', {'refresh': refresh}, format='json')
        self.assertEqual(rotated.status_code, status.HTTP_200_OK)

        replay = self.client.post('/api/auth/token/refresh/', {'refresh': refresh}, format='json')
        self.assertEqual(replay.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(replay.data.get('code'), 'refresh_token_rotated')

        forged = self.client.post('/api/auth/token/refresh/', {'refresh': 'definitely-invalid'}, format='json')
        self.assertEqual(forged.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(forged.data.get('code'), 'token_not_valid')

    def test_token_refresh_uses_its_own_throttle_bucket(self):
        """Refresh must not share the anonymous throttle scope.

        Every returning tab refreshes, and SSR refreshes all arrive from the one
        frontend-container IP. On the shared anon bucket a busy hour answered 429
        and clients treated a perfectly valid session as dead.
        """
        from django.urls import resolve

        from apps.accounts.api import SessionTokenRefreshView, TokenRefreshRateThrottle

        self.assertIs(resolve('/api/auth/token/refresh/').func.cls, SessionTokenRefreshView)
        self.assertEqual(SessionTokenRefreshView.throttle_classes, [TokenRefreshRateThrottle])
        self.assertEqual(TokenRefreshRateThrottle.scope, 'token_refresh')
        throttle = TokenRefreshRateThrottle()
        self.assertGreater(throttle.num_requests / throttle.duration, 1)

    def test_a_long_chain_of_rotations_keeps_the_session_alive(self):
        """The session survives far more rotations than one hour's worth.

        A signed-in browser rotates on every access-token expiry, so the chain
        has to keep answering 200 — one 429 or 401 in the middle is a logout.
        """
        refresh = self.login().data['refresh']
        for step in range(12):
            response = self.client.post('/api/auth/token/refresh/', {'refresh': refresh}, format='json')
            self.assertEqual(
                response.status_code, status.HTTP_200_OK,
                f'rotation {step} failed with {response.status_code}: {response.data}',
            )
            self.assertIn('access', response.data)
            refresh = response.data['refresh']

    def test_rotation_check_matches_on_the_indexed_jti(self):
        """The rotated-token lookup must not scan the whole token table.

        Every rotation adds a row and nothing expires for 400 days, so matching
        the raw JWT against the unindexed ``OutstandingToken.token`` text column
        turns a live session's race recovery into a sequential scan over every
        token ever issued. ``jti`` is unique, hence indexed.
        """
        from apps.accounts.api import _refresh_token_is_rotated

        refresh = self.login().data['refresh']
        self.assertFalse(_refresh_token_is_rotated(refresh))

        rotated = self.client.post('/api/auth/token/refresh/', {'refresh': refresh}, format='json')
        self.assertEqual(rotated.status_code, status.HTTP_200_OK)
        self.assertTrue(_refresh_token_is_rotated(refresh))
        self.assertFalse(_refresh_token_is_rotated(rotated.data['refresh']))
        # Unreadable input is simply "not rotated", never an exception.
        self.assertFalse(_refresh_token_is_rotated('definitely-invalid'))
        self.assertFalse(_refresh_token_is_rotated(None))

        with self.assertNumQueries(1):
            _refresh_token_is_rotated(refresh)
        query = str(BlacklistedToken.objects.filter(token__jti='x').query)
        self.assertIn('jti', query)

    def test_expired_tokens_are_flushed_without_touching_live_sessions(self):
        """Housekeeping must shrink the table but never end a valid session."""
        from apps.accounts.tasks import flush_expired_tokens_task

        live_refresh = self.login().data['refresh']
        stale = OutstandingToken.objects.create(
            user=self.user,
            jti='expired-jti-for-test',
            token='expired.token.value',
            created_at=timezone.now() - timedelta(days=401),
            expires_at=timezone.now() - timedelta(days=1),
        )
        BlacklistedToken.objects.create(token=stale)

        result = flush_expired_tokens_task()

        self.assertEqual(result['deleted'], 1)
        self.assertFalse(OutstandingToken.objects.filter(pk=stale.pk).exists())
        # The cascade removes the blacklist row with it.
        self.assertFalse(BlacklistedToken.objects.filter(token_id=stale.pk).exists())
        # The live session still refreshes.
        response = self.client.post('/api/auth/token/refresh/', {'refresh': live_refresh}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_expired_token_flush_is_scheduled(self):
        """Unswept blacklist growth eventually slows every refresh."""
        from django.conf import settings as django_settings

        entry = django_settings.CELERY_BEAT_SCHEDULE.get('accounts-flush-expired-tokens')
        self.assertIsNotNone(entry, 'expired-token flush must run on beat')
        self.assertEqual(entry['task'], 'apps.accounts.tasks.flush_expired_tokens_task')

    def assertSessionCookies(self, response):
        """The browser's session arrived as Set-Cookie, not as JSON for scripts.

        Safari's ITP caps script-written cookies at seven days regardless of the
        Max-Age requested, so a refresh token the page wrote itself died after a
        week and iOS visitors came back logged out with most of the year left.
        Only a cookie delivered in a response header keeps the full window — and
        HttpOnly means an XSS bug cannot read the one credential that mints
        sessions.
        """
        refresh_cookie = response.cookies.get('refresh_token')
        self.assertIsNotNone(refresh_cookie, 'API must issue the refresh cookie itself')
        self.assertTrue(refresh_cookie['httponly'])
        self.assertEqual(refresh_cookie['samesite'], 'Lax')
        self.assertGreaterEqual(int(refresh_cookie['max-age']), 399 * 24 * 60 * 60)

        flag_cookie = response.cookies.get('has_session')
        self.assertIsNotNone(flag_cookie, 'the page needs a readable "signed in" marker')
        self.assertFalse(flag_cookie['httponly'])
        self.assertEqual(flag_cookie.value, '1')
        self.assertGreaterEqual(int(flag_cookie['max-age']), 399 * 24 * 60 * 60)
        return refresh_cookie.value

    def test_login_and_register_deliver_the_session_as_cookies(self):
        cookie_refresh = self.assertSessionCookies(self.login())
        self.assertEqual(cookie_refresh, self.login().data['refresh'] and cookie_refresh)

        registered = self.client.post('/api/auth/register/', {
            'email': 'cookie@example.com',
            'username': 'cookieviewer',
            'password': 'SafeCinema42!',
        }, format='json')
        self.assertEqual(registered.status_code, status.HTTP_201_CREATED)
        self.assertSessionCookies(registered)

    def test_refresh_works_from_the_cookie_alone(self):
        """A browser sends no token at all — the HttpOnly cookie authorises it."""
        self.assertSessionCookies(self.login())

        rotated = self.client.post('/api/auth/token/refresh/', {}, format='json')

        self.assertEqual(rotated.status_code, status.HTTP_200_OK)
        self.assertIn('access', rotated.data)
        # The rotated refresh must stay in the cookie: handing it to page scripts
        # is what the HttpOnly cookie exists to prevent.
        self.assertNotIn('refresh', rotated.data)
        self.assertSessionCookies(rotated)
        # And the session keeps rotating from the cookie, indefinitely.
        for step in range(5):
            again = self.client.post('/api/auth/token/refresh/', {}, format='json')
            self.assertEqual(again.status_code, status.HTTP_200_OK, f'cookie rotation {step} failed')

    def test_refresh_still_serves_body_clients_unchanged(self):
        """The native app posts the token and still gets one back."""
        refresh = self.login().data['refresh']
        self.client.cookies.clear()

        rotated = self.client.post('/api/auth/token/refresh/', {'refresh': refresh}, format='json')

        self.assertEqual(rotated.status_code, status.HTTP_200_OK)
        self.assertIn('access', rotated.data)
        self.assertIn('refresh', rotated.data)
        self.assertNotEqual(rotated.data['refresh'], refresh)

    def test_a_dead_cookie_is_retired_but_a_raced_one_is_not(self):
        """Clearing cookies on the wrong 401 is what ended live sessions."""
        first = self.login().data['refresh']
        self.assertEqual(
            self.client.post('/api/auth/token/refresh/', {'refresh': first}, format='json').status_code,
            status.HTTP_200_OK,
        )

        # The cookie still holds the token another tab already rotated: a race,
        # not a logout. The browser's cookie must survive so the retry can win.
        self.client.cookies['refresh_token'] = first
        raced = self.client.post('/api/auth/token/refresh/', {}, format='json')
        self.assertEqual(raced.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(raced.data.get('code'), 'refresh_token_rotated')
        self.assertNotIn('refresh_token', raced.cookies)

        # A forged or long-expired token proves the session is over.
        self.client.cookies['refresh_token'] = 'definitely-invalid'
        dead = self.client.post('/api/auth/token/refresh/', {}, format='json')
        self.assertEqual(dead.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(dead.data.get('code'), 'token_not_valid')
        self.assertEqual(dead.cookies['refresh_token'].value, '')
        self.assertEqual(dead.cookies['has_session'].value, '')

    def test_refresh_without_any_token_is_401_not_400(self):
        """One status for "no usable session", so clients need one code path."""
        response = self.client.post('/api/auth/token/refresh/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data.get('code'), 'token_not_valid')

    def test_logout_ends_the_cookie_session_without_a_body(self):
        """The page cannot read the token it needs revoked; the cookie carries it."""
        self.assertSessionCookies(self.login())

        logged_out = self.client.post('/api/auth/logout/', {}, format='json')

        self.assertEqual(logged_out.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(logged_out.cookies['refresh_token'].value, '')
        self.assertEqual(logged_out.cookies['has_session'].value, '')
        # The token itself is blacklisted, so a stolen copy is useless too.
        replay = self.client.post('/api/auth/token/refresh/', {}, format='json')
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
