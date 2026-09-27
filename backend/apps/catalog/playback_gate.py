"""The test an online-playback link has to pass before a viewer is given it.

Everything else in the catalog picks the playback URL by **reading its name**.
:func:`provider_import.catalog_lookup._prefer_streamable_download` scores the
file name for container and codec tokens and returns the winner, and four
separate import paths copy that winner straight into ``video_url``.

The flaw is not the ranking — it is that a ranking has no floor. When a title's
only sources are Persian-dubbed x265 MKV files (which is most of this catalog),
the scorer still returns the best of them, and an MKV becomes the link the
player is handed. Safari, iOS and Firefox cannot demux MKV at all, so the title
is published as watchable and the viewer gets «پخش ویدیو ممکن نشد». At the time
this module was written that was true of **10,495 of 14,207** published movies
and **58,666 of 62,050** episodes.

So this module replaces "rank the names" with "test the bytes, then decide":

1. **Is it a video source at all?** Sidecars, images and dead hosts never reach
   a probe (:func:`playback_sources._classify_link`).
2. **Does the server still serve it?** A ranged GET through
   :mod:`media_probe` — providers advertise files their CDN deleted months ago.
3. **Can the player seek in it?** No byte ranges means no resume and no seek,
   which is not an acceptable online source even when the file is fine.
4. **Is it really what the name claims?** One ffprobe of the container header
   through :mod:`media_tech` — HEVC behind a codec-less ``.mp4``, Matroska
   served from a ``.mp4`` path, DTS audio that plays as silence.

Only a URL that passes all four becomes a direct playback link.

**A failure is a routing decision, not a deletion.** A source that is reachable
but undecodable is exactly what the playback gateway exists to remux, so it is
kept and marked ``gateway`` — the player asks for an HLS rewrap up front
instead of discovering the problem by failing. Clearing the link would take
three quarters of the catalog offline to fix a bug that is only about *how* the
bytes are delivered.

**Four verdicts, because two would lie.** ``direct`` / ``gateway`` / ``unknown``
/ ``none``. A host this datacenter cannot reach, an ffprobe timeout, or a codec
nobody here has an opinion about is ``unknown``: the filename heuristic decides
and the row stays queued for a re-test. Only a positive "every candidate is
gone" is ``none``, and only ``none`` may clear an existing link. A CDN outage
must never empty the catalog — the same rule :mod:`media_verification` follows.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import timedelta
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: Tested, and a strict browser plays this file as it stands.
MODE_DIRECT = 'direct'
#: Reachable and real, but the browser needs the gateway's HLS rewrap first.
MODE_GATEWAY = 'gateway'
#: Nothing could be established from here; the name decides and we retry later.
MODE_UNVERIFIED = 'unverified'
#: Every candidate answered "gone". The only verdict allowed to clear a link.
MODE_NONE = 'none'

#: Reachability probes spent choosing one title's playback link. Cheap (2 KiB
#: ranged GET) and cached, but a season pack must not stall a crawl.
#:
#: This is also the ceiling on :func:`choose_playback_link` ever reaching a
#: verdict of "gone": condemning sources nobody probed is not allowed, so a
#: title with more candidates than this budget can only ever come back
#: ``unverified`` — forever, on every sweep, no matter how dead its links are.
#: At 5 that silently applied to 29% of episodes and 18% of movies, which is
#: why it is sized off the measured distribution instead: ranked candidates run
#: p95=10, p99=13, max=16 for episodes and p95=11, p99=14 for movies, so 16
#: leaves essentially nothing permanently undecidable.
#:
#: Raising it is close to free. The loop returns at the *first* source that
#: works, so a healthy title still costs one probe; the extra budget is only
#: ever spent on a title whose mirrors are all dead, which is exactly the case
#: that has to reach a verdict for the repair crawler to be told about it.
MAX_CANDIDATES = max(1, int(os.environ.get('CATALOG_PLAYBACK_MAX_CANDIDATES', '16')))
#: ffprobes spent per title. The header read is kilobytes, the round trip is
#: not, and ``stream_gateway.probe_tech`` caches only successes — a host that
#: accepts the connection then stalls costs the full timeout every time.
MAX_TECH_PROBES = 2

_HLS_RE = re.compile(r'\.m3u8($|[?#])', re.IGNORECASE)


def gate_enabled() -> bool:
    from django.conf import settings

    return bool(getattr(settings, 'CATALOG_VERIFY_PLAYBACK_LINK', True))


@dataclass(frozen=True)
class SourceVerdict:
    """What one candidate URL turned out to be."""

    url: str
    mode: str = MODE_NONE
    reason: str = ''
    tech: dict = field(default_factory=dict)
    probe: dict = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        """Worth handing to a player, directly or through the gateway."""
        return self.mode in (MODE_DIRECT, MODE_GATEWAY)

    @property
    def dead(self) -> bool:
        return self.mode == MODE_NONE


@dataclass(frozen=True)
class PlaybackChoice:
    """The link this title should serve, and what it took to decide."""

    url: str = ''
    mode: str = MODE_UNVERIFIED
    reason: str = ''
    tech: dict = field(default_factory=dict)
    tested: int = 0
    dead: tuple[str, ...] = ()
    previous: str = ''

    @property
    def changed(self) -> bool:
        return self.url != self.previous

    def as_dict(self) -> dict:
        return {
            'url': self.url[:500], 'mode': self.mode, 'reason': self.reason,
            'tested': self.tested, 'dead': len(self.dead),
            'changed': self.changed, 'tech': self.tech or {},
        }


def _name_safe(url: str, item: dict | None = None) -> bool:
    """The old filename heuristic, kept as the fallback for ``unknown``.

    Knowing less than we hoped must never be worse than the guess we had before
    this module existed, so every path that cannot measure falls back to here.
    """
    from apps.catalog.playback_sources import _classify_link

    probe_item = dict(item or {})
    probe_item['url'] = url
    return _classify_link(probe_item, ignore_expiry=True) == 'safe'


def test_source(url: str, *, item: dict | None = None, use_cache: bool = True,
                allow_tech: bool = True) -> SourceVerdict:
    """Run one candidate URL through every test and report what it is.

    Never raises: a probe that blows up is an ``unknown``, which leaves the
    caller exactly where it was.
    """
    from apps.catalog import media_probe, media_tech

    url = (url or '').strip()
    if not url:
        return SourceVerdict(url='', mode=MODE_NONE, reason='empty_url')
    if not url.startswith(('http://', 'https://')):
        # An object key for our own HLS output. Our pipeline produced it, so
        # there is no third party here to distrust.
        return SourceVerdict(url=url, mode=MODE_DIRECT, reason='internal_storage')

    is_manifest = bool(_HLS_RE.search(url))
    try:
        probe = (
            media_probe.probe_manifest(url, use_cache=use_cache)
            if is_manifest
            else media_probe.probe_url(url, expect='video', use_cache=use_cache)
        )
    except Exception as exc:  # a probe failure is never a verdict about the film
        logger.warning('playback_gate: probe raised for %s: %s', url[:120], exc)
        return SourceVerdict(url=url, mode=MODE_UNVERIFIED, reason='probe_error')

    row = probe.as_dict()
    if probe.dead:
        return SourceVerdict(url=url, mode=MODE_NONE, reason=probe.reason or 'dead', probe=row)
    if not probe.live:
        # Timeout, TLS reset, datacenter 403. Says nothing about the file.
        return SourceVerdict(
            url=url, mode=MODE_UNVERIFIED, reason=probe.reason or 'unreachable', probe=row,
        )

    # Seekability is a playback requirement, not a download one: without byte
    # ranges the viewer cannot resume or scrub, and the gateway's own HLS
    # output is seekable even when its input is not.
    if not is_manifest and not probe.accept_ranges:
        return SourceVerdict(url=url, mode=MODE_GATEWAY, reason='no_byte_ranges', probe=row)

    if not allow_tech:
        mode = MODE_DIRECT if _name_safe(url, item) else MODE_GATEWAY
        return SourceVerdict(url=url, mode=mode, reason='name_only', probe=row)

    try:
        tech = media_tech.verify_source(url)
    except Exception as exc:
        logger.warning('playback_gate: codec probe raised for %s: %s', url[:120], exc)
        tech = {'verdict': 'unknown', 'reason': 'probe_error'}

    verdict = tech.get('verdict') or 'unknown'
    if verdict == 'safe':
        return SourceVerdict(url=url, mode=MODE_DIRECT, reason='', tech=tech, probe=row)
    if verdict == 'unsafe':
        # Real bytes, wrong wrapper or wrong codec. The gateway's whole purpose.
        return SourceVerdict(
            url=url, mode=MODE_GATEWAY, reason=tech.get('reason') or 'unsafe',
            tech=tech, probe=row,
        )

    # ffprobe could not tell us. Fall back to the name, exactly as the catalog
    # behaved before this gate existed — but say so, so the row is re-tested.
    mode = MODE_DIRECT if _name_safe(url, item) else MODE_GATEWAY
    return SourceVerdict(
        url=url, mode=mode, reason=f'name_only:{tech.get("reason") or "unknown"}'[:48],
        tech=tech, probe=row,
    )


def rank_candidates(links) -> list[dict]:
    """Playback candidates for this title, most promising first.

    The ordering is the pre-existing filename heuristic and stays that way on
    purpose: its job here is only to decide *what to test first*, so that the
    likely answer is usually found on the first probe. What it can no longer do
    is decide the outcome by itself.
    """
    from apps.catalog.media_probe import signature_expired
    from apps.catalog.playback_sources import _classify_link
    from apps.catalog.provider_import.media_links import (
        browser_playback_score, is_playable_video_link,
    )
    from apps.catalog.subtitle_extract import (
        looks_like_dub_link, looks_like_hardsub_link, looks_like_softsub_link,
    )

    ranked: list[tuple[int, int, dict]] = []
    seen: set[str] = set()
    for index, item in enumerate(links or []):
        if not isinstance(item, dict):
            continue
        url = str(item.get('url') or '').strip()
        if not url or url in seen:
            continue
        # ``ignore_expiry``: a lapsed token says nothing about the file, and a
        # link dropped here never reaches the re-crawl that would fix it.
        if _classify_link(item, ignore_expiry=True) == 'skip':
            continue
        if not is_playable_video_link(item):
            continue
        seen.add(url)
        quality = str(item.get('quality') or '').lower()
        score = browser_playback_score(url)
        if '1080' in quality or '1080' in url.lower():
            score += 30
        elif '720' in quality or '720' in url.lower():
            score += 20
        elif '480' in quality or '480' in url.lower():
            score += 10
        if 'x265' in quality or 'hevc' in quality or '10bit' in quality:
            score -= 45
        if looks_like_dub_link(item):
            score += 28
        elif looks_like_hardsub_link(item):
            score += 16
        elif looks_like_softsub_link(item):
            score += 10
        if signature_expired(url):
            # Demoted, not dropped. A lapsed token means "nobody can play this
            # until it is re-signed", so any fresh mirror — however badly named
            # — is worth testing first. It stays in the list because a title
            # whose every link has lapsed still needs a link to re-crawl from,
            # and because dropping it here would read downstream as "this title
            # has no sources", which is the deletion path.
            score -= 500
        ranked.append((score, -index, item))
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [item for _score, _i, item in ranked]


def candidate_links(obj, episode=None) -> list[dict]:
    """The link rows that could serve this target, current playback link first.

    An episode's copies live on its *series'* ``download_links``, so they have
    to be filtered down to the ones that actually name this episode — the same
    scoping :func:`media_verification._link_belongs_to_episode` performs, reused
    here rather than re-derived.
    """
    from apps.catalog.media_verification import _link_belongs_to_episode, _link_url

    target = episode if episode is not None else obj
    current = str(getattr(target, 'video_url', '') or '').strip()
    rows: list[dict] = []
    seen: set[str] = set()

    if current:
        rows.append({'url': current, 'label': 'current', 'quality': getattr(obj, 'quality', '') or ''})
        seen.add(current)

    for item in (getattr(obj, 'download_links', None) or []):
        if not isinstance(item, dict):
            continue
        url = _link_url(item)
        if not url or url in seen:
            continue
        if episode is not None and not _link_belongs_to_episode(item, url, episode):
            continue
        seen.add(url)
        rows.append(item)
    return rows


def choose_playback_link(links, *, current: str = '', use_cache: bool = True,
                         budget: int = MAX_CANDIDATES,
                         max_tech: int | None = None) -> PlaybackChoice:
    """Pick the link this title should serve online, by testing the candidates.

    Stops at the first source that passes every test. When none does, the best
    reachable source is returned marked ``gateway`` rather than discarded —
    undecodable is a delivery problem, not a missing film.

    ``max_tech=0`` buys a decision without the codec probe. That probe is the
    expensive one — a stalling host costs the full ffprobe timeout — which is
    affordable in a background sweep and not affordable with a viewer waiting
    on the answer. The name heuristic decides instead, the row comes back
    ``name_only``, and the sweep re-tests it properly later.
    """
    current = (current or '').strip()
    candidates = rank_candidates(links)
    if not candidates:
        return PlaybackChoice(mode=MODE_NONE, reason='no_candidates', previous=current)

    if not gate_enabled():
        # Flag off: behave exactly like the old heuristic, and say the mode is
        # unverified so nothing downstream claims a test happened.
        url = str(candidates[0].get('url') or '').strip()
        return PlaybackChoice(url=url, mode=MODE_UNVERIFIED, reason='gate_disabled', previous=current)

    tech_budget = MAX_TECH_PROBES if max_tech is None else max(0, int(max_tech))
    tech_spent = 0
    tested = 0
    dead: list[str] = []
    fallback: SourceVerdict | None = None

    for item in candidates[:budget]:
        url = str(item.get('url') or '').strip()
        tested += 1
        verdict = test_source(
            url, item=item, use_cache=use_cache,
            allow_tech=tech_spent < tech_budget,
        )
        if verdict.tech:
            tech_spent += 1
        if verdict.mode == MODE_DIRECT:
            return PlaybackChoice(
                url=url, mode=MODE_DIRECT, reason=verdict.reason, tech=verdict.tech,
                tested=tested, dead=tuple(dead), previous=current,
            )
        if verdict.dead:
            dead.append(url)
            continue
        # Gateway beats unverified, and among equals the incumbent wins — a
        # sweep that reshuffles working links for no gain is its own bug.
        if fallback is None:
            fallback = verdict
        elif fallback.mode != MODE_GATEWAY and verdict.mode == MODE_GATEWAY:
            fallback = verdict
        elif fallback.mode == verdict.mode and url == current:
            fallback = verdict

    if fallback is not None:
        return PlaybackChoice(
            url=fallback.url, mode=fallback.mode, reason=fallback.reason,
            tech=fallback.tech, tested=tested, dead=tuple(dead), previous=current,
        )
    if dead and tested <= budget and len(candidates) <= budget:
        # Everything this title has, and every one of them is gone.
        return PlaybackChoice(
            mode=MODE_NONE, reason='all_candidates_dead', tested=tested,
            dead=tuple(dead), previous=current,
        )
    # The budget ran out on dead mirrors. Condemning sources nobody probed is
    # the one unrecoverable mistake here, so this stays unverified.
    return PlaybackChoice(
        url=current, mode=MODE_UNVERIFIED, reason='partially_probed', tested=tested,
        dead=tuple(dead), previous=current,
    )


#: How long after a first "nothing playable" verdict a second one is allowed to
#: blank the link. Long enough that the two cannot share one bad night on a
#: provider's CDN, short enough that a genuinely dead title is not left pointing
#: at a 404 for a week.
CLEAR_CONFIRM_HOURS = 20


def clearing_confirmed(target) -> bool:
    """Has an *earlier* run already reached the same "nothing playable" verdict?

    Blanking a link is the one thing here that cannot be undone by re-running,
    so it takes two sightings from two runs. This reads the evidence for the
    second one, and must therefore be called *before* :func:`apply_choice`
    overwrites it: until then ``playback_mode`` and ``playback_checked_at`` still
    describe what the previous run concluded.

    A row nobody has tested, or one that tested playable last time, is a first
    sighting — record it, queue the repair, keep the link.
    """
    from django.utils import timezone

    from apps.catalog.models import PlaybackMode

    if getattr(target, 'playback_mode', '') != PlaybackMode.NONE:
        return False
    checked = getattr(target, 'playback_checked_at', None)
    if not checked:
        return False
    return timezone.now() - checked >= timedelta(hours=CLEAR_CONFIRM_HOURS)


def apply_choice(obj, choice: PlaybackChoice, *, allow_clear: bool = True) -> list[str]:
    """Write the decision onto a Movie or Episode. Returns changed field names.

    Does not save — the caller owns the transaction and usually has other
    fields to write in the same round trip.

    An ``unverified`` choice never overwrites a working link: not knowing is
    not a reason to change anything.
    """
    fields: list[str] = []
    if not hasattr(obj, 'video_url'):
        return fields

    previous = (getattr(obj, 'video_url', '') or '').strip()
    if choice.mode == MODE_NONE:
        if allow_clear and previous:
            obj.video_url = ''
            fields.append('video_url')
    elif choice.mode == MODE_UNVERIFIED:
        # Place a link only where there was none; never swap a tested one out.
        if choice.url and not previous:
            obj.video_url = choice.url
            fields.append('video_url')
    elif choice.url and choice.url != previous:
        obj.video_url = choice.url
        fields.append('video_url')

    if hasattr(obj, 'playback_mode') and getattr(obj, 'playback_mode', '') != choice.mode:
        obj.playback_mode = choice.mode
        fields.append('playback_mode')
    if hasattr(obj, 'playback_checked_at'):
        from django.utils import timezone

        obj.playback_checked_at = timezone.now()
        fields.append('playback_checked_at')
    return fields


def gate_links(obj, links, *, use_cache: bool = True) -> tuple[PlaybackChoice, list[str]]:
    """Choose and apply in one call — what every import path wants.

    ``links`` is the title's stored ``download_links`` *after* normalization and
    the integrity/liveness guards, so this only ever chooses among sources that
    already proved they belong to this title.
    """
    choice = choose_playback_link(
        links, current=(getattr(obj, 'video_url', '') or '').strip(), use_cache=use_cache,
    )
    # An import must not blank a link on a bad network day; only the deliberate
    # sweep, which re-tests with fresh probes, is allowed to clear.
    fields = apply_choice(obj, choice, allow_clear=False)
    if choice.changed:
        logger.info(
            'playback_gate: %s %s -> %s (%s) %s',
            obj.__class__.__name__, getattr(obj, 'pk', '?'), choice.mode,
            choice.reason or 'ok', choice.url[:100],
        )
    return choice, fields
