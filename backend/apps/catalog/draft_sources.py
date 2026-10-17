"""Hunt download sources for catalog drafts that have none at all.

This is the archive's real backlog. Measured on production, 2026-09-24:

* 5,157 of 5,174 unpublished **movies** and 1,849 of 1,859 unpublished **series**
  carry an empty ``download_links`` — they were created by the metadata crawlers
  (TMDB/IMDb charts) but no provider page was ever matched to them;
* only 606 movies + 3 series of those were enrolled in ``PlaybackSourceGap``,
  leaving **6,397 titles that nothing in the system ever looked at again**.

Two things hid them:

1. :func:`apps.catalog.playback_sources.scan` iterates ``is_published=True`` only,
   so a draft is never examined;
2. :func:`apps.catalog.playback_sources.diagnose` calls a title unplayable only
   when it has at least one *unsafe* source and no safe one. A title with **zero**
   sources therefore reports ``unplayable=False`` — "nothing is broken" — which is
   true for the player and useless for the archive.

So this module owns the other half of the problem: a title that has no source at
all. It records the same ``PlaybackSourceGap`` row with ``reason='no_source'``,
re-crawls every configured provider for it, and hands the title over:

* sources landed and at least one is browser-safe → the gap is resolved;
* sources landed but all are MKV/HEVC → the row is rewritten with the real
  container/codec reason, and the existing playback-source pipeline takes it from
  there;
* nothing upstream → ``unavailable``, retried after ``retry_hours``.

The two passes keep **separate budgets on purpose**: a browser-unplayable gap is a
viewer staring at "پخش ویدیو ممکن نشد" right now, and must never queue behind
6,397 back-archive drafts. :func:`apps.catalog.playback_sources.remediate_open_gaps`
excludes ``no_source`` rows for exactly that reason.

Used by:
* ``apps.catalog.management.commands.hunt_draft_sources`` — the CLI pass, run
  every round by the permanent ``catalog-crawler`` container
  (``backend/scripts/run_myf2m_catalog_loop.py``, the ``drafts`` lane). That is
  where this actually runs in production;
* ``apps.catalog.tasks.hunt_draft_sources_task`` — the same pass as a Celery
  task, kept for a one-off manual run. It is **not** on the beat schedule: the
  only queue that fits it runs at concurrency 1 and was ~900 messages deep, so a
  tick placed there expires unrun.
"""

from __future__ import annotations

import logging
import time

from apps.catalog.playback_sources import (
    DRAFT_GAP_REASON,
    _content_type_of,
    _recrawl_all_providers,
    diagnose,
    has_any_source,
    resolve_source_gap,
    upsert_source_gap,
)

logger = logging.getLogger(__name__)

#: ``PlaybackSourceGap.reason`` for a title with no source whatsoever. Declared in
#: playback_sources so that module can exclude these rows without importing this one.
GAP_REASON = DRAFT_GAP_REASON

#: A provider lookup matches on the English title; without one it cannot even try.
_MIN_TITLE_LEN = 2

#: Provider codes meaning "searched, this provider does not carry the title". The
#: crawl only returns these after its own title/IMDb lookup came up empty, so the
#: next round would get the same answer — the row rests for ``retry_hours``.
_NOT_LISTED_CODES = frozenset({
    'page_not_found',
    'myf2m_page_required', 'myf2m_links_empty', 'myf2m_identity_mismatch',
    'dornatv_page_required', 'dornatv_links_empty', 'dornatv_identity_mismatch',
    'kargadan_page_missing', 'kargadan_links_empty', 'kargadan_identity_mismatch',
    'kargadan_imdb_required', 'empty_download',
})

#: A provider we cannot ask yet (kargadan without its operator cookie). Neither a
#: miss nor a failure: it must not keep a title spinning in the retry queue.
_UNASKABLE_CODES = frozenset({'kargadan_session_missing', 'kargadan_login_required'})


def _providers_answered(codes: dict) -> bool:
    """True when every askable provider gave a real answer (links or "not listed").

    Anything else — an exception, a timeout, an unknown code — is a failure and
    keeps the title queued, so a provider outage never parks a title for a week.
    """
    answered = False
    for status, detail in codes.values():
        if status == 'ok' or (status == 'err' and detail in _NOT_LISTED_CODES):
            answered = True
        elif not (status == 'err' and detail in _UNASKABLE_CODES):
            return False
    return answered


def _sourceless_diag() -> dict:
    """The synthetic diagnosis a no-source row carries."""
    return {'reason': GAP_REASON, 'containers': [], 'codecs': [], 'unsafe': 0}


def iter_sourceless_drafts(order: str = 'hot', *, movies: bool = True,
                           series: bool = True, limit: int = 0):
    """Yield unpublished Movie/Series rows that carry no playable source.

    ``hot`` (default) fills this week's trending titles first, then the newest
    releases (:func:`apps.catalog.hot_titles.hot_order`); ``popularity`` is the
    TMDB number stored at import; ``random`` gives the long tail a fair rotation
    across passes and ``stale`` walks the least-recently-touched rows.
    """
    from django.db.models import Q

    from apps.catalog.models import Movie, Series

    empty = Q(download_links=[]) | Q(download_links__isnull=True)

    def _ordered(qs):
        if order == 'random':
            return qs.order_by('?')
        if order == 'stale':
            return qs.order_by('updated_at', 'id')
        if order == 'hot':
            from apps.catalog.hot_titles import hot_order

            return hot_order(qs)
        return qs.order_by('-popularity', '-updated_at', '-id')

    yielded = 0
    plans = []
    if movies:
        plans.append((Movie, ('id', 'slug', 'title', 'original_title', 'download_links',
                              'video_url', 'popularity', 'updated_at', 'tmdb_id', 'release_date')))
    if series:
        plans.append((Series, ('id', 'slug', 'title', 'original_title', 'download_links',
                               'popularity', 'updated_at', 'tmdb_id', 'start_year', 'end_year')))
    for model, fields in plans:
        qs = _ordered(model.objects.filter(is_published=False).filter(empty).only(*fields))
        for obj in qs.iterator(chunk_size=100):
            if limit and yielded >= limit:
                return
            # `download_links` can be an empty-ish list of junk dicts, and a Series
            # may still stream from its Episodes — only the real predicate decides.
            if has_any_source(obj):
                continue
            if len((getattr(obj, 'original_title', '') or '').strip()) < _MIN_TITLE_LEN:
                # Nothing to match against a provider listing; a metadata pass has
                # to fill the English title before a source hunt can mean anything.
                continue
            yielded += 1
            yield obj


def scan(*, order: str = 'hot', limit: int = 0, movies: bool = True,
         series: bool = True, record: bool = True) -> dict:
    """Enroll sourceless drafts in the gap table so something owns them.

    Enrolment is idempotent, and deliberately so: this runs on every round of the
    permanent catalog crawler, over a head of drafts that barely changes. Writing
    every row again each round would bump ``updated_at`` (the rotation key
    :func:`hunt_open_gaps` orders by) and inflate ``report_count``, which counts
    *viewer* reports — the scan would quietly rewrite the queue it feeds.

    A row is still rewritten when it sits RESOLVED, which recovers the titles the
    playback pipeline had written off: ``remediate_open_gaps`` retires the gap of
    any unpublished title as ``title_gone``, so a draft enrolled while it was
    published sits RESOLVED forever with no sources. :func:`upsert_source_gap`
    re-opens a resolved row, which is exactly the behaviour those need. A row
    left behind by the playback pipeline under a *different* reason is rewritten
    too — a title with no source at all is a ``no_source`` gap, whatever the
    container/codec verdict recorded before its links went away.
    """
    from apps.catalog.models import PlaybackSourceGap

    stats = {'scanned': 0, 'recorded': 0, 'reopened': 0, 'skipped': 0}
    for obj in iter_sourceless_drafts(order, movies=movies, series=series, limit=limit):
        stats['scanned'] += 1
        if not record:
            continue
        existing = PlaybackSourceGap.objects.filter(
            content_type=_content_type_of(obj), object_id=obj.pk, episode_id=0,
        ).values_list('status', 'reason').first()
        if existing and existing[0] != PlaybackSourceGap.Status.RESOLVED and existing[1] == GAP_REASON:
            stats['skipped'] += 1
            continue
        upsert_source_gap(obj, _sourceless_diag(), last_result='enrolled')
        stats['reopened' if existing else 'recorded'] += 1
    return stats


def hunt(obj) -> dict:
    """Crawl every provider for one sourceless title and record what landed.

    Outcome is ``sourced`` (the title now has at least one link), ``unplayable``
    (links landed but none a browser can play — handed to the playback-source
    pipeline), ``unavailable`` (providers answered, nothing to import) or
    ``provider_error`` (a provider failed and none answered; retry later). A
    provider that searched and does not list the title counts as an answer.
    """
    from apps.catalog.models import PlaybackSourceGap

    codes = _recrawl_all_providers(obj)
    answered = any(status == 'ok' for status, _ in codes.values()) or _providers_answered(codes)

    if not has_any_source(obj):
        upsert_source_gap(
            obj, _sourceless_diag(),
            status=(PlaybackSourceGap.Status.UNAVAILABLE if answered
                    else PlaybackSourceGap.Status.QUEUED),
            last_result=('no_provider_listing' if answered else 'provider_error'),
        )
        return {'outcome': 'unavailable' if answered else 'provider_error', 'codes': codes}

    diag = diagnose(obj)
    if diag['unplayable']:
        # Sources exist now but no browser can play them. Rewrite the row with the
        # real container/codec reason and let `remediate_open_gaps` hunt a mirror —
        # that pipeline already knows how to do exactly this.
        upsert_source_gap(obj, diag, status=PlaybackSourceGap.Status.OPEN,
                          last_result='sourced_unplayable')
        outcome = 'unplayable'
    else:
        resolve_source_gap(obj, last_result='sourced')
        outcome = 'sourced'
    return {'outcome': outcome, 'codes': codes, 'published': maybe_publish(obj)}


#: ``last_result`` stamped on the hunter's gap row once its draft went live. The
#: publish pass skips these, so an admin who takes the title down afterwards is
#: never overruled by the next round.
PUBLISHED_RESULT = 'auto_published'

#: How long a draft that failed the gate rests before the pass asks again. Its
#: blockers are metadata the completion lanes fill over hours, not minutes.
BLOCKED_REST_SECONDS = 6 * 3600


def _held_by_admin(obj) -> bool:
    """An admin put this title in draft or archived on purpose — never overrule that."""
    from django.db.models import Q

    from apps.catalog.models import Movie, MovieSyncAudit

    if isinstance(obj, Movie) and obj.publication_status == Movie.PublicationStatus.ARCHIVED:
        return True
    kind = _content_type_of(obj)
    return MovieSyncAudit.objects.filter(
        details__kind=kind, details__object_id=obj.pk,
    ).filter(
        Q(action=MovieSyncAudit.Action.ARCHIVE) | Q(details__state__in=['draft', 'archived']),
    ).exists()


def maybe_publish(obj) -> bool:
    """Publish a draft the hunter sourced, but only through the real quality gate.

    Governed by ``CATALOG_AUTO_PUBLISH``. The row's own ``auto_publish`` flag is
    *not* asked: that flag is set only by the TMDB date-window sync, so the
    thousands of drafts the chart crawlers made — exactly the ones this module
    exists to fill — could never go live, and every source the hunter found
    stayed invisible (measured 2026-09-26: 24 sourced, 0 published in 26 h).

    What is asked instead is everything that makes a title safe to show:
    ``auto_publish_blockers`` — Persian + English title, description, poster,
    backdrop, genres, cast, a real IMDb score and a live media probe — plus
    three ownership rules: only crawler-made rows (``metadata_source='tmdb'``;
    a hand-made draft belongs to a human), never a title an admin archived or
    put back to draft, and never a movie scheduled for later.
    """
    from django.conf import settings
    from django.utils import timezone

    from apps.catalog.media_verification import ensure_verified, verification_enabled
    from apps.catalog.models import Movie, PlaybackSourceGap

    if not getattr(settings, 'CATALOG_AUTO_PUBLISH', False) or obj.is_published:
        return False
    if (getattr(obj, 'metadata_source', '') or '') != 'tmdb':
        return False
    is_movie = isinstance(obj, Movie)
    if is_movie and obj.scheduled_publish_at and obj.scheduled_publish_at > timezone.now():
        return False
    if _held_by_admin(obj):
        return False
    if not has_any_source(obj):
        return False
    if verification_enabled():
        # Ask the hosts now (a worker, so seconds of network are fine); the
        # blockers below then read that stored verdict.
        ensure_verified(obj)
    blockers = obj.auto_publish_blockers
    if blockers:
        logger.info('draft_sources.publish_blocked %s=%s slug=%s blockers=%s',
                    _content_type_of(obj), obj.pk, obj.slug, ','.join(blockers))
        return False
    obj.is_published = True
    fields = ['is_published', 'updated_at']
    if is_movie:
        obj.publication_status = Movie.PublicationStatus.PUBLISHED
        fields.append('publication_status')
    obj.save(update_fields=fields)
    PlaybackSourceGap.objects.filter(
        content_type=_content_type_of(obj), object_id=obj.pk, episode_id=0,
    ).update(last_result=PUBLISHED_RESULT)
    logger.info('draft_sources.published %s=%s slug=%s', _content_type_of(obj), obj.pk, obj.slug)
    return True


def publish_sourced_drafts(*, limit: int = 60) -> dict:
    """Give every draft the hunter sourced another go at the publish gate.

    ``hunt`` asks the gate once, the moment links land — and at that moment the
    title usually still lacks a Persian title, cast or a media verdict, which the
    metadata lanes fill later in the round. Without this pass such a title stays
    a draft for good even after it became complete. Blocked titles rest for
    ``BLOCKED_REST_SECONDS`` so one pass is not spent on the same few rows.
    """
    from django.db.models import Q

    from apps.catalog.models import Movie, PlaybackSourceGap, Series
    from apps.catalog.refresh_rotation import recently_failed, remember_failure

    gaps = (
        PlaybackSourceGap.objects.filter(episode_id=0)
        .filter(Q(reason=GAP_REASON, status=PlaybackSourceGap.Status.RESOLVED)
                | Q(last_result__startswith='sourced'))
        .exclude(last_result__in=[PUBLISHED_RESULT, 'title_gone'])
        .order_by('-updated_at', '-id')
        .values_list('content_type', 'object_id')
    )
    wanted = {'movie': [], 'series': []}
    for content_type, object_id in gaps.iterator(chunk_size=500):
        key = 'movie' if content_type == PlaybackSourceGap.ContentType.MOVIE else 'series'
        wanted[key].append(int(object_id))

    stats = {'candidates': 0, 'published': 0, 'blocked': 0, 'resting': 0}
    budget = max(1, int(limit or 1))
    for kind, model in (('movie', Movie), ('series', Series)):
        ids = wanted[kind]
        resting = recently_failed(f'publish-{kind}', ids)
        stats['resting'] += len(resting)
        live_ids = [pk for pk in ids if pk not in resting]
        drafts = model.objects.filter(pk__in=live_ids, is_published=False, metadata_source='tmdb')
        by_pk = {obj.pk: obj for obj in drafts}
        for pk in live_ids:
            if budget <= 0:
                break
            obj = by_pk.get(pk)
            if obj is None:
                continue
            budget -= 1
            stats['candidates'] += 1
            try:
                published = maybe_publish(obj)
            except Exception:  # noqa: BLE001 - one bad row must not stop the pass
                logger.exception('draft_sources.publish_failed %s=%s', kind, pk)
                published = False
            if published:
                stats['published'] += 1
            else:
                stats['blocked'] += 1
                remember_failure(f'publish-{kind}', pk, ttl=BLOCKED_REST_SECONDS)
    if stats['published']:
        from apps.catalog.cache import bump_catalog_cache_version

        bump_catalog_cache_version()
    return stats


def _hot_gap_rows(eligible, limit: int) -> list:
    """Eligible gap rows whose draft is hot or recently released, hottest first."""
    from apps.catalog.hot_titles import MISS_RANK, hot_priority_pks
    from apps.catalog.models import Movie, PlaybackSourceGap, Series

    ranked = []
    # Plain values: an Enum member hashes by its name, so it would never match
    # the ``content_type`` string loaded from the row in the lookup below.
    for content_type, model in ((PlaybackSourceGap.ContentType.MOVIE.value, Movie),
                                (PlaybackSourceGap.ContentType.SERIES.value, Series)):
        ids = eligible.filter(content_type=content_type).values('object_id')
        for position, (pk, rank) in enumerate(hot_priority_pks(model.objects.filter(pk__in=ids), limit)):
            # Chart titles by rank across both kinds, then recent releases in turn.
            ranked.append(((rank, position) if rank < MISS_RANK else (MISS_RANK, position), content_type, pk))
    ranked.sort(key=lambda item: item[0])
    by_key = {
        (gap.content_type, gap.object_id): gap
        for gap in eligible.filter(object_id__in=[pk for _, _, pk in ranked])
    }
    rows = [by_key[(content_type, pk)] for _, content_type, pk in ranked if (content_type, pk) in by_key]
    return rows[:limit]


def hunt_open_gaps(*, limit: int = 20, retry_hours: float = 168.0, delay: float = 0.0,
                   dry_run: bool = False, on_progress=None, order: str = 'hot') -> dict:
    """Work the ``no_source`` queue: oldest untouched rows first.

    With ``order='hot'`` (default) the slice starts with drafts that are on this
    week's hot chart or came out recently, hottest first; the rest of the slice
    keeps the fair oldest-first rotation, so the tail is still reached.

    ``unavailable`` rows are retried only after ``retry_hours`` (a week by
    default) — a title missing from every provider today is usually missing
    tomorrow too, and re-asking costs the shared provider rate budget that the
    live crawlers need.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.catalog.models import Movie, PlaybackSourceGap, Series
    from apps.catalog.playback_sources import models_q_open_or_retryable

    cutoff = timezone.now() - timedelta(hours=max(0.0, float(retry_hours)))
    limit = max(1, int(limit or 1))
    eligible = (
        PlaybackSourceGap.objects.filter(episode_id=0, reason=GAP_REASON)
        .exclude(status=PlaybackSourceGap.Status.RESOLVED)
        .filter(models_q_open_or_retryable(cutoff))
    )
    rows = _hot_gap_rows(eligible, limit) if order == 'hot' else []
    if len(rows) < limit:
        rows += list(
            eligible.exclude(pk__in=[gap.pk for gap in rows])
            .order_by('status', 'updated_at', 'id')[: limit - len(rows)]
        )

    stats = {'candidates': len(rows), 'sourced': 0, 'unplayable': 0, 'unavailable': 0,
             'provider_error': 0, 'published': 0, 'skipped': 0, 'vanished': 0}
    delay = max(0.0, float(delay or 0))

    for index, gap in enumerate(rows, 1):
        model = Movie if gap.content_type == PlaybackSourceGap.ContentType.MOVIE else Series
        # Deliberately no `is_published` filter: every row in this queue is a draft.
        obj = model.objects.filter(pk=gap.object_id).first()
        if obj is None:
            gap.status = PlaybackSourceGap.Status.RESOLVED
            gap.last_result = 'title_gone'
            gap.resolved_at = timezone.now()
            gap.save(update_fields=['status', 'last_result', 'resolved_at', 'updated_at'])
            stats['vanished'] += 1
            outcome = 'vanished'
        elif has_any_source(obj):
            # Another pass (or an admin) gave it sources already.
            resolve_source_gap(obj, last_result='sourced_elsewhere')
            stats['skipped'] += 1
            outcome = 'already_sourced'
        elif dry_run:
            stats['skipped'] += 1
            outcome = 'dry_run'
        else:
            result = hunt(obj)
            outcome = result['outcome']
            stats[outcome if outcome in stats else 'provider_error'] += 1
            stats['published'] += int(bool(result.get('published')))

        if on_progress is not None:
            on_progress(index, len(rows), outcome, gap)
        if delay:
            time.sleep(delay)

    stats['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    if not dry_run and stats['published']:
        from apps.catalog.cache import bump_catalog_cache_version

        bump_catalog_cache_version()
    return stats
