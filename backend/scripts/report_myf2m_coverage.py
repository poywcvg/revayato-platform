#!/usr/bin/env python3
"""Coverage report after the myf2m full import: playback, dub/sub, sizes, episodes."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if not (_APP_ROOT / 'config').is_dir():
    _APP_ROOT = Path('/app')
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.db.models import Q

from apps.catalog.models import Episode, Movie, Season, Series
from apps.catalog.subtitle_extract import (
    download_links_imply_dub,
    download_links_imply_softsub,
    download_links_imply_subtitle,
)


def link_rows(links):
    return [
        row for row in (links or [])
        if isinstance(row, dict) and str(row.get('url') or row.get('key') or '').strip()
    ]


def has_size(links):
    return any(str(row.get('size_label') or '').strip() for row in link_rows(links))


def has_playback(obj):
    if str(getattr(obj, 'video_url', '') or '').strip():
        return True
    for row in link_rows(getattr(obj, 'download_links', None)):
        url = str(row.get('url') or '').strip().lower()
        if url.startswith(('http://', 'https://')) and url.split('?', 1)[0].endswith(
            ('.mkv', '.mp4', '.m4v', '.webm', '.m3u8')
        ):
            return True
    return False


def report_model(label, qs):
    total = qs.count()
    published = qs.filter(is_published=True).count()
    with_links = qs.exclude(download_links=[]).exclude(download_links__isnull=True).count()
    stats = {'total': total, 'published': published, 'with_links': with_links}
    if total == 0:
        return stats
    count = {'playback': 0, 'dub': 0, 'sub': 0, 'size': 0}
    only_fields = ['id', 'is_published', 'download_links']
    if any(field.name == 'video_url' for field in qs.model._meta.fields):
        only_fields.append('video_url')
    for obj in qs.only(*only_fields).iterator(chunk_size=200):
        links = obj.download_links or []
        if has_playback(obj):
            count['playback'] += 1
        if download_links_imply_dub(links):
            count['dub'] += 1
        if download_links_imply_subtitle(links) or download_links_imply_softsub(links):
            count['sub'] += 1
        if has_size(links):
            count['size'] += 1
    for key, value in count.items():
        stats[key] = value
        stats[f'{key}_pct'] = f'{value / total * 100:.1f}%'
    return stats


def main():
    print('MOVIES', report_model('movies', Movie.objects.all()))
    print('SERIES', report_model('series', Series.objects.all()))
    print('SEASONS total:', Season.objects.count())
    print('EPISODES total:', Episode.objects.count())
    print(
        'EPISODES with video_url:',
        Episode.objects.exclude(video_url='').exclude(video_url__isnull=True).count(),
    )
    print(
        'EPISODES published:',
        Episode.objects.filter(is_published=True).count(),
    )
    print(
        'SERIES with published episodes:',
        Series.objects.filter(seasons__episodes__is_published=True).distinct().count(),
    )
    print(
        'SERIES missing playable episodes:',
        Series.objects.filter(
            seasons__episodes__is_published=True,
            seasons__episodes__video_url='',
        ).distinct().count(),
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
