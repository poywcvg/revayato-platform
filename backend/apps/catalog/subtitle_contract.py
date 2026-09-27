"""Canonical subtitle track contract for storage and public API.

See docs/SUBTITLES.md for the full pipeline (Film2Media video + SubtitleStar cues).
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

from config.public_urls import media_url, object_key, validate_object_key

TRACK_LANGUAGE_DEFAULT = 'fa'
TRACK_LABEL_DEFAULT = 'فارسی'
ALLOWED_PROVIDERS = frozenset({'subtitlestar', 'subzone', 'softsub-ffmpeg', 'sidecar'})


def normalize_subtitle_track(track: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize one stored subtitle track (relative ``key`` only)."""
    if not isinstance(track, dict):
        return None
    raw_key = str(track.get('key') or track.get('src') or '').strip()
    if not raw_key:
        return None
    key = object_key(raw_key)
    if not key:
        return None
    validate_object_key(key)

    track_id = str(track.get('id') or 'fa').strip()[:80] or 'fa'
    language = str(track.get('language') or TRACK_LANGUAGE_DEFAULT).strip()[:16] or TRACK_LANGUAGE_DEFAULT
    label = str(track.get('label') or TRACK_LABEL_DEFAULT).strip()[:80] or TRACK_LABEL_DEFAULT
    provider = str(track.get('provider') or '').strip().lower()[:40]

    row: dict[str, Any] = {
        'id': track_id,
        'label': label,
        'language': language,
        'key': key,
        'default': bool(track.get('default', True)),
    }

    source_url = str(track.get('source_url') or '').strip()
    if source_url:
        row['source_url'] = source_url[:2000]

    if provider:
        row['provider'] = provider

    for meta_key in ('imdb_id', 'provider_page', 'release', 'sync_confidence'):
        value = str(track.get(meta_key) or '').strip()
        if value:
            row[meta_key] = value[:1000 if meta_key == 'provider_page' else 300]

    try:
        source_priority = int(track.get('source_priority'))
    except (TypeError, ValueError):
        source_priority = 0
    if source_priority > 0:
        row['source_priority'] = min(source_priority, 99)

    # Cumulative timing correction already BAKED into the stored VTT timestamps
    # by the auto-sync verifier (crowd consensus / FPS rescale). Informational —
    # the served file is already shifted, so players must NOT re-apply it; it is
    # kept for transparency, an "auto-synced" badge, and re-baking math.
    try:
        sync_offset = round(float(track.get('sync_offset')), 3)
    except (TypeError, ValueError):
        sync_offset = 0.0
    if sync_offset:
        row['sync_offset'] = max(-120.0, min(120.0, sync_offset))

    for num_key in ('season_number', 'episode_number'):
        raw = track.get(num_key)
        try:
            number = int(raw)
        except (TypeError, ValueError):
            continue
        if number > 0:
            row[num_key] = number

    return row


def normalize_subtitle_tracks(value: Any) -> list[dict[str, Any]]:
    """Normalize a list of subtitle tracks for DB storage."""
    if value in (None, ''):
        return []
    if not isinstance(value, list):
        raise ValidationError('Subtitle tracks must be a list.')
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(value):
        row = normalize_subtitle_track(item if isinstance(item, dict) else None)
        if not row:
            continue
        track_id = row['id']
        if track_id in seen_ids:
            row['id'] = f'{track_id}-{index + 1}'
        seen_ids.add(row['id'])
        normalized.append(row)
    return normalized


def subtitle_sync_signature(key: str) -> str:
    """Stable short signature of a served subtitle file (its storage key).

    Ties crowd sync votes to the exact VTT a viewer watched: when the verifier
    re-bakes or replaces the file the key changes, the signature changes, and
    every prior vote is transparently invalidated. Import-light (stdlib only) so
    it is safe to call from the storage contract.
    """
    import hashlib

    digest = hashlib.sha1(str(key or '').encode('utf-8')).hexdigest()
    return digest[:16]


def publicize_subtitle_tracks(tracks: Any) -> list[dict[str, Any]]:
    """Convert stored tracks to the public player contract (``src`` URLs)."""
    public: list[dict[str, Any]] = []
    for track in normalize_subtitle_tracks(tracks or []):
        key = track.get('key') or track.get('src')
        src = media_url(key) or None
        if not src:
            continue
        row = {k: v for k, v in track.items() if k not in {'key', 'src'}}
        row['src'] = src
        # Signature the player echoes back with a sync vote so the server can
        # bind the report to this exact file version.
        row['sync_sig'] = subtitle_sync_signature(key)
        public.append(row)
    return public


def track_has_playable_cues(tracks: Any) -> bool:
    for track in tracks or []:
        if not isinstance(track, dict):
            continue
        if str(track.get('key') or track.get('src') or '').strip():
            return True
    return False
