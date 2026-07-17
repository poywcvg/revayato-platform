from django.conf import settings
from django.db import models


class TasteProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='recommendation_taste_profile',
    )
    profile_data = models.JSONField(default=dict)
    is_ready = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.user.username} taste profile'


class Recommendation(models.Model):
    CONTENT_TYPES = [
        ('movie', 'Movie'),
        ('series', 'Series'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='recommendations',
        null=True,
        blank=True,
    )
    session_key = models.CharField(max_length=100, blank=True, db_index=True)

    content_type = models.CharField(max_length=20, choices=CONTENT_TYPES)
    object_id = models.PositiveBigIntegerField()

    score = models.FloatField(default=0.0)
    reason = models.CharField(max_length=100, blank=True)
    reason_details = models.JSONField(default=dict, blank=True)

    is_consumed = models.BooleanField(default=False)
    is_dismissed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-score']
        indexes = [
            models.Index(fields=['user', '-score']),
            models.Index(fields=['session_key', '-score']),
        ]
        unique_together = [
            ['user', 'content_type', 'object_id'],
            ['session_key', 'content_type', 'object_id'],
        ]

    def __str__(self):
        return f'{self.content_type}#{self.object_id} score={self.score}'


class SearchLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    session_key = models.CharField(max_length=100, blank=True)
    query = models.CharField(max_length=255, db_index=True)
    filters = models.JSONField(default=dict, blank=True)
    result_count = models.IntegerField(default=0)
    clicked_content_type = models.CharField(max_length=50, blank=True)
    clicked_object_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['query']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f'search: {self.query}'
