import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from core.models import TimeStampedModel, SoftDeleteModel, ActiveManager


class UserManager(DjangoUserManager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class User(AbstractUser, TimeStampedModel, SoftDeleteModel):
    email = models.EmailField(_('Email'), unique=True, db_index=True)
    phone = models.CharField(_('Phone'), max_length=20, unique=True, null=True, blank=True, db_index=True)
    avatar = models.ImageField(_('Avatar'), upload_to='avatars/', blank=True, null=True)
    bio = models.TextField(_('Bio'), blank=True)
    birth_date = models.DateField(_('Birth Date'), null=True, blank=True)
    gender = models.CharField(_('Gender'), max_length=20, choices=[
        ('male', _('Male')),
        ('female', _('Female')),
        ('other', _('Other')),
        ('prefer_not_to_say', _('Prefer not to say')),
    ], blank=True)
    country = models.ForeignKey('content.Country', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    language = models.CharField(_('Language'), max_length=10, default='fa')
    timezone = models.CharField(_('Timezone'), max_length=50, default='Asia/Tehran')
    is_verified = models.BooleanField(_('Verified'), default=False)
    email_verified_at = models.DateTimeField(_('Email Verified At'), null=True, blank=True)
    phone_verified_at = models.DateTimeField(_('Phone Verified At'), null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(_('Last Login IP'), null=True, blank=True)
    failed_login_attempts = models.PositiveIntegerField(_('Failed Login Attempts'), default=0)
    locked_until = models.DateTimeField(_('Locked Until'), null=True, blank=True)
    referral_code = models.CharField(_('Referral Code'), max_length=20, unique=True, null=True, blank=True)
    referred_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='referrals')

    objects = UserManager()
    all_objects = models.Manager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['-created_at']

    def __str__(self):
        return self.email

    def get_full_name(self):
        return self.get_short_name()

    def get_short_name(self):
        return self.username or self.email.split('@')[0]


class UserProfile(TimeStampedModel, SoftDeleteModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    display_name = models.CharField(_('Display Name'), max_length=100, blank=True)
    favorite_genres = models.ManyToManyField('content.Genre', verbose_name=_('Favorite Genres'), related_name='user_profiles', blank=True)
    favorite_actors = models.ManyToManyField('content.Actor', verbose_name=_('Favorite Actors'), related_name='user_profiles', blank=True)
    favorite_directors = models.ManyToManyField('content.Director', verbose_name=_('Favorite Directors'), related_name='user_profiles', blank=True)
    favorite_countries = models.ManyToManyField('content.Country', verbose_name=_('Favorite Countries'), related_name='user_profiles', blank=True)
    preferred_languages = models.JSONField(_('Preferred Languages'), default=list)
    preferred_quality = models.CharField(_('Preferred Quality'), max_length=20, blank=True)
    auto_play_next = models.BooleanField(_('Auto Play Next'), default=True)
    auto_play_trailer = models.BooleanField(_('Auto Play Trailer'), default=False)
    show_adult_content = models.BooleanField(_('Show Adult Content'), default=False)
    email_notifications = models.BooleanField(_('Email Notifications'), default=True)
    push_notifications = models.BooleanField(_('Push Notifications'), default=True)
    marketing_emails = models.BooleanField(_('Marketing Emails'), default=False)
    theme = models.CharField(_('Theme'), max_length=20, choices=[
        ('dark', _('Dark')),
        ('light', _('Light')),
        ('system', _('System')),
    ], default='dark')
    compact_mode = models.BooleanField(_('Compact Mode'), default=False)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('User Profile')
        verbose_name_plural = _('User Profiles')

    def __str__(self):
        return f'{self.user} Profile'


class UserPreference(TimeStampedModel, SoftDeleteModel):
    PREFERENCE_TYPES = [
        ('genre', _('Genre')),
        ('actor', _('Actor')),
        ('director', _('Director')),
        ('country', _('Country')),
        ('year_range', _('Year Range')),
        ('content_type', _('Content Type')),
        ('language', _('Language')),
        ('quality', _('Quality')),
        ('age_rating', _('Age Rating')),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='preferences')
    preference_type = models.CharField(_('Type'), max_length=20, choices=PREFERENCE_TYPES)
    value = models.JSONField(_('Value'))
    weight = models.FloatField(_('Weight'), default=1.0)
    is_explicit = models.BooleanField(_('Explicit'), default=False)
    source = models.CharField(_('Source'), max_length=20, choices=[
        ('explicit', _('Explicit')),
        ('implicit', _('Implicit')),
        ('inferred', _('Inferred')),
    ], default='implicit')

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('User Preference')
        verbose_name_plural = _('User Preferences')
        unique_together = ['user', 'preference_type', 'value']
        indexes = [
            models.Index(fields=['user', 'preference_type']),
        ]

    def __str__(self):
        return f'{self.user} - {self.preference_type}: {self.value}'


class UserTasteProfile(TimeStampedModel, SoftDeleteModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='taste_profile')
    genres = models.JSONField(_('Genres'), default=dict)
    actors = models.JSONField(_('Actors'), default=dict)
    directors = models.JSONField(_('Directors'), default=dict)
    countries = models.JSONField(_('Countries'), default=dict)
    content_types = models.JSONField(_('Content Types'), default=dict)
    year_ranges = models.JSONField(_('Year Ranges'), default=dict)
    last_updated = models.DateTimeField(_('Last Updated'), auto_now=True)
    version = models.PositiveIntegerField(_('Version'), default=1)
    data_points = models.PositiveIntegerField(_('Data Points'), default=0)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('User Taste Profile')
        verbose_name_plural = _('User Taste Profiles')

    def __str__(self):
        return f'{self.user} Taste Profile v{self.version}'


class UserSession(TimeStampedModel, SoftDeleteModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sessions', null=True, blank=True)
    session_key = models.CharField(_('Session Key'), max_length=64, unique=True, db_index=True)
    ip_address = models.GenericIPAddressField(_('IP Address'))
    user_agent = models.TextField(_('User Agent'))
    device_type = models.CharField(_('Device Type'), max_length=20, choices=[
        ('mobile', _('Mobile')),
        ('tablet', _('Tablet')),
        ('desktop', _('Desktop')),
        ('tv', _('TV')),
        ('other', _('Other')),
    ])
    browser = models.CharField(_('Browser'), max_length=100, blank=True)
    os = models.CharField(_('OS'), max_length=100, blank=True)
    country = models.ForeignKey('content.Country', on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions')
    city = models.CharField(_('City'), max_length=100, blank=True)
    is_active = models.BooleanField(_('Active'), default=True)
    last_activity = models.DateTimeField(_('Last Activity'), auto_now=True)
    expires_at = models.DateTimeField(_('Expires At'))

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('User Session')
        verbose_name_plural = _('User Sessions')
        ordering = ['-last_activity']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['session_key', 'is_active']),
        ]

    def __str__(self):
        return f'Session {self.session_key[:8]} ({self.device_type})'


class UserDevice(TimeStampedModel, SoftDeleteModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='devices')
    device_id = models.CharField(_('Device ID'), max_length=255, db_index=True)
    device_name = models.CharField(_('Device Name'), max_length=255, blank=True)
    device_type = models.CharField(_('Device Type'), max_length=20, choices=[
        ('mobile', _('Mobile')),
        ('tablet', _('Tablet')),
        ('desktop', _('Desktop')),
        ('tv', _('TV')),
        ('other', _('Other')),
    ])
    push_token = models.CharField(_('Push Token'), max_length=500, blank=True)
    platform = models.CharField(_('Platform'), max_length=50, blank=True)
    platform_version = models.CharField(_('Platform Version'), max_length=50, blank=True)
    app_version = models.CharField(_('App Version'), max_length=50, blank=True)
    is_active = models.BooleanField(_('Active'), default=True)
    last_used = models.DateTimeField(_('Last Used'), auto_now=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('User Device')
        verbose_name_plural = _('User Devices')
        unique_together = ['user', 'device_id']
        ordering = ['-last_used']

    def __str__(self):
        return f'{self.user} - {self.device_name or self.device_id}'