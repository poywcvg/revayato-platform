"""The Android app's self-hosted update channel.

Revayato's APK is sideloaded from ``revayato.com/downloads/``, never installed
from Google Play, so Play's In-App Updates API has nothing to talk to. This
endpoint is the replacement: on launch the app asks what the newest build is
and, when it is behind, downloads and installs the answer itself.

Truth lives in ``downloads/app-release.json``, sitting beside the APKs it
describes and mounted read-only into the backend container. A release is then a
file copy plus two numbers rather than an image rebuild, and because the
manifest lives next to the bytes the two cannot drift apart.

Every read is **verified against the directory**: a manifest naming an APK that
is not actually on disk answers "no update" instead of advertising a download
that 404s halfway through. Same instinct as the media gates — when we cannot
confirm, we do the harmless thing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any

from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

logger = logging.getLogger(__name__)

#: An APK filename is a bare name in the downloads directory. Anything with a
#: separator in it is a path-traversal attempt, not a release.
_APK_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,110}\.apk$')

#: Hashing 3.4 MB is cheap but pointless to repeat; the key carries size+mtime
#: so a replaced file invalidates itself without anyone remembering to.
_HASH_TTL = 24 * 60 * 60

#: Two answers the app is allowed to cache at the CDN edge. A launch check that
#: is a few minutes stale is fine; a release that takes a few minutes to reach
#: everyone is also fine.
_PUBLIC_MAX_AGE = 300


class AppVersionThrottle(AnonRateThrottle):
    """One launch check per app start; a household shares one NAT address."""

    scope = 'app_version'


def _release_dir() -> str:
    return getattr(settings, 'APP_RELEASE_DIR', '') or ''


def _manifest_path() -> str:
    explicit = getattr(settings, 'APP_RELEASE_MANIFEST', '') or ''
    if explicit:
        return explicit
    directory = _release_dir()
    return os.path.join(directory, 'app-release.json') if directory else ''


def _download_base() -> str:
    base = getattr(settings, 'APP_DOWNLOAD_BASE_URL', '') or ''
    if base:
        return base.rstrip('/')
    site = (getattr(settings, 'SITE_BASE_URL', '') or '').rstrip('/')
    return f'{site}/downloads' if site else '/downloads'


def read_manifest() -> dict[str, Any] | None:
    """The release manifest as written on disk, or ``None`` when unusable.

    A missing, unreadable or malformed manifest is not an error condition for
    the caller — it simply means we have nothing to offer, which is exactly what
    an app with no newer build should be told.
    """
    path = _manifest_path()
    if not path:
        return None
    try:
        with open(path, 'rb') as handle:
            data = json.loads(handle.read().decode('utf-8'))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        logger.warning('app_release: manifest at %s is unreadable: %s', path, exc)
        return None
    return data if isinstance(data, dict) else None


def _apk_file(name: str) -> tuple[str, int] | None:
    """Absolute path and byte size of ``name``, or ``None`` if it is not there."""
    directory = _release_dir()
    if not directory or not name or not _APK_NAME.match(name):
        return None
    path = os.path.realpath(os.path.join(directory, name))
    if os.path.dirname(path) != os.path.realpath(directory):
        # Only reachable via a symlink pointing out of the directory; the regex
        # already rejects separators. Refuse rather than serve what is up there.
        logger.warning('app_release: %s resolves outside %s', name, directory)
        return None
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (path, stat.st_size) if stat.st_size > 0 else None


def _sha256(path: str, size: int) -> str:
    """Checksum of the published APK, so the app can refuse a truncated download."""
    try:
        mtime = int(os.path.getmtime(path))
    except OSError:
        return ''
    key = f'app_release:sha256:{os.path.basename(path)}:{size}:{mtime}'
    cached = cache.get(key)
    if cached:
        return cached
    digest = hashlib.sha256()
    try:
        with open(path, 'rb') as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(chunk)
    except OSError as exc:
        logger.warning('app_release: could not hash %s: %s', path, exc)
        return ''
    value = digest.hexdigest()
    cache.set(key, value, _HASH_TTL)
    return value


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _notes(raw: Any) -> list[str]:
    if isinstance(raw, str):
        lines = [line.strip() for line in raw.splitlines()]
    elif isinstance(raw, (list, tuple)):
        lines = [str(line).strip() for line in raw]
    else:
        return []
    return [line for line in lines if line][:8]


def latest_release() -> dict[str, Any] | None:
    """The newest build we can actually hand out, or ``None``.

    Returns ``None`` — not a half-filled dict — whenever the manifest is absent,
    names no version, or points at an APK that is missing from the directory.
    """
    manifest = read_manifest()
    if not manifest:
        return None

    version_code = _int(manifest.get('version_code'))
    version_name = str(manifest.get('version_name') or '').strip()
    apk_name = str(manifest.get('apk') or '').strip()
    if version_code <= 0 or not version_name or not apk_name:
        logger.warning('app_release: manifest is incomplete (%s)', sorted(manifest))
        return None

    located = _apk_file(apk_name)
    if located is None:
        # The one failure worth shouting about: someone bumped the manifest and
        # forgot the file, which would otherwise break every app on launch.
        logger.error('app_release: manifest names %s but it is not in %s',
                     apk_name, _release_dir())
        return None
    path, size = located

    return {
        'package': str(manifest.get('package') or 'com.revayato.app'),
        'version_code': version_code,
        'version_name': version_name,
        # Below this, the installed build is considered unusable (a broken API
        # contract, say) and the app refuses to be dismissed. 0 means never.
        'min_supported_version_code': max(0, _int(manifest.get('min_supported_version_code'))),
        'download_url': f'{_download_base()}/{apk_name}',
        'size_bytes': size,
        'sha256': _sha256(path, size),
        'released_at': str(manifest.get('released_at') or ''),
        'notes': _notes(manifest.get('notes')),
        'min_sdk': _int(manifest.get('min_sdk'), 24),
    }


@api_view(['GET'])
@throttle_classes([AppVersionThrottle])
def app_version(request):
    """What the newest Android build is, and whether the caller needs it.

    ``?version_code=`` lets the server answer the question rather than only
    describe the world, so the "is this update required" policy can change
    without shipping an app release. The app still compares locally, because a
    build old enough to matter may predate the parameter.
    """
    release = latest_release()
    if release is None:
        # Nothing to offer. A 200 with `available: false` keeps the client's
        # path simple — an error here would look like a broken launch check.
        return Response(
            {'available': False, 'update_available': False, 'mandatory': False},
            status=status.HTTP_200_OK,
            headers={'Cache-Control': f'public, max-age={_PUBLIC_MAX_AGE}'},
        )

    installed_raw = request.query_params.get('version_code')
    installed = _int(installed_raw, -1) if installed_raw not in (None, '') else -1

    update_available = installed >= 0 and installed < release['version_code']
    mandatory = (
        update_available
        and release['min_supported_version_code'] > 0
        and installed < release['min_supported_version_code']
    )

    payload = dict(release)
    payload['available'] = True
    payload['update_available'] = update_available
    payload['mandatory'] = mandatory
    return Response(
        payload,
        status=status.HTTP_200_OK,
        headers={'Cache-Control': f'public, max-age={_PUBLIC_MAX_AGE}'},
    )
