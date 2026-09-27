"""Just-in-time remux gateway — makes every catalog title playable in every browser.

**The problem this exists to solve.** Roughly 6,600 published movies carry only
Matroska (``.mkv``) sources. Safari and Firefox ship no Matroska demuxer, so the
``<video>`` element rejects the file outright — yet a probe of the actual bytes
shows the streams inside are almost always **H.264 video with MP3/AAC audio**,
which every one of those browsers decodes happily. Measured across every open
playback gap: 89.6% Matroska with an unadvertised codec, 10.2% Matroska already
labelled x264, and just **9 titles (0.1%) genuinely HEVC**. The catalog is not
full of undecodable video; it is full of decodable video in the wrong *envelope*.

Until now the only remedy was ``playback_sources``: re-crawl the providers and
hope they publish an MP4 mirror. That genuinely works when a mirror exists, but
it has permanently exhausted itself on ~2,200 titles (``no_browser_safe_upstream``)
because for many films no MP4 was ever released. Those titles could never be
fixed by crawling harder.

**The fix is to change the envelope, not the video.** ``ffmpeg -c:v copy`` rewrites
the container without re-encoding a single frame: the expensive part of
transcoding (decode + encode) never runs, so a 1080p stream costs a few percent
of one core instead of a whole one. Audio *is* re-encoded to AAC stereo — that is
cheap, and it uniformly resolves MP3/AC3/DTS tracks that Safari would otherwise
refuse.

**Fallback only, by design.** Direct CDN playback stays the default and nothing
routes through this box while the browser can open the file itself; Chrome and
Android keep streaming straight from the provider exactly as before. The gateway
engages only once a browser has actually failed (or is known to be unable) to
play a source — so it costs bandwidth strictly for the viewers who would
otherwise have seen «پخش ویدیو ممکن نشد» and nothing at all for everyone else.

**Why sessions, and not a virtual playlist.** The obvious cheap design is a
stateless playlist of fixed six-second segments, each produced on demand by
``-ss N*6 -t 6``. It was built and measured, and it does not work: ``-c:v copy``
can only cut on a keyframe, so ``-ss`` snaps *backwards* to the keyframe at or
before the mark. Adjacent segments then overlap by a whole GOP. Against a
synthetic file the joined stream decoded with ``corrupt input packet`` and a 60s
source came back as 78s. A fixed grid and copy-mode cutting are fundamentally
incompatible, and no amount of ``-copyts`` / ``-output_ts_offset`` tuning fixes
it — those flags move the timestamps, not the frames.

So the gateway lets **ffmpeg's own HLS muxer** cut the segments. It knows where
the keyframes are, so every ``#EXTINF`` is the true duration of its segment
(measured: declared 10.375000 against an actual 10.374667) and the boundary bug
cannot occur by construction. That costs one long-lived ffmpeg per viewer and a
directory of segments to clean up, which is what everything below manages.

Segments are **fMP4**, not MPEG-TS. On a real catalog source the TS segments
carried SPS/PPS only in the first segment, so seeking into any later one failed
to decode; with fMP4 a single shared ``init.mp4`` carries the parameter sets and
all eleven test segments decoded standalone. ``-readrate`` keeps ffmpeg just
ahead of the viewer rather than racing to the end of the film, which is what
bounds both bandwidth and the disk each session occupies.

Tokens are signed (``django.core.signing``) so the endpoint cannot be used as an
open proxy for arbitrary URLs — only URLs this backend itself minted a token for,
and only until the token ages out.
"""

from __future__ import annotations

import errno
import fcntl
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from hashlib import sha1
from pathlib import Path
from secrets import token_hex

from django.conf import settings
from django.core import signing
from django.core.cache import cache

logger = logging.getLogger(__name__)

#: Salt keeps these tokens unusable anywhere else in the project that signs data.
TOKEN_SALT = 'revayato.stream.source.v1'

#: Long enough to watch a feature film without the URL dying mid-play, short
#: enough that a leaked token is not a permanent proxy grant.
TOKEN_MAX_AGE_SECONDS = 12 * 3600

#: Target segment length. ffmpeg treats it as a *minimum* and extends to the next
#: keyframe, which is exactly the behaviour that keeps every segment decodable.
SEGMENT_SECONDS = 6

#: Codecs a mainstream browser can decode once the container is fixed. Anything
#: outside this set needs a real re-encode, which is a different cost class.
COPYABLE_VIDEO = frozenset({'h264', 'avc1'})

#: ffprobe is cheap but not free (one ranged read of the container header), and
#: a title's technical shape does not change between viewings.
PROBE_CACHE_SECONDS = 6 * 3600
PROBE_TIMEOUT_SECONDS = 25

#: How far ahead of the viewer ffmpeg is allowed to run. Just above 1.0 so the
#: buffer grows steadily without the process downloading the whole film for a
#: viewer who watches four minutes and leaves.
#:
#: 1.25 rather than something bolder because the browser is not the beneficiary
#: of a bigger lead: hls.js stops fetching once it holds its own buffer (tens of
#: seconds), so everything ffmpeg writes past that sits on the volume unread. A
#: lead only buys resilience against a *sustained* slow origin, and at this rate
#: it still grows by fifteen seconds for every minute watched. What it costs is
#: exact: peak session size is (rate - 1) x the content cap + KEEP_BEHIND, so
#: 1.25 caps a session at roughly eight minutes of video on disk instead of the
#: twelve that 1.5 would hold.
READ_RATE = 1.25

#: A session stops after this much *content* so one abandoned tab cannot park a
#: full film on disk. The player reopens at the playhead when it runs out, which
#: is the same path a seek takes, so this is invisible to the viewer.
SESSION_MAX_CONTENT_SECONDS = 1800

#: Segments further behind the one being fetched than this are deleted as the
#: viewer passes them. Without it a session holds its entire content window on
#: disk at once, and disk is the scarcest thing on this box: with it, a session
#: costs roughly (how far ffmpeg runs ahead + this) times the bitrate, whatever
#: the film's length. The player treats a seek further back than this as a
#: reopen — the same path it already takes at the end of a session — so nothing
#: a viewer can actually reach is ever missing.
KEEP_BEHIND_SECONDS = 120

#: No request for this long and the viewer is gone: kill ffmpeg, drop the files.
SESSION_IDLE_SECONDS = 90

#: Backstop for a session whose heartbeat somehow keeps getting touched.
SESSION_MAX_AGE_SECONDS = 4 * 3600

#: ``\Z`` rather than ``$``: in Python ``$`` also matches just before a
#: trailing newline, so ``"init.mp4\n"`` would slip through a ``$`` pattern and
#: reach the filesystem. This is the path-traversal boundary — it has to mean
#: end-of-string literally.
_SEGMENT_NAME_RE = re.compile(r'\A(?:init\.mp4|seg\d{5}\.m4s)\Z')


def session_root() -> Path:
    """Where session directories live.

    Deliberately *not* under the backend's 128MB ``/tmp`` tmpfs — video segments
    need real room, and the gateway runs in its own container with its own
    volume so this work never competes with the web box for disk or CPU.
    """
    return Path(getattr(settings, 'STREAM_SESSION_ROOT', '/var/tmp/revayato-stream'))


def max_concurrent_remux() -> int:
    """Bounded by *disk*, not CPU: a remux is nearly free to compute but each
    live session parks its segments on the volume until the viewer leaves."""
    return max(1, int(getattr(settings, 'STREAM_MAX_CONCURRENT_REMUX', 6)))


def max_concurrent_transcode() -> int:
    return max(0, int(getattr(settings, 'STREAM_MAX_CONCURRENT_TRANSCODE', 2)))


def transcode_allowed() -> bool:
    """Re-encoding HEVC/AV1 is opt-in — it is the one path that burns a core."""
    return bool(getattr(settings, 'STREAM_ALLOW_TRANSCODE', True))


def disk_budget_bytes() -> int:
    """Hard ceiling on what every live session may hold, together.

    Concurrency caps bound the number of sessions but not their size, and the
    volume this writes to is shared with the rest of the box. Filling it would
    take the site down, so the gateway refuses new sessions before that instead
    of degrading everything around it.
    """
    return max(256, int(getattr(settings, 'STREAM_DISK_BUDGET_MB', 2048))) * 1024 * 1024


def root_bytes() -> int:
    """Bytes currently held by all session directories."""
    total = 0
    try:
        entries = session_root().rglob('*')
    except OSError:
        return 0
    for entry in entries:
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


def session_reusable(sid: str) -> bool:
    """Can a viewer arriving now still start at this session's beginning?

    Only while its first segment survives. Pruning discards the opening of a
    session as its own viewer moves past it, yet the playlist goes on listing
    every segment from zero — so a second viewer handed a pruned session would
    404 on the very first thing they fetched. A session that has not written
    its playlist yet has nothing to have pruned, and is always reusable.
    """
    directory = _dir_for(sid)
    try:
        if not (directory / 'index.m3u8').exists():
            return True
        return (directory / 'seg00000.m4s').exists()
    except OSError:
        return False


def prune_consumed(sid: str, name: str) -> int:
    """Delete the segments the viewer has already gone past.

    Called as each segment is served. Walking backwards and stopping at the
    first name that is already gone keeps this O(1) once a session is running,
    because every earlier request pruned its own tail. ``init.mp4`` is never
    touched: every segment in the session needs it to decode.
    """
    match = re.match(r'\Aseg(\d{5})\.m4s\Z', name or '')
    if not match:
        return 0
    behind = max(1, int(KEEP_BEHIND_SECONDS / max(1, SEGMENT_SECONDS)))
    oldest_kept = int(match.group(1)) - behind
    if oldest_kept <= 0:
        return 0
    directory = _dir_for(sid)
    removed = 0
    for index in range(oldest_kept - 1, -1, -1):
        try:
            (directory / f'seg{index:05d}.m4s').unlink()
        except OSError:
            # Missing (pruned on an earlier request) or unreadable — either way
            # everything below this point is already dealt with.
            break
        removed += 1
    return removed


class StreamGatewayError(Exception):
    """Safe, non-secret failure for gateway operations."""

    def __init__(self, message='Stream gateway error.', *, code='stream_error'):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------- #
# Signed source tokens
# --------------------------------------------------------------------------- #

def sign_source(url: str, *, kind: str = '', obj_id: int | None = None,
                episode_id: int | None = None) -> str:
    """Mint an opaque token standing for one upstream source URL.

    The URL travels inside the signature rather than in the path, which keeps
    provider signatures (``?md5=…&expires=…``) out of our own URLs and out of
    browser history, and makes the endpoint useless to anyone trying to stream
    an arbitrary third-party host through this server.
    """
    url = (url or '').strip()
    if not url:
        raise StreamGatewayError('A source URL is required.', code='missing_source')
    payload = {'u': url}
    if kind:
        payload['k'] = kind
    if obj_id:
        payload['o'] = int(obj_id)
    if episode_id:
        payload['e'] = int(episode_id)
    return signing.dumps(payload, salt=TOKEN_SALT, compress=True)


def unsign_source(token: str) -> dict:
    """Recover a token's payload, or raise :class:`StreamGatewayError`."""
    try:
        data = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE_SECONDS)
    except signing.SignatureExpired as exc:
        raise StreamGatewayError('This playback link expired.', code='token_expired') from exc
    except signing.BadSignature as exc:
        raise StreamGatewayError('Invalid playback link.', code='bad_token') from exc
    if not isinstance(data, dict) or not data.get('u'):
        raise StreamGatewayError('Invalid playback link.', code='bad_token')
    return data


# --------------------------------------------------------------------------- #
# Probing the real bytes
# --------------------------------------------------------------------------- #

@dataclass
class SourceTech:
    """What the file actually *is* — read from the container, never guessed.

    Every other module in the catalog infers container and codec from the
    filename (``…1080p.x265.10bit.mkv``), which is all that is available before
    download and is right most of the time. The gateway cannot afford "most of
    the time": remuxing with the wrong assumption produces a stream that fails
    in the player. So it asks ffprobe.
    """

    ok: bool = False
    container: str = ''
    video_codec: str = ''
    audio_codec: str = ''
    duration: float = 0.0
    width: int = 0
    height: int = 0
    reason: str = ''

    @property
    def video_copyable(self) -> bool:
        return self.video_codec in COPYABLE_VIDEO

    @property
    def needs_transcode(self) -> bool:
        return self.ok and not self.video_copyable

    @property
    def seekable(self) -> bool:
        """Without a real duration the player has no timeline to scrub."""
        return self.duration > 0

    def as_dict(self) -> dict:
        return asdict(self)


def _ffmpeg_network_args() -> list[str]:
    """HTTP behaviour tuned for these provider CDNs.

    Mirrors ``subtitle_extract._ffmpeg_network_args``: the same hosts serve both
    pipelines, they stall rather than reset, and they reject unfamiliar agents.
    """
    return [
        '-user_agent', 'Mozilla/5.0 (compatible; RevayatoStream/1.0)',
        '-reconnect', '1',
        '-reconnect_streamed', '1',
        '-reconnect_on_network_error', '1',
        '-reconnect_delay_max', '5',
        '-rw_timeout', '20000000',
    ]


def _probe_cache_key(url: str) -> str:
    return f'catalog:stream:tech:{sha1(url.encode("utf-8", "ignore")).hexdigest()}'


def probe_tech(url: str, *, refresh: bool = False) -> SourceTech:
    """Read container/codec/duration from the source itself.

    Only the header is fetched — ffprobe stops as soon as it has described the
    streams, so this costs kilobytes, not the file.
    """
    url = (url or '').strip()
    if not url:
        return SourceTech(reason='missing_source')
    if not shutil.which('ffprobe'):
        return SourceTech(reason='ffprobe_unavailable')

    key = _probe_cache_key(url)
    if not refresh:
        cached = cache.get(key)
        if cached:
            try:
                return SourceTech(**cached)
            except TypeError:
                pass

    cmd = [
        'ffprobe', '-hide_banner', '-loglevel', 'error',
        *_ffmpeg_network_args(),
        '-analyzeduration', '8M', '-probesize', '8M',
        '-show_entries', 'format=format_name,duration:stream=codec_type,codec_name,width,height',
        '-of', 'json', url,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, timeout=PROBE_TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        return SourceTech(reason='probe_timeout')
    except OSError as exc:
        logger.warning('stream probe failed to spawn: %s', exc)
        return SourceTech(reason='probe_spawn_error')

    if proc.returncode != 0:
        # A 4xx from the CDN is by far the most common cause and is not our bug;
        # keep it at debug volume so a rate-limited host cannot flood the log.
        logger.debug('ffprobe rc=%s for %s: %s', proc.returncode, url[:120],
                     (proc.stderr or b'')[:200])
        return SourceTech(reason='probe_failed')

    try:
        data = json.loads(proc.stdout or b'{}')
    except ValueError:
        return SourceTech(reason='probe_unparsable')

    fmt = data.get('format') or {}
    streams = data.get('streams') or []
    video = next((s for s in streams if s.get('codec_type') == 'video'), None)
    audio = next((s for s in streams if s.get('codec_type') == 'audio'), None)
    if not video:
        return SourceTech(reason='no_video_stream')

    try:
        duration = float(fmt.get('duration') or 0.0)
    except (TypeError, ValueError):
        duration = 0.0

    tech = SourceTech(
        ok=True,
        container=(fmt.get('format_name') or '').split(',')[0],
        video_codec=(video.get('codec_name') or '').lower(),
        audio_codec=((audio or {}).get('codec_name') or '').lower(),
        duration=max(0.0, duration),
        width=int(video.get('width') or 0),
        height=int(video.get('height') or 0),
    )
    cache.set(key, tech.as_dict(), PROBE_CACHE_SECONDS)
    return tech


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #

def session_id(url: str, start: float, salt: str = '') -> str:
    """Identity of a session is *what it produces*, so two viewers who open the
    same film at the same point share one ffmpeg instead of spawning two.

    ``salt`` deliberately breaks that sharing for the one case where it is
    wrong — see ``session_reusable``.
    """
    seed = f'{url}|{start:.1f}|{salt}'.encode('utf-8', 'ignore')
    return sha1(seed).hexdigest()[:20]


def _dir_for(sid: str) -> Path:
    return session_root() / sid


def _meta_path(sid: str) -> Path:
    return _dir_for(sid) / 'meta.json'


def _beat_path(sid: str) -> Path:
    return _dir_for(sid) / 'beat'


def read_meta(sid: str) -> dict:
    try:
        return json.loads(_meta_path(sid).read_text('utf-8'))
    except (OSError, ValueError):
        return {}


def touch(sid: str) -> None:
    """Heartbeat. A session with no requests is a viewer who left."""
    try:
        _beat_path(sid).write_text(str(time.time()), 'utf-8')
    except OSError:
        pass


def _last_beat(sid: str) -> float:
    try:
        return float(_beat_path(sid).read_text('utf-8').strip())
    except (OSError, ValueError):
        return 0.0


def _pid_alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError as exc:
        return exc.errno == errno.EPERM
    return True


def _pid_owns_session(pid: int, sid: str) -> bool:
    """Is this pid really the ffmpeg we started for this session?

    ``meta.json`` outlives the process it describes and Linux recycles pids, so
    a stale file can name a pid that now belongs to something else entirely —
    including a worker of this very application. Signalling on the strength of
    a number alone is therefore unsafe. Every session's command line contains
    its own segment directory, which makes this an exact test rather than a
    guess, and it is the interlock that makes ``_kill_session`` safe to run
    from a web request.
    """
    if not pid:
        return False
    try:
        with open(f'/proc/{pid}/cmdline', 'rb') as handle:
            cmdline = handle.read().decode('utf-8', 'replace')
    except OSError:
        return False
    return str(_dir_for(sid)) in cmdline


def _session_pgid(pid: int) -> int | None:
    """The process group to signal, or ``None`` if signalling one is not safe.

    ffmpeg is started with ``start_new_session=True``, so a real session process
    is always its own group leader. Anything else is a pid we did not start the
    way we think we did, and ``killpg`` on it would hit an unrelated group.
    """
    try:
        pgid = os.getpgid(pid)
    except OSError:
        return None
    if pgid != pid or pgid == os.getpgrp():
        return None
    return pgid


def session_alive(sid: str) -> bool:
    """Alive means the directory exists *and* ffmpeg either still runs or has
    already finished writing a complete playlist we can keep serving."""
    meta = read_meta(sid)
    if not meta:
        return False
    pid = int(meta.get('pid') or 0)
    if _pid_alive(pid) and _pid_owns_session(pid, sid):
        return True
    return (_dir_for(sid) / 'index.m3u8').exists()


def _kill_session(sid: str) -> None:
    meta = read_meta(sid)
    pid = int(meta.get('pid') or 0)
    # Only ever signal a process we can still positively identify as ours.
    # A pid that fails this test is already gone as far as we are concerned;
    # its directory still goes, which is what actually frees the disk.
    if _pid_alive(pid) and _pid_owns_session(pid, sid):
        pgid = _session_pgid(pid)
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                if pgid is not None:
                    # Signalling the group also catches anything ffmpeg spawned.
                    os.killpg(pgid, sig)
                else:
                    os.kill(pid, sig)
            except OSError:
                break
            for _ in range(20):
                if not _pid_alive(pid):
                    break
                time.sleep(0.05)
            if not _pid_alive(pid):
                break
        try:
            os.waitpid(pid, os.WNOHANG)
        except OSError:
            pass
    shutil.rmtree(_dir_for(sid), ignore_errors=True)


def reap_sessions() -> int:
    """Drop sessions whose viewer has gone. Cheap enough to run per request.

    This is the only thing standing between the gateway and a full disk, so it
    is deliberately unconditional: anything without a recent heartbeat dies,
    whether or not its ffmpeg is still running.
    """
    root = session_root()
    now = time.time()
    reaped = 0
    try:
        entries = list(root.iterdir())
    except OSError:
        return 0
    for entry in entries:
        if not entry.is_dir():
            continue
        sid = entry.name
        meta = read_meta(sid)
        if not meta:
            # A directory with no metadata is debris from a crashed start.
            if now - _safe_mtime(entry) > 300:
                shutil.rmtree(entry, ignore_errors=True)
                reaped += 1
            continue
        beat = _last_beat(sid) or float(meta.get('created') or 0.0)
        idle = now - beat
        age = now - float(meta.get('created') or now)
        if idle > SESSION_IDLE_SECONDS or age > SESSION_MAX_AGE_SECONDS:
            _kill_session(sid)
            reaped += 1
    return reaped


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


# --------------------------------------------------------------------------- #
# Background reaping
# --------------------------------------------------------------------------- #
#
# ``stream_open`` reaps on the way in, which is enough for a gateway that is
# being used: the same traffic that dirties the volume tidies it. What it does
# not cover is the quiet case — the last viewer of the evening closes their tab
# and their ffmpeg keeps running until someone else opens a stream, which may be
# hours. That is a whole night of one process holding a core's worth of I/O and
# its segments on a volume with very little room.
#
# It has to be a thread *here* rather than a celery-beat task, because the
# reaper reads ``/proc`` to tell a live ffmpeg from a stale pid, and a worker in
# another container shares no pid namespace with these processes: it would judge
# every live session dead and kill the site's playback instead of saving it.

#: Kept for the life of the process — closing the fd releases the lock.
_REAPER_LOCK: list[int] = []
_REAPER_STARTED = False


def reaper_interval() -> int:
    """Comfortably under ``SESSION_IDLE_SECONDS`` so a gone viewer is noticed
    within about a minute rather than at the next sweep after that."""
    return max(15, int(getattr(settings, 'STREAM_REAPER_SECONDS', 60)))


def _claim_reaper_lock() -> bool:
    """One sweeper per volume, however many web workers the container runs.

    The lock is a file on the session volume rather than a setting, so it holds
    across workers without any of them having to know how many there are.
    """
    root = session_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(root / '.reaper.lock'), os.O_CREAT | os.O_RDWR, 0o644)
    except OSError as exc:
        logger.warning('stream reaper lock unavailable: %s', exc)
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return False
    _REAPER_LOCK.append(fd)
    return True


def _reaper_loop() -> None:
    while True:
        time.sleep(reaper_interval())
        try:
            reaped = reap_sessions()
        except Exception:  # noqa: BLE001 - a sweeper must never die of one bad session
            logger.exception('stream reaper sweep failed')
            continue
        if reaped:
            logger.info('stream reaper removed %s session(s)', reaped)


def start_reaper() -> bool:
    """Start the background sweep, if this process is the one that should.

    Returns whether it started, which is only true in the gateway container and
    only in whichever of its workers wins the lock.
    """
    global _REAPER_STARTED
    if _REAPER_STARTED or not getattr(settings, 'STREAM_GATEWAY_REAPER', False):
        return False
    if not _claim_reaper_lock():
        return False
    _REAPER_STARTED = True
    threading.Thread(target=_reaper_loop, name='stream-reaper', daemon=True).start()
    logger.info('stream reaper started (every %ss)', reaper_interval())
    return True


def live_sessions() -> list[str]:
    root = session_root()
    out = []
    try:
        entries = list(root.iterdir())
    except OSError:
        return out
    for entry in entries:
        if entry.is_dir() and session_alive(entry.name):
            out.append(entry.name)
    return out


def _build_command(url: str, start: float, tech: SourceTech, out_dir: Path) -> list[str]:
    """The one ffmpeg invocation that serves a whole session.

    Video is copied whenever the browser could have decoded it all along, which
    is the overwhelmingly common case; only genuine HEVC/AV1 reaches the encoder.
    Audio is always re-encoded to AAC stereo because it is cheap and because
    MP3/AC3/DTS in an MP4 envelope is exactly what Safari refuses.
    """
    if tech.video_copyable:
        video_args = ['-c:v', 'copy']
    else:
        # Downscale as well as re-encode: a 1080p HEVC source re-encoded at full
        # size costs a whole core, and this path exists for 9 titles.
        video_args = [
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
            '-profile:v', 'high', '-level', '4.0', '-pix_fmt', 'yuv420p',
            '-vf', "scale='min(1280,iw)':-2",
        ]

    cmd = [
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
        '-readrate', str(READ_RATE),
        *_ffmpeg_network_args(),
        # Sized so a *slow* origin can still start. These are byte/µs ceilings
        # on how much ffmpeg reads before it emits anything, and the old 4M/6M
        # was set against a healthy CDN. Measured against a real catalog source
        # delivering 14.7 KB/s, filling 4 MB takes about four and a half
        # minutes, so the session could not possibly produce a segment inside
        # ``wait_for_playlist``'s budget and every such title 504'd. A remux
        # only needs the container header and one keyframe to begin; these
        # values still cover that with room to spare, and anything they do not
        # resolve falls back to the same place it did before — the gateway's
        # transcode path.
        '-analyzeduration', '2M', '-probesize', '1M',
        # Keep the source's own timestamps in the output. ``-ss`` with ``-c:v
        # copy`` cannot cut mid-GOP, so it snaps *backwards* to the keyframe at
        # or before the mark — measured at 5s on a 10s-GOP file and over 20s on
        # a real catalog source. Without this the session would silently begin
        # somewhere earlier than it claims, and the player, which reads film
        # time as ``session.start + mediaTime``, would run that far ahead of the
        # picture for the whole session — subtitles included. With it, where the
        # session truly begins is written into the segments, and ``true_start``
        # reads it back off the disk instead of guessing.
        '-copyts',
    ]
    if start > 0:
        cmd += ['-ss', f'{start:.3f}']
    cmd += ['-i', url]
    # ``-to``, not ``-t``: under -copyts a duration cap is measured against
    # source timestamps, so ``-t 1800`` on a session opened an hour in is
    # already past its limit before the first frame and writes an empty
    # playlist (measured: one segment, 0.000s of content). An absolute end
    # point is the same cap expressed in the units -copyts actually uses.
    cmd += ['-to', f'{start + SESSION_MAX_CONTENT_SECONDS:.3f}']
    cmd += [
        '-map', '0:v:0', '-map', '0:a:0?',
        *video_args,
        '-c:a', 'aac', '-ac', '2', '-b:a', '160k',
        '-sn', '-dn', '-map_chapters', '-1',
        '-f', 'hls',
        '-hls_time', str(SEGMENT_SECONDS),
        '-hls_list_size', '0',
        '-hls_playlist_type', 'event',
        '-hls_segment_type', 'fmp4',
        '-hls_fmp4_init_filename', 'init.mp4',
        '-hls_segment_filename', str(out_dir / 'seg%05d.m4s'),
        str(out_dir / 'index.m3u8'),
    ]
    return cmd


def start_session(url: str, start: float, tech: SourceTech) -> str:
    """Spawn the ffmpeg that will feed one viewer, and return its session id."""
    if not shutil.which('ffmpeg'):
        raise StreamGatewayError('Streaming is unavailable.', code='ffmpeg_unavailable')
    if tech.needs_transcode and not transcode_allowed():
        raise StreamGatewayError('This title cannot be converted for your browser.',
                                 code='transcode_disabled')

    sid = session_id(url, start)
    if session_alive(sid) and session_reusable(sid):
        touch(sid)
        return sid
    if session_alive(sid):
        # Someone is watching this exact stream, but far enough in that its
        # opening has been pruned out from behind them. It can no longer serve
        # an arrival at this point, so this viewer gets their own copy rather
        # than a playlist whose first segments are gone.
        sid = session_id(url, start, salt=token_hex(4))
    out_dir = _dir_for(sid)

    # A stale directory for this id means a previous attempt died; clear it so
    # the new ffmpeg does not append to half-written output.
    shutil.rmtree(out_dir, ignore_errors=True)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error('stream session dir %s: %s', out_dir, exc)
        raise StreamGatewayError('Streaming is unavailable.', code='session_dir_error') from exc

    cap = (max_concurrent_transcode() if tech.needs_transcode else max_concurrent_remux())
    if len(live_sessions()) >= cap or root_bytes() >= disk_budget_bytes():
        shutil.rmtree(out_dir, ignore_errors=True)
        raise StreamGatewayError('The player is busy — please try again shortly.',
                                 code='gateway_busy')

    cmd = _build_command(url, start, tech, out_dir)
    log = (out_dir / 'ffmpeg.log').open('wb')
    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            start_new_session=True,
        )
    except OSError as exc:
        log.close()
        shutil.rmtree(out_dir, ignore_errors=True)
        logger.error('stream session spawn failed: %s', exc)
        raise StreamGatewayError('Streaming is unavailable.', code='spawn_error') from exc
    finally:
        try:
            log.close()
        except OSError:
            pass

    _meta_path(sid).write_text(json.dumps({
        'pid': proc.pid,
        'start': round(float(start), 3),
        'created': time.time(),
        'tech': tech.as_dict(),
    }), 'utf-8')
    touch(sid)
    return sid


#: How long ``stream_open`` waits for ffmpeg's first segment.
#:
#: A healthy source produces one in a few seconds. The number that matters is
#: the *unhealthy* one: catalog origins that deliver at tens of KB/s are common
#: here, and at that rate even reading the container header takes longer than
#: the 30s this used to allow — so the slow titles, which are exactly the ones
#: that need the gateway, were the ones guaranteed to fail on it. This is a
#: ceiling on a wait nobody normally reaches, not a target.
PLAYLIST_WAIT_SECONDS = max(
    10.0, float(os.environ.get('STREAM_PLAYLIST_WAIT_SECONDS', '75')),
)


def wait_for_playlist(sid: str, *, timeout: float | None = None) -> bool:
    """Block until ffmpeg has written the first segment.

    Measured against a real 2h47m source, the first segment lands in a few
    seconds; the playlist file itself appears earlier but is useless until it
    lists something. Returning early on a dead process turns the whole wait into
    an immediate, honest error, which is what keeps the long ceiling affordable:
    a source that cannot be read at all still fails in seconds.
    """
    path = _dir_for(sid) / 'index.m3u8'
    meta = read_meta(sid)
    pid = int(meta.get('pid') or 0)
    deadline = time.monotonic() + (
        PLAYLIST_WAIT_SECONDS if timeout is None else float(timeout)
    )
    while time.monotonic() < deadline:
        try:
            if path.exists() and '.m4s' in path.read_text('utf-8'):
                return True
        except OSError:
            pass
        if pid and not _pid_alive(pid):
            # One last look: it may have finished a very short tail segment.
            try:
                return path.exists() and '.m4s' in path.read_text('utf-8')
            except OSError:
                return False
        time.sleep(0.25)
    return False


def true_start(sid: str, requested: float) -> float:
    """Where this session's picture *actually* begins, in film seconds.

    Copy-mode cutting lands on the keyframe at or before the requested point,
    never exactly on it, and by an amount nobody can predict from the request —
    it is a property of how that particular file was encoded. Asking the source
    where its keyframes are was measured at over 40 seconds against a real CDN
    and timed out, so the answer is taken from the one copy that is already
    local: ``-copyts`` wrote the source timestamps into the first segment, and
    that segment is sitting on our own disk.

    Cached in the session meta, because the answer cannot change once ffmpeg
    has started. Any failure falls back to the requested point, which is what
    the gateway assumed before this existed — a bounded error, not a broken
    session.
    """
    meta = read_meta(sid)
    cached = meta.get('true_start')
    if isinstance(cached, (int, float)):
        return float(cached)

    directory = _dir_for(sid)
    measured = requested
    probe = directory / '.start-probe.mp4'
    try:
        # init.mp4 carries the moov the demuxer needs; the first segment carries
        # the timestamp. Neither is readable alone, so they are joined — and the
        # name is dotted so that neither the segment route nor the pruner, both
        # of which match on segNNNNN/init names, can ever see it.
        probe.write_bytes((directory / 'init.mp4').read_bytes()
                          + (directory / 'seg00000.m4s').read_bytes())
        out = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=start_time',
             '-of', 'csv=p=0', str(probe)],
            capture_output=True, text=True, timeout=15,
        )
        value = float((out.stdout or '').strip())
        # A negative or absurd reading means the demuxer did not find what we
        # expected; the requested point is a better answer than nonsense.
        if value >= 0 and value <= requested + SEGMENT_SECONDS:
            measured = value
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        logger.warning('stream session %s start measurement failed: %s', sid, exc)
    finally:
        try:
            probe.unlink()
        except OSError:
            pass

    meta['true_start'] = round(float(measured), 3)
    try:
        _meta_path(sid).write_text(json.dumps(meta), 'utf-8')
    except OSError:
        pass
    return float(meta['true_start'])


def playlist_text(sid: str, *, url_for) -> str:
    """ffmpeg's playlist with segment names rewritten to API URLs.

    ``url_for(name)`` maps ``init.mp4`` / ``segNNNNN.m4s`` to a servable URL.
    Nothing else in the playlist is touched: the ``#EXTINF`` values are the true
    segment durations ffmpeg measured, and rewriting them is precisely the
    mistake that broke the previous design.
    """
    raw = (_dir_for(sid) / 'index.m3u8').read_text('utf-8')
    out = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith('#EXT-X-MAP:'):
            out.append(re.sub(r'URI="([^"]+)"',
                              lambda m: f'URI="{url_for(m.group(1))}"', line))
        elif stripped and not stripped.startswith('#'):
            out.append(url_for(stripped))
        else:
            out.append(line)
    return '\n'.join(out) + '\n'


def segment_file(sid: str, name: str) -> Path:
    """Resolve a segment name to a path, refusing anything that is not one.

    The name arrives from the URL, so this is the boundary where path traversal
    gets stopped — hence an exact-match pattern rather than any kind of cleanup.
    """
    if not _SEGMENT_NAME_RE.match(name or ''):
        raise StreamGatewayError('Unknown segment.', code='bad_segment')
    return _dir_for(sid) / name


def wait_for_segment(path: Path, *, timeout: float = 20.0) -> bool:
    """A player can ask for the segment ffmpeg is still writing; wait briefly.

    Size has to stop changing before the file is safe to serve — handing a
    half-written fragment to MSE is a decode error on the client.
    """
    deadline = time.monotonic() + timeout
    last = -1
    stable = 0
    while time.monotonic() < deadline:
        try:
            size = path.stat().st_size
        except OSError:
            size = -1
        if size > 0 and size == last:
            stable += 1
            if stable >= 2:
                return True
        else:
            stable = 0
        last = size
        time.sleep(0.15)
    return path.exists() and path.stat().st_size > 0


# --------------------------------------------------------------------------- #
# Deciding whether a source needs us at all
# --------------------------------------------------------------------------- #

_BAD_CONTAINER_RE = re.compile(r'\.(mkv|avi|wmv|flv|ts|m2ts|mpg|mpeg|vob|ogv|rmvb)(\?|#|$)', re.I)
_FRIENDLY_CONTAINER_RE = re.compile(r'\.(m3u8|mp4|m4v|webm)(\?|#|$)', re.I)


def container_needs_rewrap(url: str) -> bool:
    """Filename-level guess at whether a browser will refuse the envelope.

    Only a hint — ``probe_tech`` is the authority — but it is free, and it keeps
    the gateway from being offered for sources that were always fine.
    """
    u = (url or '').lower()
    if not u:
        return False
    if _FRIENDLY_CONTAINER_RE.search(u):
        return False
    return bool(_BAD_CONTAINER_RE.search(u))


def gateway_candidate(url: str) -> bool:
    """Is this a source the gateway could plausibly rescue?"""
    u = (url or '').strip().lower()
    if not u.startswith(('http://', 'https://')):
        return False
    return container_needs_rewrap(u) or bool(_FRIENDLY_CONTAINER_RE.search(u))
