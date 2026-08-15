"""Extract soft subtitle tracks into WebVTT for the HTML5 online player."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.catalog.provider_import.media_links import (
    DEAD_PLAYBACK_HOST_MARKERS as _DEAD_SOFTSUB_HOST_MARKERS,
    browser_playback_score,
    is_playable_video_link,
)

logger = logging.getLogger(__name__)


def ffmpeg_available() -> bool:
    return bool(shutil.which('ffmpeg'))


def _link_blob(item: dict | None) -> str:
    if not isinstance(item, dict):
        return ''
    return ' '.join([
        str(item.get('label') or ''),
        str(item.get('kind') or ''),
        str(item.get('type') or ''),
        str(item.get('subtitle_type') or ''),
        str(item.get('url') or ''),
    ]).lower()


def _url_path(item: dict | None) -> str:
    if not isinstance(item, dict):
        return ''
    return urlsplit(str(item.get('url') or '').strip()).path.lower()


# Film2Media SoftSub folder markers (CDN paths; often mislabeled hardsub on the page).
_SOFTSUB_PATH_TOKENS = (
    '/soft/', '/softsub/', '/soft-sub/', '/soft_sub/',
    '/sub/', '/rsub/', '/blusub/', '/subblu/', '/softblu/',
)


def url_implies_softsub(item: dict | None) -> bool:
    """CDN Soft/ SoftSub paths win over provider labels like «زیرنویس چسبیده».

    Bare ``Farsi.Sub`` in a filename is NOT enough: Film2Media also stamps that
    token on burned-in HardSub encodes. Require an explicit Soft folder or
    SoftSub release marker.
    """
    path = _url_path(item)
    if not path:
        return False
    if any(token in path for token in ('/soft/', '/softsub/', '/soft-sub/', '/soft_sub/')):
        return True
    # Film2Media /SUB|RSUB|BluSUB|SUBBlu + Farsi.Sub SoftSub encodes.
    if re.search(r'/(?:r?sub|blusub|subblu|softblu|softsub)/', path, re.I) and re.search(
        r'(?:farsi[\._-]?sub|fa[\._-]?sub|softsub|soft[\._-]?sub)',
        path,
        re.I,
    ):
        return True
    # Explicit SoftSub / Soft.Sub release names only (not bare Farsi.Sub).
    return bool(re.search(
        r'(?:^|[._/\-])(softsub|soft[\._-]?sub)(?:[._/\-]|$)',
        path,
        re.I,
    ))


def url_implies_hardsub(item: dict | None) -> bool:
    path = _url_path(item)
    if not path or url_implies_softsub(item):
        return False
    if any(token in path for token in ('/hard/', '/hardsub/', '/hard-sub/', '/hard_sub/')):
        return True
    # Dornatv / Film2Media release names: Title.1080p.HardSub.mkv
    return bool(re.search(
        r'(?:^|[._/\-])(hardsub|hard[\._-]?sub)(?:[._/\-]|$)',
        path,
        re.I,
    ))


def url_implies_dub(item: dict | None) -> bool:
    """CDN / filename evidence for Persian dub (incl. Dornatv «Duble» spelling)."""
    path = _url_path(item)
    if not path:
        return False
    if any(token in path for token in ('/dubbed/', '/dub/', '/dual')):
        return True
    # Dornatv uses «Duble» / «DUBLE»; Film2Media uses Farsi.Dubbed.
    return bool(re.search(
        r'(?:^|[._/\-])(duble|doble|dubbed|dubbled|farsi[\._-]?dub(?:bed)?|fa[\._-]?dub)(?:[._/\-]|$)',
        path,
        re.I,
    ))


def looks_like_hardsub_link(item: dict | None) -> bool:
    if not isinstance(item, dict):
        return False
    # Soft encodes are often mislabeled «چسبیده» by providers; trust the CDN path.
    if url_implies_softsub(item):
        return False
    if url_implies_dub(item):
        return False
    if url_implies_hardsub(item):
        return True
    blob = _link_blob(item)
    kind = str(item.get('kind') or item.get('type') or '').lower()
    subtitle_type = str(item.get('subtitle_type') or '').lower()
    if kind in {'hardsub', 'hard-sub', 'hard_sub'}:
        return True
    if 'hard' in subtitle_type:
        return True
    return any(
        token in blob
        for token in (
            'hardsub', 'hard-sub', 'hard_sub', 'هاردساب',
            'زیرنویس چسبیده', 'زیرنویس‌چسبیده', 'چسبیده',
        )
    )


def looks_like_softsub_link(item: dict | None) -> bool:
    if not isinstance(item, dict):
        return False
    if url_implies_softsub(item):
        return True
    if url_implies_dub(item) or looks_like_hardsub_link(item):
        return False
    blob = _link_blob(item)
    soft_markers = (
        'softsub', 'soft-sub', 'soft_sub', 'soft sub',
        'زیرنویس نرم', 'سافت ساب', 'سافت‌ساب',
    )
    if any(marker in blob for marker in soft_markers):
        return True
    # Bare Farsi.Sub / Fa.Sub only counts as Soft when the provider did not
    # explicitly mark the row as HardSub (those are usually burned-in).
    kind = str(item.get('kind') or item.get('type') or '').lower()
    subtitle_type = str(item.get('subtitle_type') or '').lower()
    if kind not in {'hardsub', 'hard-sub', 'hard_sub', 'video', 'download'} and 'hard' not in subtitle_type:
        if any(marker in blob for marker in ('farsi.sub', 'farsi_sub', 'farsi-sub', 'fa.sub')):
            return True
    if kind in {'subtitle', 'sub', 'softsub'} and subtitle_type in {'soft', 'softsub', ''}:
        return True
    if 'soft' in subtitle_type:
        return True
    # Standalone subtitle files are always soft (toggleable) tracks.
    url = str(item.get('url') or '').lower()
    if any(url.split('?', 1)[0].endswith(ext) for ext in ('.vtt', '.webvtt', '.srt', '.ass', '.ssa')):
        return True
    return False


def looks_like_subtitle_link(item: dict | None) -> bool:
    if looks_like_softsub_link(item) or looks_like_hardsub_link(item):
        return True
    blob = _link_blob(item)
    kind = str(item.get('kind') or item.get('type') or '').lower()
    if kind in {'video', 'download', 'nosub', ''}:
        return False
    return any(token in blob for token in ('subtitle', 'زیرنویس', 'softsub', 'hardsub'))


def looks_like_dub_link(item: dict | None) -> bool:
    if not isinstance(item, dict):
        return False
    if url_implies_dub(item):
        return True
    blob = _link_blob(item)
    kind = str(item.get('kind') or item.get('type') or '').lower()
    if kind in {'dubbed', 'dub', 'persian_dub', 'farsi_dub', 'dubbled', 'duble'}:
        return True
    return any(token in blob for token in (
        'dubbed', 'dubbled', 'duble', 'doble', 'دوبله', 'دوبله فارسی',
        'persian dub', 'farsi dub',
    ))


def download_links_imply_subtitle(links) -> bool:
    return any(looks_like_subtitle_link(item) for item in (links or []) if isinstance(item, dict))


def download_links_imply_softsub(links) -> bool:
    return any(looks_like_softsub_link(item) for item in (links or []) if isinstance(item, dict))


def download_links_imply_hardsub(links) -> bool:
    return any(looks_like_hardsub_link(item) for item in (links or []) if isinstance(item, dict))


def download_links_imply_dub(links) -> bool:
    return any(looks_like_dub_link(item) for item in (links or []) if isinstance(item, dict))


KIND_LABEL_FA = {
    'dubbed': 'دوبله فارسی',
    'softsub': 'زیرنویس نرم',
    'hardsub': 'زیرنویس چسبیده',
    'nosub': 'بدون زیرنویس',
}


def classify_download_link_kind(
    url: str = '',
    *,
    surrounding: str = '',
    section_kind: str = '',
    hinted_kind: str = '',
) -> tuple[str, str]:
    """Canonical (kind, subtitle_type). CDN filename evidence beats Dornatv headings.

    Dornatv often labels SoftSub encodes under «زیرنویس چسبیده» and spells dub
    as «Duble». Filename tokens (SoftSub / HardSub / Duble) always win.
    """
    item = {
        'url': str(url or ''),
        'label': str(surrounding or ''),
        'kind': str(hinted_kind or section_kind or ''),
        'type': str(hinted_kind or section_kind or ''),
    }
    path = _url_path(item)
    surrounding_text = str(surrounding or '')
    section = str(section_kind or '').strip().lower()

    # 1) Dub from filename (Duble/Dubbed) or section — before subtitle headings.
    if url_implies_dub(item) or section in {'dubbed', 'dub', 'dubbled', 'duble'}:
        return 'dubbed', ''
    if 'دوبله' in surrounding_text and not url_implies_softsub(item) and not url_implies_hardsub(item):
        return 'dubbed', ''

    # 2) SoftSub from CDN / SoftSub release name — wins over «چسبیده» headings.
    if url_implies_softsub(item):
        return 'softsub', 'soft'
    if section in {'soft', 'softsub', 'soft-sub', 'soft_sub'}:
        return 'softsub', 'soft'
    soft_heading = (
        any(token in surrounding_text for token in ('سافت', 'زیرنویس نرم'))
        or 'softsub' in surrounding_text.lower()
        or 'soft sub' in surrounding_text.lower()
    )
    if soft_heading and 'چسبیده' not in surrounding_text:
        return 'softsub', 'soft'

    # 3) HardSub folders / HardSub release names.
    if url_implies_hardsub(item):
        return 'hardsub', 'hard'
    if '/nosub/' in path or 'بدون زیرنویس' in surrounding_text or section in {'nosub', 'no-sub'}:
        return 'nosub', ''

    if section in {'hardsub', 'hard', 'hard-sub', 'hard_sub'}:
        return 'hardsub', 'hard'
    if any(token in surrounding_text for token in ('چسبیده', 'هاردساب')) or 'hardsub' in surrounding_text.lower():
        return 'hardsub', 'hard'
    if re.search(r'(?:^|[._/\-])(farsi[\._-]?sub|fa[\._-]?sub)(?:[._/\-]|$)', path, re.I):
        # Bare Farsi.Sub outside Soft/SUB Soft folders ⇒ burned-in hardsub.
        return 'hardsub', 'hard'

    hinted = str(hinted_kind or '').strip().lower()
    if hinted in {'dubbed', 'dub', 'dubbled', 'duble'}:
        return 'dubbed', ''
    if hinted in {'hardsub', 'hard', 'hard-sub', 'hard_sub'}:
        return 'hardsub', 'hard'
    if hinted in {'nosub', 'no-sub'}:
        return 'nosub', ''
    if hinted in {'softsub', 'subtitle', 'sub', 'soft', 'soft-sub', 'soft_sub'}:
        return 'softsub', 'soft'
    if 'soft' in section or 'subtitle' in section:
        return 'softsub', 'soft'
    # Plain video with no dub/sub evidence — do NOT claim SoftSub.
    return 'video', ''


def kind_label_fa(kind: str) -> str:
    return KIND_LABEL_FA.get(str(kind or '').strip().lower(), '')


def apply_kind_label(row: dict) -> dict:
    """Keep Persian kind prefixes precise (soft vs hard vs dub)."""
    if not isinstance(row, dict):
        return row
    kind = str(row.get('kind') or '').strip().lower()
    quality = str(row.get('quality') or '').strip()
    current = str(row.get('label') or '').strip()
    stale_prefixes = (
        'زیرنویس فارسی', 'زیرنویس نرم', 'زیرنویس چسبیده',
        'دوبله فارسی', 'بدون زیرنویس', 'دانلود',
    )
    if row.get('episode_number') not in (None, ''):
        return row
    prefix = kind_label_fa(kind)
    if not prefix:
        # Plain video: drop stale dub/sub prefixes so UI quality stays honest.
        if quality and (
            not current
            or any(current == p or current.startswith(f'{p} ·') or current.startswith(f'{p} ') for p in stale_prefixes)
        ):
            row['label'] = quality[:80]
        return row
    desired = prefix + (f' · {quality}' if quality else '')
    if (
        not current
        or any(current == p or current.startswith(f'{p} ·') or current.startswith(f'{p} ') for p in stale_prefixes)
        or (quality and current == quality)
    ):
        row['label'] = desired[:80]
    return row


def canonicalize_download_link(row: dict | None) -> dict:
    """Rewrite kind/type/subtitle_type/label from URL evidence."""
    if not isinstance(row, dict):
        return {}
    out = dict(row)
    url = str(out.get('url') or out.get('stream_url') or '').strip()
    surrounding = ' '.join(
        str(out.get(key) or '')
        for key in ('label', 'section', 'section_kind', 'heading')
    )
    kind, subtitle_type = classify_download_link_kind(
        url,
        surrounding=surrounding,
        section_kind=str(out.get('section_kind') or out.get('section') or ''),
        hinted_kind=str(out.get('kind') or out.get('type') or ''),
    )
    probe = {'url': url, 'kind': kind, 'label': surrounding, 'type': kind}
    # Filename evidence always wins (Dornatv SoftSub-under-چسبیده / Duble).
    if url_implies_dub(probe):
        kind, subtitle_type = 'dubbed', ''
    elif url_implies_softsub(probe):
        kind, subtitle_type = 'softsub', 'soft'
    elif url_implies_hardsub(probe):
        kind, subtitle_type = 'hardsub', 'hard'

    out['kind'] = kind
    out['type'] = kind
    if kind in {'softsub', 'hardsub'}:
        out['subtitle_type'] = subtitle_type or ('soft' if kind == 'softsub' else 'hard')
    else:
        out['subtitle_type'] = ''
    # Prefer CDN filename for quality when present.
    from apps.catalog.provider_import.providers.cdn_link_parse import _quality_from
    provided_quality = str(out.get('quality') or '').strip()
    quality = _quality_from(url, provided_quality or str(out.get('label') or ''))
    # Film2Media exposes the exact source label (for example
    # ``BluRay 1080p 10bit x265``) in each download row. Keep that richer
    # provider value instead of reducing it to resolution alone.
    if str(out.get('source') or '').strip().lower() == 'myf2m' and provided_quality:
        out['quality'] = provided_quality[:40]
    elif quality:
        out['quality'] = quality
    return apply_kind_label(out)


def canonicalize_download_links(links) -> tuple[list[dict], bool]:
    """Return (rows, changed) with every encode reclassified from URL evidence."""
    from apps.catalog.provider_import.media_links import (
        has_malformed_video_suffix,
        is_dead_playback_host,
    )

    changed = False
    out: list[dict] = []
    for item in links or []:
        if not isinstance(item, dict):
            continue
        raw = str(item.get('url') or item.get('key') or '').strip()
        if is_dead_playback_host(raw) or has_malformed_video_suffix(raw):
            changed = True
            continue
        fixed = canonicalize_download_link(item)
        if (
            fixed.get('kind') != item.get('kind')
            or fixed.get('type') != item.get('type')
            or fixed.get('subtitle_type') != item.get('subtitle_type')
            or fixed.get('label') != item.get('label')
        ):
            changed = True
        out.append(fixed)
    return out, changed


def _download_link_identity(row: dict) -> str:
    """Stable identity across CDN signature refreshes (ignore query + kind drift).

    Kind is excluded so SoftSub rows mislabeled as hardsub merge onto the same
    path after reclassification instead of duplicating.
    """
    raw = str(row.get('url') or row.get('key') or '').strip()
    path = urlsplit(raw).path.lower().rstrip('/')
    season = row.get('season_number')
    episode = row.get('episode_number')
    return f'{path}|{season}|{episode}'


def coalesce_download_links(existing, incoming, *, replace: bool = True) -> list[dict]:
    """Merge crawl results without wiping uncovered qualities / dub / SoftSub.

    Incoming rows win when the CDN path (+ episode) matches — that refreshes
    signed URLs and corrects kind labels. Every other existing encode is kept so
    multi-provider crawls and re-crawls accumulate a complete quality set.
    """
    incoming, _ = canonicalize_download_links(
        [item for item in (incoming or []) if isinstance(item, dict)],
    )
    existing, _ = canonicalize_download_links(
        [item for item in (existing or []) if isinstance(item, dict)],
    )
    if not incoming:
        return list(existing)
    if not existing:
        return list(incoming)

    by_id: dict[str, dict] = {}
    order: list[str] = []

    # Seed with existing so uncovered dub/soft/hard/quality rows survive.
    for row in existing:
        key = _download_link_identity(row)
        if not key.startswith('|'):
            if key not in by_id:
                order.append(key)
            by_id[key] = row

    for row in incoming:
        key = _download_link_identity(row)
        if key.startswith('|'):
            continue
        if key not in by_id:
            order.append(key)
        # Incoming always overwrites same identity (fresher signature / metadata).
        by_id[key] = row

    if not replace:
        # Append-only semantics for callers that pass replace=False explicitly:
        # still prefer identity merge above (already done).
        return [by_id[key] for key in order]

    return [by_id[key] for key in order]


def _http_url_reachable(url: str, *, timeout_seconds: int = 12) -> bool:
    """True when a SoftSub CDN URL still accepts byte-range / HEAD requests."""
    if not url:
        return False
    host = urlsplit(url).netloc.lower()
    if any(marker in host for marker in _DEAD_SOFTSUB_HOST_MARKERS):
        return False
    try:
        import urllib.request

        headers = {'User-Agent': 'RevayatoSubtitleBot/1.0'}
        try:
            request = urllib.request.Request(url, method='HEAD', headers=headers)
            with urllib.request.urlopen(request, timeout=max(5, int(timeout_seconds or 12))) as response:
                return 200 <= int(getattr(response, 'status', 200) or 200) < 400
        except Exception:
            request = urllib.request.Request(
                url,
                headers={**headers, 'Range': 'bytes=0-1023'},
            )
            with urllib.request.urlopen(request, timeout=max(5, int(timeout_seconds or 12))) as response:
                return 200 <= int(getattr(response, 'status', 200) or 200) < 400
    except Exception:  # noqa: BLE001 — expired CDN signatures are expected
        return False


def refresh_softsub_download_links(obj, *, queue_extract: bool = False) -> bool:
    """Re-crawl Film2Media + Dornatv so SoftSub signatures stay fresh.

    Uses replace=False so dub/hardsub rows are kept while merging both sites.
    """
    from apps.catalog.provider_import.exceptions import ProviderImportError

    is_movie = obj.__class__.__name__ == 'Movie'
    try:
        from apps.catalog.provider_import.multi_provider_crawl import (
            crawl_catalog_downloads_for_movie,
            crawl_catalog_downloads_for_series,
        )
    except Exception:
        logger.exception('softsub refresh imports failed for %s %s', obj.__class__.__name__, getattr(obj, 'pk', None))
        return False

    if is_movie:
        attempts = [
            lambda: crawl_catalog_downloads_for_movie(
                movie=obj, replace=False, queue_softsub_extract=queue_extract,
            ),
        ]
    else:
        attempts = [
            lambda: crawl_catalog_downloads_for_series(
                series=obj, replace=False, queue_softsub_extract=queue_extract,
            ),
        ]

    changed = False
    for attempt in attempts:
        try:
            attempt()
            changed = True
            obj.refresh_from_db(fields=['download_links'])
            links = [item for item in (obj.download_links or []) if isinstance(item, dict)]
            sources = _ranked_extract_sources(links)
            if sources and _http_url_reachable(_http_url(sources[0])):
                return True
        except ProviderImportError as exc:
            logger.info(
                'softsub link refresh skipped for %s %s: %s',
                obj.__class__.__name__, getattr(obj, 'pk', None), exc,
            )
        except Exception:
            logger.exception(
                'softsub link refresh failed for %s %s',
                obj.__class__.__name__, getattr(obj, 'pk', None),
            )
    return changed


def _ensure_reachable_softsub_sources(obj) -> list[dict]:
    """Return ranked SoftSub sources, refreshing CDN links when signatures expired.

    Never fall back to known-dead hosts (e.g. cdnhost.lol) — that wastes hours of
    ffmpeg against HTTP 4xx and never yields a WebVTT the player can sync.
    Always re-crawl Film2Media once when Soft encodes look stale so Soft/SUB
    mirrors get fresh signed URLs for extraction.
    """
    links = [item for item in (obj.download_links or []) if isinstance(item, dict)]
    live = _pick_live_extract_sources(links, limit=3, probe=15)
    # Prefer a fresh myf2m crawl when Soft encodes exist but may have expired tokens,
    # or when HEAD probes failed for every Soft mirror.
    needs_refresh = bool(_ranked_extract_sources(links)) and (
        not live or not any(_http_url_reachable(_http_url(item), timeout_seconds=8) for item in live[:1])
    )
    if needs_refresh or (not live and download_links_imply_subtitle(links)):
        refresh_softsub_download_links(obj, queue_extract=False)
        obj.refresh_from_db(fields=['download_links'])
        links = [item for item in (obj.download_links or []) if isinstance(item, dict)]
        live = _pick_live_extract_sources(links, limit=3, probe=15)
    return live

def apply_availability_flags(obj, links) -> list[str]:
    """Sync has_subtitle / is_dubbed from real download-link + subtitle-track data.

    Also rewrites download_links kinds/labels from CDN evidence so crawler
    reports, catalog flags, and SoftSub extraction all see the same classes.
    """
    changed: list[str] = []
    raw_links = [item for item in (links or []) if isinstance(item, dict)]
    links, links_changed = canonicalize_download_links(raw_links)
    if links_changed and hasattr(obj, 'download_links'):
        obj.download_links = links
        changed.append('download_links')

    tracks = getattr(obj, 'subtitle_tracks', None) or []
    has_real_tracks = any(
        isinstance(track, dict) and str(track.get('src') or track.get('key') or '').strip()
        for track in tracks
    )
    # Series: also honour episode-level extracted tracks.
    if not has_real_tracks and hasattr(obj, 'seasons'):
        try:
            from apps.catalog.models import Episode
            has_real_tracks = Episode.objects.filter(
                season__series_id=obj.pk,
                is_published=True,
            ).exclude(subtitle_tracks=[]).exclude(subtitle_tracks__isnull=True).exists()
        except Exception:
            has_real_tracks = False

    want_subtitle = download_links_imply_subtitle(links) or has_real_tracks
    want_dubbed = download_links_imply_dub(links)

    if getattr(obj, 'has_subtitle', False) != want_subtitle:
        obj.has_subtitle = want_subtitle
        changed.append('has_subtitle')
    if getattr(obj, 'is_dubbed', False) != want_dubbed:
        obj.is_dubbed = want_dubbed
        changed.append('is_dubbed')
    return changed


def _http_url(item: dict | None) -> str:
    if not isinstance(item, dict):
        return ''
    url = str(item.get('url') or '').strip()
    if url.startswith(('http://', 'https://')):
        return url
    return ''


def _source_url_identity(url: str) -> str:
    """Stable video identity that ignores expiring query-string signatures."""
    raw = str(url or '').strip()
    if not raw:
        return ''
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return raw.split('?', 1)[0].lower().rstrip('/')
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return ''
    return f'{parsed.netloc.lower()}{parsed.path}'.lower().rstrip('/')


def _prioritize_extract_sources(
    sources: list[dict],
    preferred_source_url: str = '',
) -> list[dict]:
    """Put the currently-playing, server-known SoftSub source first."""
    preferred = _source_url_identity(preferred_source_url)
    rows = list(sources or [])
    if not preferred:
        return rows
    return sorted(
        rows,
        key=lambda item: 0 if _source_url_identity(_http_url(item)) == preferred else 1,
    )


def _is_dead_softsub_host(url: str) -> bool:
    host = urlsplit(str(url or '')).netloc.lower()
    return any(marker in host for marker in _DEAD_SOFTSUB_HOST_MARKERS)


def _quality_score(item: dict) -> int:
    """Rank SoftSub sources for WebVTT extraction (not for playback quality).

    Prefer smaller progressive Soft encodes so ffmpeg can demux remote subtitle
    streams before the Celery time limit — 480p Soft syncs the same cues as 1080p.
    """
    quality = str(item.get('quality') or '').lower()
    score = 0
    # Extraction speed: 480p >> 720p >> 1080p >> 4K.
    if '480' in quality:
        score = 55
    elif '720' in quality:
        score = 40
    elif '1080' in quality:
        score = 18
    elif '2160' in quality or '4k' in quality:
        score = 5
    if 'x265' in quality or '10bit' in quality:
        score -= 10
    url = _http_url(item).lower()
    path = urlsplit(url).path.lower()
    if '.mp4' in url:
        score += 8
    if '.mkv' in path:
        score -= 4
    if any(url.split('?', 1)[0].endswith(ext) for ext in ('.vtt', '.webvtt', '.srt', '.ass', '.ssa')):
        score += 80
    # Prefer dedicated SoftSub encodes over Dual-Audio Dubbed SoftSub containers.
    if any(token in path for token in ('/soft/', '/softsub/', '/soft-sub/', '/soft_sub/')):
        score += 35
    # myf2m Soft CDN: Soft/, SUB/, BluSUB/, Farsi.Sub on abrtech.
    if any(token in path for token in _SOFTSUB_PATH_TOKENS):
        score += 28
    if 'farsi.sub' in path or 'fa.sub' in path:
        score += 30
    if 'abrtech.top' in urlsplit(url).netloc.lower():
        score += 12
    if any(token in path for token in ('/dubbed/', '/dub/', '/dual')):
        score -= 20
    if looks_like_dub_link(item):
        score -= 10
    if _is_dead_softsub_host(url):
        score -= 200
    return score


def _pick_live_extract_sources(
    links: list[dict],
    *,
    limit: int = 3,
    probe: int = 15,
    preferred_source_url: str = '',
) -> list[dict]:
    """Rank SoftSub encodes, skip known-dead hosts, and keep the best extract URLs.

    Prefer URLs that pass a cheap reachability probe. If HEAD/Range probes fail
    (common with picky CDNs), still fall back to the top-ranked Soft encodes so
    ffmpeg can attempt demux — otherwise we skip the fast 480p Soft and burn the
    Celery budget on slower 720p/1080p mirrors.
    """
    ranked = _prioritize_extract_sources([
        item for item in _ranked_extract_sources(links)[: max(1, int(probe or 15))]
        if _http_url(item) and not _is_dead_softsub_host(_http_url(item))
    ], preferred_source_url)
    if not ranked:
        return []

    live: list[dict] = []
    unseen: list[dict] = []
    for item in ranked:
        url = _http_url(item)
        if _http_url_reachable(url):
            live.append(item)
            if len(live) >= max(1, int(limit or 3)):
                return live
        else:
            unseen.append(item)

    # Fill remaining slots with top-ranked Soft encodes even when HEAD failed.
    for item in unseen:
        live.append(item)
        if len(live) >= max(1, int(limit or 3)):
            break
    return live or ranked[: max(1, int(limit or 3))]


def _pick_extract_source(links: list[dict]) -> dict | None:
    ranked = _ranked_extract_sources(links)
    return ranked[0] if ranked else None

def _season_episode_key(item: dict) -> tuple[int, int] | None:
    try:
        season = int(item.get('season_number') or 0)
    except (TypeError, ValueError):
        season = 0
    try:
        episode = int(item.get('episode_number') or 0)
    except (TypeError, ValueError):
        episode = 0
    if episode <= 0:
        blob = ' '.join([
            str(item.get('season') or ''),
            str(item.get('episode') or ''),
            str(item.get('label') or ''),
            str(item.get('url') or item.get('key') or ''),
        ])
        season_match = re.search(r'(?:فصل|season)\s*([0-9]{1,3})', blob, re.I)
        episode_match = re.search(r'(?:قسمت|episode)\s*([0-9]{1,3})', blob, re.I)
        if season_match:
            season = int(season_match.group(1))
        if episode_match:
            episode = int(episode_match.group(1))
        if episode <= 0:
            try:
                from apps.catalog.provider_import.providers.cdn_link_parse import _episode_from_url
                parsed_season, parsed_episode = _episode_from_url(
                    str(item.get('url') or item.get('key') or ''),
                    surrounding=blob,
                    season_hint=season or None,
                )
                if parsed_episode:
                    episode = int(parsed_episode)
                if parsed_season and not season:
                    season = int(parsed_season)
            except Exception:
                pass
    if episode <= 0:
        return None
    return (max(1, season or 1), episode)


def _links_for_episode(links: list[dict], season_number: int, episode_number: int) -> list[dict]:
    matched = []
    for item in links or []:
        if not isinstance(item, dict):
            continue
        key = _season_episode_key(item)
        if not key:
            continue
        if key == (season_number, episode_number):
            matched.append(item)
    return matched


# Text codecs the HTML5 player can eventually show (via WebVTT).
_TEXT_SUBTITLE_CODECS = frozenset({
    'subrip', 'srt', 'ass', 'ssa', 'webvtt', 'mov_text', 'text', 'dvb_teletext',
})
_BITMAP_SUBTITLE_CODECS = frozenset({
    'hdmv_pgs_subtitle', 'dvd_subtitle', 'dvdsub', 'pgssub', 'xsub', 'dvb_subtitle',
})
_PERSIAN_LANG_TAGS = frozenset({'fas', 'per', 'fa', 'farsi', 'persian', 'پارسی', 'فارسی'})


def _ranked_extract_sources(links: list[dict]) -> list[dict]:
    ranked: list[tuple[int, dict]] = []
    for item in links or []:
        if not looks_like_softsub_link(item):
            continue
        url = _http_url(item)
        if not url:
            continue
        # Never spend ffmpeg time on Soft CDNs that currently 4xx everything.
        if _is_dead_softsub_host(url):
            continue
        ranked.append((_quality_score(item), item))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return [item for _, item in ranked]

def _ffmpeg_network_args(*, with_reconnect: bool = True) -> list[str]:
    """HTTP flags so Film2Media SoftSub CDNs survive reconnects during demux."""
    args = [
        '-user_agent', 'Mozilla/5.0 (compatible; RevayatoSubtitleBot/1.0)',
        '-rw_timeout', '25000000',
        '-probesize', '8M',
        '-analyzeduration', '12M',
    ]
    if with_reconnect:
        args[2:2] = [
            '-reconnect', '1',
            '-reconnect_streamed', '1',
            '-reconnect_delay_max', '8',
        ]
    return args


def extract_webvtt_from_url(
    source_url: str,
    *,
    timeout_seconds: int = 300,
    snappy: bool = False,
) -> bytes | None:
    """Best-effort extraction / conversion of a subtitle stream into WebVTT.

    ``snappy=True`` shortens ffprobe so Soft-only playback gaps demux faster.
    """
    if not source_url:
        return None
    # Skip hosts that currently 410 every signed SoftSub URL.
    host = urlsplit(source_url).netloc.lower()
    if any(marker in host for marker in _DEAD_SOFTSUB_HOST_MARKERS):
        return None
    path = urlsplit(source_url).path.lower().split('?', 1)[0]

    # Standalone subtitle files: download (+ convert) without remuxing a container.
    if path.endswith(('.vtt', '.webvtt', '.srt', '.ass', '.ssa')):
        payload = _download_bytes(source_url, timeout_seconds=min(60, max(20, timeout_seconds)))
        if payload:
            converted = normalize_subtitle_payload(payload, filename=path)
            if converted:
                return converted
        if path.endswith(('.vtt', '.webvtt')) and ffmpeg_available():
            return _ffmpeg_subtitle_file(source_url, timeout_seconds=timeout_seconds, force_webvtt=False)
        if path.endswith(('.srt', '.ass', '.ssa')) and ffmpeg_available():
            return _ffmpeg_subtitle_file(source_url, timeout_seconds=timeout_seconds, force_webvtt=True)

    if not ffmpeg_available():
        return None

    # Probe once, then extract the best text stream by absolute index (faster + reliable).
    # Soft-only online path: keep probe short so 480p Soft demux starts quickly.
    if snappy:
        probe_budget = min(22, max(10, int(timeout_seconds or 60) // 4))
    else:
        probe_budget = min(90, max(30, timeout_seconds // 2))
    streams = _ffprobe_subtitle_streams(source_url, timeout_seconds=probe_budget)
    ranked_streams = _rank_subtitle_streams(streams)
    if ranked_streams:
        # Language tags are often missing or wrong. Validate the extracted text
        # and try the next text stream instead of accidentally saving English.
        for picked in ranked_streams[:3]:
            payload = _ffmpeg_copy_subtitle_stream(
                source_url,
                stream_index=int(picked['index']),
                codec=str(picked.get('codec') or ''),
                timeout_seconds=timeout_seconds,
            )
            if _is_usable_persian_webvtt(payload):
                return payload

        # ffprobe found concrete text streams; blind alias remaps only repeat
        # those reads and cannot turn a non-Persian stream into Persian.
        return None

    # Some CDNs reject ffprobe's access pattern but accept ffmpeg. Prefer Persian
    # SoftSub stream when present, then fall back to the first subtitle stream.
    map_budget = max(45, int(timeout_seconds or 90) // 2) if snappy else max(90, timeout_seconds // 2)
    for mapper in ('0:s:m:language:fas', '0:s:m:language:per', '0:s:m:language:fa', '0:s:0'):
        payload = _ffmpeg_map_to_webvtt(source_url, mapper, timeout_seconds=map_budget)
        if _is_usable_persian_webvtt(payload):
            return payload
    return None


def normalize_subtitle_payload(payload: bytes, *, filename: str = '') -> bytes | None:
    """Convert SRT/ASS/SSA/VTT bytes into sanitized WebVTT for the online player."""
    if not payload:
        return None
    name = (filename or '').lower()
    head = payload.lstrip()[:64].upper()
    if name.endswith(('.vtt', '.webvtt')) or head.startswith(b'WEBVTT'):
        text = _decode_subtitle_text(payload)
        return _sanitize_webvtt(text).encode('utf-8')
    if name.endswith('.srt') or _looks_like_srt(payload):
        return srt_to_webvtt(_decode_subtitle_text(payload)).encode('utf-8')
    if name.endswith(('.ass', '.ssa')) or head.startswith(b'[SCRIPT INFO]') or b'[Events]' in payload[:4000]:
        return ass_to_webvtt(_decode_subtitle_text(payload)).encode('utf-8')
    return None


def _is_usable_persian_webvtt(payload: bytes | None) -> bool:
    """Reject empty, truncated, non-Persian, or malformed extraction results."""
    if not payload:
        return False
    text = payload.decode('utf-8', errors='replace')
    if not text.lstrip().upper().startswith('WEBVTT'):
        return False
    cue_count = len(re.findall(
        r'(?m)^\s*\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3}\s*-->\s*'
        r'\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3}',
        text,
    ))
    persian_chars = len(re.findall(r'[\u0600-\u06ff]', text))
    return cue_count >= 1 and persian_chars >= 12 and text.count('\ufffd') <= 2


def _looks_like_cp1256_mojibake(text: str) -> bool:
    """True when UTF-8 Persian was decoded as Windows-1256 and re-saved as UTF-8."""
    sample = text[:12000]
    chars = re.findall(r'[\u0600-\u06ff]', sample)
    if len(chars) < 40:
        return False
    density = (sample.count('ط') + sample.count('ظ')) / len(chars)
    markers = len(re.findall(r'ظˆ|ظ…|ظ†|غŒ|ظ€', sample))
    return density >= 0.22 or markers >= 10


def _repair_cp1256_mojibake(text: str) -> str | None:
    for encoding in ('cp1256', 'windows-1256'):
        try:
            fixed = text.encode(encoding).decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        chars = re.findall(r'[\u0600-\u06ff]', fixed)
        if len(chars) < 40 or _looks_like_cp1256_mojibake(fixed):
            continue
        if (fixed.count('ط') / len(chars)) > 0.22:
            continue
        return fixed.replace('ي', 'ی').replace('ى', 'ی').replace('ك', 'ک')
    return None


def _decode_subtitle_text(payload: bytes) -> str:
    """Decode modern and legacy Persian subtitle encodings without mojibake.

    UTF-8 SoftSub/SRT packs are common. Blindly scoring windows-1256 against the
    same bytes invents extra Arabic-range glyphs and wins — producing mojibake
    VTT the player cannot usefully render. Prefer a clean UTF-8 decode first.
    """
    for encoding in ('utf-8-sig', 'utf-8'):
        try:
            text = payload.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        if '\ufffd' in text or '\x00' in text[:4000]:
            continue
        if re.search(r'[\u0600-\u06ff]', text):
            if _looks_like_cp1256_mojibake(text):
                repaired = _repair_cp1256_mojibake(text)
                if repaired:
                    return repaired
            return text.replace('ي', 'ی').replace('ى', 'ی').replace('ك', 'ک')

    best = ''
    best_score = -10**9
    for encoding in ('utf-16', 'windows-1256', 'cp1256'):
        try:
            text = payload.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        persian_chars = len(re.findall(r'[\u0600-\u06ff]', text))
        replacement_chars = text.count('\ufffd')
        nul_chars = text.count('\x00')
        # Penalize classic UTF-8→CP1256 mojibake markers (ظ… ط§ غŒ …).
        mojibake = len(re.findall(r'ظ.|ط.|غŒ|â€', text[:4000]))
        score = persian_chars * 3 - replacement_chars * 20 - nul_chars * 10 - mojibake * 8
        if score > best_score:
            best = text.replace('ي', 'ی').replace('ى', 'ی').replace('ك', 'ک')
            best_score = score
    if best:
        return best
    return payload.decode('utf-8-sig', errors='replace')


def _looks_like_srt(payload: bytes) -> bool:
    sample = _decode_subtitle_text(payload[:1200])
    return bool(re.search(r'\d+\s*\n\d{1,2}:\d{2}:\d{2}[,.]\d{2,3}\s*-->\s*\d{1,2}:\d{2}:\d{2}[,.]\d{2,3}', sample))


def _download_bytes(url: str, *, timeout_seconds: int = 45) -> bytes | None:
    try:
        import urllib.request

        request = urllib.request.Request(url, headers={'User-Agent': 'RevayatoSubtitleBot/1.0'})
        with urllib.request.urlopen(request, timeout=max(10, int(timeout_seconds or 45))) as response:
            data = response.read(8 * 1024 * 1024)
        return data if data and len(data) >= 16 else None
    except Exception as exc:  # noqa: BLE001 — network/CDN failures are expected
        logger.info('subtitle download failed for %s: %s', url[:120], exc)
        return None


def _ffprobe_subtitle_streams(source_url: str, *, timeout_seconds: int = 30) -> list[dict]:
    if not shutil.which('ffprobe'):
        return []
    command = [
        'ffprobe', '-hide_banner', '-loglevel', 'error',
        *_ffmpeg_network_args(with_reconnect=False),
        '-select_streams', 's',
        '-show_entries', 'stream=index,codec_name:stream_tags=language,title',
        '-of', 'json',
        source_url,
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=max(10, int(timeout_seconds or 30)),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.info('ffprobe subtitle streams failed for %s: %s', source_url[:120], exc)
        return []
    if completed.returncode != 0:
        return []
    try:
        import json

        payload = json.loads((completed.stdout or b'{}').decode('utf-8', errors='ignore') or '{}')
    except Exception:
        return []
    streams = []
    for item in payload.get('streams') or []:
        try:
            index = int(item.get('index'))
        except (TypeError, ValueError):
            continue
        tags = item.get('tags') or {}
        streams.append({
            'index': index,
            'codec': str(item.get('codec_name') or '').lower(),
            'language': str(tags.get('language') or '').lower(),
            'title': str(tags.get('title') or ''),
        })
    return streams


def _pick_subtitle_stream(streams: list[dict]) -> dict | None:
    ranked = _rank_subtitle_streams(streams)
    return ranked[0] if ranked else None


def _rank_subtitle_streams(streams: list[dict]) -> list[dict]:
    text_streams = [
        row for row in streams
        if row.get('codec') in _TEXT_SUBTITLE_CODECS
        or (row.get('codec') and row.get('codec') not in _BITMAP_SUBTITLE_CODECS)
    ]
    if not text_streams:
        return []

    def score(row: dict) -> tuple[int, int]:
        lang = str(row.get('language') or '').lower()
        title = str(row.get('title') or '').lower()
        points = 0
        if lang in _PERSIAN_LANG_TAGS or any(token in title for token in ('persian', 'farsi', 'فارسی', 'پارسی')):
            points += 100
        if lang in {'mul', 'und', ''}:
            points += 10
        if row.get('codec') in {'subrip', 'srt', 'ass', 'ssa', 'webvtt'}:
            points += 5
        # Prefer earlier streams when scores tie (usually the primary SoftSub).
        return (points, -int(row.get('index') or 0))

    return sorted(text_streams, key=score, reverse=True)


def _ffmpeg_copy_subtitle_stream(
    source_url: str,
    *,
    stream_index: int,
    codec: str,
    timeout_seconds: int,
) -> bytes | None:
    """Copy an embedded text subtitle by absolute stream index, then normalize to WebVTT."""
    codec = (codec or '').lower()
    if codec in _BITMAP_SUBTITLE_CODECS:
        return None
    ext = 'srt'
    if codec in {'ass', 'ssa'}:
        ext = 'ass'
    elif codec in {'webvtt'}:
        ext = 'vtt'
    # The caller's timeout is the budget for this source, not for each fallback.
    # Split it between bitstream copy and WebVTT conversion.
    attempt_timeout = max(45, int(timeout_seconds or 180) // 2)
    with tempfile.TemporaryDirectory(prefix='revayato-subs-') as tmp:
        out_path = Path(tmp) / f'track.{ext}'
        command = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
            *_ffmpeg_network_args(),
            '-i', source_url,
            '-map', f'0:{int(stream_index)}',
            '-c', 'copy',
            str(out_path),
        ]
        try:
            raw = _run_ffmpeg_raw(command, out_path, source_url, attempt_timeout, min_bytes=64)
        except subprocess.TimeoutExpired:
            return None
        if not raw:
            # Remux to WebVTT when bitstream copy is unsupported for this codec/container.
            vtt_path = Path(tmp) / 'track.vtt'
            remux = [
                'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                *_ffmpeg_network_args(),
                '-i', source_url,
                '-map', f'0:{int(stream_index)}',
                '-vn', '-an', '-dn',
                '-c:s', 'webvtt',
                '-f', 'webvtt',
                str(vtt_path),
            ]
            try:
                raw = _run_ffmpeg_raw(remux, vtt_path, source_url, attempt_timeout, min_bytes=20)
            except subprocess.TimeoutExpired:
                return None
            if not raw:
                return None
            return normalize_subtitle_payload(raw, filename='track.vtt')
        return normalize_subtitle_payload(raw, filename=out_path.name)


def srt_to_webvtt(text: str) -> str:
    """Convert SubRip to WebVTT and strip provider HTML noise."""
    cleaned = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    if not cleaned:
        return 'WEBVTT\n\n'
    blocks = re.split(r'\n\s*\n', cleaned)
    cues: list[str] = []
    for block in blocks:
        lines = [line.strip() for line in block.split('\n') if line.strip() != '']
        if not lines:
            continue
        # Optional numeric index.
        if re.fullmatch(r'\d+', lines[0] or ''):
            lines = lines[1:]
        if not lines:
            continue
        timing = lines[0].replace(',', '.')
        if '-->' not in timing:
            continue
        body_lines = [_strip_subtitle_markup(line) for line in lines[1:]]
        body = '\n'.join(line for line in body_lines if line)
        if not body:
            continue
        start, _, end = timing.partition('-->')
        cues.append(f'{_normalize_timestamp(start.strip())} --> {_normalize_timestamp(end.strip())}\n{body}')
    return 'WEBVTT\n\n' + '\n\n'.join(cues) + ('\n' if cues else '')


def ass_to_webvtt(text: str) -> str:
    """Convert basic ASS/SSA Dialogue lines to WebVTT."""
    cues: list[str] = []
    for raw_line in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        line = raw_line.strip()
        if not line.lower().startswith('dialogue:'):
            continue
        payload = line.split(':', 1)[1].strip()
        parts = payload.split(',', 9)
        if len(parts) < 10:
            continue
        start = _ass_timestamp_to_vtt(parts[1].strip())
        end = _ass_timestamp_to_vtt(parts[2].strip())
        body = _strip_subtitle_markup(parts[9].replace('\\N', '\n').replace('\\n', '\n'))
        body = re.sub(r'\{.*?\}', '', body).strip()
        if not start or not end or not body:
            continue
        cues.append(f'{start} --> {end}\n{body}')
    return 'WEBVTT\n\n' + '\n\n'.join(cues) + ('\n' if cues else '')


def _ass_timestamp_to_vtt(value: str) -> str:
    match = re.match(r'(\d+):(\d{2}):(\d{2})[.:](\d{1,3})$', value.strip())
    if not match:
        return ''
    hours, minutes, seconds, frac = match.groups()
    ms = (frac + '000')[:3]
    return f'{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}.{ms}'


def _normalize_timestamp(value: str) -> str:
    value = value.strip()
    match = re.match(r'(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?', value)
    if not match:
        return value
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    ms = (match.group(4) or '0').ljust(3, '0')[:3]
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}.{ms}'


def _strip_subtitle_markup(value: str) -> str:
    text = re.sub(r'</?[^>]+>', '', value or '')
    text = re.sub(r'\{.*?\}', '', text)
    return text.replace('&nbsp;', ' ').strip()


def _sanitize_webvtt(text: str) -> str:
    cleaned = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    if not cleaned.upper().startswith('WEBVTT'):
        cleaned = 'WEBVTT\n\n' + cleaned
    # Strip bidi isolates/embeddings that some SoftSub/SRT packs inject per cue.
    cleaned = re.sub(r'[\u200E\u200F\u202A-\u202E\u2066-\u2069]', '', cleaned)
    # Normalize SRT-style commas that sometimes leak into WebVTT.
    cleaned = re.sub(
        r'(\d{1,2}:\d{2}:\d{2}),(\d{1,3})',
        lambda m: f'{m.group(1)}.{(m.group(2) + "000")[:3]}',
        cleaned,
    )
    return cleaned if cleaned.endswith('\n') else cleaned + '\n'


def _ffmpeg_subtitle_file(source_url: str, *, timeout_seconds: int, force_webvtt: bool) -> bytes | None:
    with tempfile.TemporaryDirectory(prefix='revayato-subs-') as tmp:
        out_path = Path(tmp) / 'track.vtt'
        command = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
            '-i', source_url,
        ]
        if force_webvtt or not urlsplit(source_url).path.lower().endswith(('.vtt', '.webvtt')):
            command.extend(['-c:s', 'webvtt'])
        else:
            command.extend(['-c', 'copy'])
        command.append(str(out_path))
        try:
            raw = _run_ffmpeg_raw(command, out_path, source_url, timeout_seconds, min_bytes=20)
        except subprocess.TimeoutExpired:
            return None
        return normalize_subtitle_payload(raw, filename='track.vtt') if raw else None


def _ffmpeg_map_to_webvtt(source_url: str, mapper: str, *, timeout_seconds: int) -> bytes | None:
    with tempfile.TemporaryDirectory(prefix='revayato-subs-') as tmp:
        out_path = Path(tmp) / 'track.vtt'
        command = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
            *_ffmpeg_network_args(),
            '-i', source_url,
            '-map', mapper,
            '-vn', '-an', '-dn',
            '-c:s', 'webvtt',
            '-f', 'webvtt',
            str(out_path),
        ]
        try:
            raw = _run_ffmpeg_raw(command, out_path, source_url, timeout_seconds, min_bytes=20)
        except subprocess.TimeoutExpired:
            return None
        return normalize_subtitle_payload(raw, filename='track.vtt') if raw else None


def _run_ffmpeg_raw(
    command: list[str],
    out_path: Path,
    source_url: str,
    timeout_seconds: int,
    *,
    min_bytes: int = 20,
) -> bytes | None:
    """Run ffmpeg and return output bytes.

    Long SoftSub remotes often need minutes. Timed-out partial files desync the
    player (early cues only), so we discard them and let Celery retry.
    """
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=max(45, int(timeout_seconds or 180)),
        )
    except subprocess.TimeoutExpired:
        logger.warning('subtitle extract timed out for %s', source_url[:120])
        try:
            if out_path.exists():
                out_path.unlink(missing_ok=True)
        except OSError:
            pass
        # Propagate so callers skip remux/retry on the same slow URL.
        raise
    except OSError as exc:
        logger.warning('subtitle extract failed for %s: %s', source_url[:120], exc)
        return None
    if completed.returncode != 0 or not out_path.exists():
        stderr = (completed.stderr or b'').decode('utf-8', errors='ignore')[:300]
        logger.info('subtitle extract empty for %s (%s)', source_url[:120], stderr)
        return None
    data = out_path.read_bytes()
    if len(data) < min_bytes:
        return None
    return data


def _store_webvtt(payload: bytes, *, filename: str) -> str:
    key = f'catalog/subtitles/{filename}'
    if default_storage.exists(key):
        default_storage.delete(key)
    return default_storage.save(key, ContentFile(payload))


def _track_payload(
    saved_key: str,
    source_url: str,
    *,
    track_id: str = 'fa-softsub',
    provider: str = '',
    source_priority: int = 0,
    sync_confidence: str = '',
) -> dict:
    from apps.catalog.subtitle_contract import normalize_subtitle_track

    row = {
        'id': track_id,
        'label': 'فارسی',
        'language': 'fa',
        'key': saved_key,
        'default': True,
        # Bind VTT to the SoftSub encode so player timing stays correct.
        'source_url': str(source_url or '')[:2000],
    }
    if provider:
        row['provider'] = provider
    if source_priority > 0:
        row['source_priority'] = source_priority
    if sync_confidence:
        row['sync_confidence'] = sync_confidence
    return normalize_subtitle_track(row) or row



_SIDE_CAR_SUBTITLE_EXTS = frozenset({'.vtt', '.webvtt', '.srt', '.ass', '.ssa'})


def _is_sidecar_subtitle_url(url: str) -> bool:
    path = urlsplit(str(url or '')).path.lower()
    if not path:
        return False
    return any(path.endswith(ext) for ext in _SIDE_CAR_SUBTITLE_EXTS)


def _url_filename_stem(url: str) -> str:
    path = urlsplit(str(url or '')).path
    base = (path.split('/')[-1] or '').strip().lower()
    if not base:
        return ''
    if '.' in base:
        base = base.rsplit('.', 1)[0]
    return base


def _subtitle_stem_for_pairing(url: str) -> str:
    """Best-effort stem matching for Persian sidecar subtitles.

    Examples:
      - MovieName.fa.vtt → moviename
      - MovieName-persian.srt → moviename
    """
    stem = _url_filename_stem(url)
    if not stem:
        return ''
    stem = re.sub(r'(?i)([._-]?)(fa|farsi|persian)$', r'\1', stem).rstrip('._-').strip()
    return stem


def _pair_video_score(item: dict) -> int:
    url = _http_url(item)
    if not url:
        return -10
    path = urlsplit(url).path.lower()
    quality = str(item.get('quality') or '').lower()
    score = browser_playback_score(url)
    if '1080' in quality:
        score += 30
    elif '720' in quality:
        score += 20
    elif '480' in quality:
        score += 10
    if any(token in quality for token in ('x265', 'hevc', '10bit')):
        score -= 45
    if looks_like_dub_link(item):
        score += 28
    elif looks_like_hardsub_link(item):
        score += 16
    elif looks_like_softsub_link(item):
        score += 10
    return score


def _prefer_movie_stream_url(links: list[dict]) -> str:
    """Pick a playable playback URL for one movie (prefer dub → hardsub → softsub)."""
    ranked: list[tuple[int, str]] = []
    for item in links or []:
        if not isinstance(item, dict):
            continue
        if not is_playable_video_link(item):
            continue
        url = _http_url(item)
        if not url:
            continue
        if _is_sidecar_subtitle_url(url):
            continue
        ranked.append((_pair_video_score(item), url))
    if not ranked:
        return ''
    ranked.sort(key=lambda row: row[0], reverse=True)
    return ranked[0][1]


def _ranked_movie_stream_urls(links: list[dict]) -> list[str]:
    ranked: list[tuple[int, str]] = []
    for item in links or []:
        if not isinstance(item, dict):
            continue
        if not is_playable_video_link(item):
            continue
        url = _http_url(item)
        if not url or _is_sidecar_subtitle_url(url):
            continue
        ranked.append((_pair_video_score(item), url))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return list(dict.fromkeys(url for _, url in ranked))


def _pair_video_source_for_sidecar_subtitle(
    subtitle_url: str,
    links: list[dict],
    *,
    fallback_prefer_fn,
) -> str:
    """Bind sidecar WebVTT/SRT to the matching video URL for cue sync."""
    subtitle_url = str(subtitle_url or '')
    if not subtitle_url:
        return ''

    fallback = str(fallback_prefer_fn(links) or '')
    subtitle_stem = _subtitle_stem_for_pairing(subtitle_url)

    # 1) Prefer an explicit stem match first.
    if subtitle_stem:
        best: tuple[int, str] | None = None
        for item in links or []:
            if not isinstance(item, dict):
                continue
            url = _http_url(item)
            if not url or _is_sidecar_subtitle_url(url):
                continue
            video_stem = _url_filename_stem(url)
            if not video_stem:
                continue
            if video_stem == subtitle_stem or subtitle_stem in video_stem or video_stem in subtitle_stem:
                candidate = (_pair_video_score(item), url)
                if best is None or candidate[0] > best[0]:
                    best = candidate
        if best:
            return best[1]

    # 2) If we have a fallback preferred video, trust it for sync.
    return fallback


def _mark_has_subtitle(obj) -> bool:
    if getattr(obj, 'has_subtitle', False):
        return False
    obj.has_subtitle = True
    obj.save(update_fields=['has_subtitle', 'updated_at'])
    return True


def _ranked_subtitlestar_stream_urls(links: list[dict]) -> list[str]:
    """Playback URLs suitable for SubtitleStar sidecars (never Dub — avoid double Persian)."""
    soft: list[tuple[int, str]] = []
    other: list[tuple[int, str]] = []
    for item in links or []:
        if not isinstance(item, dict):
            continue
        url = _http_url(item)
        if not url or _is_sidecar_subtitle_url(url):
            continue
        if looks_like_dub_link(item):
            continue
        score = _pair_video_score(item)
        if looks_like_softsub_link(item) or url_implies_softsub(item):
            soft.append((score + 40, url))
        else:
            other.append((score, url))
    soft.sort(key=lambda row: row[0], reverse=True)
    other.sort(key=lambda row: row[0], reverse=True)
    return list(dict.fromkeys([*(url for _, url in soft), *(url for _, url in other)]))


def _release_compatible_sources(
    release_name: str,
    urls,
    *,
    minimum_score: int | None,
) -> list[str]:
    """Keep video URLs without source/FPS conflicts for a sidecar release."""
    from apps.catalog.subtitle_star import _release_score

    compatible: list[str] = []
    for url in urls or []:
        value = str(url or '').strip()
        if not value:
            continue
        score = _release_score(str(release_name or ''), value, strict=True)
        if score is not None and (minimum_score is None or score >= minimum_score):
            compatible.append(value)
    return list(dict.fromkeys(compatible))


def _strict_release_sources(release_name: str, urls) -> list[str]:
    return _release_compatible_sources(release_name, urls, minimum_score=4)


def _non_conflicting_release_sources(release_name: str, urls) -> list[str]:
    return _release_compatible_sources(release_name, urls, minimum_score=None)


def _attach_subtitlestar_subtitle(movie, links: list[dict], *, timeout_seconds: int) -> bool:
    """Attach an exact IMDb-matched SubtitleStar sidecar to online playback."""
    from apps.catalog.subtitle_star import find_movie_subtitle

    video_urls = _ranked_subtitlestar_stream_urls(links) or _ranked_movie_stream_urls(links)
    if not video_urls:
        return False
    match = find_movie_subtitle(
        movie,
        video_urls=video_urls,
        # Keep lookups snappy — long timeouts stall SoftSub backfills for hours.
        timeout_seconds=min(25, max(8, int(timeout_seconds or 25))),
    )
    if match is None:
        return False
    payload = normalize_subtitle_payload(match.payload, filename=match.filename)
    if not _is_usable_persian_webvtt(payload):
        logger.info(
            'SubtitleStar returned an unsupported subtitle for movie=%s filename=%s',
            getattr(movie, 'pk', None), match.filename,
        )
        return False

    filename = f'tmdb-{movie.tmdb_id or movie.pk}-fa-subtitlestar.vtt'
    saved = _store_webvtt(payload, filename=filename)
    # Keep only release-compatible URLs chosen by the provider matcher. Appending
    # every movie URL here would put BluRay cues on WEB/Dub encodes and desync them.
    preferred = _ranked_subtitlestar_stream_urls(links)
    bound_sources = _strict_release_sources(match.release_name, (
        u for u in match.source_urls
        if u and not looks_like_dub_link({'url': u, 'label': u})
    ))[:12]
    sync_confidence = 'release-match'
    if not bound_sources:
        bound_sources = _non_conflicting_release_sources(
            match.release_name,
            [*match.source_urls, *preferred, *video_urls],
        )[:1]
        sync_confidence = 'title-fallback'
    if not bound_sources:
        # Last resort: bind the best-ranked stream so a found Persian release is
        # not lost over strict source/FPS evidence.
        bound_sources = [
            u for u in [*match.source_urls, *preferred, *video_urls]
            if u and not looks_like_dub_link({'url': u, 'label': u})
        ][:1]
        sync_confidence = 'title-fallback'
    if not bound_sources:
        return False
    tracks: list[dict] = []
    for index, source_url in enumerate(bound_sources, start=1):
        track = _track_payload(
            saved,
            source_url,
            track_id=f'fa-subtitlestar-{index}',
            source_priority=2,
            sync_confidence=sync_confidence,
        )
        track.update({
            'provider': 'subtitlestar',
            'provider_page': match.page_url[:1000],
            'release': match.release_name[:300],
            'imdb_id': match.imdb_id,
        })
        tracks.append(track)
    if not tracks:
        return False
    from apps.catalog.subtitle_contract import normalize_subtitle_tracks
    movie.subtitle_tracks = normalize_subtitle_tracks(tracks)
    movie.has_subtitle = True
    movie.save(update_fields=['subtitle_tracks', 'has_subtitle', 'updated_at'])
    try:
        from apps.catalog.cache import bump_catalog_cache_version
        bump_catalog_cache_version()
    except Exception:
        pass
    return True


def _attach_subzone_subtitle(movie, links: list[dict], *, timeout_seconds: int) -> bool:
    """Attach a Subzone.ir Persian sidecar when SubtitleStar misses."""
    from apps.catalog.subzone import find_movie_subtitle

    video_urls = _ranked_subtitlestar_stream_urls(links) or _ranked_movie_stream_urls(links)
    if not video_urls:
        return False
    match = find_movie_subtitle(
        movie,
        video_urls=video_urls,
        timeout_seconds=min(18, max(6, int(timeout_seconds or 12))),
    )
    if match is None:
        return False
    payload = normalize_subtitle_payload(match.payload, filename=match.filename)
    if not _is_usable_persian_webvtt(payload):
        logger.info(
            'Subzone returned an unsupported subtitle for movie=%s filename=%s',
            getattr(movie, 'pk', None), match.filename,
        )
        return False

    filename = f'tmdb-{movie.tmdb_id or movie.pk}-fa-subzone.vtt'
    saved = _store_webvtt(payload, filename=filename)
    preferred = _ranked_subtitlestar_stream_urls(links)
    bound_sources = _strict_release_sources(match.release_name, (
        u for u in match.source_urls
        if u and not looks_like_dub_link({'url': u, 'label': u})
    ))[:12]
    sync_confidence = 'release-match'
    if not bound_sources:
        bound_sources = _non_conflicting_release_sources(
            match.release_name,
            [*match.source_urls, *preferred, *video_urls],
        )[:1]
        sync_confidence = 'title-fallback'
    if not bound_sources:
        # Last resort: bind the best-ranked stream so a found Persian release is
        # not lost over strict source/FPS evidence.
        bound_sources = [
            u for u in [*match.source_urls, *preferred, *video_urls]
            if u and not looks_like_dub_link({'url': u, 'label': u})
        ][:1]
        sync_confidence = 'title-fallback'
    if not bound_sources:
        return False
    tracks: list[dict] = []
    for index, source_url in enumerate(bound_sources, start=1):
        track = _track_payload(
            saved,
            source_url,
            track_id=f'fa-subzone-{index}',
            source_priority=3,
            sync_confidence=sync_confidence,
        )
        track.update({
            'provider': 'subzone',
            'provider_page': match.page_url[:1000],
            'release': match.release_name[:300],
            'imdb_id': match.imdb_id,
        })
        tracks.append(track)
    if not tracks:
        return False
    from apps.catalog.subtitle_contract import normalize_subtitle_tracks
    movie.subtitle_tracks = normalize_subtitle_tracks(tracks)
    movie.has_subtitle = True
    movie.save(update_fields=['subtitle_tracks', 'has_subtitle', 'updated_at'])
    try:
        from apps.catalog.cache import bump_catalog_cache_version
        bump_catalog_cache_version()
    except Exception:
        pass
    return True


def _save_movie_softsub_track(movie, payload: bytes, *, source_url: str, provider: str) -> bool:
    if not _is_usable_persian_webvtt(payload):
        logger.info('Rejected unusable/non-Persian embedded subtitle movie=%s', getattr(movie, 'pk', None))
        return False
    paired_source_url = source_url
    if _is_sidecar_subtitle_url(source_url):
        links = [item for item in (movie.download_links or []) if isinstance(item, dict)]
        paired_source_url = _pair_video_source_for_sidecar_subtitle(
            source_url,
            links,
            fallback_prefer_fn=_prefer_movie_stream_url,
        ) or source_url

    filename = f'tmdb-{movie.tmdb_id or movie.pk}-fa.vtt'
    saved = _store_webvtt(payload, filename=filename)
    movie.subtitle_tracks = [
        _track_payload(
            saved,
            paired_source_url,
            provider=provider,
            source_priority=1,
            sync_confidence='exact-source',
        ),
    ]
    movie.has_subtitle = True
    movie.save(update_fields=['subtitle_tracks', 'has_subtitle', 'updated_at'])
    try:
        from apps.catalog.cache import bump_catalog_cache_version
        bump_catalog_cache_version()
    except Exception:
        pass
    return True


def _attach_ffmpeg_softsub_movie(
    movie,
    links: list[dict],
    *,
    timeout_seconds: int = 90,
    snappy: bool = True,
    preferred_source_url: str = '',
) -> bool:
    """Demux Persian SoftSub from the Soft encode (or playable video_url)."""
    if snappy:
        # Urgent player reports go straight to the trusted catalog URLs. A HEAD
        # probe can cost two network timeouts before ffprobe even starts.
        sources = _prioritize_extract_sources(
            _ranked_extract_sources(links),
            preferred_source_url,
        )[:2]
    else:
        sources = _pick_live_extract_sources(
            links,
            limit=2,
            probe=8,
            preferred_source_url=preferred_source_url,
        )
    payload = None
    source_url = ''
    if sources:
        attempts = sources[:2]
        per_attempt = min(70, max(30, int(timeout_seconds or 90) // max(1, len(attempts))))
        for source in attempts:
            source_url = _http_url(source)
            if not source_url:
                continue
            payload = extract_webvtt_from_url(
                source_url,
                timeout_seconds=per_attempt,
                snappy=snappy,
            )
            if payload:
                break

    if not payload:
        video_url = str(getattr(movie, 'video_url', '') or '').strip()
        if video_url.startswith('http') and not _is_sidecar_subtitle_url(video_url):
            source_url = video_url
            payload = extract_webvtt_from_url(
                video_url,
                timeout_seconds=min(65, max(28, int(timeout_seconds or 90))),
                snappy=snappy,
            )

    if not payload or not source_url:
        return False
    return _save_movie_softsub_track(
        movie,
        payload,
        source_url=source_url,
        provider='softsub-ffmpeg',
    )


def attach_extracted_subtitle(
    movie,
    *,
    force: bool = False,
    timeout_seconds: int = 300,
    allow_ffmpeg: bool = False,
    prefer_embedded: bool = False,
    preferred_source_url: str = '',
) -> bool:
    """Attach a Persian WebVTT from Soft encode ffmpeg, SubtitleStar, or Subzone.

    Urgent playback reports prefer embedded demux whenever a Soft encode exists,
    so the player gets frame-accurate cues from the same release/container.
    """
    links = [item for item in (movie.download_links or []) if isinstance(item, dict)]
    if movie.subtitle_tracks and not force:
        if not movie.has_subtitle:
            movie.has_subtitle = True
            movie.save(update_fields=['has_subtitle', 'updated_at'])
        return False

    has_soft = (
        any(url_implies_softsub(item) for item in links)
        or download_links_imply_softsub(links)
    )
    has_hard = any(looks_like_hardsub_link(item) for item in links)
    soft_only = bool(has_soft and not has_hard)
    prefer_embedded = bool(prefer_embedded or soft_only)
    can_ffmpeg = bool(allow_ffmpeg or soft_only or has_soft)

    budget = max(6, int(timeout_seconds or 25))

    # Embedded-first: demux from Soft CDN first (accurate + usually faster
    # than waiting on SubtitleStar misses), then fall back to sidecars.
    if prefer_embedded and can_ffmpeg:
        ffmpeg_budget = min(95, max(40, budget if budget >= 40 else 75))
        if _attach_ffmpeg_softsub_movie(
            movie,
            links,
            timeout_seconds=ffmpeg_budget,
            snappy=True,
            preferred_source_url=preferred_source_url,
        ):
            return True

    # Fast path for open-player ensure: Star first, Subzone immediately after a miss.
    star_budget = min(budget, max(6, budget * 2 // 3)) if budget <= 20 else min(25, budget)
    if _attach_subtitlestar_subtitle(movie, links, timeout_seconds=star_budget):
        return True

    remaining = max(6, budget - min(star_budget, 8)) if budget <= 20 else min(18, max(8, budget // 2))
    if _attach_subzone_subtitle(movie, links, timeout_seconds=remaining):
        return True

    # SoftSub ffmpeg after sidecars when we did not already try the embedded path.
    if not can_ffmpeg:
        if download_links_imply_subtitle(links):
            _mark_has_subtitle(movie)
        return False
    if prefer_embedded:
        # Already attempted demux above.
        if download_links_imply_subtitle(links):
            _mark_has_subtitle(movie)
        return False

    if _attach_ffmpeg_softsub_movie(
        movie,
        links,
        timeout_seconds=min(120, max(45, budget)),
        snappy=False,
        preferred_source_url=preferred_source_url,
    ):
        return True

    if download_links_imply_subtitle(links):
        _mark_has_subtitle(movie)
    return False


def attach_extracted_subtitle_to_episode(
    episode,
    links: list[dict],
    *,
    force: bool = False,
    timeout_seconds: int = 300,
    allow_video_fallback: bool = False,
    preferred_source_url: str = '',
) -> bool:
    """Extract SoftSub WebVTT for one episode from Soft encodes (or playable video)."""
    scoped = [item for item in (links or []) if isinstance(item, dict)]
    has_soft = download_links_imply_softsub(scoped)
    if not has_soft and not allow_video_fallback:
        return False
    if episode.subtitle_tracks and not force:
        return False

    # Prefer reachable SoftSub CDN URLs. Known-dead Soft/ hosts are filtered out of
    # ranking; still probe beyond the top 3 so abrtech Farsi.Sub can win when the
    # first Soft/ mirrors are expired.
    sources = _prioritize_extract_sources(
        _ranked_extract_sources(scoped),
        preferred_source_url,
    )[:3] if has_soft else []
    if has_soft and not sources:
        series = getattr(getattr(episode, 'season', None), 'series', None)
        if series is not None:
            refresh_softsub_download_links(series, queue_extract=False)
            series.refresh_from_db(fields=['download_links'])
            season_no = getattr(episode.season, 'season_number', 1) or 1
            scoped = _links_for_episode(series.download_links or [], season_no, episode.episode_number)
            sources = _prioritize_extract_sources(
                _ranked_extract_sources(scoped),
                preferred_source_url,
            )[:3]

    payload = None
    source_url = ''
    for source in sources[:2]:
        source_url = _http_url(source)
        if not source_url:
            continue
        payload = extract_webvtt_from_url(
            source_url,
            timeout_seconds=timeout_seconds,
            snappy=True,
        )
        if payload:
            break

    if not payload and allow_video_fallback:
        video_url = str(getattr(episode, 'video_url', '') or '').strip()
        if video_url.startswith('http') and not _is_sidecar_subtitle_url(video_url):
            source_url = video_url
            payload = extract_webvtt_from_url(
                video_url,
                timeout_seconds=min(70, max(30, int(timeout_seconds or 90))),
                snappy=True,
            )

    if not _is_usable_persian_webvtt(payload):
        if payload:
            logger.info(
                'Rejected unusable/non-Persian embedded subtitle episode=%s',
                getattr(episode, 'pk', None),
            )
        return False
    paired_source_url = source_url
    if _is_sidecar_subtitle_url(source_url):
        paired_source_url = _pair_video_source_for_sidecar_subtitle(
            source_url,
            scoped,
            fallback_prefer_fn=_prefer_episode_stream_url,
        ) or source_url

    season_no = getattr(episode.season, 'season_number', 1) or 1
    filename = f'series-{episode.season.series_id}-s{season_no}e{episode.episode_number}-fa.vtt'
    saved = _store_webvtt(payload, filename=filename)
    episode.subtitle_tracks = [
        _track_payload(
            saved,
            paired_source_url,
            track_id=f'fa-softsub-s{season_no}e{episode.episode_number}',
            provider='softsub-ffmpeg',
            source_priority=1,
            sync_confidence='exact-source',
        )
    ]
    episode.save(update_fields=['subtitle_tracks', 'updated_at'])
    try:
        from apps.catalog.cache import bump_catalog_cache_version
        bump_catalog_cache_version()
    except Exception:
        pass
    return True


def _ranked_episode_stream_urls(links: list[dict]) -> list[str]:
    ranked: list[tuple[int, str]] = []
    for item in links or []:
        if not isinstance(item, dict):
            continue
        if not is_playable_video_link(item):
            continue
        url = _http_url(item)
        if not url or _is_sidecar_subtitle_url(url):
            continue
        ranked.append((_pair_video_score(item), url))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return list(dict.fromkeys(url for _, url in ranked))


def _episode_video_map(series, links: list[dict]) -> dict[tuple[int, int], list[str]]:
    """Build playable URL lists per episode for SubtitleStar binding."""
    from apps.catalog.models import Episode

    videos: dict[tuple[int, int], list[str]] = {}
    for item in links or []:
        if not isinstance(item, dict):
            continue
        key = _season_episode_key(item)
        if not key:
            continue
        url = _http_url(item)
        if not url or _is_sidecar_subtitle_url(url):
            continue
        videos.setdefault(key, [])
        if url not in videos[key]:
            videos[key].append(url)

    for episode in (
        Episode.objects.filter(season__series_id=series.pk, is_published=True)
        .select_related('season')
        .iterator(chunk_size=100)
    ):
        season_no = getattr(episode.season, 'season_number', 1) or 1
        key = (season_no, episode.episode_number)
        url = str(getattr(episode, 'video_url', '') or '').strip()
        if url.startswith(('http://', 'https://')) and not _is_sidecar_subtitle_url(url):
            videos.setdefault(key, [])
            if url not in videos[key]:
                videos[key].append(url)
        # Prefer download-link ranking order when both exist.
        if key in videos:
            scoped = _links_for_episode(links, season_no, episode.episode_number)
            ranked = _ranked_episode_stream_urls(scoped)
            if ranked:
                videos[key] = list(dict.fromkeys([*ranked, *videos[key]]))
    return {key: urls for key, urls in videos.items() if urls}


def _attach_subtitlestar_series(
    series,
    links: list[dict],
    *,
    force: bool = False,
    timeout_seconds: int = 60,
    limit: int | None = None,
) -> dict:
    """Attach SubtitleStar Persian sidecars to episodes missing online tracks."""
    from apps.catalog.models import Episode
    from apps.catalog.subtitle_star import find_series_episode_subtitles

    result = {'looked_up': False, 'attached': 0, 'matches': 0}
    star_enabled = bool(getattr(settings, 'SUBTITLESTAR_ENABLED', True))
    subzone_enabled = bool(getattr(settings, 'SUBZONE_ENABLED', True))
    if not star_enabled and not subzone_enabled:
        return result
    if not normalize_imdb_id_safe(series) and not (
        str(getattr(series, 'original_title', '') or getattr(series, 'title', '') or '').strip()
        and getattr(series, 'start_year', None)
    ):
        return result

    missing: dict[tuple[int, int], list[str]] = {}
    episode_videos = _episode_video_map(series, links)
    for key, urls in episode_videos.items():
        season_no, episode_no = key
        episode = (
            Episode.objects.filter(
                season__series_id=series.pk,
                season__season_number=season_no,
                episode_number=episode_no,
                is_published=True,
            )
            .select_related('season')
            .first()
        )
        if episode is None:
            continue
        if episode.subtitle_tracks and not force:
            continue
        missing[key] = urls
        if limit is not None and len(missing) >= max(1, int(limit)):
            break
    if not missing:
        return result

    result['looked_up'] = True
    matches = []
    if star_enabled:
        matches = find_series_episode_subtitles(
            series,
            episode_videos=missing,
            timeout_seconds=min(45, max(8, int(timeout_seconds or 60))),
        )
    result['matches'] = len(matches)

    def _persist_match(match, *, provider: str) -> bool:
        episode = (
            Episode.objects.filter(
                season__series_id=series.pk,
                season__season_number=match.season_number,
                episode_number=match.episode_number,
                is_published=True,
            )
            .select_related('season')
            .first()
        )
        if episode is None:
            return False
        if episode.subtitle_tracks and not force:
            return False
        payload = normalize_subtitle_payload(match.payload, filename=match.filename)
        if not _is_usable_persian_webvtt(payload):
            logger.info(
                '%s returned unsupported series subtitle series=%s s%02de%02d filename=%s',
                provider, series.pk, match.season_number, match.episode_number, match.filename,
            )
            return False
        filename = (
            f'series-{series.pk}-s{match.season_number}e{match.episode_number}-fa-{provider}.vtt'
        )
        saved = _store_webvtt(payload, filename=filename)
        episode_urls = episode_videos.get((match.season_number, match.episode_number), [])
        bound_sources = _strict_release_sources(match.release_name, (
            url for url in match.source_urls
            if url and not looks_like_dub_link({'url': url, 'label': url})
        ))[:12]
        sync_confidence = 'release-match'
        if not bound_sources:
            bound_sources = _non_conflicting_release_sources(match.release_name, [
                url for url in episode_urls
                if url and not looks_like_dub_link({'url': url, 'label': url})
            ])[:1]
            sync_confidence = 'title-fallback'
        if not bound_sources:
            # Last resort: bind the first playable URL for this episode so a
            # found Persian release is not lost over strict source/FPS evidence.
            bound_sources = [
                url for url in [*match.source_urls, *episode_urls]
                if url and not looks_like_dub_link({'url': url, 'label': url})
            ][:1]
            sync_confidence = 'title-fallback'
        if not bound_sources:
            return False
        tracks: list[dict] = []
        for index, source_url in enumerate(bound_sources, start=1):
            track = _track_payload(
                saved,
                source_url,
                track_id=f'fa-{provider}-s{match.season_number}e{match.episode_number}-{index}',
                source_priority=2 if provider == 'subtitlestar' else 3,
                sync_confidence=sync_confidence,
            )
            track.update({
                'provider': provider,
                'provider_page': match.page_url[:1000],
                'release': match.release_name[:300],
                'imdb_id': match.imdb_id,
            })
            tracks.append(track)
        if not tracks:
            return False
        from apps.catalog.subtitle_contract import normalize_subtitle_tracks
        episode.subtitle_tracks = normalize_subtitle_tracks(tracks)
        episode.save(update_fields=['subtitle_tracks', 'updated_at'])
        return True

    attached_keys: set[tuple[int, int]] = set()
    for match in matches:
        if _persist_match(match, provider='subtitlestar'):
            result['attached'] += 1
            attached_keys.add((int(match.season_number), int(match.episode_number)))
            if result['attached'] == 1:
                try:
                    from apps.catalog.cache import bump_catalog_cache_version
                    bump_catalog_cache_version()
                except Exception:
                    pass
                if not getattr(series, 'has_subtitle', False):
                    series.has_subtitle = True
                    save = getattr(series, 'save', None)
                    if callable(save):
                        save(update_fields=['has_subtitle', 'updated_at'])

    # Subzone fills episodes SubtitleStar still missed.
    still_missing = {
        key: urls for key, urls in missing.items()
        if key not in attached_keys
    }
    if still_missing and subzone_enabled:
        from apps.catalog.subzone import find_series_episode_subtitles as find_subzone_episode_subtitles
        subzone_matches = find_subzone_episode_subtitles(
            series,
            episode_videos=still_missing,
            timeout_seconds=min(30, max(6, int(timeout_seconds or 30) // 2)),
        )
        result['matches'] += len(subzone_matches)
        for match in subzone_matches:
            if _persist_match(match, provider='subzone'):
                result['attached'] += 1
                if result['attached'] == 1:
                    try:
                        from apps.catalog.cache import bump_catalog_cache_version
                        bump_catalog_cache_version()
                    except Exception:
                        pass
                    if not getattr(series, 'has_subtitle', False):
                        series.has_subtitle = True
                        save = getattr(series, 'save', None)
                        if callable(save):
                            save(update_fields=['has_subtitle', 'updated_at'])
    return result


def normalize_imdb_id_safe(obj) -> str:
    try:
        from apps.catalog.subtitle_star import normalize_imdb_id
        return normalize_imdb_id(getattr(obj, 'imdb_id', ''))
    except Exception:
        return ''


def _prefer_episode_stream_url(links: list[dict]) -> str:
    """Pick a progressive playback URL for one episode (prefer dub, then hardsub/softsub)."""
    ranked: list[tuple[int, str]] = []
    for item in links or []:
        if not isinstance(item, dict):
            continue
        if not is_playable_video_link(item):
            continue
        url = _http_url(item)
        if not url:
            continue
        # Sidecar subtitle files are not playable video.
        path = urlsplit(url).path.lower()
        if path.endswith(('.vtt', '.webvtt', '.srt', '.ass', '.ssa')):
            continue
        quality = str(item.get('quality') or '').lower()
        score = browser_playback_score(url)
        if '1080' in quality:
            score += 30
        elif '720' in quality:
            score += 20
        elif '480' in quality:
            score += 10
        if any(token in quality for token in ('x265', 'hevc', '10bit')):
            score -= 45
        if looks_like_dub_link(item):
            score += 28
        elif looks_like_hardsub_link(item):
            score += 16
        elif looks_like_softsub_link(item):
            score += 10
        ranked.append((score, url))
    if not ranked:
        return ''
    ranked.sort(key=lambda row: row[0], reverse=True)
    return ranked[0][1]


def ensure_episodes_from_download_links(series) -> int:
    """Create published Season/Episode rows only when a playable stream URL exists.

    Skips empty shells: no season/episode without a real download-backed video URL.
    """
    from apps.catalog.models import Episode, Season

    links = [item for item in (series.download_links or []) if isinstance(item, dict)]
    keys: set[tuple[int, int]] = set()
    for item in links:
        key = _season_episode_key(item)
        if key:
            keys.add(key)
    if not keys:
        return 0

    created = 0
    touched_season_ids: set[int] = set()
    for season_no, episode_no in sorted(keys):
        scoped = _links_for_episode(links, season_no, episode_no)
        preferred = _prefer_episode_stream_url(scoped)
        if not preferred:
            # No playable URL for this S/E — do not invent an empty stub row.
            continue

        season, _ = Season.objects.get_or_create(
            series=series,
            season_number=season_no,
            defaults={
                'title': f'فصل {season_no}',
                'is_published': True,
                'episode_count': 0,
            },
        )
        season_fields: list[str] = []
        if not season.is_published:
            season.is_published = True
            season_fields.append('is_published')
        episode, was_created = Episode.objects.get_or_create(
            season=season,
            episode_number=episode_no,
            defaults={
                'title': f'قسمت {episode_no}',
                'is_published': True,
                'video_url': preferred,
            },
        )
        episode_fields: list[str] = []
        if was_created:
            created += 1
        elif not episode.is_published:
            episode.is_published = True
            episode_fields.append('is_published')
        # Keep episode.video_url in sync with download_links for watch/player fallbacks.
        # Only replace when missing or the previous URL is no longer in this episode's pool
        # (avoids thrashing preferred quality across re-crawls).
        previous = (episode.video_url or '').strip()
        scoped_urls = {
            str(item.get('url') or item.get('stream_url') or '').strip()
            for item in scoped
            if isinstance(item, dict)
        }
        from apps.catalog.provider_import.media_links import is_playable_video_url
        scoped_urls = {url for url in scoped_urls if is_playable_video_url(url)}
        if not previous:
            episode.video_url = preferred
            episode_fields.append('video_url')
        elif previous != preferred and previous.startswith(('http://', 'https://')):
            from apps.catalog.provider_import.media_links import browser_playback_score
            # Re-crawls may add an MP4/HLS rendition after an MKV was originally
            # mirrored into Episode.video_url. Promote the safer container even
            # while the old URL remains a valid download quality.
            if (
                previous not in scoped_urls
                or browser_playback_score(preferred) > browser_playback_score(previous)
            ):
                episode.video_url = preferred
                episode_fields.append('video_url')
        if episode_fields:
            episode.save(update_fields=[*dict.fromkeys(episode_fields), 'updated_at'])
        if season_fields:
            season.save(update_fields=[*season_fields, 'updated_at'])
        touched_season_ids.add(season.pk)

    # Keep season.episode_count accurate for seasons we just wired to streams.
    for season in Season.objects.filter(series=series, pk__in=touched_season_ids):
        count = season.episodes.filter(is_published=True).exclude(video_url='').count()
        if season.episode_count != count:
            season.episode_count = count
            season.save(update_fields=['episode_count', 'updated_at'])
    return created


def attach_series_softsub_tracks(
    series,
    *,
    force: bool = False,
    timeout_seconds: int = 300,
    limit: int | None = None,
    allow_ffmpeg: bool = False,
    prefer_embedded: bool = False,
    preferred_episode_id: int = 0,
    preferred_source_url: str = '',
) -> dict:
    """Attach Persian WebVTT for episodes via Soft encode ffmpeg and/or SubtitleStar.

    Soft-only series demux embedded SoftSub from each episode Soft file first so
    online playback stays in sync with the same stream users download.
    """
    from apps.catalog.models import Episode

    links = [item for item in (series.download_links or []) if isinstance(item, dict)]
    result = {
        'series_id': series.pk,
        'processed': 0,
        'extracted': 0,
        'skipped': 0,
        'episodes_created': 0,
        'refreshed': False,
        'subtitlestar_attached': 0,
        'subtitlestar_matches': 0,
    }

    has_softsub = download_links_imply_softsub(links)
    has_hard = any(looks_like_hardsub_link(item) for item in links)
    soft_only = bool(has_softsub and not has_hard)
    prefer_embedded = bool(prefer_embedded or soft_only)
    subtitlestar_eligible = bool(
        getattr(settings, 'SUBTITLESTAR_ENABLED', True)
        and (
            normalize_imdb_id_safe(series)
            or (
                str(getattr(series, 'original_title', '') or getattr(series, 'title', '') or '').strip()
                and getattr(series, 'start_year', None)
            )
        )
    )

    # Materialize episode stubs so SubtitleStar / Soft demux have rows to bind onto.
    if links and (
        has_softsub
        or download_links_imply_subtitle(links)
        or download_links_imply_dub(links)
        or subtitlestar_eligible
    ):
        result['episodes_created'] = ensure_episodes_from_download_links(series)

    from django.core.cache import cache

    def _run_ffmpeg_episodes() -> None:
        if not (allow_ffmpeg and has_softsub):
            return
        soft_sources = _ranked_extract_sources(links)
        needs_refresh = (
            not soft_sources
            or not any(_http_url_reachable(_http_url(item), timeout_seconds=8) for item in soft_sources[:2])
        )
        if needs_refresh:
            result['refreshed'] = refresh_softsub_download_links(series, queue_extract=False)
            series.refresh_from_db(fields=['download_links'])
            nonlocal_links = [item for item in (series.download_links or []) if isinstance(item, dict)]
            links[:] = nonlocal_links

        soft_episode_keys: list[tuple[int, int]] = []
        seen_keys: set[tuple[int, int]] = set()
        for item in links:
            if not looks_like_softsub_link(item):
                continue
            key = _season_episode_key(item)
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            soft_episode_keys.append(key)
        soft_episode_keys.sort()
        if preferred_episode_id:
            preferred_episode = (
                Episode.objects.filter(
                    pk=int(preferred_episode_id),
                    season__series_id=series.pk,
                    is_published=True,
                )
                .select_related('season')
                .first()
            )
            if preferred_episode is not None:
                preferred_key = (
                    int(getattr(preferred_episode.season, 'season_number', 1) or 1),
                    int(preferred_episode.episode_number or 0),
                )
                if preferred_key in soft_episode_keys:
                    soft_episode_keys.remove(preferred_key)
                    soft_episode_keys.insert(0, preferred_key)

        for season_no, episode_no in soft_episode_keys:
            if limit is not None and result['processed'] >= max(1, int(limit)):
                break
            episode = (
                Episode.objects.filter(
                    season__series_id=series.pk,
                    season__season_number=season_no,
                    episode_number=episode_no,
                    is_published=True,
                )
                .select_related('season')
                .first()
            )
            if episode is None:
                result['skipped'] += 1
                continue
            # An urgent report may force the open episode, but must not spend the
            # front of the queue re-demuxing already-ready neighbouring episodes.
            force_this_episode = bool(
                force
                and (
                    not preferred_episode_id
                    or episode.pk == int(preferred_episode_id)
                )
            )
            if episode.subtitle_tracks and not force_this_episode:
                result['skipped'] += 1
                continue
            scoped = _links_for_episode(links, season_no, episode_no)
            if not scoped or not download_links_imply_softsub(scoped):
                result['skipped'] += 1
                continue
            result['processed'] += 1
            ep_timeout = min(70 if prefer_embedded else 90, int(timeout_seconds or 90))
            if attach_extracted_subtitle_to_episode(
                episode, scoped, force=force_this_episode, timeout_seconds=ep_timeout,
                preferred_source_url=(
                    preferred_source_url if episode.pk == int(preferred_episode_id or 0) else ''
                ),
            ):
                result['extracted'] += 1
            else:
                result['skipped'] += 1

    # Soft-only: demux embedded SoftSub before SubtitleStar for accurate sync.
    if prefer_embedded:
        _run_ffmpeg_episodes()

    # SubtitleStar — one season ZIP can cover many episodes in seconds.
    # Skip while the circuit is open so Soft ffmpeg can still run without waiting
    # on guaranteed 403s.
    if subtitlestar_eligible and not cache.get('catalog:subtitlestar:circuit-open'):
        star = _attach_subtitlestar_series(
            series,
            links,
            # Embedded tracks are priority 1 and must never be overwritten by a
            # fallback provider in the same run.
            force=False if prefer_embedded else force,
            timeout_seconds=timeout_seconds,
            limit=limit,
        )
        result['subtitlestar_attached'] = int(star.get('attached') or 0)
        result['subtitlestar_matches'] = int(star.get('matches') or 0)
        result['extracted'] += result['subtitlestar_attached']

    if not prefer_embedded:
        _run_ffmpeg_episodes()

    if result['extracted'] or Episode.objects.filter(
        season__series_id=series.pk,
        is_published=True,
    ).exclude(subtitle_tracks=[]).exclude(subtitle_tracks__isnull=True).exists():
        series.has_subtitle = True
    flag_fields = apply_availability_flags(series, links)
    update_fields = list(dict.fromkeys([*flag_fields, 'updated_at']))
    if update_fields:
        series.save(update_fields=update_fields)
    return result
