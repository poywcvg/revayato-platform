from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.catalog'

    def ready(self):
        # Register provider-import signals (auto-crawl download links on publish).
        from apps.catalog.provider_import import signals  # noqa: F401
        from apps.catalog.cache import connect_cache_signals

        connect_cache_signals()
