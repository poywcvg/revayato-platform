from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='account_profile',
    )
    avatar = models.ImageField(upload_to='accounts/avatars/', null=True, blank=True)
    bio = models.TextField(blank=True, max_length=500)
    preferred_language = models.CharField(max_length=10, blank=True, default='fa')
    is_email_verified = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.user.username


class UserPrivacySetting(models.Model):
    class PrivacyLevel(models.TextChoices):
        PUBLIC = 'public', _('Public')
        FOLLOWERS_ONLY = 'followers_only', _('Followers Only')
        PRIVATE = 'private', _('Private')

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='privacy_settings',
    )
    profile_visibility = models.CharField(
        _('Profile Visibility'), max_length=20,
        choices=PrivacyLevel.choices, default=PrivacyLevel.PUBLIC,
    )
    watchlist_visibility = models.CharField(
        _('Watchlist Visibility'), max_length=20,
        choices=PrivacyLevel.choices, default=PrivacyLevel.PRIVATE,
    )
    activity_visibility = models.CharField(
        _('Activity Visibility'), max_length=20,
        choices=PrivacyLevel.choices, default=PrivacyLevel.FOLLOWERS_ONLY,
    )
    ratings_visibility = models.CharField(
        _('Ratings Visibility'), max_length=20,
        choices=PrivacyLevel.choices, default=PrivacyLevel.PUBLIC,
    )
    followers_visibility = models.CharField(
        _('Followers Visibility'), max_length=20,
        choices=PrivacyLevel.choices, default=PrivacyLevel.PUBLIC,
    )
    show_online_status = models.BooleanField(_('Show Online Status'), default=True)
    allow_follow_requests = models.BooleanField(_('Allow Follow Requests'), default=True)
    allow_dm = models.BooleanField(_('Allow Direct Messages'), default=False)
    is_private_account = models.BooleanField(_('Private Account'), default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('User Privacy Setting')
        verbose_name_plural = _('User Privacy Settings')

    def __str__(self):
        return f'{self.user.username} privacy settings'
