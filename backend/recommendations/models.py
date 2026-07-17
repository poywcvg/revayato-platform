from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from core.models import TimeStampedModel, SoftDeleteModel, ActiveManager


class Recommendation(TimeStampedModel, SoftDeleteModel):
    ALGORITHM_CHOICES = [
        ('content_based', _('Content Based')),
        ('collaborative', _('Collaborative Filtering')),
        ('hybrid', _('Hybrid')),
        ('trending', _('Trending')),
        ('popular', _('Popular')),
        ('similar_users', _('Similar Users')),
        ('genre_based', _('Genre Based')),
        ('actor_based', _('Actor Based')),
        ('director_based', _('Director Based')),
        ('recent', _('Recently Added')),
        ('continue_watching', _('Continue Watching')),
        ('watchlist', _('From Watchlist')),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='recommendations')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField(db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    algorithm = models.CharField(_('Algorithm'), max_length=30, choices=ALGORITHM_CHOICES, db_index=True)
    score = models.FloatField(_('Score'), db_index=True)
    rank = models.PositiveIntegerField(_('Rank'), default=0)
    reason = models.JSONField(_('Reason'), default=dict, blank=True)
    context = models.JSONField(_('Context'), default=dict, blank=True)
    is_shown = models.BooleanField(_('Shown'), default=False)
    is_clicked = models.BooleanField(_('Clicked'), default=False)
    is_dismissed = models.BooleanField(_('Dismissed'), default=False)
    shown_at = models.DateTimeField(_('Shown At'), null=True, blank=True)
    clicked_at = models.DateTimeField(_('Clicked At'), null=True, blank=True)
    dismissed_at = models.DateTimeField(_('Dismissed At'), null=True, blank=True)
    expires_at = models.DateTimeField(_('Expires At'), null=True, blank=True, db_index=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Recommendation')
        verbose_name_plural = _('Recommendations')
        ordering = ['-score', 'rank']
        unique_together = ['user', 'content_type', 'object_id', 'algorithm']
        indexes = [
            models.Index(fields=['user', 'algorithm', '-score']),
            models.Index(fields=['user', 'is_shown', '-score']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f'{self.user} -> {self.content_object} ({self.algorithm}: {self.score})'


class RecommendationBatch(TimeStampedModel, SoftDeleteModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='recommendation_batches')
    algorithm = models.CharField(_('Algorithm'), max_length=30, choices=Recommendation.ALGORITHM_CHOICES)
    name = models.CharField(_('Name'), max_length=100)
    description = models.TextField(_('Description'), blank=True)
    items = models.JSONField(_('Items'), default=list)
    total_count = models.PositiveIntegerField(_('Total Count'), default=0)
    is_active = models.BooleanField(_('Active'), default=True)
    generated_at = models.DateTimeField(_('Generated At'), auto_now_add=True)
    expires_at = models.DateTimeField(_('Expires At'), db_index=True)
    metadata = models.JSONField(_('Metadata'), default=dict, blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Recommendation Batch')
        verbose_name_plural = _('Recommendation Batches')
        ordering = ['-generated_at']
        indexes = [
            models.Index(fields=['user', 'algorithm', 'is_active']),
        ]

    def __str__(self):
        return f'{self.name} for {self.user}'


class SimilarityIndex(TimeStampedModel, SoftDeleteModel):
    SIMILARITY_TYPES = [
        ('content', _('Content Similarity')),
        ('user', _('User Similarity')),
        ('item', _('Item Similarity')),
    ]

    source_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='source_similarities')
    source_object_id = models.UUIDField(db_index=True)
    source_object = GenericForeignKey('source_content_type', 'source_object_id')
    target_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='target_similarities')
    target_object_id = models.UUIDField(db_index=True)
    target_object = GenericForeignKey('target_content_type', 'target_object_id')
    similarity_type = models.CharField(_('Type'), max_length=20, choices=SIMILARITY_TYPES, db_index=True)
    score = models.FloatField(_('Score'), db_index=True)
    features = models.JSONField(_('Features'), default=dict, blank=True)
    algorithm = models.CharField(_('Algorithm'), max_length=50, default='cosine')
    version = models.PositiveIntegerField(_('Version'), default=1)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Similarity Index')
        verbose_name_plural = _('Similarity Indices')
        unique_together = ['source_content_type', 'source_object_id', 'target_content_type', 'target_object_id', 'similarity_type']
        ordering = ['-score']
        indexes = [
            models.Index(fields=['source_content_type', 'source_object_id', 'similarity_type', '-score']),
            models.Index(fields=['target_content_type', 'target_object_id', '-score']),
        ]

    def __str__(self):
        return f'{self.source_object} ~ {self.target_object} ({self.similarity_type}: {self.score})'


class TrendingContent(TimeStampedModel, SoftDeleteModel):
    PERIOD_CHOICES = [
        ('hourly', _('Hourly')),
        ('daily', _('Daily')),
        ('weekly', _('Weekly')),
        ('monthly', _('Monthly')),
    ]

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField(db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    period = models.CharField(_('Period'), max_length=20, choices=PERIOD_CHOICES, db_index=True)
    rank = models.PositiveIntegerField(_('Rank'), db_index=True)
    score = models.FloatField(_('Score'), db_index=True)
    views = models.PositiveIntegerField(_('Views'), default=0)
    likes = models.PositiveIntegerField(_('Likes'), default=0)
    watch_time = models.PositiveBigIntegerField(_('Watch Time (seconds)'), default=0)
    completion_rate = models.DecimalField(_('Completion Rate'), max_digits=5, decimal_places=2, default=0)
    period_start = models.DateTimeField(_('Period Start'), db_index=True)
    period_end = models.DateTimeField(_('Period End'), db_index=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Trending Content')
        verbose_name_plural = _('Trending Content')
        unique_together = ['content_type', 'object_id', 'period', 'period_start']
        ordering = ['period', 'rank']
        indexes = [
            models.Index(fields=['period', 'period_start', 'rank']),
            models.Index(fields=['content_type', 'period', 'rank']),
        ]

    def __str__(self):
        return f'{self.content_object} - {self.period} #{self.rank}'


class UserSimilarity(TimeStampedModel, SoftDeleteModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='similarities')
    similar_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='similar_to')
    score = models.FloatField(_('Similarity Score'), db_index=True)
    common_items = models.PositiveIntegerField(_('Common Items'), default=0)
    algorithm = models.CharField(_('Algorithm'), max_length=50, default='cosine')
    version = models.PositiveIntegerField(_('Version'), default=1)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('User Similarity')
        verbose_name_plural = _('User Similarities')
        unique_together = ['user', 'similar_user', 'algorithm', 'version']
        ordering = ['-score']
        indexes = [
            models.Index(fields=['user', '-score']),
        ]

    def __str__(self):
        return f'{self.user} ~ {self.similar_user} ({self.score})'