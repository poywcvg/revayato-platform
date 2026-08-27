import os
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import update_last_login
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.exceptions import InvalidToken, TokenBackendError, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Profile
from .serializers import (
    LoginSerializer,
    MeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileSerializer,
    RegisterSerializer,
)

User = get_user_model()
MAX_FAILED_LOGIN_ATTEMPTS = 5
LOGIN_LOCK_MINUTES = 15

# Per-endpoint auth throttles. ScopedRateThrottle lets us key the bucket on the
# trusted client IP (config.client_ip.client_ip) instead of REMOTE_ADDR, which
# Uvicorn rewrites from X-Forwarded-For. All real users behind one shared CDN
# egress still get their own bucket, so VPN off/on no longer exhausts a single
# global rate limit. Rates are tuned here and read from settings below.
AUTH_LOGIN_RATE = os.environ.get('AUTH_LOGIN_RATE', '10/minute')
AUTH_REGISTER_RATE = os.environ.get('AUTH_REGISTER_RATE', '5/hour')
AUTH_PASSWORD_RESET_RATE = os.environ.get('AUTH_PASSWORD_RESET_RATE', '5/hour')
# Token refresh is how a signed-in browser stays signed in: every access token
# expiry, every cold tab and every returning visit calls it. On the shared
# anonymous bucket (100/hour) it competed with public traffic from the same CDN
# egress, so a busy hour answered 429 and clients treated a live session as
# dead. It gets its own bucket instead, sized like the catalog scope: SSR
# refreshes arrive through the frontend container, where every visitor shares a
# single client IP.
AUTH_TOKEN_REFRESH_RATE = os.environ.get('AUTH_TOKEN_REFRESH_RATE', '600/minute')

# Session cookies the *server* owns.
#
# The refresh token used to be written by JavaScript, which Safari's ITP caps at
# seven days regardless of the Max-Age asked for — so an iOS visitor who stayed
# away longer than a week came back logged out even though the session had 400
# days left. A cookie delivered through Set-Cookie is not subject to that cap,
# so the browser copy of the refresh token is now issued (and rotated) here.
#
# HttpOnly is the other half: script on the page can no longer read the one
# credential that can mint new sessions, so an XSS bug cannot walk away with a
# 400-day login.
REFRESH_COOKIE_NAME = 'refresh_token'
# JS *does* need to know a session exists — the access token expires hourly and
# the client has to decide whether to rotate or render as a guest. This flag
# carries no credential, only the answer to "is someone signed in here".
SESSION_FLAG_COOKIE_NAME = 'has_session'
# Chromium clamps persistent cookies to 400 days; asking for more is silently
# truncated, so match it and let rotation push the window forward.
MAX_BROWSER_COOKIE_DAYS = 400


def _session_cookie_max_age():
    days = min(getattr(settings, 'JWT_REFRESH_TOKEN_DAYS', MAX_BROWSER_COOKIE_DAYS), MAX_BROWSER_COOKIE_DAYS)
    return days * 24 * 60 * 60


def _attach_session_cookies(response, refresh):
    """Hand the browser a fresh 400-day session, server-side."""
    shared = {
        'max_age': _session_cookie_max_age(),
        'path': '/',
        'samesite': 'Lax',
        # Lax already keeps the cookie off cross-site POSTs, which is what makes
        # a cookie-authorised refresh endpoint safe from CSRF.
        'secure': not settings.DEBUG,
    }
    response.set_cookie(REFRESH_COOKIE_NAME, refresh, httponly=True, **shared)
    response.set_cookie(SESSION_FLAG_COOKIE_NAME, '1', httponly=False, **shared)
    return response


def _clear_session_cookies(response):
    for name in (REFRESH_COOKIE_NAME, SESSION_FLAG_COOKIE_NAME):
        response.delete_cookie(name, path='/', samesite='Lax')
    return response



class AuthClientRateThrottle(SimpleRateThrottle):
    """Auth-throttle base that buckets on the trusted client IP.

    SimpleRateThrottle requires subclasses to implement ``get_cache_key``; this
    implementation keys on ``self.scope`` + ``get_ident`` so a view-level
    ``throttle_scope`` attribute is not needed. DRF's default get_ident() uses
    HTTP_X_FORWARDED_FOR / REMOTE_ADDR, which here equals the Cloudflare edge
    address (Uvicorn trusts proxies). Real users would then share one bucket and
    exhaust the limit together. We override it with the resolved public client
    IP from config.client_ip so each user behind the CDN gets their own bucket —
    and a spoofed forwarded header cannot disable it.
    """

    def get_cache_key(self, request, view):
        if self.scope is None:
            return None
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request),
        }

    def get_ident(self, request):
        return _client_ip(request) or super().get_ident(request)


class LoginRateThrottle(AuthClientRateThrottle):
    scope = 'login'
    rate = AUTH_LOGIN_RATE


class RegisterRateThrottle(AuthClientRateThrottle):
    scope = 'register'
    rate = AUTH_REGISTER_RATE


class PasswordResetRateThrottle(AuthClientRateThrottle):
    scope = 'password_reset'
    rate = AUTH_PASSWORD_RESET_RATE


class TokenRefreshRateThrottle(AuthClientRateThrottle):
    scope = 'token_refresh'
    rate = AUTH_TOKEN_REFRESH_RATE


def _client_ip(request):
    """Trusted client IP; falls back to REMOTE_ADDR only when unknown."""
    try:
        from config.client_ip import client_ip as resolve_client_ip
    except ImportError:  # pragma: no cover - defensive
        return request.META.get('REMOTE_ADDR') or None
    return resolve_client_ip(request) or request.META.get('REMOTE_ADDR') or None


def _token_payload(user):
    refresh = RefreshToken.for_user(user)
    profile, _created = Profile.objects.get_or_create(user=user)
    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': MeSerializer({'user': user, 'profile': profile}).data,
    }


def _refresh_token_is_rotated(raw):
    """True when this exact refresh token was already rotated/revoked.

    ``BlacklistedToken.token`` is a relation to ``OutstandingToken``, so the JWT
    has to be matched through it. Matching on ``token__token`` — the previous
    shape of this helper — compares against an unindexed ``TextField``, i.e. a
    sequential scan of every token this deployment ever issued. With 400-day
    rotation that table only grows, and the scan sits on the path a *live*
    session takes to recover from a lost rotation race. Matching on ``jti``
    instead hits a unique index.

    The ``jti`` is read without verifying the signature: the token is already
    known to be unusable, and nothing is authorised from this answer. It only
    tells the client whether a newer refresh token is worth retrying (both
    outcomes are still 401), so a forged ``jti`` gains an attacker one pointless
    retry against a token they do not have.
    """
    try:
        jti = RefreshToken(raw, verify=False).payload.get('jti')
    except Exception:  # noqa: BLE001 - unreadable token is simply not a rotated one
        return False
    if not jti:
        return False
    try:
        return BlacklistedToken.objects.filter(token__jti=jti).exists()
    except Exception:  # noqa: BLE001 - a DB hiccup must not mask the original error
        return False


class ResilientTokenRefreshSerializer(TokenRefreshSerializer):
    """Refresh serializer that always answers 401 for an unusable token.

    Every refresh failure must look the same to a client: HTTP 401. SimpleJWT
    only converts ``TokenError`` itself, so ``TokenBackendError`` (bad signature)
    and ``TypeError`` (garbage payload) escaped as 500, and a locally raised
    ``ValidationError`` answered 400. Clients then either retried a dead session
    forever or dropped a live one, depending on which shape they got.

    The ``code`` distinguishes the two reasons a token can be refused so the
    client can react instead of guessing:

    * ``refresh_token_rotated`` — this token was already exchanged (a sibling
      tab, or a retried request, won the race). A newer refresh token exists in
      the cookie jar, so the client retries with that one and the session lives.
    * ``token_not_valid`` — expired, revoked or forged. The session is over.
    """

    def validate(self, attrs):
        try:
            return super().validate(attrs)
        except (TokenError, TokenBackendError, TypeError) as exc:
            rotated = _refresh_token_is_rotated(attrs.get('refresh'))
            raise InvalidToken({
                'detail': str(exc) or 'Token is invalid or expired',
                'code': 'refresh_token_rotated' if rotated else 'token_not_valid',
            }) from exc


class SessionTokenRefreshView(TokenRefreshView):
    """Rotating refresh endpoint that keeps a signed-in client signed in.

    Two kinds of caller share it:

    * A browser sends nothing and is authorised by the HttpOnly cookie. The
      rotated token goes straight back into that cookie and never touches the
      response body, so page scripts cannot read it.
    * The native app (and any non-browser client) still posts ``{"refresh": …}``
      and still gets the rotated token in the body, exactly as before.

    Wired at the URL layer (config.urls) so DRF's request lifecycle runs exactly
    once — nesting an APIView inside an @api_view handler would re-enter dispatch
    with a DRF Request and blow up.
    """

    serializer_class = ResilientTokenRefreshSerializer
    throttle_classes = [TokenRefreshRateThrottle]

    def post(self, request, *args, **kwargs):
        presented = request.data.get('refresh') if hasattr(request.data, 'get') else None
        from_cookie = False
        if not presented:
            presented = request.COOKIES.get(REFRESH_COOKIE_NAME)
            from_cookie = bool(presented)

        if not presented:
            # No token anywhere: there is no session to keep alive. Same 401 the
            # invalid case gets, so a client needs only one code path.
            return Response(
                {'detail': 'No refresh token was provided.', 'code': 'token_not_valid'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = self.get_serializer(data={'refresh': presented})
        try:
            serializer.is_valid(raise_exception=True)
        except InvalidToken as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {'detail': exc.detail}
            response = Response(detail, status=status.HTTP_401_UNAUTHORIZED)
            # A token we know was merely rotated means a newer one is already in
            # the jar — clearing cookies there would end a live session. Only a
            # genuinely dead token retires the browser's copy.
            if from_cookie and detail.get('code') != 'refresh_token_rotated':
                _clear_session_cookies(response)
            return response

        data = dict(serializer.validated_data)
        rotated = data.get('refresh')
        if from_cookie:
            data.pop('refresh', None)
        response = Response(data, status=status.HTTP_200_OK)
        if rotated:
            _attach_session_cookies(response, rotated)
        return response


token_refresh = SessionTokenRefreshView.as_view()


def _revoke_user_refresh_tokens(user):
    outstanding_tokens = list(
        OutstandingToken.objects.select_for_update()
        .filter(user=user)
    )
    BlacklistedToken.objects.bulk_create(
        [BlacklistedToken(token=token) for token in outstanding_tokens],
        ignore_conflicts=True,
    )


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([LoginRateThrottle])
def login_user(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    identifier = serializer.validated_data['login']
    password = serializer.validated_data['password']

    if '@' in identifier:
        account = User.all_objects.filter(email__iexact=identifier.lower()).first()
    else:
        account = User.all_objects.filter(username__iexact=identifier).first()

    if not account:
        return Response(
            {
                'code': 'user_not_found',
                'detail': 'حسابی با این ایمیل یا نام کاربری پیدا نشد.',
                'hint': 'می‌توانی همین حالا یک حساب تازه بسازی.',
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if account.locked_until and account.locked_until > timezone.now():
        remaining_minutes = max(1, int((account.locked_until - timezone.now()).total_seconds() // 60) + 1)
        return Response(
            {
                'code': 'account_locked',
                'detail': f'ورود این حساب برای {remaining_minutes} دقیقه بسته شده است.',
                'hint': 'کمی صبر کن یا رمز عبورت را بازیابی کن.',
            },
            status=status.HTTP_423_LOCKED,
        )

    if not account.is_active or account.is_deleted:
        return Response(
            {'code': 'account_disabled', 'detail': 'این حساب در حال حاضر فعال نیست.', 'hint': 'با پشتیبانی تماس بگیر.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    user = authenticate(request=request, email=account.email, password=password)
    if not user:
        if account.is_active and not account.is_deleted:
            with transaction.atomic():
                locked_account = User.all_objects.select_for_update().get(pk=account.pk)
                locked_account.failed_login_attempts += 1
                update_fields = ['failed_login_attempts']
                if locked_account.failed_login_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
                    locked_account.locked_until = timezone.now() + timedelta(minutes=LOGIN_LOCK_MINUTES)
                    update_fields.append('locked_until')
                locked_account.save(update_fields=update_fields)
        return Response(
            {
                'code': 'invalid_credentials',
                'detail': 'رمز عبور درست نیست.',
                'hint': 'رمز را دوباره بررسی کن یا از بازیابی رمز عبور استفاده کن.',
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_ip = _client_ip(request)
    user.save(update_fields=['failed_login_attempts', 'locked_until', 'last_login_ip'])
    update_last_login(None, user)
    payload = _token_payload(user)
    return _attach_session_cookies(Response(payload), payload['refresh'])


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([RegisterRateThrottle])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    payload = _token_payload(user)
    return _attach_session_cookies(
        Response(payload, status=status.HTTP_201_CREATED),
        payload['refresh'],
    )


@api_view(['POST'])
@permission_classes([AllowAny])
def logout_user(request):
    # Logging out is the one thing that must always end the session, so accept
    # the token from wherever the caller keeps it — the browser's HttpOnly cookie
    # is unreadable to the page script that triggered this.
    refresh_token = request.data.get('refresh') or request.COOKIES.get(REFRESH_COOKIE_NAME)
    if refresh_token:
        try:
            RefreshToken(refresh_token).blacklist()
        except TokenError:
            pass
    return _clear_session_cookies(Response(status=status.HTTP_204_NO_CONTENT))


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetRateThrottle])
def request_password_reset(request):
    serializer = PasswordResetRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = User.objects.filter(email__iexact=serializer.validated_data['email'], is_active=True).first()

    if user:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        frontend_url = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
        reset_url = f'{frontend_url}/auth/reset-password?uid={uid}&token={token}'
        send_mail(
            subject='بازیابی رمز عبور روایتو',
            message=f'برای ساخت رمز عبور تازه، این لینک را باز کن:\n{reset_url}\n\nاگر این درخواست را نداده‌ای، این پیام را نادیده بگیر.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )

    return Response({
        'detail': 'اگر این ایمیل در سایت ثبت شده باشد، لینک بازیابی برای آن فرستاده می‌شود.',
    })


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetRateThrottle])
def confirm_password_reset(request):
    serializer = PasswordResetConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        user_id = force_str(urlsafe_base64_decode(serializer.validated_data['uid']))
        user = User.objects.get(pk=user_id, is_active=True)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if not user or not default_token_generator.check_token(user, serializer.validated_data['token']):
        return Response(
            {'code': 'invalid_reset_link', 'detail': 'این لینک بازیابی معتبر نیست یا زمان آن گذشته است.', 'hint': 'یک لینک تازه درخواست کن.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        user.set_password(serializer.validated_data['password'])
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save(update_fields=['password', 'failed_login_attempts', 'locked_until'])
        # Password recovery is the user's emergency session-revocation path.
        # Long-lived refresh tokens must not survive a credential reset.
        _revoke_user_refresh_tokens(user)
    return Response({'detail': 'رمز عبور با موفقیت تغییر کرد.'})


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def me(request):
    profile, _created = Profile.objects.get_or_create(user=request.user)

    if request.method == 'PATCH':
        profile_serializer = ProfileSerializer(profile, data=request.data, partial=True)
        profile_serializer.is_valid(raise_exception=True)
        profile_serializer.save()

    return Response(MeSerializer({'user': request.user, 'profile': profile}).data)
