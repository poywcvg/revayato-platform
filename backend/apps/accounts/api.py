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
from rest_framework import serializers as drf_serializers, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import ValidationError
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


class _RefreshTokenErrorHelper:
    """Static helpers so the lenient serializer reads plainly."""

    @staticmethod
    def _simplejwt_error(exc):
        """Convert a SimpleJWT exception into DRF error detail for the response."""
        message = str(exc) or 'Token is invalid or expired'
        return drf_serializers.ErrorDetail(message, 'token_not_valid')

    @staticmethod
    def _token_is_blacklisted(raw):
        """True when this exact refresh token string is blacklisted (rotated)."""
        try:
            return BlacklistedToken.objects.filter(token=raw).exists()
        except Exception:  # noqa: BLE001 - a DB hiccup must not mask the original error
            return False


class LenientRefreshSerializer(TokenRefreshSerializer):
    """Refresh serializer that tolerates the rotation race across tabs.

    SimpleJWT rotation blacklists a refresh token the moment it is used. A user
    with two browser tabs (or an SSR cold-start racing an open tab) can therefore
    send the SAME token twice: the first request rotates it, the second receives
    "Token is blacklisted" (plain TokenError). That 400 must not end a session
    that is very much alive — the second request simply raced the first. We
    degrade that single specific error to an empty rotation (no new token) and
    let the client fall back to the refresh token a sibling tab already rotated
    to. Everything else (expired, wrong type, bad signature) is a real session
    failure and is still surfaced so the client clears cookies.
    """

    def validate(self, attrs):
        try:
            return super().validate(attrs)
        except (TokenError, TokenBackendError, TypeError) as exc:
            if _RefreshTokenErrorHelper._token_is_blacklisted(attrs.get('refresh')):
                return {}
            raise ValidationError({'detail': _RefreshTokenErrorHelper._simplejwt_error(exc)}) from exc


# The lenient serializer is wired on ASGI/uvicorn at the URL layer (config.urls)
# so DRF's request lifecycle runs exactly once — nesting the second APIView inside
# the @api_view handler would re-enter dispatch with a DRF Request and blow up.
lenient_token_refresh = TokenRefreshView.as_view(
    serializer_class=LenientRefreshSerializer,
)


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
    return Response(_token_payload(user))


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([RegisterRateThrottle])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    return Response(_token_payload(user), status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def logout_user(request):
    refresh_token = request.data.get('refresh')
    if refresh_token:
        try:
            RefreshToken(refresh_token).blacklist()
        except TokenError:
            pass
    return Response(status=status.HTTP_204_NO_CONTENT)


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
