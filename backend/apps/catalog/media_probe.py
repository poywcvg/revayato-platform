"""Network layer of the pre-publish media check: does this URL really stream?

Everything else in the catalog judges a source by *reading its URL* — container,
codec, host, signature expiry (``media_links``, ``playback_sources``,
``link_integrity``). That catches the wrong kind of file, never the missing one:
a 404, a soft-404 HTML error page, a truncated 12 KB placeholder or a CDN that
has since revoked the path all look perfectly healthy as strings, so the title
goes live and the first viewer is the one who discovers it is broken.

This module asks the server. One small ranged GET per URL (never a full
download) answers three questions a string cannot:

* is it **there** (HTTP status of the final URL after redirects);
* is it **video** (content type / magic bytes, not an HTML "link expired" page);
* is it **seekable** (``Accept-Ranges`` + a plausible ``Content-Length``) —
  without byte ranges the web player cannot seek and mid-file resume breaks.

**Three outcomes, never two.** The verdict is ``live`` / ``dead`` / ``unknown``,
because this box cannot always reach a host that viewers can: some provider CDNs
RESET the TLS handshake for datacenter egress (see ``subtitle_extract``), and a
403/timeout from here is not proof of a broken link. Only a *definitive* answer
from the server (404/410/451, or an HTML error body where video was promised)
counts as ``dead``; everything else is ``unknown`` and the caller keeps the link,
retries later, and refuses to publish rather than deleting a good source.

**And one answer is not quite enough.** These hosts do not answer the same
question the same way twice: one missing file answered ``404 206 404 404 206``
to five identical ranged GETs a second apart — where each 206 was a 4 KB styled
"not found" page, not the film. The verdict was right both times, but it is
reached down two different code paths, and a host willing to improvise that much
under load is a host whose *first* answer deserves a second look. So ``dead``,
the only verdict anything deletes on, must be reached twice
(:data:`_DEAD_CONFIRM_BACKOFF`): one ``live`` answer wins outright, and two
attempts that disagree collapse to ``unknown``, which keeps the link.

**A lapsed signature is not a death.** Most provider links here are time-limited
(``?md5=…&expires=…``), and when the token lapses the CDN answers ``410 Gone``
— which is a *definitive* missing status, indistinguishable from a file that
was really deleted. That collision is not survivable at this scale: 6,956
movies and 19,688 episodes carry such a token, it lapses in about thirteen
hours, and nothing re-signs it on the way to a viewer. Believing those 410s
condemned 4,119 of the first 6,387 movies swept. So a URL whose token has
already lapsed is never probed and never judged: the answer would describe the
token, not the film. It comes back ``unknown``/``signature_expired``, which
keeps the link, keeps it out of every deletion path, and routes it to the one
repair that actually fixes it — a re-crawl for a fresh signature
(:mod:`playback_resolve`).

Results are cached briefly and a repeatedly failing host trips a circuit breaker,
so one dead CDN costs a few milliseconds instead of stalling an import run.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field, replace
from urllib.parse import urlsplit

from django.core.cache import cache

logger = logging.getLogger(__name__)

USER_AGENT = 'RevayatoMediaProbe/1.0 (+https://revayato.com)'

# How much of the file to pull. Enough for a container signature, small enough
# that probing a whole catalog costs kilobytes.
PROBE_BYTES = 2048
#: How much of an HTML answer to read before calling it a dead link. Block pages
#: open with a long inline ``<style>`` block and only then say what they are —
#: mehracdn's "turn your VPN off" page puts its first words at byte ~3000 of
#: 4213, past the 2 KB slice above, so judging the slice read a geo block as a
#: dead file and the sweep unpublished films that play fine in Iran.
HTML_PROBE_BYTES = 16384
CONNECT_TIMEOUT = 6.0
READ_TIMEOUT = 10.0
MAX_REDIRECTS = 5

#: Provider CDNs routinely serve expired or incomplete certificate chains, and a
#: probe that fails them would report healthy films as broken. Nothing secret is
#: sent (a public URL, no credentials) and only status/size/type are read, so the
#: default is off — but it is a setting, so an operator can demand strict TLS.
def _verify_tls() -> bool:
    from django.conf import settings

    return bool(getattr(settings, 'CATALOG_PROBE_VERIFY_TLS', False))

# A real feature/episode file is megabytes. Anything smaller is a placeholder,
# an error page saved with a video extension, or a truncated upload.
MIN_VIDEO_BYTES = 1_000_000
# HLS manifests are tiny text files — judged by content, not size.
MIN_MANIFEST_BYTES = 16

#: Statuses where the server positively states the file is gone. Only these
#: justify dropping a stored link.
DEFINITIVE_MISSING = {404, 410, 451}

_CACHE_PREFIX = 'catalog:mediaprobe:'
_LIVE_TTL = 1800         # 30 min — a good link rarely dies within an import run
_DEAD_TTL = 3600         # 1 h — a 404 does not un-404 quickly
_UNKNOWN_TTL = 300       # 5 min — re-ask soon, the box may just be having a bad minute

#: Pauses before each re-ask that a ``dead`` verdict must survive. One extra
#: attempt, not three: a real transient (5xx, reset, timeout) is already
#: ``unknown`` rather than ``dead``, so this is insurance against a single
#: improvised error page, and insurance that costs a second per dead link is
#: affordable across a 76,000-row catalog while several seconds is not.
_DEAD_CONFIRM_BACKOFF = (1.0,)

# Per-host circuit breaker: after this many consecutive unknowns, stop paying the
# timeout for every remaining URL on that host in this window.
_HOST_FAIL_KEY = _CACHE_PREFIX + 'hostfail:'
_HOST_FAIL_LIMIT = 5
_HOST_FAIL_TTL = 600

#: Query parameters these providers use to time-limit a URL. Deliberately a
#: short, explicit list: a false positive here makes a healthy link unprobeable,
#: which is worse than missing one vendor's spelling.
_SIGNATURE_EXPIRY_RE = re.compile(
    r'(?:^|[?&])(?:expires?|valid_until|token_expires)=(\d{9,13})(?:&|#|$)', re.IGNORECASE,
)

#: Treat a token as lapsed slightly before it really does. A probe that starts
#: inside the last few seconds of validity can still be answered after it, and a
#: player handed such a URL fails mid-buffer instead of at once.
SIGNATURE_SKEW_SECONDS = 120


def signature_expiry(url: str) -> float | None:
    """Unix time this URL's access token lapses, or ``None`` if it carries none.

    Both seconds and milliseconds appear in the wild; anything past the year
    2200 in seconds is read as milliseconds rather than as a link valid for
    nine thousand years.
    """
    match = _SIGNATURE_EXPIRY_RE.search(url or '')
    if not match:
        return None
    try:
        value = float(match.group(1))
    except (TypeError, ValueError):
        return None
    if value > 7_258_118_400:  # 2200-01-01 in seconds — so it must be millis
        value /= 1000.0
    return value


def signature_expired(url: str, *, skew: float = SIGNATURE_SKEW_SECONDS) -> bool:
    """Has this URL's access token already lapsed? False when it has none."""
    expiry = signature_expiry(url)
    if expiry is None:
        return False
    return expiry <= time.time() + max(0.0, float(skew))


_HTML_SNIFF_RE = re.compile(rb'^\s*(<!doctype html|<html|<head|<body|\{|\[)', re.IGNORECASE)

#: Markers of a geo/VPN block page served with 200 OK where a video was
#: promised. Several provider CDNs serve Iranian catalogues only to Iranian
#: egress IPs and answer everyone else (including this datacenter, which is in
#: France) with a styled HTML page telling the viewer to turn their VPN off
#: (``فیلتر شکن را خاموش کنید``). That answer describes *where the probe ran*,
#: not the file: the same URL plays fine in a browser on an Iranian network.
#: Judging it ``dead`` would condemn healthy links, clear playback URLs and
#: teach the gateway a file is missing that is not — so it is ``unknown``,
#: which keeps the link and retries later, exactly like a 403 or a timeout.
_GEO_BLOCK_MARKERS = (
    'فیلتر شکن',
    'فیلترشکن',
    'وی پی ان',
    'تحریم',
    'موقعیت جغرافیایی',
    'turn off your vpn',
    'disable your vpn',
    'turn your vpn off',
    'vpn detected',
    'proxy detected',
    'not available in your country',
    'not available in your region',
    'blocked in your country',
    'outside of iran',
    'inside iran',
    'iran only',
    'only in iran',
)


def _looks_like_geo_block(body: bytes) -> bool:
    """Is this HTML body a geo/VPN block page rather than a missing-file page?"""
    if not body:
        return False
    text = body.decode('utf-8', 'ignore').lower()
    return any(marker in text for marker in _GEO_BLOCK_MARKERS)
_MANIFEST_RE = re.compile(r'\.m3u8($|[?#])', re.IGNORECASE)
_VIDEO_CONTENT_TYPE_RE = re.compile(
    r'^(video/|application/(octet-stream|x-mpegurl|vnd\.apple\.mpegurl|dash\+xml|mp4)|binary/)',
    re.IGNORECASE,
)
_MANIFEST_CONTENT_TYPE_RE = re.compile(
    r'(mpegurl|application/(x-mpegurl|vnd\.apple\.mpegurl)|text/plain)', re.IGNORECASE,
)


@dataclass(frozen=True)
class Probe:
    """What the server said about one URL."""

    url: str
    verdict: str = 'unknown'          # live | dead | unknown
    reason: str = ''                  # machine code, '' when live
    status: int = 0
    content_type: str = ''
    content_length: int = 0
    accept_ranges: bool = False
    elapsed_ms: int = 0
    final_url: str = ''
    detail: dict = field(default_factory=dict)

    @property
    def live(self) -> bool:
        return self.verdict == 'live'

    @property
    def dead(self) -> bool:
        return self.verdict == 'dead'

    def as_dict(self) -> dict:
        return {
            'url': self.url[:500],
            'verdict': self.verdict,
            'reason': self.reason,
            'status': self.status,
            'content_type': self.content_type[:80],
            'bytes': self.content_length,
            'ranges': self.accept_ranges,
            'ms': self.elapsed_ms,
        }


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or '').lower()
    except ValueError:
        return ''


def _cache_key(url: str) -> str:
    import hashlib

    return _CACHE_PREFIX + hashlib.sha1(url.encode('utf-8', 'ignore')).hexdigest()[:32]


def _host_tripped(host: str) -> bool:
    if not host:
        return False
    return int(cache.get(_HOST_FAIL_KEY + host) or 0) >= _HOST_FAIL_LIMIT


def _note_host(host: str, *, failed: bool) -> None:
    """Track consecutive unreachable results per host for the circuit breaker."""
    if not host:
        return
    key = _HOST_FAIL_KEY + host
    if not failed:
        cache.delete(key)
        return
    try:
        if cache.add(key, 1, _HOST_FAIL_TTL):
            return
        cache.incr(key)
    except ValueError:  # key expired between add and incr
        cache.set(key, 1, _HOST_FAIL_TTL)


def _classify_status(status: int) -> tuple[str, str]:
    """Map an HTTP status to ``(verdict, reason)``."""
    if status in DEFINITIVE_MISSING:
        return 'dead', f'http_{status}'
    if 200 <= status < 300:
        return 'live', ''
    if status in {401, 403}:
        # Hotlink protection and datacenter blocks look like this. A viewer's
        # browser (with a Referer and a residential IP) may still play it, so
        # this is never proof of a dead file.
        return 'unknown', f'http_{status}'
    if 300 <= status < 400:
        return 'unknown', 'too_many_redirects'
    if status >= 500:
        return 'unknown', f'http_{status}'
    return 'unknown', f'http_{status}'


def _looks_like_html(body: bytes, content_type: str) -> bool:
    if 'text/html' in content_type or 'application/json' in content_type:
        return True
    return bool(body and _HTML_SNIFF_RE.match(body))


def _content_length(response, body: bytes) -> int:
    """Total file size: ``Content-Range`` total when ranged, else Content-Length."""
    crange = response.headers.get('content-range') or ''
    if '/' in crange:
        total = crange.rsplit('/', 1)[-1].strip()
        if total.isdigit():
            return int(total)
    raw = response.headers.get('content-length') or ''
    if raw.isdigit():
        size = int(raw)
        # On a 206 the header is the slice, not the file — only trust a 200.
        if response.status_code == 206 and size <= PROBE_BYTES:
            return 0
        return size
    return len(body or b'')


def probe_url(url: str, *, expect: str = 'video', use_cache: bool = True) -> Probe:
    """Ask the server whether ``url`` is a real, seekable media file.

    ``expect`` is ``video`` for a progressive file or ``manifest`` for HLS/DASH
    (tiny text, judged by its ``#EXTM3U`` body rather than its size).
    Never raises: transport failures come back as ``unknown``.
    """
    url = (url or '').strip()
    if not url:
        return Probe(url='', verdict='unknown', reason='empty_url')
    if not url.startswith(('http://', 'https://')):
        # Object keys for our own storage are resolved elsewhere; not our call.
        return Probe(url=url, verdict='unknown', reason='not_http')

    key = _cache_key(url)
    if use_cache:
        cached = cache.get(key)
        if isinstance(cached, dict):
            return Probe(**{**cached, 'detail': {'cached': True}})

    if signature_expired(url):
        # Asking would only tell us the token lapsed, which we already know, and
        # the answer (``410``) would read as proof the film is gone. Not probed,
        # not cached: the moment a re-crawl re-signs it, this URL is a different
        # string anyway.
        return Probe(url=url, verdict='unknown', reason='signature_expired')

    host = _host(url)
    if _host_tripped(host):
        return Probe(url=url, verdict='unknown', reason='host_circuit_open')

    probe = _confirm(url, expect=expect)
    if use_cache:
        ttl = {'live': _LIVE_TTL, 'dead': _DEAD_TTL}.get(probe.verdict, _UNKNOWN_TTL)
        cache.set(key, {
            'url': probe.url, 'verdict': probe.verdict, 'reason': probe.reason,
            'status': probe.status, 'content_type': probe.content_type,
            'content_length': probe.content_length, 'accept_ranges': probe.accept_ranges,
            'elapsed_ms': probe.elapsed_ms, 'final_url': probe.final_url,
        }, ttl)
    # Only transport-level failure feeds the breaker: a 403 is an answer, and a
    # host that answers is not the kind of host that hangs the importer.
    _note_host(host, failed=probe.reason in _TRANSPORT_REASONS)
    return probe


_TRANSPORT_REASONS = {'timeout', 'connect_error', 'dns_error', 'tls_error', 'transport_error'}


def _confirm(url: str, *, expect: str) -> Probe:
    """One probe — plus the corroboration a ``dead`` verdict has to survive.

    Anything but ``dead`` is returned as it came: only the destructive verdict
    pays for a second opinion.
    """
    probe = _request(url, expect=expect)
    if probe.verdict != 'dead':
        return probe

    for pause in _DEAD_CONFIRM_BACKOFF:
        time.sleep(pause)
        retry = _request(url, expect=expect)
        if retry.verdict == 'live':
            # It was there the whole time; the first answer was the host
            # flapping. Report what the file actually is, and say so.
            return replace(retry, detail={**(retry.detail or {}), 'flapped': probe.reason})
        if retry.verdict != 'dead':
            # One answer says gone, the next cannot tell. That is a disagreement,
            # not proof, and proof is what deleting a link requires.
            return replace(
                probe,
                verdict='unknown',
                reason=f'unconfirmed_{probe.reason}'[:60],
                detail={**(probe.detail or {}), 'retry': retry.reason},
            )

    return replace(probe, detail={**(probe.detail or {}), 'attempts': len(_DEAD_CONFIRM_BACKOFF) + 1})


def _request(url: str, *, expect: str) -> Probe:
    import httpx

    started = time.monotonic()
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': '*/*',
        # Ranged GET, not HEAD: these CDNs frequently 403 or lie about HEAD while
        # serving ranges correctly — and the range is what the player uses anyway.
        'Range': f'bytes=0-{PROBE_BYTES - 1}',
    }
    try:
        with httpx.Client(
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
            timeout=httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT),
            verify=_verify_tls(),
        ) as client:
            with client.stream('GET', url, headers=headers) as response:
                body = _read(response, PROBE_BYTES)
            content_type = (response.headers.get('content-type') or '').split(';')[0].strip().lower()
            if (
                expect != 'manifest'
                and len(body) >= PROBE_BYTES
                and _looks_like_html(body, content_type)
                and not _looks_like_geo_block(body)
            ):
                # The slice was cut before the page said what it is. Read the
                # rest of it (pages are small) before condemning the link.
                fuller = {**headers, 'Range': f'bytes=0-{HTML_PROBE_BYTES - 1}'}
                with client.stream('GET', url, headers=fuller) as page:
                    if page.status_code < 400:
                        body = _read(page, HTML_PROBE_BYTES) or body
            return _judge(url, response, body, expect=expect, started=started)
    except Exception as exc:  # noqa: BLE001 — every transport failure is 'unknown'
        return Probe(
            url=url, verdict='unknown', reason=_transport_reason(exc),
            elapsed_ms=int((time.monotonic() - started) * 1000),
            detail={'error': type(exc).__name__},
        )


def _read(response, limit: int) -> bytes:
    body = b''
    for chunk in response.iter_bytes(min(limit, PROBE_BYTES)):
        body += chunk
        if len(body) >= limit:
            break
    return body[:limit]


def _transport_reason(exc: Exception) -> str:
    import httpx

    if isinstance(exc, httpx.TooManyRedirects):
        return 'too_many_redirects'
    if isinstance(exc, httpx.TimeoutException):
        return 'timeout'
    if isinstance(exc, httpx.ConnectError):
        text = str(exc).lower()
        if 'name or service not known' in text or 'nodename nor servname' in text:
            return 'dns_error'
        if 'ssl' in text or 'tls' in text or 'certificate' in text:
            return 'tls_error'
        return 'connect_error'
    if isinstance(exc, httpx.TransportError):
        return 'transport_error'
    return 'probe_error'


def _judge(url: str, response, body: bytes, *, expect: str, started: float) -> Probe:
    elapsed = int((time.monotonic() - started) * 1000)
    status = int(response.status_code)
    content_type = (response.headers.get('content-type') or '').split(';')[0].strip().lower()
    size = _content_length(response, body)
    accept_ranges = (
        status == 206
        or 'bytes' in (response.headers.get('accept-ranges') or '').lower()
    )
    final_url = str(response.url) if response.url else url

    verdict, reason = _classify_status(status)
    base = dict(
        url=url, status=status, content_type=content_type, content_length=size,
        accept_ranges=accept_ranges, elapsed_ms=elapsed, final_url=final_url[:500],
    )
    if verdict != 'live':
        return Probe(verdict=verdict, reason=reason, **base)

    # 2xx is not enough — providers answer 200 with an HTML "link expired" page.
    if expect == 'manifest':
        text = body.decode('utf-8', 'ignore').lstrip('﻿').strip()
        if not text.startswith('#EXTM3U'):
            return Probe(verdict='dead', reason='not_a_manifest', **base)
        if len(body) < MIN_MANIFEST_BYTES:
            return Probe(verdict='dead', reason='empty_manifest', **base)
        # Kept for the segment check; deliberately not cached (see probe_url).
        return Probe(verdict='live', reason='', detail={'body': text[:PROBE_BYTES]}, **base)

    if _looks_like_html(body, content_type):
        if _looks_like_geo_block(body):
            # Served to the wrong network, not a missing file. See
            # _GEO_BLOCK_MARKERS: an Iranian CDN answering a French probe.
            return Probe(verdict='unknown', reason='geo_blocked', **base)
        return Probe(verdict='dead', reason='html_not_video', **base)
    if content_type and not _VIDEO_CONTENT_TYPE_RE.match(content_type):
        # An explicit non-video type (text/plain, image/…) where a film should be.
        return Probe(verdict='dead', reason=f'not_video:{content_type}'[:60], **base)
    if size and size < MIN_VIDEO_BYTES:
        return Probe(verdict='dead', reason='too_small', **base)
    if not body:
        return Probe(verdict='unknown', reason='empty_body', **base)
    if not accept_ranges:
        # Plays, but the viewer cannot seek and a dropped connection restarts the
        # film. Usable as a download, not good enough to be the streaming source.
        return Probe(verdict='live', reason='no_byte_ranges', **base)
    return Probe(verdict='live', reason='', **base)


def probe_manifest(url: str, *, use_cache: bool = True) -> Probe:
    """Verify an HLS manifest *and* that its first real segment is fetchable.

    A manifest that lists segments the CDN has already purged is the exact shape
    of "it played yesterday, it spins forever today".
    """
    manifest = probe_url(url, expect='manifest', use_cache=use_cache)
    if not manifest.live:
        return manifest
    segment_url = _first_segment(url, manifest)
    if not segment_url:
        # A cached manifest probe carries no body — the manifest itself was
        # verified when it was fetched, so there is nothing further to prove.
        return manifest
    segment = probe_url(segment_url, expect='video', use_cache=use_cache)
    if segment.dead:
        return Probe(
            url=url, verdict='dead', reason=f'segment_{segment.reason}'[:60],
            status=manifest.status, content_type=manifest.content_type,
            elapsed_ms=manifest.elapsed_ms + segment.elapsed_ms,
            final_url=manifest.final_url, detail={'segment': segment.as_dict()},
        )
    return manifest


def _first_segment(manifest_url: str, probe: Probe) -> str:
    """First variant/segment URI from a manifest we already fetched."""
    from urllib.parse import urljoin

    body = (probe.detail or {}).get('body') or ''
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            return urljoin(manifest_url, line)
    return ''
