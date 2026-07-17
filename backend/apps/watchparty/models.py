import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


def generate_invite_code():
    return secrets.token_urlsafe(18)


def default_room_expiry():
    minutes = getattr(settings, 'WATCH_PARTY_DEFAULT_EXPIRY_MINUTES', 240)
    return timezone.now() + timedelta(minutes=minutes)


class WatchRoom(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        ENDED = 'ended', 'Ended'
        EXPIRED = 'expired', 'Expired'

    invite_code = models.CharField(
        max_length=32, unique=True, db_index=True, default=generate_invite_code, editable=False,
    )
    movie = models.ForeignKey(
        'catalog.Movie', on_delete=models.CASCADE, related_name='watch_rooms', null=True, blank=True,
    )
    episode = models.ForeignKey(
        'catalog.Episode', on_delete=models.CASCADE, related_name='watch_rooms', null=True, blank=True,
    )
    host_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='hosted_watch_rooms',
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(default=default_room_expiry, db_index=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(movie__isnull=False, episode__isnull=True)
                    | Q(movie__isnull=True, episode__isnull=False)
                ),
                name='watchroom_exactly_one_content',
            ),
        ]
        indexes = [
            models.Index(fields=['status', 'expires_at']),
            models.Index(fields=['host_user', '-created_at']),
        ]

    def __str__(self):
        return f'{self.invite_code} ({self.status})'

    @property
    def content_object(self):
        return self.movie or self.episode

    @property
    def is_expired(self):
        return self.expires_at <= timezone.now()

    @property
    def is_joinable(self):
        return self.status == self.Status.ACTIVE and not self.is_expired

    def clean(self):
        if bool(self.movie_id) == bool(self.episode_id):
            raise ValidationError('A watch room must reference exactly one movie or episode.')
        if self.expires_at <= timezone.now():
            raise ValidationError({'expires_at': 'Expiry must be in the future.'})


class WatchRoomMember(models.Model):
    class Role(models.TextChoices):
        HOST = 'host', 'Host'
        MEMBER = 'member', 'Member'

    room = models.ForeignKey(WatchRoom, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='watch_room_memberships',
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    is_online = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ['role', 'joined_at']
        constraints = [
            models.UniqueConstraint(fields=['room', 'user'], name='watchroom_unique_member'),
            models.UniqueConstraint(
                fields=['room'], condition=Q(role='host'), name='watchroom_single_host_member',
            ),
        ]
        indexes = [
            models.Index(fields=['room', 'is_online']),
        ]

    def __str__(self):
        return f'{self.user_id} in {self.room_id} ({self.role})'


class WatchRoomMessage(models.Model):
    room = models.ForeignKey(WatchRoom, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='watch_room_messages',
    )
    message = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_deleted = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['room', 'is_deleted', '-created_at']),
        ]

    def __str__(self):
        return f'Message {self.pk} in room {self.room_id}'


class WatchRoomPlaybackState(models.Model):
    room = models.OneToOneField(WatchRoom, on_delete=models.CASCADE, related_name='playback_state')
    is_playing = models.BooleanField(default=False)
    position_seconds = models.FloatField(default=0, validators=[MinValueValidator(0)])
    duration_seconds = models.FloatField(default=0, validators=[MinValueValidator(0)])
    playback_rate = models.FloatField(
        default=1, validators=[MinValueValidator(0.25), MaxValueValidator(4)],
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='watch_room_playback_updates',
        null=True, blank=True,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'Playback state for room {self.room_id}'
