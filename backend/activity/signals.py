from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from django.conf import settings
from django.contrib.contenttypes.models import ContentType

from activity.models import UserActivity, SearchLog, SearchSuggestion


# create_user_watchlist receiver removed: it referenced a 'name' field and
# container-style list_type values ('favorites', 'watched') that no longer
# exist on activity.models.UserWatchlist (per-item content_type/object_id
# schema), so it crashed on every user creation. Watchlist/favorite
# membership is now handled per-item by apps.engagement.WatchlistItem.


@receiver(post_save, sender=SearchLog)
def update_search_suggestions(sender, instance, created, **kwargs):
    if created and instance.normalized_query:
        suggestion, _ = SearchSuggestion.objects.get_or_create(
            normalized_query=instance.normalized_query,
            defaults={
                'query': instance.query,
                'language': instance.user.profile.preferred_languages[0] if hasattr(instance.user, 'profile') and instance.user.profile.preferred_languages else 'fa',
            }
        )
        if not created:
            suggestion.count += 1
            suggestion.save(update_fields=['count', 'last_searched'])