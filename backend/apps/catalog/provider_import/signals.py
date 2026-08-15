"""Signals that auto-populate provider download links when titles are published."""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _auto_crawl_enabled() -> bool:
    return bool(getattr(settings, 'MYF2M_AUTO_CRAWL_ON_PUBLISH', True))


def _is_excluded_iranian(instance) -> bool:
    if not bool(getattr(settings, 'CATALOG_EXCLUDE_IRANIAN', True)):
        return False
    from apps.catalog.iranian import is_iranian_catalog_item
    return is_iranian_catalog_item(instance)


def _movie_is_published(instance) -> bool:
    status = getattr(instance, 'publication_status', '') or ''
    return bool(getattr(instance, 'is_published', False) or status == 'published')


def _has_download_links(instance) -> bool:
    from apps.catalog.provider_import.media_links import is_playable_video_link

    links = getattr(instance, 'download_links', None) or []
    if not isinstance(links, list):
        return False
    for item in links:
        if not isinstance(item, dict):
            continue
        if is_playable_video_link(item) or str(item.get('key') or '').strip():
            return True
    return False


def enqueue_provider_movie_auto_crawl(movie_id: int, *, replace: bool = True, reason: str = '') -> bool:
    """Enqueue Celery crawl for a movie. Returns True when queued."""
    if not movie_id:
        return False

    from django.core.cache import cache

    lock_key = f'myf2m-enqueue-movie-{int(movie_id)}'
    if not cache.add(lock_key, reason or '1', timeout=90):
        logger.info('Skip duplicate myf2m enqueue for movie %s (reason=%s)', movie_id, reason)
        return False

    def _enqueue():
        from .tasks import auto_crawl_myf2m_movie_downloads_task

        try:
            async_result = auto_crawl_myf2m_movie_downloads_task.delay(int(movie_id), replace)
            logger.info(
                'Queued myf2m auto-crawl for movie %s (task=%s reason=%s replace=%s)',
                movie_id, async_result.id, reason or 'unspecified', replace,
            )
        except Exception:
            cache.delete(lock_key)
            logger.exception('Failed to enqueue myf2m auto-crawl for movie %s', movie_id)

    transaction.on_commit(_enqueue)
    return True


def enqueue_provider_series_auto_crawl(series_id: int, *, replace: bool = True, reason: str = '') -> bool:
    if not series_id:
        return False

    from django.core.cache import cache

    lock_key = f'myf2m-enqueue-series-{int(series_id)}'
    if not cache.add(lock_key, reason or '1', timeout=90):
        logger.info('Skip duplicate myf2m enqueue for series %s (reason=%s)', series_id, reason)
        return False

    def _enqueue():
        from .tasks import auto_crawl_myf2m_series_downloads_task

        try:
            async_result = auto_crawl_myf2m_series_downloads_task.delay(int(series_id), replace)
            logger.info(
                'Queued myf2m auto-crawl for series %s (task=%s reason=%s replace=%s)',
                series_id, async_result.id, reason or 'unspecified', replace,
            )
        except Exception:
            cache.delete(lock_key)
            logger.exception('Failed to enqueue myf2m auto-crawl for series %s', series_id)

    transaction.on_commit(_enqueue)
    return True


@receiver(pre_save, dispatch_uid='provider_remember_movie_publish_state')
def remember_movie_publish_state(sender, instance, **kwargs):
    from apps.catalog.models import Movie

    if sender is not Movie:
        return
    if not instance.pk:
        instance._provider_was_published = False
        return
    previous = (
        Movie.objects.filter(pk=instance.pk)
        .values_list('is_published', 'publication_status')
        .first()
    )
    if not previous:
        instance._provider_was_published = False
        return
    was_published, previous_status = previous
    instance._provider_was_published = bool(was_published or previous_status == 'published')


@receiver(pre_save, dispatch_uid='provider_remember_series_publish_state')
def remember_series_publish_state(sender, instance, **kwargs):
    from apps.catalog.models import Series

    if sender is not Series:
        return
    if not instance.pk:
        instance._provider_was_published = False
        return
    previous = Series.objects.filter(pk=instance.pk).values_list('is_published', flat=True).first()
    instance._provider_was_published = bool(previous)


@receiver(post_save, dispatch_uid='provider_auto_crawl_on_movie_publish')
def auto_crawl_on_movie_publish(sender, instance, created, **kwargs):
    from apps.catalog.models import Movie

    if sender is not Movie:
        return
    if not _auto_crawl_enabled():
        return
    if _is_excluded_iranian(instance):
        return
    if not _movie_is_published(instance):
        return
    if _has_download_links(instance):
        return

    was_published = bool(getattr(instance, '_provider_was_published', False))
    newly_published = created or not was_published
    update_fields = kwargs.get('update_fields')
    publish_fields_touched = update_fields is None or bool(
        set(update_fields or []) & {'is_published', 'publication_status', 'download_links'}
    )
    if not (newly_published or publish_fields_touched):
        return

    enqueue_provider_movie_auto_crawl(
        instance.pk,
        replace=True,
        reason='movie_publish' if newly_published else 'movie_published_missing_links',
    )


@receiver(post_save, dispatch_uid='provider_auto_crawl_on_series_publish')
def auto_crawl_on_series_publish(sender, instance, created, **kwargs):
    from apps.catalog.models import Series

    if sender is not Series:
        return
    if not _auto_crawl_enabled():
        return
    if _is_excluded_iranian(instance):
        return
    if not getattr(instance, 'is_published', False):
        return
    if _has_download_links(instance):
        return

    was_published = bool(getattr(instance, '_provider_was_published', False))
    newly_published = created or not was_published
    update_fields = kwargs.get('update_fields')
    publish_fields_touched = update_fields is None or bool(
        set(update_fields or []) & {'is_published', 'download_links'}
    )
    if not (newly_published or publish_fields_touched):
        return

    enqueue_provider_series_auto_crawl(
        instance.pk,
        replace=True,
        reason='series_publish' if newly_published else 'series_published_missing_links',
    )
