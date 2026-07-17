from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from core.models import TimeStampedModel, SoftDeleteModel, ActiveManager


class UserActivity(TimeStampedModel, SoftDeleteModel):
    ACTION_CHOICES = [
        ('view_movie', _('View Movie')),
        ('view_series', _('View Series')),
        ('view_episode', _('View Episode')),
        ('view_actor', _('View Actor')),
        ('view_director', _('View Director')),
        ('view_genre', _('View Genre')),
        ('play', _('Play')),
        ('pause', _('Pause')),
        ('watch_progress', _('Watch Progress')),
        ('complete_watch', _('Complete Watch')),
        ('like', _('Like')),
        ('dislike', _('Dislike')),
        ('rate', _('Rate')),
        ('add_to_watchlist', _('Add to Watchlist')),
        ('remove_from_watchlist', _('Remove from Watchlist')),
        ('search', _('Search')),
        ('click_search_result', _('Click Search Result')),
        ('filter_genre', _('Filter by Genre')),
        ('filter_year', _('Filter by Year')),
        ('filter_country', _('Filter by Country')),
        ('filter_rating', _('Filter by Rating')),
        ('open_actor_page', _('Open Actor Page')),
        ('open_director_page', _('Open Director Page')),
        ('share', _('Share')),
        ('comment', _('Comment')),
        ('download_click', _('Download Click')),
        ('trailer_watch', _('Trailer Watch')),
        ('add_to_favorites', _('Add to Favorites')),
        ('remove_from_favorites', _('Remove from Favorites')),
        ('follow_actor', _('Follow Actor')),
        ('unfollow_actor', _('Unfollow Actor')),
        ('follow_director', _('Follow Director')),
        ('unfollow_director', _('Unfollow Director')),
        ('subscribe', _('Subscribe')),
        ('unsubscribe', _('Unsubscribe')),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='activities',
        null=True,
        blank=True,
        db_index=True
    )
    session_id = models.CharField(_('Session ID'), max_length=64, db_index=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.UUIDField(null=True, blank=True, db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    action = models.CharField(_('Action'), max_length=50, choices=ACTION_CHOICES, db_index=True)
    value = models.JSONField(_('Value'), default=dict, blank=True)
    duration = models.PositiveIntegerField(_('Duration (seconds)'), default=0)
    progress = models.DecimalField(_('Progress (%)'), max_digits=5, decimal_places=2, default=0)
    metadata = models.JSONField(_('Metadata'), default=dict, blank=True)
    ip_address = models.GenericIPAddressField(_('IP Address'), null=True, blank=True)
    user_agent = models.TextField(_('User Agent'), blank=True)
    device_type = models.CharField(_('Device Type'), max_length=20, choices=[
        ('mobile', _('Mobile')),
        ('tablet', _('Tablet')),
        ('desktop', _('Desktop')),
        ('tv', _('TV')),
        ('other', _('Other')),
    ], blank=True)
    referrer = models.URLField(_('Referrer'), blank=True)
    utm_source = models.CharField(_('UTM Source'), max_length=100, blank=True)
    utm_medium = models.CharField(_('UTM Medium'), max_length=100, blank=True)
    utm_campaign = models.CharField(_('UTM Campaign'), max_length=100, blank=True)
    utm_term = models.CharField(_('UTM Term'), max_length=100, blank=True)
    utm_content = models.CharField(_('UTM Content'), max_length=100, blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('User Activity')
        verbose_name_plural = _('User Activities')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'action', '-created_at']),
            models.Index(fields=['session_id', '-created_at']),
            models.Index(fields=['content_type', 'object_id', '-created_at']),
            models.Index(fields=['action', '-created_at']),
        ]

    def __str__(self):
        user_str = self.user.email if self.user else f'Session {self.session_id[:8]}'
        return f'{user_str} - {self.action} - {self.created_at}'


class UserWatchProgress(TimeStampedModel, SoftDeleteModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='watch_progress')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')
    episode = models.ForeignKey('content.Episode', on_delete=models.CASCADE, null=True, blank=True, related_name='watch_progress')
    position = models.PositiveIntegerField(_('Position (seconds)'), default=0)
    duration = models.PositiveIntegerField(_('Duration (seconds)'), default=0)
    progress_percent = models.DecimalField(_('Progress (%)'), max_digits=5, decimal_places=2, default=0)
    is_completed = models.BooleanField(_('Completed'), default=False)
    completed_at = models.DateTimeField(_('Completed At'), null=True, blank=True)
    last_watched_at = models.DateTimeField(_('Last Watched At'), auto_now=True)
    watch_count = models.PositiveIntegerField(_('Watch Count'), default=1)
    device = models.CharField(_('Device'), max_length=255, blank=True)
    quality = models.CharField(_('Quality'), max_length=20, blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Watch Progress')
        verbose_name_plural = _('Watch Progress')
        unique_together = ['user', 'content_type', 'object_id', 'episode']
        ordering = ['-last_watched_at']
        indexes = [
            models.Index(fields=['user', 'is_completed', '-last_watched_at']),
            models.Index(fields=['user', 'content_type', '-last_watched_at']),
        ]

    def __str__(self):
        return f'{self.user} - {self.content_object} ({self.progress_percent}%)'


class UserRating(TimeStampedModel, SoftDeleteModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ratings')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')
    rating = models.DecimalField(_('Rating'), max_digits=3, decimal_places=1)
    review = models.TextField(_('Review'), blank=True)
    is_spoiler = models.BooleanField(_('Spoiler'), default=False)
    is_verified = models.BooleanField(_('Verified Purchase/Watch'), default=False)
    helpful_count = models.PositiveIntegerField(_('Helpful Count'), default=0)
    not_helpful_count = models.PositiveIntegerField(_('Not Helpful Count'), default=0)
    is_edited = models.BooleanField(_('Edited'), default=False)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('User Rating')
        verbose_name_plural = _('User Ratings')
        unique_together = ['user', 'content_type', 'object_id']
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id', '-rating']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f'{self.user} rated {self.content_object}: {self.rating}/10'


class UserComment(TimeStampedModel, SoftDeleteModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comments')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    text = models.TextField(_('Text'))
    is_spoiler = models.BooleanField(_('Spoiler'), default=False)
    is_pinned = models.BooleanField(_('Pinned'), default=False)
    is_edited = models.BooleanField(_('Edited'), default=False)
    like_count = models.PositiveIntegerField(_('Like Count'), default=0)
    dislike_count = models.PositiveIntegerField(_('Dislike Count'), default=0)
    report_count = models.PositiveIntegerField(_('Report Count'), default=0)
    is_hidden = models.BooleanField(_('Hidden'), default=False)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('User Comment')
        verbose_name_plural = _('User Comments')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['parent', '-created_at']),
        ]

    def __str__(self):
        return f'{self.user} on {self.content_object}: {self.text[:50]}'


class CommentVote(TimeStampedModel):
    VOTE_CHOICES = [
        ('like', _('Like')),
        ('dislike', _('Dislike')),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comment_votes')
    comment = models.ForeignKey(UserComment, on_delete=models.CASCADE, related_name='votes')
    vote = models.CharField(_('Vote'), max_length=10, choices=VOTE_CHOICES)

    class Meta:
        verbose_name = _('Comment Vote')
        verbose_name_plural = _('Comment Votes')
        unique_together = ['user', 'comment']

    def __str__(self):
        return f'{self.user} {self.vote} on {self.comment}'


class UserWatchlist(TimeStampedModel, SoftDeleteModel):
    LIST_TYPES = [
        ('watchlist', _('Watchlist')),
        ('favorites', _('Favorites')),
        ('watched', _('Watched')),
        ('watching', _('Watching')),
        ('plan_to_watch', _('Plan to Watch')),
        ('dropped', _('Dropped')),
        ('on_hold', _('On Hold')),
        ('custom', _('Custom')),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='watchlist_items')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')
    list_type = models.CharField(_('List Type'), max_length=20, choices=LIST_TYPES, default='watchlist', db_index=True)
    custom_list_name = models.CharField(_('Custom List Name'), max_length=100, blank=True)
    notes = models.TextField(_('Notes'), blank=True)
    priority = models.PositiveIntegerField(_('Priority'), default=0)
    tags = models.JSONField(_('Tags'), default=list, blank=True)
    started_at = models.DateTimeField(_('Started At'), null=True, blank=True)
    completed_at = models.DateTimeField(_('Completed At'), null=True, blank=True)
    rating = models.DecimalField(_('Personal Rating'), max_digits=3, decimal_places=1, null=True, blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Watchlist Item')
        verbose_name_plural = _('Watchlist Items')
        unique_together = ['user', 'content_type', 'object_id', 'list_type']
        ordering = ['-priority', '-created_at']
        indexes = [
            models.Index(fields=['user', 'list_type', '-created_at']),
            models.Index(fields=['user', 'content_type', 'list_type']),
        ]

    def __str__(self):
        return f'{self.user} - {self.content_object} ({self.list_type})'


class SearchLog(TimeStampedModel, SoftDeleteModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='search_logs', null=True, blank=True)
    session_id = models.CharField(_('Session ID'), max_length=64, db_index=True)
    query = models.CharField(_('Query'), max_length=500, db_index=True)
    normalized_query = models.CharField(_('Normalized Query'), max_length=500, db_index=True)
    filters = models.JSONField(_('Filters'), default=dict, blank=True)
    results_count = models.PositiveIntegerField(_('Results Count'), default=0)
    clicked_result_id = models.UUIDField(null=True, blank=True)
    clicked_result_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    clicked_position = models.PositiveIntegerField(_('Clicked Position'), null=True, blank=True)
    took_ms = models.PositiveIntegerField(_('Time (ms)'), default=0)
    ip_address = models.GenericIPAddressField(_('IP Address'), null=True, blank=True)
    user_agent = models.TextField(_('User Agent'), blank=True)
    device_type = models.CharField(_('Device Type'), max_length=20, blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Search Log')
        verbose_name_plural = _('Search Logs')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['normalized_query', '-created_at']),
            models.Index(fields=['session_id', '-created_at']),
        ]

    def __str__(self):
        user_str = self.user.email if self.user else f'Session {self.session_id[:8]}'
        return f'{user_str} searched: {self.query}'


class SearchSuggestion(TimeStampedModel, SoftDeleteModel):
    query = models.CharField(_('Query'), max_length=500, unique=True, db_index=True)
    normalized_query = models.CharField(_('Normalized Query'), max_length=500, db_index=True)
    count = models.PositiveIntegerField(_('Count'), default=1)
    last_searched = models.DateTimeField(_('Last Searched'), auto_now=True)
    language = models.CharField(_('Language'), max_length=10, default='fa')
    is_active = models.BooleanField(_('Active'), default=True)
    suggestion_type = models.CharField(_('Type'), max_length=20, choices=[
        ('user', _('User Query')),
        ('auto', _('Auto-generated')),
        ('trending', _('Trending')),
        ('correction', _('Correction')),
    ], default='user')

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = _('Search Suggestion')
        verbose_name_plural = _('Search Suggestions')
        ordering = ['-count', 'query']
        indexes = [
            models.Index(fields=['normalized_query']),
            models.Index(fields=['language', '-count']),
        ]

    def __str__(self):
        return f'{self.query} ({self.count})'