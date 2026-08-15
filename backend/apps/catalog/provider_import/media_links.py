"""Shared guards for provider media links.

Provider pages commonly embed a trailer beside real download qualities.  Keep
that asset out of download boxes and progressive playback selection while
allowing legitimate episode titles such as ``Trailer.Park.Boys.S01E01``.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit


_EPISODE_RE = re.compile(
    r'(?:^|[._\-/ ])S\d{1,2}E\d{1,3}(?:[._\-/ ]|$)'
    r'|(?:^|[._\-/ ])\d{1,2}x\d{1,3}(?:[._\-/ ]|$)',
    re.I,
)
_EXPLICIT_TRAILER_RE = re.compile(
    r'(?:^|[._\-/ ])(?:official[._\- ]*)?(?:teaser|preview|sample)(?:[._\-/ ]|$)'
    r'|(?:^|[._\-/ ])official[._\- ]*trailer(?:[._\-/ ]|$)',
    re.I,
)
_TRAILER_TOKEN_RE = re.compile(r'(?:^|[._\-/ ])trailer(?:[._\-/ ]|$)', re.I)
_TRAILER_SUFFIX_RE = re.compile(
    r'(?:^|[._\- ])trailer(?:[._\- ](?:2160p|1080p|720p|480p))?\.(?:mp4|m4v|webm|mkv)$',
    re.I,
)
_SHORT_TRAILER_SUFFIX_RE = re.compile(r'(?:[._\-](?:t|tr))\.(?:mp4|m4v|webm)$', re.I)
_FULL_ENCODE_RE = re.compile(
    r'(?:2160p|1080p|720p|480p|360p|4k|uhd|bluray|blu-ray|web[._\- ]?dl|'
    r'webrip|hdtv|remux|x26[45]|h26[45]|hevc)',
    re.I,
)
_META_TRAILER_RE = re.compile(r'\b(?:trailer|teaser|preview|sample)\b|تریلر|پیش.?نمایش', re.I)

# These hosts have repeatedly failed browser-compatible TLS/range probes.  Keep
# the list centralized so imports, repairs and public playback make the same
# decision.  ``dlyar.top`` currently serves self-signed certificates on most
# media nodes while the remaining nodes time out, so browsers cannot use it.
DEAD_PLAYBACK_HOST_MARKERS = ('cdnhost.lol', 'dlyar.top')
VIDEO_MEDIA_SUFFIXES = ('.m3u8', '.mp4', '.m4v', '.webm', '.mkv')
SUBTITLE_MEDIA_SUFFIXES = ('.vtt', '.webvtt', '.srt', '.ass', '.ssa', '.sub')
NON_VIDEO_MEDIA_SUFFIXES = (
    *SUBTITLE_MEDIA_SUFFIXES,
    '.aac', '.mka', '.mp3', '.wav', '.flac',
    '.jpg', '.jpeg', '.png', '.webp', '.gif',
    '.zip', '.rar', '.7z', '.pdf', '.txt', '.html', '.htm',
)


def is_dead_playback_host(url: str) -> bool:
    """Return True for provider hosts known to permanently reject media URLs."""
    raw = str(url or '').strip()
    if not raw:
        return False
    try:
        host = (urlsplit(raw).hostname or '').lower()
    except ValueError:
        host = raw.lower()
    return any(
        host == marker or host.endswith(f'.{marker}')
        for marker in DEAD_PLAYBACK_HOST_MARKERS
    )


def _media_path(url: str) -> str:
    try:
        return unquote(urlsplit(str(url or '').strip()).path or '').lower().rstrip('/')
    except ValueError:
        return str(url or '').split('?', 1)[0].lower().rstrip('/')


def video_container(url: str) -> str:
    """Return the normalized video container suffix, without query fragments."""
    path = _media_path(url)
    for suffix in VIDEO_MEDIA_SUFFIXES:
        if path.endswith(suffix):
            return suffix[1:]
    return ''


def browser_playback_score(url: str) -> int:
    """Rank a URL by cross-browser playback compatibility.

    This is intentionally only a ranking signal: MKV remains a valid download
    and Chromium fallback, but HLS/MP4/WebM should become the primary online
    source whenever a provider exposes one. Codec tokens in provider filenames
    are used to avoid HEVC/10-bit defaults on browsers without those decoders.
    """
    container = video_container(url)
    score = {
        'm3u8': 180,
        'mp4': 150,
        'm4v': 140,
        'webm': 120,
        'mkv': 0,
    }.get(container, 20)
    path = _media_path(url)
    compact = re.sub(r'[^a-z0-9]+', '', path)
    if any(token in compact for token in ('x265', 'h265', 'hevc', '10bit')):
        score -= 55
    elif any(token in compact for token in ('x264', 'h264', 'avc')):
        score += 12
    return score


def is_browser_native_video_url(url: str) -> bool:
    """True for containers broadly supported by HTML5 players."""
    return is_playable_video_url(url) and video_container(url) in {
        'm3u8', 'mp4', 'm4v', 'webm',
    }


def has_malformed_video_suffix(url: str) -> bool:
    """Catch provider typos such as ``.mp41`` and ``.mkvر``."""
    path = _media_path(url)
    for suffix in VIDEO_MEDIA_SUFFIXES:
        index = path.rfind(suffix)
        if index >= 0 and index + len(suffix) != len(path):
            return True
    return False


def is_sidecar_subtitle_url(url: str) -> bool:
    path = _media_path(url)
    return path.endswith(SUBTITLE_MEDIA_SUFFIXES)


def is_playable_video_url(url: str) -> bool:
    """Static guard for URLs eligible to become an online player source.

    Reachability is checked separately by the repair/import health probe. This
    guard prevents subtitles, trailers, dead mirrors and malformed media names
    from ever being stored in ``video_url`` / ``Episode.video_url``.
    """
    raw = str(url or '').strip()
    if not raw:
        return False
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return False
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return False
    if is_dead_playback_host(raw) or has_malformed_video_suffix(raw):
        return False
    path = _media_path(raw)
    if path.endswith(NON_VIDEO_MEDIA_SUFFIXES):
        return False
    if is_trailer_media_url(raw):
        return False
    return True


def is_playable_video_link(item: dict | None) -> bool:
    if not isinstance(item, dict) or is_trailer_download_link(item):
        return False
    kind = str(item.get('kind') or item.get('type') or '').strip().lower()
    # Older provider rows use ``subtitle`` for burned-in video encodes, so the
    # URL suffix (rather than that ambiguous kind) decides subtitle sidecars.
    if kind in {'audio', 'trailer', 'sample', 'preview'}:
        return False
    return is_playable_video_url(str(item.get('url') or ''))


def is_trailer_media_url(url: str) -> bool:
    """Return True for a trailer/sample URL, without rejecting real episodes."""
    path = unquote(urlsplit(str(url or '').strip()).path or '')
    filename = path.rsplit('/', 1)[-1]
    if not filename:
        return False
    if _EXPLICIT_TRAILER_RE.search(filename) or _SHORT_TRAILER_SUFFIX_RE.search(filename):
        return True
    if _EPISODE_RE.search(filename):
        return False
    if _TRAILER_SUFFIX_RE.search(filename):
        return True
    # A bare Trailer token without normal feature-encode markers is almost
    # always the small preview asset exposed beside the download box.
    return bool(_TRAILER_TOKEN_RE.search(filename) and not _FULL_ENCODE_RE.search(filename))


def is_trailer_download_link(item: dict | None) -> bool:
    if not isinstance(item, dict):
        return False
    metadata = ' '.join(
        str(item.get(key) or '') for key in ('label', 'quality', 'kind', 'type')
    )
    if _META_TRAILER_RE.search(metadata):
        return True
    return is_trailer_media_url(str(item.get('url') or item.get('key') or item.get('src') or ''))
