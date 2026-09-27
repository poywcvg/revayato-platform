"""Self-describing-URL identity guard for incoming provider links.

abrtech.top (and sibling) CDN paths encode the true identity of the media in
the path itself::

    /yA3f/Film/<year>/<Title.Year>/DUB|SUB/<Title.Year.quality...>.mkv
    /yA3f/Film/<fyear>/<Franchise>.All.in.One/<real_year>/...          (franchise)
    /yA3f/Series/<Name>/<Name.SxxExx...>

The leaf filename grammar is ``<Title.Tokens>.<YEAR>.<quality tokens>...`` where
the *real* film year is the 4-digit token immediately BEFORE the first quality
token (1080p / BluRay / WEB-DL / x265 ...). That parses correctly through the
year-in-title traps (Blade.Runner.2049.2017 -> 2017, 1917.2019 -> 2019).

This module reuses that grammar to reject links whose encoded identity does not
match the catalog row they are about to be attached to, so the importer can no
longer store another film's stream (or a series pack) on a Movie.

``release_year`` is the false-positive-proof discriminator: a foreign film with
an English CDN name (Il buono -> The.Good.the.Bad.and.the.Ugly.1966) is LEGIT
because its year matches the catalog even when no title token overlaps. Real
contamination always carries a mismatched year, so we never strip on a
title-only disagreement.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import unquote, urlsplit

# --- tokenisation -----------------------------------------------------------
_EP = re.compile(
    r'(?:^|[._\-/ ])S\d{1,2}E\d{1,3}(?:[._\-/ ]|$)|(?:^|[._\-/ ])\d{1,2}x\d{1,3}(?:[._\-/ ]|$)',
    re.I,
)
_QUAL = {
    '1080p', '720p', '480p', '360p', '2160p', '4k', 'uhd', 'bluray', 'blu',
    'brrip', 'bdrip', 'bd', 'web', 'webdl', 'webrip', 'hdtv', 'hdrip', 'dvdrip',
    'remux', 'x264', 'x265', 'h264', 'h265', 'hevc', '10bit', '8bit', 'imax',
    'remastered', 'extended', 'unrated', 'uncut', 'proper', 'repack', 'yify',
    'yts', 'softsub', 'hardsub', 'dubbed', 'farsi', 'dl', 'rip', 'atmos',
    'truehd', 'dts', 'aac', 'dooble', '2dooble', '3dooble', '2dubbed', 'byndr',
    'sub', 'dubbe',
}
_YEAR = re.compile(r'^(19|20)\d{2}$')
_SEASON_DIR = re.compile(r'^(s|season)[ ._-]?\d{1,2}$')
_STOP = {'the', 'and', 'film', 'movie', 'dub', 'sub', 'web', 'part', 'farsi', 'bluray'}
_ROMAN = {'ii': 2, 'iii': 3, 'iv': 4, 'v': 5, 'vi': 6, 'vii': 7, 'viii': 8, 'ix': 9, 'x': 10}


def _norm(s) -> str:
    return (
        unicodedata.normalize('NFKC', str(s or ''))
        .replace('ي', 'ی')
        .replace('ك', 'ک')
        .replace('‌', ' ')
        .casefold()
    )


def _toks(s) -> set[str]:
    return {t for t in re.split(r'[^a-z0-9؀-ۿ]+', _norm(s)) if len(t) >= 3}


def _seqnum(title) -> int:
    parts = [p for p in re.split(r'[^a-z0-9؀-ۿ]+', _norm(title)) if p]
    if not parts:
        return 0
    last = parts[-1]
    if last.isdigit() and len(last) <= 2:
        return int(last)
    if last in _ROMAN:
        return _ROMAN[last]
    return 0


def _basetoks(title) -> frozenset[str]:
    ts = _toks(title) - _STOP
    return frozenset(t for t in ts if not (t.isdigit() and len(t) <= 2) and t not in _ROMAN)


def _leafpath(url):
    p = unquote(urlsplit(str(url or '')).path or '').lower()
    return p, p.rsplit('/', 1)[-1]


def parse_year_title(leaf: str):
    """Return (year, title_tokens_str) parsed from a CDN leaf filename."""
    parts = re.split(r'[._\-\s]+', leaf)
    qi = next((i for i, t in enumerate(parts) if t in _QUAL), None)
    yrs = [(i, int(t)) for i, t in enumerate(parts) if _YEAR.match(t)]
    if not yrs:
        return None, ''
    if qi is not None:
        before = [y for y in yrs if y[0] < qi]
        yi, yr = before[-1] if before else yrs[-1]
    else:
        yi, yr = yrs[-1]
    return yr, ' '.join(parts[:yi])


# Categories that mean "this link belongs to a different title": safe to drop.
STRIP_CATS = frozenset({'A_series', 'B_wrongfilm', 'seq_diff', 'remake'})
# Reported / kept: same_title_yeardiff (metadata year slip), C_offby1 & B_partial
# (mostly legit foreign alt-titles) are never auto-stripped.


def classify_movie_link(movie, url: str) -> str:
    """Classify a download/subtitle URL against a Movie's identity.

    Returns one of: ``A_series``, ``B_wrongfilm``, ``seq_diff``, ``remake``,
    ``same_title_yeardiff``, ``C_offby1``, ``B_partial`` or ``ok``.
    Only the members of :data:`STRIP_CATS` are contamination.
    """
    p, leaf = _leafpath(url)
    if _EP.search(p) or '/series/' in p:
        return 'A_series'
    if '/film/' in p or '/movie/' in p or '/movies/' in p:
        yr, pt = parse_year_title(leaf)
        release_year = getattr(movie, 'release_year', None)
        if yr and release_year:
            d = abs(yr - int(release_year))
            cbase = _basetoks(getattr(movie, 'title', '')) | _basetoks(getattr(movie, 'original_title', ''))
            pbase = _basetoks(pt)
            cseq = max(_seqnum(getattr(movie, 'title', '')), _seqnum(getattr(movie, 'original_title', '')))
            pseq = _seqnum(pt)
            same_base = bool(cbase and pbase and cbase == pbase)
            disjoint = bool(cbase and pbase and not (cbase & pbase))
            if d > 1:
                if same_base and cseq == pseq and d <= 3:
                    return 'same_title_yeardiff'
                if same_base and cseq != pseq:
                    return 'seq_diff'
                if same_base and d > 3:
                    return 'remake'
                if disjoint:
                    return 'B_wrongfilm'
                return 'B_partial'
            if d >= 1 and disjoint and cseq == pseq:
                return 'C_offby1'
            if d >= 1 and same_base and cseq != pseq:
                return 'seq_diff'
    return 'ok'


def classify_series_link(series, url: str) -> str:
    """Classify a link against a Series identity (conservative).

    A series legitimately owns many ``SxxExx`` leaves. Contamination is a
    *movie* file leaf whose title+year disagree, or a ``/series/<Other>/`` pack
    whose name shares no base token with this series. Episode leaves and
    same-name packs are always kept.
    """
    p, leaf = _leafpath(url)
    sbase = _basetoks(getattr(series, 'title', '')) | _basetoks(getattr(series, 'original_title', ''))
    # A movie file (has a year-before-quality leaf, no episode marker) on a series row.
    if not _EP.search(p) and ('/film/' in p or '/movie/' in p or '/movies/' in p):
        yr, pt = parse_year_title(leaf)
        pbase = _basetoks(pt)
        if yr and sbase and pbase and not (sbase & pbase):
            return 'B_wrongfilm'
    # A /series/<Other>/ pack whose name is disjoint from ours.
    if '/series/' in p:
        # Some CDNs file packs by upload date or shard (/series/2023/09/Reacher/,
        # /Series/1/Reacher/): the pack name is the first non-numeric folder.
        # A season folder before any name means there is no name to judge.
        folders = p.split('/series/', 1)[1].split('/')[:-1]
        seg = next((f for f in folders if f and not f.isdigit()), '')
        if _SEASON_DIR.match(seg):
            seg = ''
        obase = _basetoks(seg)
        if sbase and obase and not (sbase & obase):
            return 'B_wrongfilm'
    return 'ok'


def _url_of(item: dict) -> str:
    if not isinstance(item, dict):
        return ''
    return str(item.get('url') or item.get('source_url') or '').strip()


def filter_contaminated_links(obj, links: list) -> tuple[list, list]:
    """Split ``links`` into (kept, dropped).

    ``dropped`` items are ``(item, category)`` tuples for logging. Rows are only
    dropped when the encoded CDN identity proves a different title (STRIP_CATS).
    Non-dict items, and links with no classifiable CDN path, are always kept so
    this can never make a legitimate import empty by mistake.
    """
    from apps.catalog.models import Series

    is_series = isinstance(obj, Series)
    kept: list = []
    dropped: list = []
    for item in links or []:
        url = _url_of(item)
        if not url:
            kept.append(item)
            continue
        cat = classify_series_link(obj, url) if is_series else classify_movie_link(obj, url)
        if cat in STRIP_CATS:
            dropped.append((item, cat))
        else:
            kept.append(item)
    return kept, dropped
