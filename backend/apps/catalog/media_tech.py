"""What a source *is*, read from its bytes instead of its filename.

:mod:`media_probe` proved a URL is **there**. This module answers the next
question — is it something a browser can actually decode — and it answers it
from the container header rather than the file name.

Everywhere else the catalog reads the codec out of the URL
(:func:`playback_sources.codec_family`, the frontend's ``downloadMeta.ts``),
because a name like ``Movie.1080p.x265.10bit.mkv`` is all that exists before
download. That is right most of the time, and wrong in the three ways that
actually reach viewers:

* **A name that says nothing.** ``Film.2024.1080p.WEB-DL.mp4`` carries no codec
  token, so the heuristic calls it safe. When the encode inside is HEVC, the
  title is published as playable and Firefox and Chrome show a black frame —
  the «پخش ویدیو ممکن نشد» report the playback crawler then chases *afterwards*.
* **A container that lies.** Providers routinely serve a Matroska file from a
  ``.mp4`` path. The extension passes every string test; Safari and Firefox
  still cannot demux it.
* **Audio nobody mentions.** A perfectly good H.264 video muxed with DTS,
  TrueHD, AC-3 or E-AC-3 plays as a silent picture in Chrome and Firefox. No
  filename convention records this, so nothing downstream has ever checked it.

The cost of knowing is one ffprobe of the header — kilobytes, already
implemented and cached for the playback gateway
(:func:`stream_gateway.probe_tech`), so this module is mostly *policy* over
that measurement.

**Three verdicts, never two**, matching :mod:`media_probe`: ``safe`` /
``unsafe`` / ``unknown``. A host this box cannot reach, an ffprobe timeout or a
codec nobody here has an opinion about all return ``unknown``, and callers fall
back to the filename heuristic. Knowing less than we hoped must never be worse
than the guess we had before.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

#: Video codecs every mainstream browser decodes in a ``<video>`` element.
#: H.264 is the only universal one; VP8/VP9 are accepted because the catalog
#: already treats ``.webm`` as friendly and every browser that matters plays it.
BROWSER_SAFE_VIDEO = frozenset({'h264', 'avc1', 'vp8', 'vp9'})
#: Decodable by at most one engine: HEVC is Safari-only, AV1 is patchy and
#: absent on the hardware most of this audience watches on.
BROWSER_UNSAFE_VIDEO = frozenset({'hevc', 'h265', 'av1', 'vc1', 'mpeg4', 'msmpeg4v3', 'wmv3'})

#: Audio a browser can decode. Everything here ships in every engine.
BROWSER_SAFE_AUDIO = frozenset({'aac', 'mp3', 'opus', 'vorbis', 'flac', 'mp2'})
#: Cinema audio formats. The picture plays and the viewer hears nothing — the
#: most confusing failure of the lot, because the player reports no error.
BROWSER_UNSAFE_AUDIO = frozenset({'dts', 'truehd', 'eac3', 'ac3', 'mlp', 'pcm_bluray', 'dtshd'})

#: ffprobe reports one name for several containers; these are the ones a strict
#: browser cannot demux progressively.
UNDEMUXABLE_CONTAINERS = frozenset({'avi', 'asf', 'flv', 'rm', 'rmvb'})

_HLS_RE = re.compile(r'\.m3u8($|[?#])', re.IGNORECASE)


def codec_verification_enabled() -> bool:
    from django.conf import settings

    return bool(getattr(settings, 'CATALOG_VERIFY_CODEC_BEFORE_PUBLISH', True))


def real_tech(url: str, *, refresh: bool = False):
    """The source's true container/codecs, or a ``SourceTech`` saying why not.

    Thin pass-through to the gateway's probe so there is exactly one ffprobe
    implementation and one cache in the codebase.
    """
    from apps.catalog import stream_gateway as gw

    return gw.probe_tech(url, refresh=refresh)


def _container_family(container: str, video_codec: str) -> str:
    """Normalise ffprobe's ``format_name`` into what a browser cares about.

    ffprobe calls both MKV and WebM ``matroska`` (the demuxer is shared), and
    the two could not be further apart for playback: WebM is native everywhere,
    MKV is native nowhere except Chromium. The video codec is what separates
    them — VP8/VP9 means WebM in practice.
    """
    name = (container or '').strip().lower()
    if not name:
        return ''
    if name in {'matroska', 'webm'}:
        return 'webm' if video_codec in {'vp8', 'vp9', 'av1'} else 'mkv'
    if name in {'mov', 'mp4', 'm4v', '3gp'}:
        return 'mp4'
    if name in {'hls', 'applehttp'}:
        return 'hls'
    return name


def classify_tech(tech, *, is_manifest: bool = False) -> tuple[str, str]:
    """``(verdict, reason)`` for a probed source: safe / unsafe / unknown.

    ``reason`` is a short machine code naming the disqualifying property, so a
    stored verdict can be read back later without re-probing.
    """
    if tech is None or not getattr(tech, 'ok', False):
        return 'unknown', (getattr(tech, 'reason', '') or 'not_probed')

    video = (tech.video_codec or '').lower()
    audio = (tech.audio_codec or '').lower()
    container = _container_family(tech.container, video)

    # An HLS manifest is a playlist of segments; the container check below does
    # not apply to it, only its codecs do.
    if not is_manifest and container in UNDEMUXABLE_CONTAINERS:
        return 'unsafe', f'container_{container}'
    if not is_manifest and container == 'mkv':
        # The interesting case: the URL may well have ended in .mp4.
        return 'unsafe', 'container_mkv'

    if video in BROWSER_UNSAFE_VIDEO:
        return 'unsafe', f'video_{video}'
    if video and video not in BROWSER_SAFE_VIDEO:
        # A codec nobody here has an opinion about. Not a licence to publish.
        return 'unknown', f'video_unrecognised_{video}'[:40]

    # Audio is only disqualifying when we know what it is. A file with no audio
    # stream at all is odd but perfectly playable.
    if audio and audio in BROWSER_UNSAFE_AUDIO:
        return 'unsafe', f'audio_{audio}'
    if audio and audio not in BROWSER_SAFE_AUDIO:
        return 'unknown', f'audio_unrecognised_{audio}'[:40]

    return 'safe', ''


def verify_source(url: str, *, refresh: bool = False) -> dict:
    """Probe one URL and report what a browser will make of it.

    Returns ``{verdict, reason, container, video, audio, duration, width,
    height}``. Never raises and never blocks longer than the gateway probe's own
    timeout.
    """
    url = (url or '').strip()
    blank = {
        'verdict': 'unknown', 'reason': '', 'container': '', 'video': '',
        'audio': '', 'duration': 0.0, 'width': 0, 'height': 0,
    }
    if not url:
        return {**blank, 'reason': 'empty_url'}
    if not codec_verification_enabled():
        return {**blank, 'reason': 'disabled'}
    if not url.startswith(('http://', 'https://')):
        # An object key for our own HLS output — our pipeline produced it, so
        # there is no third party to distrust.
        return {**blank, 'reason': 'internal_storage'}

    tech = real_tech(url, refresh=refresh)
    verdict, reason = classify_tech(tech, is_manifest=bool(_HLS_RE.search(url)))
    return {
        'verdict': verdict,
        'reason': reason,
        'container': _container_family(getattr(tech, 'container', ''), (tech.video_codec or '').lower())
                     if getattr(tech, 'ok', False) else '',
        'video': (getattr(tech, 'video_codec', '') or ''),
        'audio': (getattr(tech, 'audio_codec', '') or ''),
        'duration': round(float(getattr(tech, 'duration', 0.0) or 0.0), 3),
        'width': int(getattr(tech, 'width', 0) or 0),
        'height': int(getattr(tech, 'height', 0) or 0),
    }


def real_duration(url: str) -> float:
    """The source's true runtime in seconds, or ``0.0`` when unknown.

    This is what makes subtitle sync checkable: a cue file can only be judged
    against the film it claims to caption, and the film's real length is not in
    the catalog metadata (TMDB runtime is the *theatrical* cut and routinely
    disagrees with the actual encode by minutes).
    """
    tech = real_tech(url)
    if not getattr(tech, 'ok', False):
        return 0.0
    return max(0.0, round(float(tech.duration or 0.0), 3))
