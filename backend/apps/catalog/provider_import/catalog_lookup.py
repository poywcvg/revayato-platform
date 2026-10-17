"""Film2Media / myf2m catalog lookup / discover-only orchestration."""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import (
    Movie,
    ProviderCredential,
    ProviderImportItem,
    ProviderImportJob,
    ProviderImportLog,
    ProviderSource,
    Series,
)

from .exceptions import (
    InteractiveVerificationRequired,
    ProviderContractUnknown,
    ProviderImportError,
    ProviderNotConfigured,
    ProviderRateLimited,
)
from .matching import score_provider_candidate_against_movie, score_provider_candidate_against_series
from .registry import get_connector
from .sanitizers import sanitize_payload


def _min_auto_match_score() -> float:
    return float(getattr(settings, 'CATALOG_PROVIDER_MIN_AUTO_MATCH_SCORE', 0.95))


def _auto_crawl_on_match_enabled() -> bool:
    return bool(getattr(settings, 'CATALOG_PROVIDER_AUTO_CRAWL_ON_MATCH', True))


def _min_auto_crawl_score() -> float:
    return float(getattr(settings, 'CATALOG_PROVIDER_MIN_AUTO_CRAWL_SCORE', 0.6))


def append_log(job, level, message, context=None, *, event_code=''):
    ProviderImportLog.objects.create(
        job=job,
        level=level,
        event_code=(event_code or '')[:64],
        message=str(sanitize_payload(message))[:500],
        context=sanitize_payload(context or {}),
    )


def schedule_provider_lookup_for_catalog_object(
    *,
    content_type: str,
    object_id: int,
    triggered_by=None,
    force: bool = False,
    trigger: str = ProviderImportJob.Trigger.MANUAL,
):
    """Enqueue discover-only after the surrounding DB transaction commits."""
    if content_type not in {'movie', 'series'}:
        raise ProviderImportError('content_type must be movie or series.')

    def _enqueue():
        from .tasks import run_provider_import_job_task

        job = create_catalog_discover_job(
            content_type=content_type,
            object_id=object_id,
            user=triggered_by,
            force=force,
            trigger=trigger,
        )
        if job is None or getattr(job, 'reused', False):
            return job
        async_result = run_provider_import_job_task.delay(str(job.id))
        ProviderImportJob.objects.filter(pk=job.pk).update(task_id=async_result.id)
        return job

    transaction.on_commit(_enqueue)
    return True


#: Job states the ``uniq_active_provider_*_job`` constraints treat as active.
ACTIVE_JOB_STATUSES = [
    ProviderImportJob.Status.QUEUED,
    ProviderImportJob.Status.VALIDATING,
    ProviderImportJob.Status.SEARCHING,
    ProviderImportJob.Status.AWAITING_REVIEW,
    ProviderImportJob.Status.RUNNING,
    ProviderImportJob.Status.TRANSFERRING,
    ProviderImportJob.Status.CANCEL_REQUESTED,
]
#: Active states in which a worker is (or is about to be) doing the work.
WORKING_JOB_STATUSES = {
    ProviderImportJob.Status.QUEUED,
    ProviderImportJob.Status.VALIDATING,
    ProviderImportJob.Status.SEARCHING,
    ProviderImportJob.Status.RUNNING,
    ProviderImportJob.Status.TRANSFERRING,
}
#: A "working" job untouched this long lost its worker (restart, expired message).
STALE_JOB_AFTER_SECONDS = 45 * 60


def _retire_job(job, reason: str):
    """Close an active job so a new one may take its slot. A status change, never a delete."""
    ProviderImportJob.objects.filter(pk=job.pk, status__in=ACTIVE_JOB_STATUSES).update(
        status=ProviderImportJob.Status.CANCELLED,
        error_message=reason[:500],
        finished_at=timezone.now(),
        updated_at=timezone.now(),
    )
    append_log(job, 'info', reason, event_code='superseded')


def create_catalog_discover_job(
    *,
    content_type: str,
    object_id: int,
    user=None,
    force: bool = False,
    trigger: str = ProviderImportJob.Trigger.MANUAL,
    mode: str = ProviderImportJob.Mode.DISCOVER_ONLY,
):
    """The discover job for one catalog row — reusing, or replacing, an active one.

    The database allows one active job per provider+title+mode. ``force`` used
    to create a second one anyway, which is how a re-search on a series whose
    last job sat in «awaiting review» died with a unique-constraint error. Now:

    * a job a worker is actually running is returned as is (``job.reused``) —
      two crawls of the same title only race each other;
    * without ``force`` the existing job is returned, as before;
    * with ``force`` an idle one (awaiting review, or a worker that vanished)
      is closed as superseded and a fresh job takes its place.

    Callers must not queue a job that comes back with ``reused`` set.
    """
    from django.db import IntegrityError

    provider = ensure_myf2m_provider()
    movie = series = None
    if content_type == 'movie':
        movie = Movie.objects.get(pk=object_id)
        target = {'target_movie': movie}
    else:
        series = Series.objects.get(pk=object_id)
        target = {'target_series': series}

    stale_before = timezone.now() - timedelta(seconds=STALE_JOB_AFTER_SECONDS)
    actives = list(
        ProviderImportJob.objects.filter(provider=provider, status__in=ACTIVE_JOB_STATUSES, **target)
        .order_by('-updated_at')
    )
    for job in actives:
        if job.status in WORKING_JOB_STATUSES and job.updated_at >= stale_before:
            job.reused = True
            return job
    if actives and not force:
        return actives[0]
    for job in actives:
        _retire_job(job, 'Superseded by a new re-search requested from the admin panel.')

    try:
        with transaction.atomic():
            job = ProviderImportJob.objects.create(
                provider=provider,
                started_by=user,
                trigger=trigger,
                target_movie=movie,
                target_series=series,
                content_type=ProviderImportJob.ContentType.MOVIE if movie else ProviderImportJob.ContentType.SERIES,
                mode=mode,
                params=sanitize_payload({'force': force, 'dry_run': True}),
                status=ProviderImportJob.Status.QUEUED,
            )
    except IntegrityError:
        # Another request created the active job between our read and write.
        job = ProviderImportJob.objects.filter(
            provider=provider, mode=mode, status__in=ACTIVE_JOB_STATUSES, **target,
        ).order_by('-updated_at').first()
        if job is None:
            raise
        job.reused = True
    return job


def run_catalog_discover_job(job_id) -> dict:
    job = ProviderImportJob.objects.select_related(
        'provider', 'target_movie', 'target_series',
    ).get(pk=job_id)
    if job.status in {
        ProviderImportJob.Status.COMPLETED,
        ProviderImportJob.Status.FAILED,
        ProviderImportJob.Status.CANCELLED,
        ProviderImportJob.Status.BLOCKED,
    }:
        return {'status': job.status}

    job.status = ProviderImportJob.Status.VALIDATING
    job.started_at = job.started_at or timezone.now()
    job.save(update_fields=['status', 'started_at', 'updated_at'])
    append_log(job, 'info', 'Validating Film2Media access.', event_code='validate_start')

    connector = None
    try:
        connector = get_connector(job.provider)
        auth = connector.authenticate()
        append_log(job, 'info', auth.message, {'auth_type': auth.auth_type}, event_code='validate_ok')
        cred = job.provider.credential
        cred.status = ProviderCredential.Status.VALID
        cred.last_validated_at = timezone.now()
        cred.last_validation_message = str(auth.message)[:500]
        cred.last_error_code = ''
        cred.save()

        job.status = ProviderImportJob.Status.SEARCHING
        job.save(update_fields=['status', 'updated_at'])

        if job.target_movie_id:
            _discover_for_movie(job, connector, job.target_movie)
        elif job.target_series_id:
            _discover_for_series(job, connector, job.target_series)
        else:
            raise ProviderContractUnknown('Catalog target missing on job.')

        if job.cancel_requested:
            job.status = ProviderImportJob.Status.CANCELLED
            job.finished_at = timezone.now()
            job.save(update_fields=['status', 'finished_at', 'updated_at'])
            append_log(job, 'warning', 'Job cancelled.', event_code='cancelled')
            return {'status': job.status}

        # Close the discover session before opening a fresh crawl session.
        if connector is not None and hasattr(connector, 'close'):
            connector.close()
            connector = None

        crawl_result = None
        if job.target_movie_id:
            crawl_result = _auto_crawl_best_movie_match(job, job.target_movie)

        if crawl_result:
            job.status = ProviderImportJob.Status.COMPLETED
            job.finished_at = timezone.now()
            job.save(update_fields=[
                'status', 'finished_at', 'updated_at', 'total_items', 'matched_items',
                'processed_items', 'skipped_items',
            ])
            append_log(
                job, 'info',
                f'Auto-crawled {crawl_result.get("imported_count", 0)} download link(s).',
                {'page_path': crawl_result.get('page_path'), 'imported_count': crawl_result.get('imported_count')},
                event_code='auto_crawl_ok',
            )
            return {'status': job.status, 'crawl': crawl_result}

        job.status = ProviderImportJob.Status.AWAITING_REVIEW
        job.finished_at = timezone.now()
        job.save(update_fields=[
            'status', 'finished_at', 'updated_at', 'total_items', 'matched_items',
            'processed_items', 'skipped_items',
        ])
        append_log(job, 'info', 'Discovery complete; awaiting review.', event_code='awaiting_review')
        return {'status': job.status}
    except InteractiveVerificationRequired as exc:
        return _block_job(job, str(exc), code=exc.code)
    except (ProviderNotConfigured, ProviderContractUnknown, ProviderImportError) as exc:
        return _fail_job(job, str(exc), code=getattr(exc, 'code', 'provider_import_error'))
    except Exception:
        append_log(job, 'error', 'Unexpected provider lookup failure.', event_code='unexpected_error')
        return _fail_job(job, 'Provider lookup failed unexpectedly.', code='unexpected_error')
    finally:
        if connector is not None and hasattr(connector, 'close'):
            connector.close()


def _discover_for_movie(job, connector, movie: Movie):
    query = {
        'title': movie.title,
        'original_title': movie.original_title,
        'year': movie.release_year,
        'tmdb_id': movie.tmdb_id,
        'imdb_id': movie.imdb_id or '',
    }
    candidates = list(connector.search_movie(query) or [])
    job.total_items = len(candidates)
    job.save(update_fields=['total_items', 'updated_at'])
    append_log(job, 'info', f'Discovered {len(candidates)} movie candidate(s).', event_code='search_ok')

    for candidate in candidates:
        if job.cancel_requested:
            break
        match = score_provider_candidate_against_movie(candidate, movie)
        status = ProviderImportItem.Status.AWAITING_APPROVAL
        if match.score >= _min_auto_match_score() and not match.requires_manual_approval:
            status = ProviderImportItem.Status.MATCHED
            job.matched_items += 1
        elif match.score <= 0:
            status = ProviderImportItem.Status.SKIPPED
            job.skipped_items += 1
        else:
            job.matched_items += 1
        ProviderImportItem.objects.update_or_create(
            job=job,
            provider_item_id=str(candidate.provider_item_id),
            content_type=ProviderImportItem.ContentType.MOVIE,
            defaults={
                'title': candidate.title,
                'original_title': candidate.original_title,
                'year': candidate.year,
                'tmdb_id': candidate.tmdb_id,
                'imdb_id': candidate.imdb_id or '',
                'match_score': match.score,
                'match_reasons': match.reasons,
                'matched_movie': movie,
                'status': status,
                'status_message': match.reason,
                'raw_payload': sanitize_payload(candidate.to_public_dict()),
            },
        )
        job.processed_items += 1
    job.save(update_fields=['matched_items', 'skipped_items', 'processed_items', 'updated_at'])


def _discover_for_series(job, connector, series: Series):
    query = {
        'title': series.title,
        'original_title': series.original_title,
        'year': series.start_year,
        'tmdb_id': series.tmdb_id,
        'imdb_id': series.imdb_id or '',
    }
    candidates = list(connector.search_series(query) or [])
    job.total_items = len(candidates)
    job.save(update_fields=['total_items', 'updated_at'])
    append_log(job, 'info', f'Discovered {len(candidates)} series candidate(s).', event_code='search_ok')

    for candidate in candidates:
        if job.cancel_requested:
            break
        match = score_provider_candidate_against_series(candidate, series)
        status = ProviderImportItem.Status.AWAITING_APPROVAL
        if match.score >= _min_auto_match_score() and not match.requires_manual_approval:
            status = ProviderImportItem.Status.MATCHED
            job.matched_items += 1
        elif match.score <= 0:
            status = ProviderImportItem.Status.SKIPPED
            job.skipped_items += 1
        else:
            job.matched_items += 1
        ProviderImportItem.objects.update_or_create(
            job=job,
            provider_item_id=str(candidate.provider_item_id),
            content_type=ProviderImportItem.ContentType.SERIES,
            defaults={
                'title': candidate.title,
                'original_title': candidate.original_title,
                'year': candidate.year,
                'tmdb_id': candidate.tmdb_id,
                'imdb_id': candidate.imdb_id or '',
                'match_score': match.score,
                'match_reasons': match.reasons,
                'matched_series': series,
                'status': status,
                'status_message': match.reason,
                'raw_payload': sanitize_payload(candidate.to_public_dict()),
            },
        )
        job.processed_items += 1
    job.save(update_fields=['matched_items', 'skipped_items', 'processed_items', 'updated_at'])


def approve_match_candidate(*, job: ProviderImportJob, candidate_id: int, user=None) -> ProviderImportItem:
    item = job.items.get(pk=candidate_id)
    item.selected = True
    item.manually_approved = True
    item.status = ProviderImportItem.Status.APPROVED
    item.status_message = 'Manually approved'
    item.save(update_fields=[
        'selected', 'manually_approved', 'status', 'status_message', 'updated_at',
    ])
    append_log(
        job, 'info', 'Match approved by staff.',
        {'candidate_id': item.id, 'provider_item_id': item.provider_item_id},
        event_code='match_approved',
    )
    if job.target_movie_id and item.content_type == ProviderImportItem.ContentType.MOVIE:
        try:
            crawl_myf2m_downloads_for_movie(
                movie=job.target_movie,
                provider_item_id=item.provider_item_id,
                replace=True,
                user=user,
            )
            append_log(
                job, 'info', 'Download links crawled after manual approval.',
                {'provider_item_id': item.provider_item_id},
                event_code='manual_crawl_ok',
            )
            if job.status == ProviderImportJob.Status.AWAITING_REVIEW:
                job.status = ProviderImportJob.Status.COMPLETED
                job.finished_at = timezone.now()
                job.save(update_fields=['status', 'finished_at', 'updated_at'])
        except ProviderImportError as exc:
            append_log(
                job, 'warning', f'Approved but crawl failed: {exc}',
                event_code=getattr(exc, 'code', 'myf2m_crawl_failed'),
            )
    return item


def _auto_crawl_best_movie_match(job: ProviderImportJob, movie: Movie) -> dict | None:
    """Pick the best discovered candidate and store Film2Media download links."""
    if not _auto_crawl_on_match_enabled():
        return None

    threshold = _min_auto_crawl_score()
    item = (
        job.items.filter(
            content_type=ProviderImportItem.ContentType.MOVIE,
            status__in=[
                ProviderImportItem.Status.MATCHED,
                ProviderImportItem.Status.AWAITING_APPROVAL,
                ProviderImportItem.Status.APPROVED,
            ],
            match_score__gte=threshold,
        )
        .order_by('-match_score', '-manually_approved', '-id')
        .first()
    )
    if item is None:
        append_log(
            job, 'info',
            f'No Film2Media candidate scored ≥ {threshold} for auto-crawl.',
            event_code='auto_crawl_skipped',
        )
        return None

    item.selected = True
    item.status = ProviderImportItem.Status.APPROVED
    if not item.status_message or item.status_message in {'', 'title_year', 'title_only', 'fuzzy_title', 'tmdb_id', 'imdb_id'}:
        item.status_message = f'Auto-approved (score={item.match_score:.2f})'
    item.save(update_fields=['selected', 'status', 'status_message', 'updated_at'])

    try:
        return crawl_myf2m_downloads_for_movie(
            movie=movie,
            provider_item_id=item.provider_item_id,
            replace=True,
            user=job.started_by,
        )
    except InteractiveVerificationRequired as exc:
        append_log(job, 'error', str(exc), event_code=exc.code)
        return None
    except ProviderImportError as exc:
        append_log(
            job, 'warning', f'Auto-crawl failed: {exc}',
            event_code=getattr(exc, 'code', 'myf2m_crawl_failed'),
        )
        return None



def _prefer_streamable_download(links: list[dict]) -> str:
    """Pick the best direct file URL for HTML5 / progressive playback.

    Prefers Persian dub when available, then hardsub (burned-in), then softsub
    (paired with extracted WebVTT), then other encodes.
    """
    if not links:
        return ''
    from apps.catalog.provider_import.media_links import (
        browser_playback_score,
        is_playable_video_link,
    )
    from apps.catalog.subtitle_extract import looks_like_dub_link, looks_like_hardsub_link, looks_like_softsub_link

    ranked = []
    for item in links:
        if not is_playable_video_link(item):
            continue
        url = str(item.get('url') or '').strip()
        quality = str(item.get('quality') or '').lower()
        label = str(item.get('label') or '').lower()
        kind = str(item.get('kind') or '').lower()
        blob = f'{url} {quality} {label} {kind}'.lower()
        # Container/codec compatibility must dominate language and resolution:
        # a 720p MP4 that starts is a better default than a 1080p MKV/HEVC that
        # many mobile, Safari and Firefox clients reject outright.
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
            # HardSub stays visible in the browser player without extraction.
            score += 16
        elif looks_like_softsub_link(item):
            # SoftSub needs extracted WebVTT; still a good default when no dub.
            score += 10
        ranked.append((score, url))
    if not ranked:
        return ''
    ranked.sort(key=lambda row: row[0], reverse=True)
    return ranked[0][1]


def _block_job(job, message, *, code):
    job.status = ProviderImportJob.Status.BLOCKED
    job.error_message = str(sanitize_payload(message))[:500]
    job.sanitized_error_code = code[:64]
    job.finished_at = timezone.now()
    job.save(update_fields=[
        'status', 'error_message', 'sanitized_error_code', 'finished_at', 'updated_at',
    ])
    append_log(job, 'error', job.error_message, event_code=code)
    try:
        cred = job.provider.credential
        cred.status = ProviderCredential.Status.NEEDS_INTERACTIVE
        cred.last_error_code = code[:64]
        cred.last_validation_message = job.error_message
        cred.last_validated_at = timezone.now()
        cred.save()
    except ProviderCredential.DoesNotExist:
        pass
    return {'status': job.status, 'error': job.error_message, 'code': code}


def _fail_job(job, message, *, code):
    job.status = ProviderImportJob.Status.FAILED
    job.error_message = str(sanitize_payload(message))[:500]
    job.sanitized_error_code = code[:64]
    job.finished_at = timezone.now()
    job.save(update_fields=[
        'status', 'error_message', 'sanitized_error_code', 'finished_at', 'updated_at',
    ])
    append_log(job, 'error', job.error_message, event_code=code)
    return {'status': job.status, 'error': job.error_message, 'code': code}


def ensure_myf2m_provider() -> ProviderSource:
    provider, _ = ProviderSource.objects.update_or_create(
        slug='myf2m',
        defaults={
            'name': 'Film2Media (myf2m)',
            'provider_type': ProviderSource.ProviderType.STATIC_LINKS,
            'base_url': getattr(settings, 'MYF2M_BASE_URL', 'https://www.myf2ms.top'),
            'auth_type': ProviderSource.AuthType.NONE,
            'is_active': True,
            'rate_limit_per_minute': getattr(settings, 'MYF2M_RATE_LIMIT_PER_MINUTE', 30),
            'timeout_seconds': getattr(settings, 'MYF2M_TIMEOUT_SECONDS', 30),
            'verify_ssl': getattr(settings, 'MYF2M_VERIFY_SSL', True),
            'config': {
                'supports_movies': True,
                'supports_series': True,
                'public_downloads': True,
            },
        },
    )
    return provider


def _myf2m_movie_targets(connector, movie: Movie) -> list[str]:
    query = {
        'title': movie.title,
        'original_title': movie.original_title,
        'year': movie.release_year,
        'titles': [t for t in (movie.original_title, movie.title) if t],
    }
    return [hit.provider_item_id for hit in (connector.search_movie(query) or []) if hit.provider_item_id]


def _myf2m_series_targets(connector, series: Series) -> list[str]:
    query = {
        'title': series.title,
        'original_title': series.original_title,
        'year': series.start_year,
        'titles': [t for t in (series.original_title, series.title) if t],
    }
    return [hit.provider_item_id for hit in (connector.search_series(query) or []) if hit.provider_item_id]


def _auto_resolve_myf2m_movie_target(connector, movie: Movie) -> str:
    return next(iter(_myf2m_movie_targets(connector, movie)), '')


def _auto_resolve_myf2m_series_target(connector, series: Series) -> str:
    return next(iter(_myf2m_series_targets(connector, series)), '')


logger = logging.getLogger(__name__)


_HEADING_YEAR_RE = re.compile(r'\b(19\d{2}|20\d{2})\b')


def _identity_conflict(crawled: dict, expected_imdb: str, expected_year: int | None = None) -> bool:
    """True when the page says it is a different title than the one we hold.

    Film2Media is found by title + year, which is how two films sharing a name
    (or a remake and its original) end up swapped. Two signals, strongest first:

    * The page's IMDb links. When the page names IMDb titles and ours is not
      among them, it is someone else's page.
    * The page heading (``Masters of the Universe 2026``). Every page carries
      one; the current layout links no IMDb title at all, so for movies this is
      the check that actually runs. A year more than one off is a different
      film (festival vs. release year explains one). Only ever given for movies:
      a series heading may carry a later season's year.

    A page with neither signal proves nothing and is let through to the other
    guards.
    """
    expected = (expected_imdb or '').strip().lower()
    found = {str(value).lower() for value in (crawled.get('imdb_ids') or [])}
    if expected and found:
        return expected not in found
    if expected_year:
        years = _HEADING_YEAR_RE.findall(str(crawled.get('page_heading') or ''))
        if years:
            return abs(int(years[-1]) - int(expected_year)) > 1
    return False


def _crawl_with_healed_path(
    connector,
    *,
    target: str,
    content_type: str,
    resolve,
    explicit: bool,
    expected_imdb: str = '',
    expected_year: int | None = None,
    alternatives=None,
) -> dict:
    """Crawl a provider detail page, re-resolving a permalink that has died.

    A stored ``page_path`` is not permanent. Film2Media has both moved domain and
    rewritten its permalinks (Persian slug → ``/{id}/{latin-slug}/``), and a dead
    permalink 301s to ``/profile/`` instead of returning 404 — so the crawl fails
    with ``myf2m_page_required`` forever. Measured on production, one refresh
    round failed 200 of 200 titles that way, which means published films kept
    pointing at links nothing could ever renew.

    Re-resolving by search once turns that permanent failure into a self-heal:
    the fresh page path comes back with the imported links and replaces the dead
    one. Only attempted when the caller supplied the path (a search-resolved
    target that fails has nothing better to fall back to).

    With ``expected_imdb``, a page that belongs to a different IMDb title is
    refused, and the remaining search results (``alternatives``) are tried in
    order before giving up — the right page is usually the second hit, not
    missing.
    """
    try:
        crawled = connector.crawl_download_links(target, content_type=content_type)
    except ProviderImportError as exc:
        if not explicit or getattr(exc, 'code', '') != 'myf2m_page_required':
            raise
        healed = (resolve() or '').strip()
        if not healed or healed == target.strip():
            raise
        logger.info('myf2m.page_path_healed type=%s from=%s to=%s', content_type, target, healed)
        target = healed
        crawled = connector.crawl_download_links(healed, content_type=content_type)

    if not _identity_conflict(crawled, expected_imdb, expected_year):
        return crawled
    tried = {target.strip(), str(crawled.get('page_path') or '').strip()}
    logger.warning(
        'myf2m.identity_mismatch type=%s page=%s page_imdb=%s heading=%r expected=%s year=%s',
        content_type, target, ','.join(crawled.get('imdb_ids') or []),
        crawled.get('page_heading') or '', expected_imdb, expected_year or '',
    )
    for candidate in (alternatives() if alternatives else []) or []:
        candidate = (candidate or '').strip()
        if not candidate or candidate in tried:
            continue
        tried.add(candidate)
        try:
            other = connector.crawl_download_links(candidate, content_type=content_type)
        except ProviderImportError:
            continue
        if not _identity_conflict(other, expected_imdb, expected_year):
            logger.info('myf2m.identity_resolved type=%s from=%s to=%s', content_type, target, candidate)
            return other
    raise ProviderImportError(
        f'Film2Media page {target} belongs to a different title than {expected_imdb or expected_year}.',
        code='myf2m_identity_mismatch',
    )


def crawl_myf2m_downloads_for_movie(
    *,
    movie: Movie,
    page_url: str = '',
    provider_item_id: str = '',
    replace: bool = True,
    user=None,
    queue_softsub_extract: bool = True,
) -> dict:
    """Crawl a myf2m movie detail page and store public download links."""
    from config.public_urls import normalize_download_links

    ensure_myf2m_provider()
    target = (page_url or provider_item_id or '').strip()
    connector = get_connector('myf2m')
    try:
        if not target:
            target = _auto_resolve_myf2m_movie_target(connector, movie)
        if not target:
            raise ProviderImportError(
                'Provide a myf2m page URL or ensure the title matches a Film2Media listing.',
                code='myf2m_page_required',
            )
        crawled = _crawl_with_healed_path(
            connector,
            target=target,
            content_type='movie',
            resolve=lambda: _auto_resolve_myf2m_movie_target(connector, movie),
            explicit=bool((page_url or provider_item_id or '').strip()),
            expected_imdb=movie.imdb_id or '',
            expected_year=movie.release_year or (movie.release_date.year if movie.release_date else None),
            alternatives=lambda: _myf2m_movie_targets(connector, movie),
        )
    except ProviderImportError:
        raise
    except Exception as exc:
        raise ProviderImportError(f'myf2m crawl failed: {exc}', code='myf2m_crawl_failed') from exc
    finally:
        close = getattr(connector, 'close', None)
        if callable(close):
            close()

    available = crawled.get('available_links') or []
    if not available:
        raise ProviderImportError(
            crawled.get('message') or 'No download links were available on the myf2m page.',
            code=crawled.get('code') or 'myf2m_links_empty',
        )

    normalized = normalize_download_links(available)
    if not normalized:
        raise ProviderImportError('Parsed myf2m links were empty after normalization.', code='myf2m_links_empty')

    # Same two guards the shared storage path applies: reject links whose CDN
    # path proves they belong to another title, then drop the ones the host says
    # are gone. This path used to write straight to download_links, so neither
    # guard had ever seen a myf2m movie import.
    from apps.catalog.provider_import.link_apply import guard_provider_links

    normalized, _bad, dead = guard_provider_links(movie, normalized)
    if not normalized:
        raise ProviderImportError(
            'Every myf2m link failed the pre-storage media check.'
            if dead else 'Parsed myf2m links were empty after normalization.',
            code='myf2m_links_dead' if dead else 'myf2m_links_empty',
        )

    previous_download_urls = {
        str(item.get('url') or '').strip()
        for item in (movie.download_links or [])
        if isinstance(item, dict) and str(item.get('url') or '').strip()
    }
    previous_video = (movie.video_url or '').strip()

    from apps.catalog.subtitle_extract import (
        apply_availability_flags,
        attach_extracted_subtitle,
        coalesce_download_links,
        download_links_imply_softsub,
        _ranked_movie_stream_urls,
    )

    movie.download_links = coalesce_download_links(movie.download_links or [], normalized, replace=replace)

    if not movie.quality and normalized[0].get('quality'):
        movie.quality = normalized[0]['quality']

    # Tested, not guessed: the player only gets a source that answered a probe,
    # supports byte ranges and holds a codec a browser decodes. See playback_gate.
    gate_fields: list[str] = []
    if not previous_video or previous_video in previous_download_urls:
        from apps.catalog import playback_gate

        _choice, gate_fields = playback_gate.gate_links(movie, movie.download_links or [])

    flag_fields = apply_availability_flags(movie, movie.download_links)
    movie.save(update_fields=list(dict.fromkeys([
        'download_links', 'quality', 'updated_at', *gate_fields, *flag_fields,
    ])))

    should_queue_subtitle = (
        download_links_imply_softsub(movie.download_links or [])
        or (
            bool(getattr(settings, 'SUBTITLESTAR_ENABLED', True))
            and bool(movie.imdb_id)
            and bool(_ranked_movie_stream_urls(movie.download_links or []))
        )
    )
    if queue_softsub_extract and should_queue_subtitle:
        try:
            from apps.catalog.tasks import enqueue_movie_softsub
            # Embedded Film2Media SoftSub first, exact SubtitleStar fallback second.
            queued = enqueue_movie_softsub(movie.pk, force=not bool(movie.subtitle_tracks))
            if not queued and not movie.subtitle_tracks:
                # Lock held by another worker — optional sync fallback is skipped.
                pass
        except Exception:
            logger = __import__('logging').getLogger(__name__)
            logger.exception('failed to queue softsub extract for movie %s', movie.pk)
            try:
                attach_extracted_subtitle(movie, timeout_seconds=180)
            except Exception:
                logger.exception('softsub extract failed for movie %s', movie.pk)

    return {
        'movie_id': movie.id,
        'page_path': crawled.get('page_path'),
        'page_url': crawled.get('page_url'),
        'imported_count': len(normalized),
        'total_entries_seen': crawled.get('total_entries', 0),
        'download_links': normalized,
        'video_url': movie.video_url,
        'is_dubbed': movie.is_dubbed,
        'has_subtitle': movie.has_subtitle,
        'code': crawled.get('code') or 'ok',
    }


def crawl_myf2m_downloads_for_series(
    *,
    series: Series,
    page_url: str = '',
    provider_item_id: str = '',
    replace: bool = True,
    user=None,
    queue_softsub_extract: bool = True,
) -> dict:
    """Crawl a myf2m series detail page and store public download links."""
    from config.public_urls import normalize_download_links

    ensure_myf2m_provider()
    target = (page_url or provider_item_id or '').strip()
    connector = get_connector('myf2m')
    try:
        if not target:
            target = _auto_resolve_myf2m_series_target(connector, series)
        if not target:
            raise ProviderImportError(
                'Provide a myf2m series URL or ensure the title matches a Film2Media listing.',
                code='myf2m_page_required',
            )
        crawled = _crawl_with_healed_path(
            connector,
            target=target,
            content_type='series',
            resolve=lambda: _auto_resolve_myf2m_series_target(connector, series),
            explicit=bool((page_url or provider_item_id or '').strip()),
            expected_imdb=series.imdb_id or '',
            alternatives=lambda: _myf2m_series_targets(connector, series),
        )
    except ProviderImportError:
        raise
    except Exception as exc:
        raise ProviderImportError(f'myf2m series crawl failed: {exc}', code='myf2m_crawl_failed') from exc
    finally:
        close = getattr(connector, 'close', None)
        if callable(close):
            close()

    available = crawled.get('available_links') or []
    if not available:
        raise ProviderImportError(
            crawled.get('message') or 'No download links were available on the myf2m series page.',
            code=crawled.get('code') or 'myf2m_links_empty',
        )

    normalized = normalize_download_links(available)
    if not normalized:
        raise ProviderImportError('Parsed myf2m series links were empty after normalization.', code='myf2m_links_empty')

    from apps.catalog.subtitle_extract import (
        apply_availability_flags,
        coalesce_download_links,
        download_links_imply_softsub,
        ensure_episodes_from_download_links,
    )

    series.download_links = coalesce_download_links(series.download_links or [], normalized, replace=replace)

    flag_fields = apply_availability_flags(series, series.download_links)
    series.save(update_fields=['download_links', 'updated_at', *flag_fields])

    # Mirror per-episode stream URLs into Episode.video_url so the player/list UIs stay in sync.
    try:
        ensure_episodes_from_download_links(series)
    except Exception:
        logger = __import__('logging').getLogger(__name__)
        logger.exception('failed to sync episodes from download links for series %s', series.pk)

    if queue_softsub_extract:
        should_queue_subtitle = download_links_imply_softsub(series.download_links or [])
        if not should_queue_subtitle and bool(getattr(settings, 'SUBTITLESTAR_ENABLED', True)) and series.imdb_id:
            from apps.catalog.models import Episode
            from apps.catalog.subtitle_extract import _ranked_episode_stream_urls
            # Any playable episode encode is enough for SubtitleStar sidecars.
            should_queue_subtitle = any(
                _ranked_episode_stream_urls([item])
                for item in (series.download_links or [])
                if isinstance(item, dict)
            ) or Episode.objects.filter(
                season__series_id=series.pk,
                is_published=True,
            ).exclude(video_url='').exists()
        if should_queue_subtitle:
            try:
                from apps.catalog.tasks import enqueue_series_softsub
                enqueue_series_softsub(series.pk, force=False, episode_limit=40)
            except Exception:
                logger = __import__('logging').getLogger(__name__)
                logger.exception('failed to queue softsub extract for series %s', series.pk)

    return {
        'series_id': series.id,
        'page_path': crawled.get('page_path'),
        'page_url': crawled.get('page_url'),
        'imported_count': len(normalized),
        'total_entries_seen': crawled.get('total_entries', 0),
        'download_links': normalized,
        'is_dubbed': series.is_dubbed,
        'has_subtitle': series.has_subtitle,
        'code': crawled.get('code') or 'ok',
    }
