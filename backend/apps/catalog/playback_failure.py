"""Automatic playback-failure triage: player error -> repairable report.

When a viewer opens online playback (single or watch-party) and the video
does not start for *any* reason, the player already knows *how* it failed:

* ``<video>.error.code`` (2 = network, 3 = decode, 4 = unsupported),
* HLS.js fatal type (``NETWORK_ERROR`` / ``MEDIA_ERROR``),
* startup/stall watchdogs, gateway ``stream/open`` codes,
* an expired signed URL or an empty source list.

A human tapping «گزارش خطا» picks a ``problem_type`` from
:mod:`apps.catalog.report_catalog`. This module is the same decision made by
code, so an automatic report lands on the *exact* repair
:mod:`apps.catalog.content_remediation` would run for a manual one — no
free-text parsing, no guessing, and no new repair paths to maintain.

Only two outcomes are auto-detectable from a player failure:

* ``playback`` — nothing ever played (black player, immediate error).
* ``buffering`` — playback started and then stalled (mid-film network loss).

Everything else (audio, subtitles, wrong title/episode, quality) needs a
human judgement and stays manual. An explicit ``problem_type`` supplied by
the caller is honoured when valid, so a client that *does* know more (e.g.
"picture but no sound") can still use this endpoint.
"""

from __future__ import annotations

import re

from apps.catalog.report_catalog import VALID_PROBLEMS

#: Player error codes as emitted by the web player (VideoPlayer.vue) and the
#: Android player. Kept as strings too — clients post JSON, types drift.
NETWORK_CODES = frozenset({'2', 'network', 'media_err_network', 'hls_network', 'stall', 'timeout', 'startup_timeout'})
DECODE_CODES = frozenset({'3', '4', 'decode', 'unsupported', 'media_err_decode', 'media_err_src_not_supported', 'hls_media', 'codec', 'mkv', 'hevc', 'av1'})

_GATEWAY_TO_PROBLEM = {
    'probe_failed': 'playback',
    'stream_start_failed': 'buffering',
    'transcode_disabled': 'playback',
    'gateway_busy': 'buffering',
    'source_expired': 'playback',
    'unknown_source': 'playback',
    'unsupported_source': 'playback',
    'geo_locked': 'playback',
    'bad_request': 'playback',
}

_MESSAGE_NEEDS_BUFFERING = re.compile(r'قطع|بافر|stall|buffer|stalled|spinning|rebuffer', re.IGNORECASE)
_MESSAGE_NEEDS_PLAYBACK = re.compile(r'410|403|404|expired|منقضی|پخش نمی|باز نمی|decode|رمزگشایی|codec|کدک|mkv|hevc|av1|unsupported|پشتیبانی نمی', re.IGNORECASE)

#: What the viewer is told while the fix runs. One line, Persian, no jargon.
USER_MESSAGES_FA = {
    'received': 'خطای پخش ثبت شد؛ داریم نسخه سالم را آماده می‌کنیم…',
    'fixed': 'پخش درست شد؛ ادامه از همان لحظه…',
    'gateway': 'نسخه سازگار با این مرورگر فعال شد.',
    'queued': 'خطای پخش ثبت شد؛ ترمیم خودکار در صف است و به‌زودی پخش برمی‌گردد.',
    'needs_review': 'این مورد به پشتیبانی ارجاع شد؛ نتیجه همین‌جا اطلاع‌رسانی می‌شود.',
    'unavailable': 'فعلاً نسخه سالمی از سرویس‌دهنده گرفته نشد؛ تلاش خودکار ادامه دارد.',
    'already_playable': 'لینک تازه بررسی شد و سالم است؛ صفحه را تازه کن.',
}


def classify_failure(
    *,
    error_code: str = '',
    error_message: str = '',
    gateway_code: str = '',
    source_url: str = '',
    played_seconds: float = 0,
    had_played: bool = False,
    hint_problem: str = '',
) -> dict:
    """Map a player failure onto a remediable ``problem_type``.

    Never raises, never returns an invalid problem. ``hint_problem`` (a valid
    catalogue value supplied by a client that knows more) wins; otherwise the
    decision is purely mechanical from codes + message + playback position.
    """
    hint = (hint_problem or '').strip().lower()
    if hint in VALID_PROBLEMS:
        from apps.catalog.report_catalog import normalize as normalize_problem

        return {
            'problem_type': normalize_problem(hint),
            'confidence': 'explicit',
            'reason': f'hint:{hint}',
        }

    code = str(error_code or '').strip().lower()
    gw = str(gateway_code or '').strip().lower()
    msg = str(error_message or '')

    if gw and gw in _GATEWAY_TO_PROBLEM:
        problem = _GATEWAY_TO_PROBLEM[gw]
        return {'problem_type': problem, 'confidence': 'gateway', 'reason': f'gateway:{gw}'}

    # Played-then-stalled is buffering even when the code says network.
    try:
        played = float(played_seconds or 0)
    except (TypeError, ValueError):
        played = 0
    if had_played or played > 1:
        # A decode failure after minutes of playback is still a stall of the
        # current mirror, not a missing title — but a *decode* code means the
        # mirror itself is undecodable, which the playback repair handles.
        if code in DECODE_CODES and played < 1:
            return {'problem_type': 'playback', 'confidence': 'code', 'reason': f'code:{code}'}
        if _MESSAGE_NEEDS_PLAYBACK.search(msg) and not _MESSAGE_NEEDS_BUFFERING.search(msg) and played < 1:
            return {'problem_type': 'playback', 'confidence': 'message', 'reason': 'message:playback'}
        return {'problem_type': 'buffering', 'confidence': 'position', 'reason': f'played:{played:.0f}s'}

    if code in NETWORK_CODES:
        return {'problem_type': 'buffering' if _MESSAGE_NEEDS_BUFFERING.search(msg) else 'playback', 'confidence': 'code', 'reason': f'code:{code}'}
    if code in DECODE_CODES:
        return {'problem_type': 'playback', 'confidence': 'code', 'reason': f'code:{code}'}
    if _MESSAGE_NEEDS_BUFFERING.search(msg):
        return {'problem_type': 'buffering', 'confidence': 'message', 'reason': 'message:buffering'}
    # Default: the player failed before a frame — the playback repair.
    return {'problem_type': 'playback', 'confidence': 'default', 'reason': 'default:playback'}


def build_auto_detail(
    *,
    error_code: str = '',
    error_message: str = '',
    gateway_code: str = '',
    player: str = '',
    room_code: str = '',
    extra: str = '',
) -> str:
    """Deterministic ``detail`` stored on the auto-filed report.

    Prefix ``auto:`` distinguishes machine reports in admin/support views.
    Bounded so a hostile client cannot bloat the row.
    """
    parts = ['auto: playback-failure']
    if error_code:
        parts.append(f'code={str(error_code)[:32]}')
    if gateway_code:
        parts.append(f'gw={str(gateway_code)[:32]}')
    if player:
        parts.append(f'player={str(player)[:16]}')
    if room_code:
        parts.append(f'room={str(room_code)[:32]}')
    if error_message:
        parts.append(str(error_message)[:180])
    if extra:
        parts.append(str(extra)[:180])
    return ' | '.join(parts)[:500]


def fixed_playback_for(owner, episode=None) -> dict:
    """Current servable playback after remediation (crawl-free read)."""
    try:
        target = episode if episode is not None else owner
        url = str(getattr(target, 'video_url', '') or '').strip()
        mode = str(getattr(target, 'playback_mode', '') or '')
        return {'url': url, 'playback_mode': mode, 'has_url': bool(url)}
    except Exception:  # noqa: BLE001 — status read must never fail
        return {'url': '', 'playback_mode': '', 'has_url': False}
