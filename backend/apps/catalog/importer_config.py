from types import SimpleNamespace

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError


def _fallback_settings():
    return SimpleNamespace(
        pk=None,
        language=getattr(settings, 'TMDB_LANGUAGE', 'fa-IR'),
        fallback_language=getattr(settings, 'TMDB_FALLBACK_LANGUAGE', 'en-US'),
        region=getattr(settings, 'TMDB_REGION', 'IR'),
        daily_lookback_days=getattr(settings, 'CATALOG_SYNC_LOOKBACK_DAYS', 2),
        daily_lookahead_days=getattr(settings, 'CATALOG_SYNC_LOOKAHEAD_DAYS', 7),
        daily_max_pages=getattr(settings, 'CATALOG_SYNC_MAX_PAGES', 5),
        trending_window='day',
        trending_max_pages=3,
        import_people_images=True,
        cast_import_limit=15,
        fetch_imdb_ratings=True,
        feature_trending=True,
        auto_publish=getattr(settings, 'CATALOG_AUTO_PUBLISH', False),
        automation_enabled=getattr(settings, 'CATALOG_SYNC_ENABLED', False),
        automation_mode='daily',
        automation_interval_hours=getattr(settings, 'CATALOG_SYNC_INTERVAL_HOURS', 24),
        updated_at=None,
    )


def get_importer_settings():
    """Return the singleton config, including safely during migrations/startup."""
    from .models import CatalogImporterSettings

    try:
        return CatalogImporterSettings.get_solo()
    except (OperationalError, ProgrammingError):
        return _fallback_settings()
