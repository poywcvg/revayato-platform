"""Staff-only user management endpoints for the Nuxt admin panel."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from users.username_policy import validate_username_policy

User = get_user_model()


def _user_activity_stats(user):
    """Real per-user engagement stats for the admin user-detail drawer.

    All values are live counts from the engagement tables — never fabricated.
    """
    from apps.catalog.models import Movie, Series
    from apps.engagement.models import Like, Rating, UserActivityEvent, WatchlistItem

    events = UserActivityEvent.objects.filter(user=user)
    action_counts = {
        row['action']: row['count']
        for row in events.values('action').annotate(count=Count('id'))
    }
    downloads = action_counts.get('download_click', 0)
    plays = action_counts.get('play', 0)
    completes = action_counts.get('complete_watch', 0)
    searches = action_counts.get('search', 0)

    # Most recent activity (typed, title-resolved where possible).
    recent_rows = list(
        events.order_by('-created_at')
        .values('action', 'content_type', 'object_id', 'query', 'created_at')[:15]
    )
    movie_ids = [r['object_id'] for r in recent_rows if r['content_type'] == 'movie' and r['object_id']]
    series_ids = [r['object_id'] for r in recent_rows if r['content_type'] == 'series' and r['object_id']]
    movies = Movie.objects.in_bulk(movie_ids)
    series = Series.objects.in_bulk(series_ids)
    recent_activity = []
    for row in recent_rows:
        item = None
        if row['content_type'] == 'movie':
            item = movies.get(row['object_id'])
        elif row['content_type'] == 'series':
            item = series.get(row['object_id'])
        recent_activity.append({
            'action': row['action'],
            'content_type': row['content_type'],
            'object_id': row['object_id'],
            'title': (item.title if item else '') or row.get('query') or '',
            'slug': item.slug if item else '',
            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
        })

    last_event = events.order_by('-created_at').values_list('created_at', flat=True).first()
    last_seen = max([t for t in (user.last_login, last_event) if t], default=None)

    return {
        'stats': {
            'downloads': downloads,
            'plays': plays,
            'completes': completes,
            'searches': searches,
            'total_events': events.count(),
            'likes': Like.objects.filter(user=user).count(),
            'ratings': Rating.objects.filter(user=user).count(),
            'watchlist': WatchlistItem.objects.filter(user=user).count(),
            'last_seen': last_seen.isoformat() if last_seen else None,
            'days_since_joined': (timezone.now() - user.date_joined).days if user.date_joined else None,
        },
        'recent_activity': recent_activity,
    }


class IsStaffUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class StaffAdminThrottle(UserRateThrottle):
    rate = '60/minute'


class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            'id', 'email', 'username', 'first_name', 'last_name', 'phone',
            'is_active', 'is_staff', 'is_superuser', 'is_verified',
            'date_joined', 'last_login', 'created_at', 'updated_at',
            'failed_login_attempts', 'locked_until',
        )
        read_only_fields = (
            'id', 'date_joined', 'last_login', 'created_at', 'updated_at',
            'failed_login_attempts', 'locked_until',
        )


class AdminUserCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(min_length=8, write_only=True)
    first_name = serializers.CharField(required=False, allow_blank=True, default='')
    last_name = serializers.CharField(required=False, allow_blank=True, default='')
    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)
    is_staff = serializers.BooleanField(default=False)
    is_active = serializers.BooleanField(default=True)
    is_verified = serializers.BooleanField(default=False)

    def validate_email(self, value):
        email = value.strip().lower()
        if User.all_objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('این ایمیل قبلاً ثبت شده است.')
        return email

    def validate_username(self, value):
        try:
            username = validate_username_policy(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        if User.all_objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError(
                f'نام کاربری «{username}» قبلاً گرفته شده است. یک نام کاربری دیگر انتخاب کن.',
            )
        return username

    def create(self, validated_data):
        phone = validated_data.get('phone') or None
        user = User.objects.create_user(
            email=validated_data['email'],
            username=validated_data['username'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name') or '',
            last_name=validated_data.get('last_name') or '',
            phone=phone,
            is_staff=bool(validated_data.get('is_staff')),
            is_active=bool(validated_data.get('is_active', True)),
            is_verified=bool(validated_data.get('is_verified')),
        )
        return user


class AdminUserUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    username = serializers.CharField(max_length=150, required=False)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    is_active = serializers.BooleanField(required=False)
    is_staff = serializers.BooleanField(required=False)
    is_superuser = serializers.BooleanField(required=False)
    is_verified = serializers.BooleanField(required=False)
    password = serializers.CharField(min_length=8, required=False, write_only=True)

    def validate_email(self, value):
        email = value.strip().lower()
        qs = User.all_objects.filter(email__iexact=email)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('این ایمیل قبلاً ثبت شده است.')
        return email

    def validate_username(self, value):
        try:
            username = validate_username_policy(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        qs = User.all_objects.filter(username__iexact=username)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f'نام کاربری «{username}» قبلاً گرفته شده است. یک نام کاربری دیگر انتخاب کن.',
            )
        return username

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for key, value in validated_data.items():
            if key == 'phone' and value == '':
                value = None
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class AdminUserPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def admin_user_list_create(request):
    if request.method == 'POST':
        serializer = AdminUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)

    query = (request.query_params.get('q') or '').strip()
    role = (request.query_params.get('role') or '').strip().lower()
    active = (request.query_params.get('active') or '').strip().lower()

    queryset = User.objects.all().order_by('-date_joined', '-id')
    if query:
        queryset = queryset.filter(
            Q(email__icontains=query)
            | Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(phone__icontains=query)
        )
    if role == 'staff':
        queryset = queryset.filter(is_staff=True)
    elif role == 'user':
        queryset = queryset.filter(is_staff=False)
    if active in {'1', 'true', 'yes'}:
        queryset = queryset.filter(is_active=True)
    elif active in {'0', 'false', 'no'}:
        queryset = queryset.filter(is_active=False)

    paginator = AdminUserPagination()
    page = paginator.paginate_queryset(queryset, request)
    response = paginator.get_paginated_response(AdminUserSerializer(page, many=True).data)
    response.data['summary'] = {
        'total': User.objects.count(),
        'active': User.objects.filter(is_active=True).count(),
        'inactive': User.objects.filter(is_active=False).count(),
        'staff': User.objects.filter(is_staff=True).count(),
        'verified': User.objects.filter(is_verified=True).count(),
    }
    return response


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated, IsStaffUser])
@throttle_classes([StaffAdminThrottle])
def admin_user_detail(request, user_id):
    user = get_object_or_404(User.objects.all(), pk=user_id)

    if request.method == 'GET':
        data = AdminUserSerializer(user).data
        data.update(_user_activity_stats(user))
        return Response(data)

    serializer = AdminUserUpdateSerializer(instance=user, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)

    # Safety: staff cannot strip their own staff flag or deactivate themselves.
    if user.pk == request.user.pk:
        if 'is_staff' in serializer.validated_data and not serializer.validated_data['is_staff']:
            return Response(
                {'detail': 'نمی‌توانید دسترسی مدیریت خودتان را بردارید.', 'code': 'cannot_demote_self'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if 'is_active' in serializer.validated_data and not serializer.validated_data['is_active']:
            return Response(
                {'detail': 'نمی‌توانید حساب خودتان را غیرفعال کنید.', 'code': 'cannot_deactivate_self'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if 'is_superuser' in serializer.validated_data and not serializer.validated_data['is_superuser']:
            return Response(
                {'detail': 'نمی‌توانید دسترسی ابرکاربر خودتان را بردارید.', 'code': 'cannot_demote_self'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # Only superusers may grant/revoke superuser.
    if 'is_superuser' in serializer.validated_data and not request.user.is_superuser:
        return Response(
            {'detail': 'فقط ابرکاربر می‌تواند وضعیت ابرکاربر را تغییر دهد.', 'code': 'superuser_required'},
            status=status.HTTP_403_FORBIDDEN,
        )

    updated = serializer.save()
    return Response(AdminUserSerializer(updated).data)
