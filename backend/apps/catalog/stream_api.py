"""HTTP surface for the playback gateway.

Three endpoints, and the shape of them follows from one decision: the player
must never be handed a URL that might not play. So ``stream_open`` does the
probing, starts the session, and only answers once ffmpeg has actually written
a playable segment — a slow answer that works beats a fast one the player has
to fail on and retry.

The endpoints are deliberately *not* an open proxy. ``stream_open`` accepts a
title and a URL and refuses the pair unless that URL is genuinely one of that
title's own sources, so the gateway can only ever be pointed at bytes the
catalog already publishes.
"""

from __future__ import annotations

import logging

from django.http import FileResponse, Http404, HttpResponse
from django.views.decorators.http import require_GET
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from apps.catalog.models import Episode, Movie, Series
from apps.catalog import stream_gateway as gw
from config.public_urls import is_geo_locked_url

logger = logging.getLogger(__name__)

#: HLS is a chatty protocol — a viewer pulls a segment every few seconds — so
#: the segment bucket has to be far larger than the session-opening one.
class StreamOpenThrottle(AnonRateThrottle):
    """Opening a session spawns ffmpeg; keep that expensive and rare."""

    scope = 'stream_open'


class StreamSegmentThrottle(AnonRateThrottle):
    """Playlist and segment reads: one every few seconds per viewer, normally."""

    scope = 'stream_segment'


def _source_urls(kind: str, obj_id: int) -> set[str]:
    """Every URL the given title legitimately owns.

    This is the allowlist that stops the endpoint being a general-purpose proxy.
    Episodes are looked up through their series because episode-level links are
    stored on the series' ``download_links``.
    """
    urls: set[str] = set()

    def absorb(obj):
        if obj is None:
            return
        direct = (getattr(obj, 'video_url', '') or '').strip()
        if direct:
            urls.add(direct)
        for item in (getattr(obj, 'download_links', None) or []):
            if isinstance(item, dict):
                url = (item.get('url') or '').strip()
                if url:
                    urls.add(url)

    if kind == 'movie':
        absorb(Movie.objects.filter(pk=obj_id, is_published=True).first())
    elif kind == 'series':
        absorb(Series.objects.filter(pk=obj_id, is_published=True).first())
    elif kind == 'episode':
        episode = (
            Episode.objects
            .filter(pk=obj_id, is_published=True)
            .select_related('season__series')
            .first()
        )
        absorb(episode)
        if episode is not None:
            absorb(episode.season.series)
    return urls


def _error(code: str, message: str, status: int = 400):
    return Response({'ok': False, 'code': code, 'detail': message}, status=status)


def _resigned(kind: str, obj_id: int, url: str) -> str:
    """``url`` with a live token, or '' when the title now serves something else.

    A fresh token changes only the query string, so the common case still
    streams the file the caller asked for. When the crawl comes back pointing at
    a different mirror entirely, that is a new source this request never
    validated, and the honest answer is to make the client ask again.
    """
    from apps.catalog.media_probe import signature_expired
    from apps.catalog.playback_api import resolve_target
    from apps.catalog.playback_resolve import resolve_playback

    if not signature_expired(url):
        return url

    owner, episode = resolve_target(kind, obj_id)
    if owner is None:
        return url

    result = resolve_playback(owner, episode)
    if not result.url or result.stale:
        # Nothing better exists. Try the stale URL anyway rather than refusing:
        # some CDNs honour a lapsed token, and failing at the player is no worse
        # than failing here.
        return url
    if _same_file(result.url, url):
        return result.url
    return ''


def _same_file(a: str, b: str) -> bool:
    """Same scheme, host and path — differing only in their query string."""
    from urllib.parse import urlsplit

    left, right = urlsplit(a), urlsplit(b)
    return (left.scheme, left.netloc, left.path) == (right.scheme, right.netloc, right.path)


@api_view(['POST'])
@throttle_classes([StreamOpenThrottle])
def stream_open(request):
    """Start (or join) a gateway session and return a playable HLS URL.

    Answers only once the first segment exists, so a 200 here means the player
    can start immediately. Everything that can go wrong — an unreachable source,
    a codec we will not transcode, the box already at capacity — comes back as a
    coded error the player can show in Persian rather than a dead <video>.
    """
    data = request.data if isinstance(request.data, dict) else {}
    kind = str(data.get('kind') or '').strip().lower()
    url = str(data.get('url') or '').strip()
    try:
        obj_id = int(data.get('id') or 0)
    except (TypeError, ValueError):
        obj_id = 0
    try:
        start = max(0.0, float(data.get('t') or 0.0))
    except (TypeError, ValueError):
        start = 0.0

    if kind not in {'movie', 'series', 'episode'} or not obj_id or not url:
        return _error('bad_request', 'A title and source are required.')
    if not gw.gateway_candidate(url):
        return _error('unsupported_source', 'This source cannot be converted.')
    if is_geo_locked_url(url):
        # The CDN answers only Iranian IPs; from this server it serves its
        # «turn your VPN off» page, so probing would just burn ~30 s on a 502.
        return _error('geo_locked', 'This source only plays from an Iranian connection.', 422)
    if url not in _source_urls(kind, obj_id):
        # Either the title moved on since the page loaded, or someone is trying
        # to stream an unrelated host through us. Same answer for both.
        return _error('unknown_source', 'This source does not belong to this title.', 404)

    # Re-sign before ffmpeg ever sees it. A lapsed provider token is answered
    # with 410, ffmpeg writes nothing, and the session dies on
    # ``wait_for_playlist`` — a 504 that costs a spawned process, a session slot
    # and thirty seconds of the viewer's patience to rediscover something a
    # string parse already knew. Only the URL we were asked for is re-signed:
    # if the refresh yields a different source the player is told to re-ask,
    # because the source allowlist above was checked against the old one.
    url = _resigned(kind, obj_id, url)
    if not url:
        return _error('source_expired', 'This source has moved. Please try again.', 409)

    # Reaping here rather than on a timer means the disk is tidied by the same
    # traffic that dirties it, and a burst cannot outrun the cleanup.
    gw.reap_sessions()

    tech = gw.probe_tech(url)
    if not tech.ok:
        return _error('probe_failed', 'The video file could not be read.', 502)
    if tech.needs_transcode and not gw.transcode_allowed():
        return _error('transcode_disabled', 'This title cannot be converted for your browser.')
    if tech.duration and start >= tech.duration:
        start = max(0.0, tech.duration - 10.0)

    try:
        sid = gw.start_session(url, start, tech)
    except gw.StreamGatewayError as exc:
        status = 503 if exc.code == 'gateway_busy' else 500
        return _error(exc.code, str(exc), status)

    if not gw.wait_for_playlist(sid):
        gw.reap_sessions()
        return _error('stream_start_failed', 'Preparing this video took too long.', 504)

    gw.touch(sid)
    # What the player is told must be where the picture genuinely starts, not
    # where it was asked to start: copy-mode cutting lands on the preceding
    # keyframe, and the player reads film time as start + mediaTime. Reporting
    # the request instead of the truth would put the clock, the scrubber and
    # every subtitle cue ahead of the picture by up to a whole GOP.
    start = gw.true_start(sid, start)
    return Response({
        'ok': True,
        'session': sid,
        'playlist': request.build_absolute_uri(f'/api/stream/{sid}/index.m3u8'),
        'start': round(start, 3),
        'duration': round(tech.duration, 3),
        'mode': 'transcode' if tech.needs_transcode else 'remux',
        'video': tech.video_codec,
        'audio': tech.audio_codec,
        'width': tech.width,
        'height': tech.height,
        # A session stops after this much content; the player reopens at the
        # playhead when it runs out, exactly as it does for a seek.
        'chunk_seconds': gw.SESSION_MAX_CONTENT_SECONDS,
        # …and it only keeps this much of what the viewer already watched, so a
        # rewind further than this has to reopen rather than 404 on a segment
        # that was pruned behind it.
        'keep_behind_seconds': gw.KEEP_BEHIND_SECONDS,
    })


@require_GET
def stream_playlist(request, session):
    """The session's HLS playlist, with segment names pointed back at us."""
    if not gw.session_alive(session):
        raise Http404('stream session not found')
    gw.touch(session)
    try:
        body = gw.playlist_text(
            session,
            url_for=lambda name: f'/api/stream/{session}/{name}',
        )
    except OSError:
        raise Http404('stream session not ready')
    response = HttpResponse(body, content_type='application/vnd.apple.mpegurl')
    # The playlist grows while ffmpeg runs, so it must never be cached.
    response['Cache-Control'] = 'no-store'
    return response


@require_GET
def stream_segment(request, session, name):
    """One init or media segment, straight off the session directory."""
    if not gw.session_alive(session):
        raise Http404('stream session not found')
    gw.touch(session)
    try:
        path = gw.segment_file(session, name)
    except gw.StreamGatewayError:
        raise Http404('unknown segment')
    if not gw.wait_for_segment(path):
        raise Http404('segment not ready')
    try:
        handle = path.open('rb')
    except OSError:
        raise Http404('segment not ready')
    # The handle is already open, so pruning cannot pull this file out from
    # under the response — only the ones the viewer went past minutes ago.
    gw.prune_consumed(session, name)
    content_type = 'video/mp4' if name.endswith('.mp4') else 'video/iso.segment'
    response = FileResponse(handle, content_type=content_type)
    # Segments are immutable once written, but they live only as long as the
    # session, so let the browser reuse them without letting a proxy keep them.
    response['Cache-Control'] = 'private, max-age=60'
    return response


@api_view(['GET'])
@throttle_classes([StreamSegmentThrottle])
def stream_status(request):
    """Operational view: what the gateway is currently doing."""
    sessions = []
    for sid in gw.live_sessions():
        meta = gw.read_meta(sid)
        codec = (meta.get('tech') or {}).get('video_codec') or ''
        sessions.append({
            'session': sid,
            'start': meta.get('start'),
            'created': meta.get('created'),
            'mode': 'remux' if codec in gw.COPYABLE_VIDEO else 'transcode',
        })
    used = gw.root_bytes()
    budget = gw.disk_budget_bytes()
    return Response({
        'ok': True,
        'live': len(sessions),
        'capacity': gw.max_concurrent_remux(),
        # Disk, not CPU, is what this feature runs out of first on this host,
        # so it is the number worth watching.
        'disk_used_mb': round(used / (1024 * 1024), 1),
        'disk_budget_mb': round(budget / (1024 * 1024), 1),
        'accepting': used < budget and len(sessions) < gw.max_concurrent_remux(),
        'sessions': sessions,
    })
