from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.catalog'

    def ready(self):
        # Register provider-import signals (auto-crawl download links on publish).
        from apps.catalog.provider_import import signals  # noqa: F401
        from apps.catalog.cache import connect_cache_signals

        connect_cache_signals()

        from apps.catalog.slugs import connect_slug_signals

        connect_slug_signals()

        from apps.catalog.link_sizes import connect_link_size_signals

        connect_link_size_signals()

        from apps.catalog.indexnow import connect_indexnow_signals

        connect_indexnow_signals()

        # Only ever true in the stream-gateway container, which is the one
        # process namespace where abandoned ffmpeg sessions are visible.
        from apps.catalog.stream_gateway import start_reaper

        start_reaper()
