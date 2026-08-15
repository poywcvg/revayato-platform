"""Repair UTF-8→CP1256 mojibake in stored WebVTT tracks and bust CDN cache keys."""

from __future__ import annotations

import os
import re
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.core.files.base import ContentFile  # noqa: E402
from django.core.files.storage import default_storage  # noqa: E402

from apps.catalog.cache import bump_catalog_cache_version  # noqa: E402
from apps.catalog.models import Episode, Movie  # noqa: E402
from apps.catalog.subtitle_extract import _sanitize_webvtt  # noqa: E402

MOJIBAKE_MARKERS = re.compile(r'ظˆ|ظ…|ظ†|غŒ|ظ€|â€')


def persian_chars(text: str) -> list[str]:
    return re.findall(r'[\u0600-\u06ff]', text)


def is_mojibake(text: str) -> bool:
    sample = text[:8000]
    chars = persian_chars(sample)
    if len(chars) < 40:
        return False
    taa = sample.count('ط')
    zaa = sample.count('ظ')
    density = (taa + zaa) / max(1, len(chars))
    markers = len(MOJIBAKE_MARKERS.findall(sample))
    return density >= 0.28 or markers >= 12


def try_repair(text: str) -> str | None:
    for enc in ('cp1256', 'windows-1256'):
        try:
            fixed = text.encode(enc).decode('utf-8')
        except Exception:
            continue
        chars = persian_chars(fixed)
        if len(chars) < 40 or is_mojibake(fixed):
            continue
        if (fixed.count('ط') / len(chars)) > 0.25:
            continue
        return fixed
    return None


def new_key(old_key: str) -> str:
    if old_key.endswith('-u8.vtt'):
        return old_key
    if old_key.endswith('.vtt'):
        return f'{old_key[:-4]}-u8.vtt'
    return f'{old_key}-u8.vtt'


def main() -> int:
    key_owners: dict[str, int] = {}
    for model in (Movie, Episode):
        for obj in model.objects.exclude(subtitle_tracks=[]).exclude(subtitle_tracks__isnull=True).iterator(chunk_size=200):
            for track in (obj.subtitle_tracks or []):
                if not isinstance(track, dict):
                    continue
                key = str(track.get('key') or '').strip()
                if key:
                    key_owners[key] = key_owners.get(key, 0) + 1

    repaired = 0
    skipped_ok = 0
    failed = 0
    key_map: dict[str, str] = {}

    for old_key in key_owners:
        if not default_storage.exists(old_key):
            failed += 1
            continue
        raw = default_storage.open(old_key, 'rb').read()
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            text = None
            for enc in ('utf-16', 'cp1256', 'windows-1256'):
                try:
                    candidate = raw.decode(enc)
                except Exception:
                    continue
                if persian_chars(candidate):
                    text = candidate
                    break
            if text is None:
                failed += 1
                continue
            fixed = text if not is_mojibake(text) else try_repair(text)
            if fixed is None:
                failed += 1
                continue
        else:
            if not is_mojibake(text):
                skipped_ok += 1
                continue
            fixed = try_repair(text)
            if fixed is None:
                failed += 1
                continue

        body = fixed if fixed.lstrip().upper().startswith('WEBVTT') else f'WEBVTT\n\n{fixed}'
        out = _sanitize_webvtt(body).encode('utf-8')
        dest = new_key(old_key)
        if default_storage.exists(dest):
            default_storage.delete(dest)
        saved = default_storage.save(dest, ContentFile(out))
        key_map[old_key] = saved
        repaired += 1

    updated_movies = 0
    updated_episodes = 0
    for model, label in ((Movie, 'movie'), (Episode, 'episode')):
        for obj in model.objects.exclude(subtitle_tracks=[]).exclude(subtitle_tracks__isnull=True).iterator(chunk_size=200):
            tracks = obj.subtitle_tracks or []
            changed = False
            new_tracks = []
            for track in tracks:
                if not isinstance(track, dict):
                    new_tracks.append(track)
                    continue
                row = dict(track)
                key = str(row.get('key') or '').strip()
                if key in key_map:
                    row['key'] = key_map[key]
                    row.pop('src', None)
                    changed = True
                new_tracks.append(row)
            if changed:
                obj.subtitle_tracks = new_tracks
                obj.save(update_fields=['subtitle_tracks', 'updated_at'])
                if label == 'movie':
                    updated_movies += 1
                else:
                    updated_episodes += 1

    bump_catalog_cache_version()
    print(f'unique_keys={len(key_owners)}')
    print(f'repaired={repaired} already_ok={skipped_ok} failed={failed}')
    print(f'updated_movies={updated_movies} updated_episodes={updated_episodes}')
    for old, new in list(key_map.items())[:3]:
        sample = default_storage.open(new, 'rb').read(180).decode('utf-8', errors='replace')
        print(f'map {old} -> {new}')
        print(sample)
    return 0


if __name__ == '__main__':
    sys.exit(main())
