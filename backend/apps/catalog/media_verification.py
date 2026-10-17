"""Pre-publish media verification: prove a title plays before viewers see it.

The importer used to publish on the *presence* of links. Presence is not
playability: a signed CDN URL that expired an hour ago, a path the provider has
purged, or an HTML "file not found" page served with a ``.mkv`` name all satisfy
"has download links", and the breakage surfaces as a viewer's «پخش نمی‌شود»
report hours later.

This module closes that gap. Before anything is published it asks the servers
(:mod:`apps.catalog.media_probe`) whether the sources are really there, and
records the answer as a :class:`~apps.catalog.models.MediaCheck`. Publication
then reads that row — cheap, no network in a request path or a model property.

Two questions are answered separately, because they fail separately:

``playable``
    at least one **browser-safe** source (HLS/MP4 + H.264, per
    :mod:`playback_sources`) answered and supports byte ranges → the online
    player works. Seeking matters: a source without ranges cannot be scrubbed.
``downloadable``
    at least one live link of any container → the download button works. An
    MKV/x265 title is legitimately downloadable-but-not-playable, and the site
    shows it as a download while the playback crawler hunts a browser-safe
    mirror.

**Conservative by construction.** A probe that cannot get an answer (timeout,
TLS reset, 403 from this datacenter) is ``unknown``, never ``dead``: links are
kept, the title simply is not published yet, and the next pass tries again. Only
a server that positively says the file is gone (404/410/451, HTML where video was
promised, a truncated placeholder) lets a link be pruned — and pruning goes
through the normal save path so availability flags stay honest.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import timedelta
from functools import lru_cache
from typing import Any
from urllib.parse import unquote

from django.db import models, transaction
from django.utils import timezone

from apps.catalog.media_probe import Probe, probe_manifest, probe_url

logger = logging.getLogger(__name__)

#: How long a passing check is trusted. Provider signatures (dornatv) self-expire
#: in ~13 h, so a "verified" stamp older than this proves nothing any more.
FRESH_SECONDS = 6 * 3600
#: A failed/unknown check is retried sooner — the fix may already have landed.
RETRY_SECONDS = 1800
#: Upper bound on probes per target, so one title with 40 mirrors cannot stall a run.
MAX_PROBES_PER_TARGET = 6
#: Episodes probed per series check (the rest ride on the series-level verdict).
MAX_EPISODE_SAMPLE = 3


def _kind(obj) -> str:
    return 'movie' if obj.__class__.__name__ == 'Movie' else 'series'


def _link_url(item) -> str:
    if not isinstance(item, dict):
        return ''
    return str(item.get('url') or '').strip()


def _expect_for(url: str) -> str:
    return 'manifest' if url.lower().split('?')[0].endswith('.m3u8') else 'video'


def _probe(url: str, *, use_cache: bool = True) -> Probe:
    if _expect_for(url) == 'manifest':
        return probe_manifest(url, use_cache=use_cache)
    return probe_url(url, expect='video', use_cache=use_cache)


def _candidate_sources(obj, episode=None) -> list[dict]:
    """Every *video* source that could serve this target, browser-safe ones first.

    Ordering is the whole efficiency story: the first live browser-safe hit
    answers both questions at once and the rest are never probed.

    Entries :func:`_classify_link` calls ``skip`` are left out on purpose. That
    bucket is subtitles, audio-only tracks, images and links whose signature has
    already expired — probing them would report "not a video" and get a perfectly
    good ``.srt`` pruned as dead.

    Sources marked ``internal`` are object-storage keys for media our own
    pipeline produced and our own stack serves (``movies/9001/hls/master.m3u8``).
    There is no third-party host to interrogate, so they are trusted rather than
    probed — the failure mode this module exists to catch is a *provider* pulling
    a file out from under us.
    """
    from apps.catalog.playback_sources import _classify_link

    sources: list[dict] = []
    seen: set[str] = set()

    def add(url: str, *, safe: bool, origin: str):
        url = (url or '').strip()
        if not url or url in seen:
            return
        seen.add(url)
        sources.append({'url': url, 'safe': safe, 'origin': origin})

    target = episode if episode is not None else obj
    own_stream = str(getattr(target, 'video_url', '') or '').strip()
    if own_stream:
        from apps.catalog.playback_sources import _video_url_browser_safe

        remote = own_stream.startswith(('http://', 'https://'))
        add(
            own_stream,
            safe=_video_url_browser_safe(target),
            origin='video_url' if remote else 'internal',
        )

    # An episode's playable copies live on the series' link list too.
    for item in (getattr(obj, 'download_links', None) or []):
        url = _link_url(item)
        key = str(item.get('key') or '').strip() if isinstance(item, dict) else ''
        verdict = _classify_link(item)
        if verdict == 'skip':
            continue
        if key and not url:
            add(key, safe=True, origin='internal')
            continue
        if not url:
            continue
        if episode is not None and not _link_belongs_to_episode(item, url, episode):
            continue
        add(url, safe=verdict == 'safe', origin='download_links')

    sources.sort(key=lambda row: (not row['safe'], row['origin'] != 'video_url'))
    return sources


#: Persian (``۰۱۲``) and Arabic-Indic (``٠١٢``) digits, so a label written
#: «قسمت ۱۰» is read exactly like «قسمت 10».
_EASTERN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def _positive_int(value) -> int | None:
    """``value`` as a positive int, or ``None`` if it is not one."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _searchable_text(*parts) -> str:
    """One lowercase, percent-decoded, Western-digit rendering of a link.

    Percent-decoding is not cosmetic. ``Karen%20Pirie%20S01E03%20720p`` puts a
    digit immediately before the ``S``, so every ``\\b``-anchored pattern below
    slides straight past the season/episode pair and the link reads as naming
    nothing — on a provider that encodes its spaces, that was every episode of
    the show.
    """
    text = ' '.join(str(part) for part in parts if part)
    return unquote(text).lower().translate(_EASTERN_DIGITS)


#: How a link writes down which episode it is. Both readers below compile
#: against these and nothing else: :func:`_link_belongs_to_episode` decides
#: whether a link may be *offered* to an episode, and
#: :func:`stated_episode_identity` reads what a stored link *claims* so an
#: audit can catch the two disagreeing. They answer different questions, and
#: the one thing that must never differ is which spellings they can read at
#: all — a form only one of them understood is precisely how a correct link
#: comes to look like a mistake.
#:
#: Pairs are matched as pairs on purpose: ``/Dexter/S01-S09/`` sits in every
#: one of that pack's URLs, names two seasons, and means neither.
_PAIR_SEASON_EPISODE = re.compile(r'\bs\s*([0-9]{1,3})\s*[.\-_ ]?\s*e\s*([0-9]{1,3})\b')
_PAIR_SEASON_X_EPISODE = re.compile(r'\b([0-9]{1,2})\s*x\s*([0-9]{1,3})\b')
_WORD_SEASON = re.compile(r'(?:فصل|season)\s*([0-9]{1,3})')
_WORD_EPISODE = re.compile(r'(?:قسمت|episode)\s*([0-9]{1,3})')
#: ``E35``, ``E035``, ``Ep 35`` and ``E0035`` are one episode written four
#: ways. Long-running serials pad to three digits, so the number is compared
#: numerically rather than by spelling.
_BARE_EPISODE = re.compile(r'\be\.?p?\.?\s*([0-9]{1,4})\b')


def _stated_pairs(blob: str) -> set[tuple[int, int]]:
    """Every ``(season, episode)`` the text spells out as a pair."""
    return {
        (int(s_no), int(e_no))
        for pattern in (_PAIR_SEASON_EPISODE, _PAIR_SEASON_X_EPISODE)
        for s_no, e_no in pattern.findall(blob)
    }


def _link_belongs_to_episode(item: dict, url: str, episode) -> bool:
    """Keep only links that name *this* episode — this season's, not any season's.

    A season pack stores every episode of every season on the one Series row,
    so this test is all that stands between an episode and the several hundred
    files that are not it. Matching the episode number alone is not enough:
    «قسمت ۱۰» is equally true of S01E10 and S06E10.

    That was not a theoretical worry. Dexter S06E10 was handed 69 candidates
    whose first five were all season 1; the probe budget was spent on files
    that 404, and the gate returned "could not tell" — on every sweep, forever.
    The episode went on serving a dead link precisely because the test never
    got far enough to call it dead.

    Evidence in order of strength: what the importer parsed and stored, then an
    ``S06E10`` pair written in the text, then «فصل ۶ … قسمت ۱۰». Only when the
    link says nothing at all about seasons does the episode number decide by
    itself — that is the single-season pack, where it is the whole truth.
    """
    number = int(getattr(episode, 'episode_number', 0) or 0)
    if not number:
        return True
    season = int(getattr(getattr(episode, 'season', None), 'season_number', 0) or 0)

    # 1. Structured fields. The importer already parsed this link when it
    #    created the row; no regex over a file name knows better than that.
    if isinstance(item, dict):
        item_episode = _positive_int(item.get('episode_number'))
        if item_episode is not None:
            if item_episode != number:
                return False
            item_season = _positive_int(item.get('season_number'))
            return not (season and item_season is not None and item_season != season)

    blob = _searchable_text(url, item.get('label'), item.get('quality'))

    # 2. An ``sNNeNN`` / ``NxNN`` pair states both numbers at once and so
    #    answers the question on its own. Pairs only, deliberately: the folder
    #    ``/Dexter/S01-S09/`` sits in every one of these URLs, names two
    #    seasons, and means neither of them.
    pairs = _stated_pairs(blob)
    if pairs:
        if season:
            return (season, number) in pairs
        return any(e_no == number for _s_no, e_no in pairs)

    # 3. The same statement in words. A season named here that is not ours
    #    settles it before the episode number is even read.
    said_season = _WORD_SEASON.search(blob)
    if season and said_season and int(said_season.group(1)) != season:
        return False
    said_episode = _WORD_EPISODE.search(blob)
    if said_episode:
        return int(said_episode.group(1)) == number

    # 4. Nothing states a season anywhere — a single-season pack, where the
    #    episode number really is the whole truth. This is the original test,
    #    kept for exactly the case it was right about, but comparing the number
    #    rather than its spelling: ``E35``, ``E035`` and ``Ep 35`` are one
    #    episode written three ways, and long-running serials pad to three.
    #    Matching the two-digit form literally made every ``E035`` file look
    #    like somebody else's episode.
    return any(int(found.group(1)) == number for found in _BARE_EPISODE.finditer(blob))


# One pack is read once per episode of its series — 363 links across 136
# episodes for «در برزخ» — and the answer for a given URL never changes.
@lru_cache(maxsize=8192)
def stated_episode_identity(url: str) -> tuple[int | None, int] | None:
    """What a link's *file name* says it is — ``(season or None, episode)``.

    The file name and nothing else. Not ``episode_number``, and — the part that
    took a production dry run to learn — not ``label`` either. All three come
    from the same pass over the same provider page, so none of them can be a
    witness against the others; an audit built on any of them only ever agrees
    with itself. The file name is the one statement the provider's *host* made
    about the bytes.

    That is not a hypothetical. On «فندک و شاهزاده خانم» the provider's page
    labels two different files «قسمت ۱», so from ``EP03`` onward every label
    runs one episode behind the file it names. Reading the label made all 34
    episodes look unrepairable; reading the file name makes the off-by-one
    obvious and fixable. And the reverse case is real too: Esref Ruya's
    ``S01E26`` is the catalogue's S02E13, because the provider numbers the
    serial straight through — there the file name disagrees and *nothing* in
    the pack can fix it, which is why the caller leaves that class alone.

    ``None`` means the name states no episode, and equally that it states more
    than one: a name pointing two ways is not evidence of anything. Silence and
    ambiguity both have to read as "no claim", because the caller turns a claim
    into a repair.

    A number below 1 is a third way of saying nothing, and it is the one that
    took real data to find. ``The.Good.Place.S02E0.720p.mkv`` is a *truncated*
    S02E07, and ``Euphoria.S01E00`` is a special that has no episode row at
    all — read literally, both hand a caller an "episode 0" to file links
    under or repair rows against. :func:`_season_episode_key` has always
    refused episode numbers below 1; this refuses them at the same floor, in
    the one place where a claim becomes an edit. The readers still parse the
    same spellings — that is what :data:`_PAIR_SEASON_EPISODE` and friends are
    for — they just disagree about what a zero is worth, which is a judgement
    and not a grammar.
    """
    blob = _searchable_text(url)

    pairs = {(s_no, e_no) for s_no, e_no in _stated_pairs(blob) if e_no >= 1}
    if pairs:
        return pairs.pop() if len(pairs) == 1 else None

    said_episode = _WORD_EPISODE.search(blob)
    if said_episode:
        number = int(said_episode.group(1))
        if number < 1:
            return None
        said_season = _WORD_SEASON.search(blob)
        return (int(said_season.group(1)) if said_season else None, number)

    numbers = {int(found.group(1)) for found in _BARE_EPISODE.finditer(blob)}
    numbers = {number for number in numbers if number >= 1}
    return (None, numbers.pop()) if len(numbers) == 1 else None


def episode_identity_matches(stated: tuple[int | None, int] | None, episode) -> bool:
    """Does an identity read off a link's text name *this* episode?

    A text that gives no season cannot contradict one, so it matches on the
    episode number alone — which is the single-season pack, and the serials
    that never write a season at all.
    """
    if not stated:
        return False
    season_said, episode_said = stated
    if episode_said != int(getattr(episode, 'episode_number', 0) or 0):
        return False
    season = int(getattr(getattr(episode, 'season', None), 'season_number', 0) or 0)
    return not (season and season_said is not None and season_said != season)


def verify_target(
    obj, *, episode=None, use_cache: bool = True, tech_deadline: float | None = None,
) -> dict[str, Any]:
    """Probe this target's sources and record a :class:`MediaCheck`.

    Returns the verdict dict: ``status``, ``playable``, ``downloadable``,
    ``reason``, ``checked``, ``dead``, ``probes``.

    ``tech_deadline`` is a :func:`time.monotonic` instant after which codec
    probing stops for this caller. One title never needs it; a batch sweep does,
    because ffprobe waits on the host and a serial loop over eighty targets can
    otherwise outlast its own schedule.
    """
    sources = _candidate_sources(obj, episode)
    probes: list[dict] = []
    playable = downloadable = False
    dead: list[str] = []
    unknown = 0
    geo_blocked = 0
    tech_probes = 0
    accepted_tech: dict | None = None
    measured_tech: dict | None = None

    for source in sources[:MAX_PROBES_PER_TARGET]:
        if source['origin'] == 'internal':
            probes.append({
                'url': source['url'], 'verdict': 'live', 'reason': 'internal_storage',
                'safe': source['safe'],
            })
            downloadable = True
            if source['safe']:
                playable = True
                break
            continue

        result = _probe(source['url'], use_cache=use_cache)
        row = result.as_dict()
        row['safe'] = source['safe']
        probes.append(row)

        if result.dead:
            dead.append(source['url'])
            continue
        if result.verdict == 'unknown':
            if result.reason == 'geo_blocked':
                geo_blocked += 1
            unknown += 1
            continue
        downloadable = True
        # Byte ranges are required for the player (seek + resume), not for a download.
        if source['safe'] and result.reason != 'no_byte_ranges':
            # `safe` so far means the *filename* looked browser-friendly. Before
            # that becomes a publish verdict, read the container header and find
            # out what the file actually is.
            confirmed, tech_probes = _confirm_browser_safe(
                source['url'], tech_probes, deadline=tech_deadline,
            )
            row['tech'] = confirmed
            if measured_tech is None and (confirmed.get('duration') or 0) > 0:
                # ffprobe read this file. Even if the encode is one no browser
                # will play, the runtime it measured is real and the subtitle
                # gate needs it.
                measured_tech = confirmed
            if confirmed['verdict'] == 'unsafe':
                # The name lied — HEVC behind a .mp4 path, Matroska behind any
                # path, DTS audio no browser decodes. Downloadable, not playable;
                # the playback-source crawler picks it up from here.
                row['safe'] = False
                continue
            accepted_tech = confirmed
            playable = True
            break

    status, reason = _verdict(
        sources=sources, probes=probes, playable=playable,
        downloadable=downloadable, dead=dead, unknown=unknown,
        truncated=len(sources) > MAX_PROBES_PER_TARGET, geo_blocked=geo_blocked,
    )
    if reason == 'geo_blocked':
        downloadable = True
    record = _record(
        obj, episode, status=status, reason=reason, playable=playable,
        downloadable=downloadable, probes=probes, dead=len(dead),
        tech=accepted_tech or measured_tech,
    )
    if dead:
        pruned = prune_dead_links(obj, dead, episode=episode)
        if pruned:
            logger.info(
                'media_check: dropped %d dead link(s) from %s %s',
                pruned, _kind(obj), getattr(obj, 'pk', '?'),
            )
    _keep_measured_sizes(obj, probes)
    return {
        'status': record.status, 'playable': record.playable,
        'downloadable': record.downloadable, 'reason': record.reason,
        'checked': len(probes), 'dead': len(dead), 'probes': probes,
    }


def _keep_measured_sizes(obj, probes) -> None:
    """The probe just learned each live mirror's byte count — put it on the link."""
    measured = {
        row['url']: int(row.get('bytes') or 0)
        for row in probes
        if row.get('verdict') == 'live' and int(row.get('bytes') or 0) > 0
    }
    if not measured or not getattr(obj, 'pk', None) or not hasattr(obj, 'download_links'):
        return
    try:
        from apps.catalog.link_sizes import stamp_sizes

        stamp_sizes(obj, measured)
    except Exception as exc:  # a size is a nicety; the verdict above is not
        logger.warning('media_check: could not keep sizes for %s: %s', getattr(obj, 'pk', '?'), exc)


#: ffprobes spent per target. Reachability is cheap and runs on every mirror;
#: reading a container header costs a real round-trip, so only the sources that
#: are about to be called playable are worth one.
MAX_TECH_PROBES_PER_TARGET = 2


def _confirm_browser_safe(url: str, spent: int, *, deadline: float | None = None) -> tuple[dict, int]:
    """Ask the bytes whether this source is really browser-playable.

    Returns ``(verdict_dict, probes_spent)``. Falling back to the filename
    heuristic is always allowed: an ffprobe that times out, a host that refuses
    us or a budget that has run out all yield ``unknown``, which leaves the
    caller exactly where it was before this check existed.
    """
    from apps.catalog import media_tech

    if not media_tech.codec_verification_enabled():
        return {'verdict': 'unknown', 'reason': 'disabled'}, spent
    if spent >= MAX_TECH_PROBES_PER_TARGET:
        return {'verdict': 'unknown', 'reason': 'tech_budget_spent'}, spent
    if deadline is not None and time.monotonic() >= deadline:
        return {'verdict': 'unknown', 'reason': 'tech_time_spent'}, spent
    try:
        return media_tech.verify_source(url), spent + 1
    except Exception as exc:  # never let a probe failure block an import
        logger.warning('media_check: codec probe failed for %s: %s', url[:120], exc)
        return {'verdict': 'unknown', 'reason': 'probe_error'}, spent + 1


def _verdict(
    *, sources, probes, playable, downloadable, dead, unknown, truncated=False, geo_blocked=0,
) -> tuple[str, str]:
    from apps.catalog.models import MediaCheck

    S = MediaCheck.Status
    if not sources:
        return S.FAILED, 'no_sources'
    if playable:
        return S.PASSED, ''
    if downloadable:
        # Real, reachable files — just none a browser can play. The playback
        # crawler's job, not a reason to call the import broken.
        return S.PASSED, 'download_only'
    if geo_blocked:
        # The host answered — with its "turn your VPN off" page, because this
        # server is not in Iran and the audience is. That is a CDN that is up
        # and serving the people who will press the button; holding the title
        # back would mean no mirror behind an Iranian CDN could ever go live.
        # Mirrors that proved dead beside it are still pruned below.
        return S.PASSED, 'geo_blocked'
    if unknown and not dead:
        return S.UNKNOWN, (probes[0]['reason'] if probes else 'unreachable')
    if dead and not unknown:
        if truncated:
            # The probe budget ran out on dead mirrors. Those are pruned, so the
            # next pass starts on the ones nobody has tested — calling the title
            # dead now would condemn links we never asked about.
            return S.UNKNOWN, 'partially_probed'
        return S.FAILED, 'all_sources_dead'
    if not probes:
        return S.UNKNOWN, 'not_probed'
    return S.UNKNOWN, 'partially_unreachable'


def _record(obj, episode, *, status, reason, playable, downloadable, probes, dead, tech=None):
    from apps.catalog.models import MediaCheck

    record, _created = MediaCheck.objects.get_or_create(
        content_type=_kind(obj),
        object_id=obj.pk,
        episode_id=getattr(episode, 'pk', 0) or 0,
    )
    record.status = status
    record.reason = (reason or '')[:64]
    record.playable = playable
    record.downloadable = downloadable
    record.checked_urls = len(probes)
    record.dead_urls = dead
    record.attempts = (record.attempts or 0) + 1
    detail = {'probes': probes[:MAX_PROBES_PER_TARGET]}
    if tech and (tech.get('duration') or 0) > 0:
        # The measured truth about this encode. Kept for every source ffprobe
        # actually read, not only the browser-safe ones: a Matroska copy is
        # still published as a download and still gets subtitles attached, and
        # `duration` is the only trustworthy runtime to judge their sync
        # against — TMDB's runtime describes the theatrical cut, not this file.
        detail['tech'] = tech
    record.detail = detail
    record.checked_at = timezone.now()
    record.save()
    return record


def prune_dead_links(obj, dead_urls, *, episode=None) -> int:
    """Remove links the server positively reported gone. Never called on doubt.

    A dead mirror leaves the download list at once: the list holds others, and
    the next crawl re-imports it if the host was lying. The ``video_url`` on the
    row that actually holds it (the episode when one is given, otherwise the
    movie) is held to the stricter bar — blanking it takes the title offline
    until a provider yields a replacement, so it waits for the second sighting
    that :func:`playback_gate.clearing_confirmed` defines. Either way the verdict
    is recorded now, which is what makes a second sighting possible at all.
    """
    dead = {url for url in dead_urls if url}
    if not dead:
        return 0

    from apps.catalog import playback_gate

    removed = 0
    with transaction.atomic():
        stream_owner = episode if episode is not None else obj
        if str(getattr(stream_owner, 'video_url', '') or '').strip() in dead:
            # The verdict described the URL that just went away, and leaving it
            # behind would have the API tell the player a deleted file plays.
            # But the stream link is the one thing here a re-run cannot put back
            # by itself, so it goes on the second sighting, not the first —
            # ``playback_gate`` owns that rule and the gate sweep obeys the same
            # one. Read it before the verdict below overwrites the evidence.
            confirmed = playback_gate.clearing_confirmed(stream_owner)
            owner_fields: list[str] = []
            if confirmed:
                stream_owner.video_url = ''
                owner_fields.append('video_url')
                removed += 1
            if hasattr(stream_owner, 'playback_mode'):
                from apps.catalog.models import PlaybackMode

                # Stamp the verdict on the way in, but only when it is news.
                # Re-stamping an unchanged "none" on every later import would
                # keep pushing the clock forward and the second opinion would
                # never come due.
                if confirmed or getattr(stream_owner, 'playback_mode', '') != PlaybackMode.NONE:
                    stream_owner.playback_mode = PlaybackMode.NONE
                    stream_owner.playback_checked_at = timezone.now()
                    owner_fields.extend(['playback_mode', 'playback_checked_at'])
            if owner_fields:
                stream_owner.save(update_fields=[*owner_fields, 'updated_at'])

        links = list(getattr(obj, 'download_links', None) or [])
        kept = [item for item in links if _link_url(item) not in dead]
        if len(kept) != len(links):
            obj.download_links = kept
            obj.save(update_fields=['download_links', 'updated_at'])
            removed += len(links) - len(kept)
    return removed


#: Distinct episodes sampled when screening an incoming provider batch.
MAX_SCREEN_GROUPS = 12
#: Mirrors probed inside one episode before moving on (a dead mirror is common,
#: a dead episode is what matters).
MAX_SCREEN_PER_GROUP = 2
#: Hard ceiling on probes for one batch, so a 40-episode pack stays fast.
MAX_SCREEN_PROBES = 18


def _group_key(item) -> tuple[int, int]:
    """(season, episode) for a link, ``(0, 0)`` for a movie."""
    from apps.catalog.subtitle_extract import _season_episode_key

    try:
        return _season_episode_key(item) or (0, 0)
    except Exception:
        return (0, 0)


def screen_links(obj, links: list, *, limit: int = MAX_SCREEN_PROBES) -> tuple[list, list]:
    """Test incoming provider links and drop the ones the host says are gone.

    This is the guard that makes "published" mean "watchable". Provider pages
    keep advertising files their CDN has already deleted, and until now those
    went straight into ``download_links`` and onto the site, where a viewer found
    them for us.

    Screening is sampled, not exhaustive: one episode's first live mirror
    settles that episode, and a whole season pack must not stall a crawl. The
    periodic sweep re-checks everything else afterwards.

    Returns ``(kept, dropped)``; ``dropped`` is a list of ``(item, reason)``.
    """
    from apps.catalog.playback_sources import _classify_link

    if not verification_enabled() or not screening_enabled():
        return list(links), []

    groups: dict[tuple[int, int], list[int]] = {}
    for index, item in enumerate(links):
        if not isinstance(item, dict) or not _link_url(item):
            continue
        if _classify_link(item) == 'skip':
            continue
        groups.setdefault(_group_key(item), []).append(index)

    try:
        from django.conf import settings

        group_workers = max(1, min(6, int(getattr(settings, 'CATALOG_SCREEN_PROBE_WORKERS', 4) or 4)))
    except (TypeError, ValueError):
        group_workers = 4

    def _settle_group(key) -> tuple[tuple[int, int], list[tuple[int, str]], int]:
        """Probe one episode's mirrors in rank order; first live/unverifiable wins.

        Sequential inside the group on purpose: a healthy episode still costs a
        single probe, and the verdict is identical to the old serial loop. Only
        independent episodes run in parallel.
        """
        candidates = sorted(
            groups[key],
            key=lambda i: _classify_link(links[i]) != 'safe',
        )[:MAX_SCREEN_PER_GROUP]
        dead_here: list[tuple[int, str]] = []
        used = 0
        for index in candidates:
            used += 1
            result = _probe(_link_url(links[index]))
            if result.dead:
                dead_here.append((index, result.reason))
                continue
            break  # live or unverifiable — this episode has something to serve
        return key, dead_here, used

    ordered_keys = sorted(groups)[:MAX_SCREEN_GROUPS]
    dead_indexes: dict[int, str] = {}
    probes = 0
    if group_workers <= 1 or len(ordered_keys) <= 1:
        for key in ordered_keys:
            if probes >= limit:
                break
            _key, dead_here, used = _settle_group(key)
            probes += used
            for dead_index, reason in dead_here:
                dead_indexes[dead_index] = reason
    else:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=min(group_workers, len(ordered_keys))) as pool:
            # map() preserves input order, so results stay deterministic even
            # though the probes themselves run concurrently.
            for _key, dead_here, used in pool.map(_settle_group, ordered_keys):
                if probes >= limit:
                    break
                probes += used
                for dead_index, reason in dead_here:
                    dead_indexes[dead_index] = reason

    if not dead_indexes:
        return list(links), []

    kept = [item for index, item in enumerate(links) if index not in dead_indexes]
    dropped = [(links[index], reason) for index, reason in dead_indexes.items()]
    logger.warning(
        'media_screen: dropped %d dead link(s) of %d for %s %s (%d probed): %s',
        len(dropped), len(links), _kind(obj), getattr(obj, 'pk', '?'), probes,
        ', '.join(f'{reason}:{_link_url(item)[:80]}' for item, reason in dropped[:6]),
    )
    return kept, dropped


def screening_enabled() -> bool:
    from django.conf import settings

    return bool(getattr(settings, 'CATALOG_SCREEN_PROVIDER_LINKS', True))


def latest_check(obj, *, episode=None):
    from apps.catalog.models import MediaCheck

    return MediaCheck.objects.filter(
        content_type=_kind(obj), object_id=obj.pk,
        episode_id=getattr(episode, 'pk', 0) or 0,
    ).first()


def measured_duration(obj, *, episode=None) -> float:
    """This encode's real runtime in seconds, ``0.0`` when never measured.

    Read from the stored check, so it costs nothing and is safe anywhere. It is
    not the TMDB runtime: that describes the theatrical cut and disagrees with
    the actual file by minutes often enough to be useless for judging whether a
    subtitle belongs to it.
    """
    record = latest_check(obj, episode=episode)
    detail = getattr(record, 'detail', None) or {}
    try:
        return max(0.0, float((detail.get('tech') or {}).get('duration') or 0.0))
    except (TypeError, ValueError):
        return 0.0


def is_fresh(record, *, seconds: int = FRESH_SECONDS) -> bool:
    if record is None or record.checked_at is None:
        return False
    return record.checked_at >= timezone.now() - timedelta(seconds=seconds)


def ensure_verified(obj, *, episode=None, force: bool = False) -> dict[str, Any]:
    """Return a fresh verdict, probing only when the stored one is stale."""
    record = latest_check(obj, episode=episode)
    if not force and is_fresh(record):
        return {
            'status': record.status, 'playable': record.playable,
            'downloadable': record.downloadable, 'reason': record.reason,
            'checked': record.checked_urls, 'dead': record.dead_urls, 'cached': True,
        }
    return verify_target(obj, episode=episode)


def media_publish_blockers(obj, *, episode=None, verify: bool = False) -> list[str]:
    """Media reasons this target must not go live ( ``[]`` when it may).

    Reads the stored check by default so it is safe in gates and properties; pass
    ``verify=True`` from the importer, where a few seconds of network is correct.
    """
    from apps.catalog.models import MediaCheck

    if not verification_enabled():
        return []
    if verify:
        # A stored pass may be trusted for its freshness window; a stored refusal
        # may not. The gate is asked again exactly when something changed —
        # new links, a fixed probe, a host back up — and answering from a
        # six-hour-old "no" is how a repaired title stays refused all day.
        stored = latest_check(obj, episode=episode)
        refused = stored is not None and stored.status != MediaCheck.Status.PASSED
        verdict = ensure_verified(obj, episode=episode, force=refused)
        status, playable, downloadable = (
            verdict['status'], verdict['playable'], verdict['downloadable'],
        )
    else:
        record = latest_check(obj, episode=episode)
        if not is_fresh(record):
            return ['media_unverified']
        status, playable, downloadable = record.status, record.playable, record.downloadable

    if status == MediaCheck.Status.FAILED:
        return ['media_sources_dead']
    if status == MediaCheck.Status.UNKNOWN:
        return ['media_unverified']
    if not (playable or downloadable):
        return ['media_sources_dead']
    return []


def verification_enabled() -> bool:
    from django.conf import settings

    return bool(getattr(settings, 'CATALOG_VERIFY_MEDIA_BEFORE_PUBLISH', True))


def verify_before_publish(obj, *, episode=None) -> tuple[bool, list[str]]:
    """The importer's gate: probe now, and say whether publishing is allowed."""
    blockers = media_publish_blockers(obj, episode=episode, verify=True)
    return (not blockers), blockers


#: Most published titles one sweep may send back to draft. A provider outage
#: must degrade into "a few titles re-crawled", never into an emptied catalog.
MAX_UNPUBLISH_PER_SWEEP = 10

#: Wall clock one sweep may spend reading container headers, across all targets.
#: ``probe_tech`` caches only successes, so a host that accepts the connection
#: and then stalls costs the full ffprobe timeout on *every* sweep, forever.
#: A normal sweep never comes close — a header read is a second or two — so this
#: only ever bites the pathological case, and it bites it by falling back to the
#: filename heuristic, which is where this code started.
SWEEP_TECH_SECONDS = 600


def sweep_published_media(limit: int | None = None) -> dict[str, Any]:
    """Re-test published titles whose verdict has gone stale; repair what broke.

    Ordering puts the never-checked first (they went live before this gate
    existed), then the oldest verdicts.
    """
    from django.conf import settings

    from apps.catalog.models import MediaCheck, Movie, Series

    if not verification_enabled():
        return {'checked': 0, 'skipped': 'disabled'}

    limit = limit or int(getattr(settings, 'CATALOG_MEDIA_RECHECK_BATCH', 40))
    stats = {
        'checked': 0, 'passed': 0, 'failed': 0, 'unknown': 0,
        'recrawled': 0, 'unpublished': 0,
    }
    unpublished = 0
    tech_deadline = time.monotonic() + SWEEP_TECH_SECONDS

    for obj in _stale_published(Movie, 'movie', limit) + _stale_published(Series, 'series', limit):
        verdict = verify_target(obj, tech_deadline=tech_deadline)
        stats['checked'] += 1
        if verdict['status'] == MediaCheck.Status.PASSED:
            stats['passed'] += 1
            continue
        if verdict['status'] == MediaCheck.Status.UNKNOWN:
            # Could not reach the host from here. Not evidence of breakage —
            # leave the title alone and try again next sweep.
            stats['unknown'] += 1
            continue

        stats['failed'] += 1
        obj.refresh_from_db()
        if _has_any_source(obj):
            if _request_recrawl(obj):
                stats['recrawled'] += 1
            continue
        if unpublished < MAX_UNPUBLISH_PER_SWEEP and _send_to_draft(obj):
            unpublished += 1
            stats['unpublished'] += 1

    return stats


def _stale_published(model, kind: str, limit: int) -> list:
    """Published rows whose media verdict is missing or older than FRESH_SECONDS."""
    from django.db.models import OuterRef, Subquery

    from apps.catalog.models import MediaCheck

    checked_at = MediaCheck.objects.filter(
        content_type=kind, object_id=OuterRef('pk'), episode_id=0,
    ).values('checked_at')[:1]
    queryset = (
        model.objects.filter(is_published=True)
        .annotate(media_checked_at=Subquery(checked_at))
        .filter(
            models.Q(media_checked_at__isnull=True)
            | models.Q(media_checked_at__lt=timezone.now() - timedelta(seconds=FRESH_SECONDS))
        )
        .order_by(models.F('media_checked_at').asc(nulls_first=True))
    )
    return list(queryset[: max(1, limit // 2)])


def _has_any_source(obj) -> bool:
    return bool(
        (getattr(obj, 'download_links', None) or [])
        or str(getattr(obj, 'video_url', '') or '').strip()
    )


def _request_recrawl(obj) -> bool:
    """Send a broken title down the existing provider repair path."""
    from apps.catalog.provider_import.signals import (
        enqueue_provider_movie_auto_crawl,
        enqueue_provider_series_auto_crawl,
    )

    try:
        if _kind(obj) == 'movie':
            return enqueue_provider_movie_auto_crawl(obj.pk, replace=True, reason='media_check_failed')
        return enqueue_provider_series_auto_crawl(obj.pk, replace=True, reason='media_check_failed')
    except Exception:
        logger.exception('media_check: could not enqueue re-crawl for %s %s', _kind(obj), obj.pk)
        return False


def _send_to_draft(obj) -> bool:
    """Unpublish a title that has nothing left to serve (never on doubt)."""
    from apps.catalog.models import Movie

    fields = ['is_published', 'updated_at']
    obj.is_published = False
    if isinstance(obj, Movie):
        obj.publication_status = Movie.PublicationStatus.DRAFT
        fields.append('publication_status')
    obj.save(update_fields=fields)
    logger.warning(
        'media_check: unpublished %s %s — every source is gone',
        _kind(obj), obj.pk,
    )
    return True


def verify_series_episodes(series, *, limit: int = MAX_EPISODE_SAMPLE) -> dict[str, Any]:
    """Verify a sample of a series' episodes and return the tally.

    A series is only as watchable as its episodes, and episode links rot
    individually. Sampling keeps an import run bounded; the periodic sweep walks
    the rest over time.
    """
    from apps.catalog.models import Episode, MediaCheck

    episodes = list(
        Episode.objects.filter(season__series_id=series.pk)
        .select_related('season')
        .order_by('season__season_number', 'episode_number')[: max(1, limit)]
    )
    stats = {'checked': 0, 'passed': 0, 'failed': 0, 'unknown': 0}
    for episode in episodes:
        verdict = verify_target(series, episode=episode)
        stats['checked'] += 1
        if verdict['status'] == MediaCheck.Status.PASSED:
            stats['passed'] += 1
        elif verdict['status'] == MediaCheck.Status.FAILED:
            stats['failed'] += 1
        else:
            stats['unknown'] += 1
    return stats
