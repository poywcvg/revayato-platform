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
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.exceptions import TokenError
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


class LoginRateThrottle(AnonRateThrottle):
    rate = '10/minute'


class RegisterRateThrottle(AnonRateThrottle):
    rate = '5/hour'


class PasswordResetRateThrottle(AnonRateThrottle):
    rate = '5/hour'


def _client_ip(request):
    return request.META.get('REMOTE_ADDR') or None


def _token_payload(user):
    refresh = RefreshToken.for_user(user)
    profile, _created = Profile.objects.get_or_create(user=user)
    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': MeSerializer({'user': user, 'profile': profile}).data,
    }


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([LoginRateThrottle])
def login_user(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data['email']
    password = serializer.validated_data['password']
    account = User.all_objects.filter(email__iexact=email).first()

    if account and account.locked_until and account.locked_until > timezone.now():
        remaining_minutes = max(1, int((account.locked_until - timezone.now()).total_seconds() // 60) + 1)
        return Response(
            {
                'code': 'account_locked',
                'detail': f'ورود این حساب برای {remaining_minutes} دقیقه بسته شده است.',
                'hint': 'کمی صبر کن یا رمز عبورت را بازیابی کن.',
            },
            status=status.HTTP_423_LOCKED,
        )

    if account and (not account.is_active or account.is_deleted):
        return Response(
            {'code': 'account_disabled', 'detail': 'این حساب در حال حاضر فعال نیست.', 'hint': 'با پشتیبانی تماس بگیر.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    user = authenticate(request=request, email=email, password=password)
    if not user:
        if account and account.is_active and not account.is_deleted:
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
                'detail': 'ایمیل یا رمز عبور درست نیست.',
                'hint': 'اطلاعات را دوباره بررسی کن یا از بازیابی رمز عبور استفاده کن.',
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

    user.set_password(serializer.validated_data['password'])
    user.failed_login_attempts = 0
    user.locked_until = None
    user.save(update_fields=['password', 'failed_login_attempts', 'locked_until'])
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
