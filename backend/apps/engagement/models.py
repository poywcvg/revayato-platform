from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


RATEABLE_CONTENT_TYPES = [
    ('movie', 'Movie'),
    ('series', 'Series'),
]


class Rating(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='engagement_ratings',
    )
    content_type = models.CharField(max_length=20, choices=RATEABLE_CONTENT_TYPES)
    object_id = models.PositiveBigIntegerField(db_index=True)

    score = models.DecimalField(
        max_digits=3, decimal_places=1,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
    )
    review = models.TextField(blank=True)
    is_spoiler = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'content_type', 'object_id'],
                name='uq_rating_user_content',
            ),
        ]
        indexes = [
            models.Index(fields=['content_type', 'object_id', '-score']),
        ]

    def __str__(self):
        return f'{self.user} rated {self.content_type}#{self.object_id}: {self.score}'


class WatchlistItem(models.Model):
    class ListType(models.TextChoices):
        WATCHLIST = 'watchlist', 'Watchlist'
        FAVORITE = 'favorite', 'Favorite'
        WATCHED = 'watched', 'Watched'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='engagement_watchlist_items',
    )
    content_type = models.CharField(max_length=20, choices=RATEABLE_CONTENT_TYPES)
    object_id = models.PositiveBigIntegerField(db_index=True)
    list_type = models.CharField(max_length=20, choices=ListType.choices, default=ListType.WATCHLIST)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'content_type', 'object_id', 'list_type'],
                name='uq_watchlist_user_content_type',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'list_type', '-created_at']),
        ]

    def __str__(self):
        return f'{self.user} - {self.content_type}#{self.object_id} ({self.list_type})'


class Like(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='likes',
    )
    content_type = models.CharField(max_length=20, choices=RATEABLE_CONTENT_TYPES)
    object_id = models.PositiveBigIntegerField(db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'content_type', 'object_id'],
                name='uq_like_user_content',
            ),
        ]

    def __str__(self):
        return f'{self.user} likes {self.content_type}#{self.object_id}'


class UserActivityEvent(models.Model):
    ACTIONS = [
        ('view_movie', 'View Movie'),
        ('view_series', 'View Series'),
        ('view_episode', 'View Episode'),
        ('play', 'Play'),
        ('pause', 'Pause'),
        ('watch_progress', 'Watch Progress'),
        ('complete_watch', 'Complete Watch'),
        ('like', 'Like'),
        ('remove_like', 'Remove Like'),
        ('dislike', 'Dislike'),
        ('rate', 'Rate'),
        ('add_to_watchlist', 'Add to Watchlist'),
        ('remove_from_watchlist', 'Remove from Watchlist'),
        ('search', 'Search'),
        ('click_search_result', 'Click Search Result'),
        ('filter_genre', 'Filter Genre'),
        ('filter_year', 'Filter Year'),
        ('filter_country', 'Filter Country'),
        ('open_actor_page', 'Open Actor Page'),
        ('open_director_page', 'Open Director Page'),
        ('share', 'Share'),
        ('comment', 'Comment'),
        ('download_click', 'Download Click'),
        ('trailer_watch', 'Trailer Watch'),
    ]

    CONTENT_TYPES = [
        ('movie', 'Movie'),
        ('series', 'Series'),
        ('episode', 'Episode'),
        ('actor', 'Actor'),
        ('director', 'Director'),
        ('genre', 'Genre'),
        ('search', 'Search'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='activity_events',
        null=True,
        blank=True,
    )
    client_event_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    session_key = models.CharField(max_length=100, blank=True, db_index=True)

    content_type = models.CharField(max_length=50, choices=CONTENT_TYPES)
    object_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    action = models.CharField(max_length=50, choices=ACTIONS, db_index=True)
    value = models.FloatField(default=1.0)
    duration = models.PositiveIntegerField(null=True, blank=True)
    progress = models.FloatField(null=True, blank=True)
    query = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    device_type = models.CharField(max_length=50, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'action']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['session_key', 'created_at']),
        ]

    def __str__(self):
        return f'{self.action} - {self.content_type}#{self.object_id}'
