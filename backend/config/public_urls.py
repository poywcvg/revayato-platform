"""Build public asset URLs from deployment configuration.

Media/HLS rows still prefer relative object keys. Download links may be full
http(s) URLs from external hosts, or legacy relative download keys.
"""

import re
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
    """Allow both relative object keys and absolute URLs.

    The ingestion pipeline stores external CDN URLs directly in video_url
    and download_key. Relative keys are still preferred for local uploads.
    """
    if not value:
        return
    raw = str(value).strip()
    if not raw:
        return
    # Reject clearly invalid values (bare schemes, empty hosts, etc.)
    parsed = urlsplit(raw)
    if parsed.scheme and not parsed.netloc:
        raise ValidationError('URL missing host.')


def validate_subtitle_tracks(value):
    """Validate subtitle metadata while keeping only relative object keys."""
    from apps.catalog.subtitle_contract import normalize_subtitle_tracks

    if value in (None, ''):
        return
    # Raises ValidationError on bad shapes; returns normalized list.
    normalize_subtitle_tracks(value)


def normalize_download_links(value):
    """Normalize download rows; prefer full http(s) URLs from external hosts."""
    if value in (None, ''):
        return []
    if isinstance(value, str):
        import json
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationError('Download links must be a JSON list.') from exc
    if not isinstance(value, list):
        raise ValidationError('Download links must be a list.')
    normalized = []
    from apps.catalog.provider_import.media_links import (
        has_malformed_video_suffix,
        is_dead_playback_host,
        is_trailer_download_link,
    )

    for item in value:
        if not isinstance(item, dict):
            raise ValidationError('Each download link must be an object.')
        raw = str(item.get('url') or item.get('key') or item.get('src') or '').strip()
        if not raw:
            continue
        if is_trailer_download_link(item):
            continue
        # Do not persist provider URLs which are already known to be permanently
        # dead, or media filenames corrupted by page markup/typos.
        if is_dead_playback_host(raw) or has_malformed_video_suffix(raw):
            continue
        parsed = urlsplit(raw)
        raw_label = str(item.get('label') or '').strip()
        label = raw_label or str(item.get('quality') or 'دانلود').strip()
        quality = str(item.get('quality') or '').strip()[:40]
        size_label = str(item.get('size_label') or item.get('size') or '').strip()[:40]
        season_number = item.get('season_number')
        episode_number = item.get('episode_number')
        season = str(item.get('season') or '').strip()[:80]
        episode = str(item.get('episode') or '').strip()[:80]
        row = {
            'label': label[:80] or 'دانلود',
            'quality': quality,
            'size_label': size_label,
        }
        kind = str(item.get('kind') or item.get('type') or '').strip()[:40]
        subtitle_type = str(item.get('subtitle_type') or '').strip()[:40]
        page_path = str(item.get('page_path') or '').strip()[:300]
        source = str(item.get('source') or '').strip()[:40]
        if kind:
            row['kind'] = kind
        if subtitle_type:
            row['subtitle_type'] = subtitle_type
        if page_path:
            row['page_path'] = page_path
        if source:
            row['source'] = source

        # Backfill season/episode grouping from legacy labels / provider metadata.
        meta = parse_season_episode_meta({
            'season': season,
            'episode': episode,
            'season_number': season_number,
            'episode_number': episode_number,
            'label': raw_label or label,
            'url': raw,
        })
        if meta['season']:
            row['season'] = meta['season']
        if meta['episode']:
            row['episode'] = meta['episode']
        if meta['season_number'] is not None:
            row['season_number'] = meta['season_number']
        if meta['episode_number'] is not None:
            row['episode_number'] = meta['episode_number']

        if parsed.scheme in {'http', 'https'} and parsed.netloc:
            # Keep external host URLs as-is (no Arvan/object-key rewrite).
            row['url'] = raw[:2000]
        else:
            key = object_key(raw)
            if not key:
                continue
            row['key'] = key
        normalized.append(row)
    return normalized


def validate_download_links(value):
    """Validate download link metadata (external URLs or relative keys)."""
    normalize_download_links(value)


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
    """Return a download URL for a relative object key."""
    return _build_url(value, settings.DOWNLOAD_CDN_BASE_URL, '/downloads')


def signed_media_url(value, **_kwargs):
    """Signing hook for future private media/CDN integrations."""
    return media_url(value)


def signed_download_url(value, **_kwargs):
    """Signing hook for future private download integrations."""
    return download_url(value)


def resolve_download_href(value):
    """Return a public href for a stored download value (URL or object key)."""
    raw = str(value or '').strip()
    if not raw:
        return ''
    parsed = urlsplit(raw)
    if parsed.scheme in {'http', 'https'} and parsed.netloc:
        return raw
    return signed_download_url(raw) or ''


def download_quality_rank(quality):
    """Higher number = better quality; used to order download rows for the public UI."""
    raw = str(quality or '').strip().lower().replace(' ', '')
    named = {
        '2160p': 60, '4k': 60, 'uhd': 60,
        '1440p': 50, '2k': 50,
        '1080p': 40, 'fhd': 40, 'fullhd': 40, 'full-hd': 40,
        '720p': 30, 'hd': 30,
        '480p': 20, 'sd': 20,
        '360p': 10, '240p': 5,
    }
    for key, rank in named.items():
        if key in raw:
            return rank
    match = re.search(r'(\d{3,4})\s*p?', raw)
    if match:
        return max(1, int(match.group(1)) // 36)
    return 0


def parse_season_episode_meta(item):
    """Return season/episode numbers + labels, backfilling from Persian/English text labels."""
    if not isinstance(item, dict):
        return {
            'season': '',
            'episode': '',
            'season_number': None,
            'episode_number': None,
        }

    season = str(item.get('season') or '').strip()[:80]
    episode = str(item.get('episode') or '').strip()[:80]
    season_number = item.get('season_number')
    episode_number = item.get('episode_number')
    haystack = ' '.join(
        part for part in (
            season,
            episode,
            str(item.get('label') or '').strip(),
            str(item.get('url') or item.get('key') or '').strip(),
        ) if part
    )

    if season_number is None or str(season_number).strip() == '':
        m_season = re.search(r'(?:فصل|season)\s*([0-9]{1,3})', haystack, flags=re.I)
        if m_season:
            try:
                season_number = int(m_season.group(1))
            except (TypeError, ValueError):
                season_number = None
    else:
        try:
            season_number = int(season_number)
        except (TypeError, ValueError):
            season_number = None

    if episode_number is None or str(episode_number).strip() == '':
        m_episode = re.search(r'(?:قسمت|episode)\s*([0-9]{1,3})', haystack, flags=re.I)
        if m_episode:
            try:
                episode_number = int(m_episode.group(1))
            except (TypeError, ValueError):
                episode_number = None
    else:
        try:
            episode_number = int(episode_number)
        except (TypeError, ValueError):
            episode_number = None

    if episode_number is None:
        try:
            from apps.catalog.provider_import.providers.cdn_link_parse import _episode_from_url
            parsed_season, parsed_episode = _episode_from_url(
                str(item.get('url') or item.get('key') or ''),
                surrounding=haystack,
                season_hint=season_number,
            )
            if parsed_episode is not None:
                episode_number = int(parsed_episode)
            if season_number is None and parsed_season is not None:
                season_number = int(parsed_season)
        except Exception:
            pass

    if not season and season_number is not None:
        season = f'فصل {season_number}'
    if not episode and episode_number is not None:
        episode = f'قسمت {episode_number}'

    return {
        'season': season,
        'episode': episode,
        'season_number': season_number,
        'episode_number': episode_number,
    }


def public_download_links(instance):
    """Build public download payloads (external URLs preferred over local keys), highest quality first."""
    links = []
    from apps.catalog.provider_import.media_links import is_trailer_download_link

    for item in (getattr(instance, 'download_links', None) or []):
        if not isinstance(item, dict):
            continue
        if is_trailer_download_link(item):
            continue
        href = resolve_download_href(item.get('url') or item.get('key') or '')
        if not href:
            continue
        meta = parse_season_episode_meta(item)
        row = {
            'label': item.get('label') or item.get('quality') or 'دانلود',
            'quality': item.get('quality') or '',
            'size_label': item.get('size_label') or '',
            'url': href,
        }
        kind = str(item.get('kind') or item.get('type') or '').strip()
        subtitle_type = str(item.get('subtitle_type') or '').strip()
        if kind:
            row['kind'] = kind
        if subtitle_type:
            row['subtitle_type'] = subtitle_type
        if meta['season']:
            row['season'] = meta['season']
        if meta['episode']:
            row['episode'] = meta['episode']
        if meta['season_number'] is not None:
            row['season_number'] = meta['season_number']
        if meta['episode_number'] is not None:
            row['episode_number'] = meta['episode_number']
        links.append(row)
    if links:
        return sorted(
            links,
            key=lambda row: (
                download_quality_rank(row.get('quality')),
                -(row.get('season_number') or 0),
                -(row.get('episode_number') or 0),
                row.get('quality') or '',
                row.get('label') or '',
            ),
            reverse=True,
        )
    download_key = getattr(instance, 'download_key', '') or ''
    href = resolve_download_href(download_key)
    if not href:
        return []
    quality = getattr(instance, 'quality', '') or ''
    return [{
        'label': quality or 'دانلود',
        'quality': quality,
        'size_label': '',
        'url': href,
    }]


def site_url(path=''):
    return _build_url(path, settings.SITE_BASE_URL, '') if path else settings.SITE_BASE_URL


def api_url(path=''):
    return _build_url(path, settings.API_BASE_URL, '/api') if path else settings.API_BASE_URL
