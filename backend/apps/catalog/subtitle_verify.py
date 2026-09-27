"""Read the subtitle file itself, before it is allowed onto the site.

The subtitle pipeline had a gap exactly the shape of this module. Three layers
already exist, and none of them opens the cue file:

* :mod:`subtitle_metadata` verifies the provider *page* — right film, right
  year, right cast. It proves we downloaded from the correct listing, not that
  the listing served a correct file.
* :func:`subtitle_extract._fps_prealigned_payload` rescales for framerate drift,
  but only when both framerates are spelled out in release tags. Most releases
  do not spell them out, so most files pass through untouched.
* :mod:`subtitle_sync` fixes timing from crowd consensus — *after* publication,
  once enough viewers have been annoyed enough to drag the offset slider.

So a file could be an English subtitle labelled فارسی, a half-download that
stops at minute forty, an advert dump with nine cues, or a perfectly good
subtitle for a 25 fps PAL release drifting four percent against our 23.976 fps
encode, and every layer above would wave it through. This module is the
preventive check for the file's own contents, run at import:

**Structure** — does it parse, and does it hold enough cues to be a subtitle at
all. **Language** — is the text actually Persian script, not an English file
someone mislabelled. **Substance** — is it a real translation rather than a
channel advert with a handful of lines. **Sync** — do the cues fit *this*
encode, judged against the runtime ffprobe measured
(:func:`media_verification.measured_duration`), because TMDB's runtime describes
the theatrical cut and routinely disagrees with the actual file by minutes.

And where a rejected file's timing is a clean framerate ratio, it is
**corrected rather than thrown away**: the cues are rescaled onto the real
runtime and the fixed file is what gets stored. Throwing it away would leave the
film with no subtitle at all when a multiplication would have made it correct.

The correction is deliberately confined to files that fail the sync check.
A subtitle authored for a *faster* encode overshoots the end of the film, which
is unambiguous and gets fixed here. Drift in the other direction — cues ending
a few percent early — is not distinguishable from a subtitle that simply ends
before the credits, so it is left alone: stretching a correct file is a worse
outcome than leaving a slightly early one. That direction is handled at the two
points where real evidence exists instead of an inference —
:func:`subtitle_extract._fps_prealigned_payload` when the release tags state
both framerates, and the crowd-consensus layer once viewers report a constant
offset.

Three verdicts as everywhere else: ``passed`` / ``failed`` / ``unknown``.
``unknown`` (undecodable bytes, verification switched off) stores the file
exactly as today — never a regression against the behaviour this replaces.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

#: Below this a file is a stub, a header, or an advert — not a translation.
MIN_CUES = 10
#: Share of letters that must be Persian/Arabic script in a track claiming fa.
#: Real Persian subtitles carry English song titles, signs and credits, so this
#: sits well below 1.0; an English file mislabelled فارسی scores near 0.
MIN_PERSIAN_RATIO = 0.45
#: Above this share of promo cues the file is an advert with a film attached.
MAX_PROMO_RATIO = 0.5
#: Cues may end a little past the measured runtime (credits trimmed from the
#: encode, rounding); beyond this the file belongs to a different cut.
TAIL_TOLERANCE_SECONDS = 30.0
#: Last cue must reach at least this share of the runtime. A half-finished
#: download or the wrong episode lands far below it.
MIN_COVERAGE = 0.70
#: Coverage window a framerate correction must land in to be accepted. Tight on
#: purpose: a genuine framerate fix puts the last cue right up against the end
#: of the film, and a loose window lets a second ratio fit too, at which point
#: we would be choosing between them at random.
FIXED_COVERAGE_MIN = 0.94
FIXED_COVERAGE_MAX = 1.002

_CUE_LINE = re.compile(r'-->')
_TS = re.compile(r'\d{1,3}:\d{2}:\d{2}[.,]\d{1,3}|\d{1,2}:\d{2}[.,]\d{1,3}')
_PERSIAN = re.compile(r'[؀-ۿﭐ-﷿ﹰ-﻿]')
_LATIN = re.compile(r'[A-Za-z]')
#: Markers of a channel advert. Narrow on purpose — a single credit line saying
#: «مترجم» is normal and must not count against a real file.
_PROMO = re.compile(
    r'(t\.me/|telegram|@\w{4,}|www\.|https?://|\.ir\b|\.com\b|'
    r'کانال\s*ما|تلگرام|اینستاگرام|دانلود\s*فیلم|سفارش\s*ترجمه)',
    re.IGNORECASE,
)

#: Framerate *families*, not framerates. 23.976 and 24 differ by 0.1%, as do
#: 29.97 and 30, and including both members of a pair would put two ratios
#: 0.1% apart in the candidate list — the uniqueness test below would then
#: reject every real correction as ambiguous. One representative each, and the
#: film standard (23.976) wins its family because essentially every WEB and
#: BluRay encode uses it.
_FPS = (23.976, 25.0, 29.97)


def subtitle_verification_enabled() -> bool:
    from django.conf import settings

    return bool(getattr(settings, 'CATALOG_VERIFY_SUBTITLES_BEFORE_PUBLISH', True))


def _decode(payload: bytes) -> str | None:
    if payload[:3] == b'\xef\xbb\xbf':
        payload = payload[3:]
    for encoding in ('utf-8', 'utf-8-sig', 'cp1256'):
        try:
            return payload.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return None


def _ts_seconds(token: str) -> float:
    token = token.strip().replace(',', '.')
    parts = token.split(':')
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        return int(parts[0]) * 60 + float(parts[1])
    except (ValueError, IndexError):
        return -1.0


def parse_cues(text: str) -> tuple[list[tuple[float, float]], str]:
    """``(cue spans, concatenated cue text)`` from a WebVTT/SRT document.

    Only lines carrying ``-->`` define a span; everything up to the next blank
    line is that cue's text. Deliberately forgiving — a stray header or a
    numbering line from an SRT conversion is not a defect.
    """
    spans: list[tuple[float, float]] = []
    body: list[str] = []
    lines = text.split('\n')
    index = 0
    while index < len(lines):
        line = lines[index]
        if _CUE_LINE.search(line):
            stamps = _TS.findall(line)
            if len(stamps) >= 2:
                start, end = _ts_seconds(stamps[0]), _ts_seconds(stamps[1])
                if start >= 0 and end >= start:
                    spans.append((start, end))
            index += 1
            while index < len(lines) and lines[index].strip():
                body.append(lines[index])
                index += 1
            continue
        index += 1
    return spans, '\n'.join(body)


def _persian_ratio(body: str) -> float:
    persian = len(_PERSIAN.findall(body))
    latin = len(_LATIN.findall(body))
    total = persian + latin
    return (persian / total) if total else 0.0


def _promo_ratio(text: str) -> float:
    cue_blocks = [block for block in re.split(r'\n\s*\n', text) if block.strip()]
    if not cue_blocks:
        return 0.0
    hits = sum(1 for block in cue_blocks if _PROMO.search(block))
    return hits / len(cue_blocks)


def _candidate_scales() -> list[float]:
    """Every distinct framerate ratio, nearest-to-1 first."""
    seen: dict[str, float] = {}
    for src in _FPS:
        for dst in _FPS:
            if abs(src - dst) < 0.05:
                continue
            scale = src / dst
            seen[f'{scale:.5f}'] = scale
    return sorted(seen.values(), key=lambda s: abs(s - 1.0))


def _fit_framerate(last_end: float, duration: float) -> float | None:
    """The one framerate ratio that makes these cues fit, or ``None``.

    Two refusals matter more than the fit itself:

    *Already fitting.* If the cues land inside the window untouched, there is
    nothing to correct — and a candidate ratio can still "fit" a file that was
    fine, so without this guard the function would happily shrink a correct
    subtitle by 4%.

    *Ambiguity.* If two ratios both land inside the window we cannot tell which
    encode the file was authored for, and guessing would bake a wrong stretch
    into a file that is merely suspicious.
    """
    if last_end <= 0 or duration <= 0:
        return None
    if FIXED_COVERAGE_MIN <= last_end / duration <= FIXED_COVERAGE_MAX:
        return None
    fits = [
        scale for scale in _candidate_scales()
        if FIXED_COVERAGE_MIN <= (last_end * scale) / duration <= FIXED_COVERAGE_MAX
    ]
    if len(fits) != 1:
        return None
    return fits[0]


def _sync_report(spans, duration: float) -> tuple[str, str, float]:
    """``(verdict, reason, coverage)`` for cue spans against a real runtime."""
    last_end = spans[-1][1] if spans else 0.0
    coverage = (last_end / duration) if duration > 0 else 0.0
    if last_end > duration + TAIL_TOLERANCE_SECONDS:
        return 'failed', f'overruns_runtime_by_{int(last_end - duration)}s', coverage
    if coverage < MIN_COVERAGE:
        return 'failed', f'covers_only_{int(coverage * 100)}pct', coverage
    return 'passed', '', coverage


def verify_payload(payload: bytes, *, duration: float = 0.0, language: str = 'fa') -> dict:
    """Judge a subtitle file and return the bytes that should actually be stored.

    ``{'verdict', 'reason', 'payload', 'cues', 'coverage', 'persian_ratio',
    'fixed', 'scale'}``. ``payload`` is the input unless a framerate correction
    was applied, in which case it is the rescaled document — so the caller stores
    a file that is already in sync rather than one it merely approved.
    """
    blank = {
        'verdict': 'unknown', 'reason': '', 'payload': payload, 'cues': 0,
        'coverage': 0.0, 'persian_ratio': 0.0, 'fixed': '', 'scale': 1.0,
    }
    if not payload:
        return {**blank, 'verdict': 'failed', 'reason': 'empty_file'}
    if not subtitle_verification_enabled():
        return {**blank, 'reason': 'disabled'}

    text = _decode(payload)
    if text is None:
        # Undecodable is genuinely unknown, not proven bad: the player may still
        # manage it, and rejecting would lose a file we cannot read but ffmpeg
        # produced. Store it, flagged.
        return {**blank, 'reason': 'undecodable'}

    spans, body = parse_cues(text)
    report = {**blank, 'cues': len(spans), 'persian_ratio': round(_persian_ratio(body), 3)}

    if len(spans) < MIN_CUES:
        return {**report, 'verdict': 'failed', 'reason': f'only_{len(spans)}_cues'}
    if not body.strip():
        return {**report, 'verdict': 'failed', 'reason': 'no_cue_text'}
    if language.lower().startswith('fa') and report['persian_ratio'] < MIN_PERSIAN_RATIO:
        return {**report, 'verdict': 'failed', 'reason': 'not_persian'}
    if _promo_ratio(text) > MAX_PROMO_RATIO:
        return {**report, 'verdict': 'failed', 'reason': 'advert_dump'}

    if duration <= 0:
        # Structure is sound; there is simply no measured runtime to check the
        # timing against. Publishing is right — the crowd-consensus layer is the
        # backstop for exactly this case.
        return {**report, 'verdict': 'passed', 'reason': 'sync_unmeasured'}

    verdict, reason, coverage = _sync_report(spans, duration)
    report['coverage'] = round(coverage, 3)
    if verdict == 'passed':
        return {**report, 'verdict': 'passed', 'reason': ''}

    # Out of sync — but a clean framerate ratio is a correction, not a rejection.
    scale = _fit_framerate(spans[-1][1], duration)
    if scale is None:
        return {**report, 'verdict': 'failed', 'reason': reason}

    from apps.catalog.subtitle_sync import shift_and_scale_webvtt

    rescaled = shift_and_scale_webvtt(text, scale=scale)
    fixed_spans, _ = parse_cues(rescaled)
    fixed_verdict, fixed_reason, fixed_coverage = _sync_report(fixed_spans, duration)
    if fixed_verdict != 'passed':
        # The stretch did not actually land it; do not store a file we have now
        # modified *and* still believe is wrong.
        return {**report, 'verdict': 'failed', 'reason': reason}

    logger.info(
        'subtitle-verify: framerate corrected ×%.5f (%d cues, coverage %.0f%% → %.0f%%)',
        scale, len(spans), coverage * 100, fixed_coverage * 100,
    )
    return {
        **report, 'verdict': 'passed', 'reason': 'fps_corrected',
        'payload': rescaled.encode('utf-8'), 'coverage': round(fixed_coverage, 3),
        'fixed': 'fps', 'scale': round(scale, 5),
    }
