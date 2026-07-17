from celery import shared_task
from django.conf import settings
from django.core.management import call_command


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 3})
def sync_catalog_task(self):
    if not getattr(settings, 'CATALOG_SYNC_ENABLED', False):
        return {'status': 'disabled'}
    call_command('sync_catalog')


@shared_task
def publish_ready_catalog_task():
    if not getattr(settings, 'CATALOG_AUTO_PUBLISH', False):
        return {'status': 'disabled'}
    call_command('publish_ready_catalog')
