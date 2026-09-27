"""In-process search-as-you-type index for the header/app search boxes.

``/api/search/`` answers from PostgreSQL with ``icontains`` + Case/When ranking
across ~17k titles and ~50k people: 0.5–1.1 s for every query the Redis cache
has not seen, and while typing almost every prefix is new. This module keeps a
Persian-normalized copy of just the searchable names in each web worker, so a
keystroke is answered by a scan in memory (a few ms) and only the handful of
winning cards touch the database — and those are memoized too.

The index follows the catalog cache version (bumped by every Movie/Series/Actor
save) and is rebuilt in a background thread, so a request never waits on a
rebuild except the very first one after a worker starts.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

from django.conf import settings
from django.db import close_old_connections, connections

from .cache import _running_tests, catalog_cache_version
from .search import normalize_search_text

logger = logging.getLogger(__name__)

# Tiers mirror title_rank_annotation so both endpoints order results alike.
EXACT, PREFIX, WORD_PREFIX, CONTAINS, TOKENS = 100, 88, 76, 62, 54
# Weight subtracted per name slot: title, original_title, slug.
_SLOT_PENALTY = (0, 2, 8)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, '').strip()
    return int(raw) if raw.isdigit() else default


CHECK_INTERVAL = _env_int('SEARCH_SUGGEST_CHECK_SECONDS', 15)
MAX_AGE = _env_int('SEARCH_SUGGEST_MAX_AGE_SECONDS', 600)
CARD_CACHE_SIZE = _env_int('SEARCH_SUGGEST_CARD_CACHE', 4000)


@dataclass(slots=True)
class _Doc:
    id: int
    names: tuple  # ((normalized, compact, words), ...) in slot order
    hay: str  # ' ' + every normalized name and compact form, for C-speed rejects
    year: int | None
    rank: tuple  # tie-breaker, higher first


def _name_parts(value: str):
    normalized = normalize_search_text(value)
    if not normalized:
        return None
    return normalized, normalized.replace(' ', ''), tuple(normalized.split())


def _make_doc(pk, names, year, rank) -> _Doc | None:
    parts = []
    hay = []
    for value in names:
        part = _name_parts(value or '')
        parts.append(part)
        if part:
            hay.append(part[0])
            hay.append(part[1])
    if not hay:
        return None
    return _Doc(id=pk, names=tuple(parts), hay=' ' + ' '.join(hay), year=year, rank=rank)


class SuggestIndex:
    def __init__(self, movies, series, actors, version):
        self.movies = movies
        self.series = series
        self.actors = actors
        self.version = version
        self.built_at = time.monotonic()
        self.checked_at = self.built_at

    @classmethod
    def build(cls) -> 'SuggestIndex':
        from .models import Actor, Movie, Series

        version = catalog_cache_version()
        started = time.monotonic()

        def titles(model, year_field):
            docs = []
            rows = (
                model.objects.filter(is_published=True)
                .values_list('id', 'title', 'original_title', 'slug', year_field, 'view_count', 'popularity')
                .iterator(chunk_size=4000)
            )
            for pk, title, original, slug, year, views, popularity in rows:
                doc = _make_doc(
                    pk,
                    (title, original, (slug or '').replace('-', ' ')),
                    year,
                    (views or 0, popularity or 0.0),
                )
                if doc:
                    docs.append(doc)
            return docs

        movies = titles(Movie, 'release_year')
        series = titles(Series, 'start_year')
        actors = []
        for pk, name, original, popularity in (
            Actor.objects.values_list('id', 'name', 'original_name', 'popularity').iterator(chunk_size=8000)
        ):
            doc = _make_doc(pk, (name, original), None, (popularity or 0.0,))
            if doc:
                actors.append(doc)
        logger.info(
            'search suggest index built: movies=%s series=%s actors=%s in %.2fs (v%s)',
            len(movies), len(series), len(actors), time.monotonic() - started, version,
        )
        return cls(movies, series, actors, version)


def _score(doc: _Doc, query: str, compact: str, tokens: tuple, allow_contains: bool) -> int:
    best = 0
    for slot, part in enumerate(doc.names):
        if not part:
            continue
        normalized, name_compact, words = part
        if normalized == query or name_compact == compact:
            score = EXACT
        elif normalized.startswith(query) or name_compact.startswith(compact):
            score = PREFIX
        elif all(any(word.startswith(token) for word in words) for token in tokens):
            score = WORD_PREFIX
        elif allow_contains and (query in normalized or compact in name_compact):
            score = CONTAINS
        elif allow_contains and len(tokens) > 1 and all(token in normalized for token in tokens):
            score = TOKENS
        else:
            continue
        score -= _SLOT_PENALTY[slot] if slot < len(_SLOT_PENALTY) else 10
        if score > best:
            best = score
    return best


def rank(docs, text: str, *, year: int | None, limit: int) -> tuple[list[int], bool]:
    """Return (ids, has_exact) for ``docs`` matching ``text`` (already year-free).

    One-character queries only match at the start of a word: "a" finding every
    title that merely contains an "a" is noise, not a suggestion.
    """
    query = normalize_search_text(text)
    if year is not None:
        docs = [doc for doc in docs if doc.year == year]
    if not query:
        if year is None:
            return [], False
        ordered = sorted(docs, key=lambda doc: doc.rank, reverse=True)
        return [doc.id for doc in ordered[:limit]], False

    compact = query.replace(' ', '')
    tokens = tuple(query.split())
    allow_contains = len(compact) >= 2
    # Cheap C-level rejects before the per-name scoring loop.
    needle = tokens[0] if allow_contains else ' ' + tokens[0]
    alt = compact if allow_contains else ' ' + compact
    hits = []
    for doc in docs:
        hay = doc.hay
        if needle not in hay and alt not in hay:
            continue
        score = _score(doc, query, compact, tokens, allow_contains)
        if score:
            hits.append((score, doc.rank, doc.id))
    hits.sort(reverse=True)
    top = hits[:limit]
    return [item[2] for item in top], bool(top) and top[0][0] > PREFIX


_index: SuggestIndex | None = None
_build_lock = threading.Lock()
_refreshing = False


def _sync_mode() -> bool:
    return settings.DEBUG or _running_tests()


def _refresh_in_background() -> None:
    global _index, _refreshing
    try:
        close_old_connections()
        _index = SuggestIndex.build()
        clear_card_cache()
    except Exception:
        logger.exception('search suggest index refresh failed')
    finally:
        _refreshing = False
        # This thread owns its own connection; hand it back (or to the pool).
        connections.close_all()


def get_index() -> SuggestIndex:
    """The current index; stale-while-rebuilding once a worker has one."""
    global _index, _refreshing
    if _sync_mode():
        _index = SuggestIndex.build()
        clear_card_cache()
        return _index
    index = _index
    if index is None:
        with _build_lock:
            if _index is None:
                _index = SuggestIndex.build()
            return _index
    now = time.monotonic()
    if now - index.checked_at >= CHECK_INTERVAL:
        index.checked_at = now
        stale = now - index.built_at >= MAX_AGE
        try:
            stale = stale or catalog_cache_version() != index.version
        except Exception:
            pass
        if stale and not _refreshing:
            with _build_lock:
                if not _refreshing:
                    _refreshing = True
                    threading.Thread(
                        target=_refresh_in_background, name='search-suggest-index', daemon=True,
                    ).start()
    return index


# --- serialized cards --------------------------------------------------------
_cards: OrderedDict = OrderedDict()
_cards_lock = threading.Lock()


def clear_card_cache() -> None:
    with _cards_lock:
        _cards.clear()


def serialize_cards(model, serializer_class, ids, *, prefetch=()) -> list:
    """Serialize ``ids`` in order, reusing cards this worker already built.

    Unpublished (or deleted) rows drop out because the DB fetch re-checks them,
    so a stale index never leaks a title that was just taken down.
    """
    if not ids:
        return []
    label = model._meta.label_lower
    found = {}
    with _cards_lock:
        for pk in ids:
            card = _cards.get((label, pk))
            if card is not None:
                _cards.move_to_end((label, pk))
                found[pk] = card
    missing = [pk for pk in ids if pk not in found]
    if missing:
        queryset = model.objects.filter(id__in=missing)
        if hasattr(model, 'is_published'):
            queryset = queryset.filter(is_published=True)
        if prefetch:
            queryset = queryset.prefetch_related(*prefetch)
        objs = list(queryset)
        fresh = dict(zip((obj.id for obj in objs), serializer_class(objs, many=True).data))
        found.update(fresh)
        if not _sync_mode():
            with _cards_lock:
                for pk, card in fresh.items():
                    _cards[(label, pk)] = card
                while len(_cards) > CARD_CACHE_SIZE:
                    _cards.popitem(last=False)
    return [found[pk] for pk in ids if pk in found]
