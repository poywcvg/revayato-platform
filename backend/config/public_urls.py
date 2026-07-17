"""Build public asset URLs from deployment configuration.

Only object keys should be persisted in the database.  These helpers keep
the URL construction in one place so CDN or download domains can be changed
without touching catalog rows.
"""

from urllib.parse import quote, urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError


def object_key(value):
    """Return a safe relative object key for a stored value.

    ``FieldFile`` values are accepted for convenience.  Absolute URLs from
    older rows are reduced to their path as a migration-safe fallback.
    """
    if not value:
        return ''
    value = getattr(value, 'name', value)
    value = str(value).strip()
    if not value:
        return ''
    parsed = urlsplit(value)
    was_absolute = bool(parsed.scheme or parsed.netloc)
    if was_absolute:
        value = parsed.path
    key = value.split('?', 1)[0].lstrip('/')
    if was_absolute:
        for prefix in ('media/', 'downloads/'):
            if key.startswith(prefix):
                key = key[len(prefix):]
                break
    return key


def validate_object_key(value):
    """Reject absolute URLs at write time; only relative object keys persist."""
    if not value:
        return
    parsed = urlsplit(str(value).strip())
    if parsed.scheme or parsed.netloc:
        raise ValidationError('Store a relative media/download object key, not a full URL.')


def validate_subtitle_tracks(value):
    """Validate subtitle metadata while keeping only relative object keys."""
    if value in (None, ''):
        return
    if not isinstance(value, list):
        raise ValidationError('Subtitle tracks must be a list.')
    for track in value:
        if not isinstance(track, dict):
            raise ValidationError('Each subtitle track must be an object.')
        key = track.get('key') or track.get('src')
        if not key:
            raise ValidationError('Each subtitle track needs an object key.')
        validate_object_key(key)


def _build_url(value, base_url, fallback_prefix):
    key = object_key(value)
    if not key:
        return ''
    encoded_key = quote(key, safe='/@:+,.-_~')
    base = str(base_url or '').strip().rstrip('/')
    if base:
        return f'{base}/{encoded_key}'
    return f'{fallback_prefix.rstrip("/")}/{encoded_key}'


def media_url(value):
    """Return a poster, image, HLS, subtitle or other media URL."""
    return _build_url(value, settings.MEDIA_CDN_BASE_URL, '/media')


def download_url(value):
    """Return a download URL; signing can be added behind this seam later."""
    return _build_url(value, settings.DOWNLOAD_CDN_BASE_URL, '/downloads')


def signed_media_url(value, **_kwargs):
    """Signing hook for future private media/CDN integrations."""
    return media_url(value)


def signed_download_url(value, **_kwargs):
    """Signing hook for future private download integrations."""
    return download_url(value)


def site_url(path=''):
    return _build_url(path, settings.SITE_BASE_URL, '') if path else settings.SITE_BASE_URL


def api_url(path=''):
    return _build_url(path, settings.API_BASE_URL, '/api') if path else settings.API_BASE_URL
