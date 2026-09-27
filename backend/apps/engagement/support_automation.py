"""Automatic first-response + remediation for the support inbox («درخواست‌ها»).

Every OPEN :class:`~apps.engagement.models.SupportTicket` a user files is picked
up here and answered by the روایتو team account with a *real, honest* reply —
never a canned "we got it" that hides the fact nothing happened:

============== =================================================================
category       what the engine actually does
============== =================================================================
content_request Look the title up in our own catalog. If we already carry it,
               reply with the watch link and resolve. Otherwise confirm it
               against TMDB and draft it into the library so the import pipeline
               can complete it, and tell the user it's on the way.
bug            If the ticket points at a specific title, re-run the same
content_fix    battle-tested fixers the player's «گزارش خطا» uses (browser-safe
               source re-crawl + SoftSub ensure) and reply with what was
               refreshed. A ticket mirrored from a ContentIssueReport is closed
               against that report's own remediation outcome.
suggestion     A genuine, specific acknowledgement and an ``in_progress`` status
support        so a human can follow up — no false "fixed" claim.
cooperation
============== =================================================================

The engine runs in two phases and is self-healing:

* **first response** — every ``OPEN`` ticket still lacking an automated reply is
  answered and moved out of ``OPEN`` (resolved / waiting_user / in_progress).
  Selection is *status*-based, not ``unread_by_staff``-based: a human merely
  opening the inbox clears that flag without resolving anything, which must not
  make the engine abandon the ticket.
* **retry** — a ticket parked in ``in_progress`` (title still importing, no
  browser-safe source yet, subtitle still landing) is re-checked on a backoff.
  The re-check is *crawl-free*: the dedicated playback/subtitle crawlers own the
  actual fixing, and this only watches the catalog/source state and closes the
  loop with the user the moment it genuinely resolves — never a repeated "still
  working on it".
"""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from apps.engagement import services
from apps.engagement.models import SupportTicket

logger = logging.getLogger(__name__)

BOT_EMAIL = 'team@revayato.internal'
BOT_USERNAME = 'revayato_team'
BOT_DISPLAY = 'تیم روایتو'

# --- self-healing retry policy ---------------------------------------------
# A ticket the engine could not resolve on first contact (a title still importing,
# a source with no browser-safe mirror yet, a subtitle the SoftSub worker is still
# fetching) is parked in ``in_progress`` and re-attempted on a backoff. Each retry
# silently re-runs the exact same remediation; the user only ever hears back again
# when it *actually* resolves — never a repeated "still working on it".
# The recheck is a cheap DB read, so the backoff is bounded by *age*, not by a small
# attempt count: a flat cap of 12 used to abandon a ticket after ~6h even though the
# crawler might land a browser-safe mirror on day two. Widening intervals keep the
# watch alive for the whole RETRY_MAX_AGE_DAYS window without spamming the box.
RETRY_BACKOFF_SECONDS = (1800, 1800, 3600, 3600, 7200, 7200, 14400, 21600)
RETRY_MAX_AGE_DAYS = 21        # stop auto-retrying tickets older than three weeks
TICKET_LOCK_TTL_SECONDS = 600  # one worker per ticket at a time (event path vs beat sweep)
# A report remediated within this window is reused, not re-crawled, when the ticket speaks.
RECENT_REMEDIATION_SECONDS = 300

# Categories whose in_progress state can genuinely self-heal in the background
# (a catalog import completing, a provider re-crawl, a subtitle landing). A
# suggestion/support/cooperation acknowledgement has nothing to auto-resolve, so
# it is never retried — it waits for a human.
_RETRYABLE_CATEGORIES = (
    SupportTicket.Category.BUG,
    SupportTicket.Category.CONTENT_FIX,
    SupportTicket.Category.CONTENT_REQUEST,
)

_RETRIES_RE = re.compile(r'retries=(\d+)')


# --- concurrency -----------------------------------------------------------

@contextmanager
def _ticket_lock(ticket_id: int):
    """Cross-worker mutex: the event-driven task and the beat sweep can both reach
    the same ticket in the same second; only one may answer it (no double reply).
    """
    key = f'support:ticket:lock:{int(ticket_id)}'
    acquired = False
    try:
        acquired = bool(cache.add(key, '1', TICKET_LOCK_TTL_SECONDS))
    except Exception:  # noqa: BLE001 — a cache outage must not silence support
        acquired = True
    try:
        yield acquired
    finally:
        if acquired:
            try:
                cache.delete(key)
            except Exception:  # noqa: BLE001
                pass


# --- outcome ---------------------------------------------------------------

@dataclass
class Outcome:
    """What the engine decided for one ticket."""

    reply: str
    status: str
    note: str = ''
    action: str = ''
    handled: bool = True


# --- shared helpers --------------------------------------------------------

def get_bot_user():
    """The staff account every automated reply is authored by.

    Created once, with an unusable password so it can never be signed into.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.filter(email=BOT_EMAIL).first()
    if user:
        return user
    user = User(
        email=BOT_EMAIL,
        username=BOT_USERNAME,
        first_name=BOT_DISPLAY,
        is_staff=True,
        is_active=True,
    )
    user.set_unusable_password()
    try:
        user.save()
    except Exception:  # pragma: no cover — a racing create or a taken username
        existing = User.objects.filter(Q(email=BOT_EMAIL) | Q(username=BOT_USERNAME)).first()
        if existing is None:
            raise
        return existing
    return user


def site_base() -> str:
    base = (getattr(settings, 'SITE_BASE_URL', '') or getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
    return base or 'https://revayato.com'


def _watch_url(content_type: str, slug: str) -> str:
    kind = 'series' if content_type == 'series' else 'movies'
    return f'{site_base()}/{kind}/{slug}'


def _requested_title(ticket: SupportTicket) -> str:
    """Best guess at the title a content_request is about."""
    if ticket.related_title.strip():
        return ticket.related_title.strip()
    subject = ticket.subject.strip()
    # Drop a leading generic label like «درخواست عنوان:» the composer may prepend.
    for sep in (':', '：', '-', '—'):
        if sep in subject:
            head, _, tail = subject.partition(sep)
            if tail.strip() and len(head) <= 20:
                return tail.strip()
    return subject


# Each catalog model spells its year field differently.
_YEAR_FIELD = {'movie': 'release_year', 'series': 'start_year'}


def _year_of(obj, ctype: str) -> int | None:
    return getattr(obj, _YEAR_FIELD.get(ctype, 'release_year'), None)


def _find_catalog_title(title: str, year: int | None):
    """Return ``(obj, content_type, published)`` for a title already in the
    catalog, or ``None``. Prefers an exact title match and a published row.
    """
    from apps.catalog.models import Movie, Series

    title = (title or '').strip()
    if not title:
        return None

    models_map = (('movie', Movie), ('series', Series))
    candidates: list[tuple[Any, str]] = []
    for ctype, model in models_map:
        exact = model.objects.filter(
            Q(title__iexact=title) | Q(original_title__iexact=title)
        )
        if year:
            exact = list(exact.filter(**{_YEAR_FIELD[ctype]: year})) or list(exact)
        else:
            exact = list(exact)
        candidates.extend((obj, ctype) for obj in exact)

    if not candidates:
        # Looser contains match — only trust it when it is unambiguous.
        for ctype, model in models_map:
            near = list(
                model.objects.filter(
                    Q(title__icontains=title) | Q(original_title__icontains=title)
                )[:3]
            )
            candidates.extend((obj, ctype) for obj in near)
        if len(candidates) != 1:
            return None

    # Prefer a published match; among those, a year match if we have a year.
    def sort_key(item):
        obj, ctype = item
        published = bool(getattr(obj, 'is_published', False))
        year_match = bool(year and _year_of(obj, ctype) == year)
        return (published, year_match)

    obj, ctype = sorted(candidates, key=sort_key, reverse=True)[0]
    return obj, ctype, bool(getattr(obj, 'is_published', False))


# --- category handlers -----------------------------------------------------

def _handle_content_request(ticket: SupportTicket) -> Outcome:
    title = _requested_title(ticket)
    year = ticket.related_year

    found = _find_catalog_title(title, year)
    if found is not None:
        obj, ctype, published = found
        name = getattr(obj, 'title', title)
        if published:
            url = _watch_url(ctype, obj.slug)
            return Outcome(
                reply=(
                    f'خبر خوب! «{name}» همین حالا در روایتو موجود است و می‌توانی از این نشانی تماشا کنی:\n'
                    f'{url}\n\n'
                    'اگر منظورت عنوان دیگری بود، همین‌جا بنویس تا دوباره بررسی کنیم.'
                ),
                status=SupportTicket.Status.RESOLVED,
                note=f'matched_published:{ctype}:{obj.slug}',
                action='catalog_match',
            )
        return Outcome(
            reply=(
                f'«{name}» در کتابخانهٔ روایتو ثبت شده و در مرحلهٔ آماده‌سازی نهایی است. '
                'به‌محض آماده‌شدن منبع پخش، همین‌جا اطلاع می‌دهیم. ممنون که صبوری می‌کنی!'
            ),
            status=SupportTicket.Status.IN_PROGRESS,
            note=f'matched_unpublished:{ctype}:{obj.slug}',
            action='catalog_match',
        )

    # Not in our catalog yet — try to draft it from TMDB so the import pipeline
    # can pick it up. Honest wording: registered & being prepared, not "watchable".
    drafted = _draft_from_tmdb(title, year)
    if drafted is not None:
        name, ctype = drafted
        return Outcome(
            reply=(
                f'«{name}» را در فهرست افزودن روایتو ثبت کردیم و برای آماده‌سازی در صف قرار گرفت. '
                'تیم ما منبع پخش و زیرنویس را تکمیل می‌کند و نتیجه را همین‌جا به تو اطلاع می‌دهیم. '
                'ممنون که کمک می‌کنی کتابخانه کامل‌تر شود!'
            ),
            status=SupportTicket.Status.IN_PROGRESS,
            note=f'drafted_from_tmdb:{ctype}:{name}',
            action='tmdb_draft',
        )

    # Couldn't find or confirm it — ask for the detail that unblocks us.
    return Outcome(
        reply=(
            'برای افزودن دقیق این عنوان کمی اطلاعات بیشتر لازم داریم. '
            'اگر ممکن است نام انگلیسی، سال ساخت یا نشانی صفحهٔ IMDb را همین‌جا برایمان بنویس '
            'تا سریع‌تر بررسی و اضافه‌اش کنیم.'
        ),
        status=SupportTicket.Status.WAITING_USER,
        note='needs_more_info',
        action='request_details',
    )


def _draft_from_tmdb(title: str, year: int | None) -> tuple[str, str] | None:
    """Confirm a title on TMDB and upsert it as an unpublished draft.

    Returns ``(name, content_type)`` on success, else ``None``. Never raises —
    a missing/misconfigured TMDB or an import-structure block just yields None.
    """
    try:
        from apps.catalog.tmdb import configured_tmdb_client
        from apps.catalog.ingestion import upsert_tmdb_movie, upsert_tmdb_series
    except Exception:  # pragma: no cover
        return None

    try:
        client = configured_tmdb_client()
    except Exception:
        return None

    # Movies first (the bulk of requests), then TV.
    try:
        movie_hits = (client.search_movies(title, year=year).get('results') or [])
    except Exception:
        movie_hits = []
    try:
        tv_hits = (client.search_tv(title, first_air_year=year).get('results') or [])
    except Exception:
        tv_hits = []

    if movie_hits:
        tmdb_id = movie_hits[0].get('id')
        try:
            details = client.movie_details(tmdb_id)
            movie, _created, _published, _skipped = upsert_tmdb_movie(details, auto_publish=False)
            return getattr(movie, 'title', title), 'movie'
        except Exception as exc:
            logger.info('content_request movie draft failed for %r: %s', title, exc)

    if tv_hits:
        tmdb_id = tv_hits[0].get('id')
        try:
            details = client.tv_details(tmdb_id)
            series, _created = upsert_tmdb_series(details)
            return getattr(series, 'title', title), 'series'
        except Exception as exc:
            logger.info('content_request series draft failed for %r: %s', title, exc)

    return None


def _resolve_ticket_target(ticket: SupportTicket):
    """Best effort at the Movie/Series a bug/content_fix ticket is about."""
    from urllib.parse import unquote

    from apps.catalog.models import Movie, Series
    from apps.catalog.slugs import canonical_slug

    # 1) A slug embedded in related_url (…/movies/<slug> or …/series/<slug>).
    url = ticket.related_url.strip()
    for kind, model, ctype in (('movies', Movie, 'movie'), ('series', Series, 'series')):
        marker = f'/{kind}/'
        if marker in url:
            slug = unquote(url.split(marker, 1)[1].split('/', 1)[0].split('?', 1)[0].strip())
            obj = model.objects.filter(slug=canonical_slug(model, slug)).first()
            if obj:
                return obj, ctype

    # 2) Fall back to a title lookup.
    found = _find_catalog_title(ticket.related_title or ticket.subject, ticket.related_year)
    if found is not None:
        obj, ctype, _published = found
        return obj, ctype
    return None


def _handle_content_issue(ticket: SupportTicket) -> Outcome:
    # Ticket mirrored from a player report — close it against that report's fix.
    report = ticket.content_issue_reports.order_by('-created_at').first()
    if report is not None:
        return _handle_from_report(report)

    target = _resolve_ticket_target(ticket)
    if target is None:
        return Outcome(
            reply=(
                'گزارشت ثبت شد و در حال بررسی است. اگر ممکن است نام دقیق فیلم/سریال و '
                '(برای سریال) شمارهٔ فصل و قسمت را همین‌جا بنویس تا سریع‌تر رفعش کنیم.'
            ),
            status=SupportTicket.Status.IN_PROGRESS,
            note='no_target_identified',
            action='ack',
        )

    obj, ctype = target
    result = _run_title_remediation(ctype, obj)
    name = getattr(obj, 'title', '')
    if result.get('resolved'):
        return Outcome(
            reply=(
                f'مشکل «{name}» را بررسی و رفع کردیم: {result["summary"]} '
                'اگر باز هم به مشکل خوردی، همین‌جا بنویس.'
            ),
            status=SupportTicket.Status.RESOLVED,
            note=result.get('note', 'remediated'),
            action='title_remediation',
        )
    return Outcome(
        reply=(
            f'روی «{name}» کار کردیم و {result["summary"]} '
            'به‌محض کامل‌شدن، همین‌جا خبرت می‌کنیم.'
        ),
        status=SupportTicket.Status.IN_PROGRESS,
        note=result.get('note', 'queued'),
        action='title_remediation',
    )


def _run_title_remediation(content_type: str, obj) -> dict[str, Any]:
    """Re-crawl a browser-safe source and re-ensure subtitles for a title.

    Uses the exact same production helpers the player's «گزارش خطا» remediation
    calls. Returns ``{resolved, summary, note}`` and never raises.
    """
    summary_parts: list[str] = []
    resolved = False
    note_parts: list[str] = []

    try:
        from apps.catalog import playback_sources

        outcome = playback_sources.remediate(obj)
        state = str(outcome.get('outcome') or '').lower()
        if state == 'refreshed':
            summary_parts.append('یک منبع پخش سازگار با مرورگر جایگزین شد')
            resolved = True
        elif state == 'unavailable':
            summary_parts.append('فعلاً منبع پخش سالمی پیدا نشد و برای بازبینی ثبت شد')
        else:  # provider_error → retry later
            summary_parts.append('منبع پخش برای بازخزش دوباره در صف قرار گرفت')
        note_parts.append(f'playback:{state or "pending"}')
    except Exception as exc:  # noqa: BLE001
        logger.info('playback remediation failed: %s', exc)
        note_parts.append('playback:error')

    try:
        from apps.catalog.playback_subtitle import ensure_playback_subtitles

        sub = ensure_playback_subtitles(
            content_type=content_type,
            slug=getattr(obj, 'slug', ''),
            sync=True,
            timeout_seconds=12,
        )
        sstate = str(sub.get('status') or sub.get('state') or '').lower()
        if sub.get('ready') or sstate in {'ready', 'resolved', 'attached'}:
            summary_parts.append('زیرنویس فارسی بررسی و به‌روزرسانی شد')
        note_parts.append(f'subtitle:{sstate or "pending"}')
    except Exception as exc:  # noqa: BLE001
        logger.info('subtitle ensure failed: %s', exc)
        note_parts.append('subtitle:error')

    summary = '؛ '.join(summary_parts) + '.' if summary_parts else 'بررسی انجام شد.'
    return {'resolved': resolved, 'summary': summary, 'note': ','.join(note_parts)}


# Honest, actionable guidance for the one class the crawler cannot fix by
# itself: the only upstream copy is an MKV/HEVC encode some browsers cannot play.
_PLAYBACK_WORKAROUND = (
    'تا آن موقع، پخش با مرورگر کروم یا اپلیکیشن اندروید روایتو معمولاً مشکلی ندارد '
    'و بخش دانلود هم در دسترس است.'
)


def _handle_from_report(report) -> Outcome:
    """Run the content-issue remediation engine and phrase its outcome."""
    from apps.catalog.content_remediation import remediate_report

    outcome = remediate_report(report, min_interval_seconds=RECENT_REMEDIATION_SECONDS)
    status = str(outcome.get('status') or '').lower()
    result = str(outcome.get('result') or '')
    playback = report.problem_type == 'playback'

    if status == 'resolved':
        return Outcome(
            reply=(
                'مشکلی که گزارش کردی برطرف شد ✅ منبع/زیرنویس تازه‌ای جایگزین شد. '
                'اگر باز هم تکرار شد، همین‌جا بنویس تا دوباره بررسی کنیم.'
            ),
            status=SupportTicket.Status.RESOLVED,
            note=f'cir:{report.pk}:{result}'[:1000],
            action='report_remediation',
        )
    if status == 'unavailable':
        tail = f' {_PLAYBACK_WORKAROUND}' if playback else ''
        return Outcome(
            reply=(
                'گزارشت را بررسی کردیم؛ فعلاً نسخهٔ سازگار با مرورگر برای این مورد در منابع '
                'پیدا نشد. آن را در فهرست پیگیری گذاشتیم، به‌صورت خودکار دوباره بررسی می‌کنیم '
                f'و به‌محض پیداشدن منبع، همین‌جا خبرت می‌کنیم.{tail}'
            ),
            status=SupportTicket.Status.IN_PROGRESS,
            note=f'cir:{report.pk}:{result}'[:1000],
            action='report_remediation',
        )
    return Outcome(
        reply=(
            'گزارشت ثبت و بررسی شد و برای رفع کامل در صف قرار گرفت. '
            'نتیجه را همین‌جا اطلاع می‌دهیم — ممنون که کمک کردی کیفیت بهتر شود.'
        ),
        status=SupportTicket.Status.IN_PROGRESS,
        note=f'cir:{report.pk}:{result}'[:1000],
        action='report_remediation',
    )


_ACK_BY_CATEGORY = {
    SupportTicket.Category.SUGGESTION: (
        'ممنون بابت پیشنهادت! آن را برای تیم محصول روایتو ثبت کردیم تا در '
        'بهبودهای بعدی بررسی شود. اگر جزئیات بیشتری داری، همین‌جا اضافه کن.'
    ),
    SupportTicket.Category.COOPERATION: (
        'خوشحالیم که برای همکاری پیش‌قدم شدی 🌱 درخواستت به تیم روایتو رسید و '
        'به‌زودی برای هماهنگی در همین گفتگو پاسخت را می‌دهیم.'
    ),
    SupportTicket.Category.SUPPORT: (
        'پیامت به تیم پشتیبانی روایتو رسید و در حال بررسی است. اگر سؤال یا جزئیات '
        'بیشتری داری، همین‌جا بنویس تا سریع‌تر کمکت کنیم.'
    ),
}


def _handle_generic(ticket: SupportTicket) -> Outcome:
    reply = _ACK_BY_CATEGORY.get(
        ticket.category,
        'پیامت را دریافت کردیم و در حال بررسی است. به‌زودی همین‌جا پاسخت را می‌دهیم.',
    )
    return Outcome(
        reply=reply,
        status=SupportTicket.Status.IN_PROGRESS,
        note='acknowledged',
        action='ack',
    )


_DISPATCH = {
    SupportTicket.Category.CONTENT_REQUEST: _handle_content_request,
    SupportTicket.Category.BUG: _handle_content_issue,
    SupportTicket.Category.CONTENT_FIX: _handle_content_issue,
}


# --- public entry points ---------------------------------------------------

def decide(ticket: SupportTicket) -> Outcome:
    """Choose an outcome for a ticket without writing anything (pure, testable)."""
    handler = _DISPATCH.get(ticket.category, _handle_generic)
    try:
        return handler(ticket)
    except Exception as exc:  # noqa: BLE001 — one bad ticket must not break a run
        logger.exception('support automation failed for ticket %s', ticket.tracking_code)
        return Outcome(
            reply=(
                'پیامت ثبت شد و در حال بررسی است. به‌زودی همین‌جا پاسخ می‌دهیم.'
            ),
            status=SupportTicket.Status.IN_PROGRESS,
            note=f'handler_error:{type(exc).__name__}',
            action='error',
            handled=False,
        )


def resolve_ticket(ticket: SupportTicket, *, dry_run: bool = False) -> Outcome:
    """Answer one ticket: post the staff reply and set its final status."""
    outcome = decide(ticket)
    if dry_run:
        return outcome

    bot = get_bot_user()
    services.reply_support_ticket(
        ticket=ticket,
        author=bot,
        body=outcome.reply,
        is_staff_reply=True,
    )
    # reply_support_ticket lands the ticket in WAITING_USER; move it to the final
    # state the handler chose (resolved / in_progress) unless that already is it.
    if outcome.status != SupportTicket.Status.WAITING_USER:
        services.set_support_ticket_status(
            ticket=ticket,
            status=outcome.status,
            staff_note=(f'[auto:{outcome.action}] {outcome.note}')[:2000],
        )
    return outcome


def _retry_count(ticket: SupportTicket) -> int:
    match = _RETRIES_RE.search(ticket.staff_note or '')
    return int(match.group(1)) if match else 0


# Stamped in the staff_note once the viewer has been told there is no
# browser-safe source yet, so the update is posted exactly once per ticket.
_DEAD_END_MARK = 'no_safe_source_notified'


def _dead_end_unannounced(ticket: SupportTicket, report) -> bool:
    """Has auto-remediation given up on this report without telling the viewer?"""
    status = str(report.status).lower()
    dead_end = status == 'unavailable' or (
        status == 'needs_review' and report.remediation_action == 'auto_exhausted'
    )
    return dead_end and _DEAD_END_MARK not in (ticket.staff_note or '')


def _recheck_resolved(ticket: SupportTicket) -> Outcome | None:
    """Crawl-free check: has the thing this parked ticket is about *since* been
    fixed — by the dedicated playback-crawler landing a browser-safe source, or an
    import finishing and publishing the requested title?

    Returns a RESOLVED :class:`Outcome` to post, or ``None`` to leave the ticket
    parked. Deliberately does **no** network work: detection is a cheap DB read.
    The specialised crawlers own the *fixing*; this only watches and closes the
    loop with the user, so the 180s beat never adds crawl load to the box.
    """
    # A requested title that has since been imported & published.
    if ticket.category == SupportTicket.Category.CONTENT_REQUEST:
        found = _find_catalog_title(_requested_title(ticket), ticket.related_year)
        if found is not None and found[2]:  # published now
            obj, ctype, _ = found
            name = getattr(obj, 'title', '') or _requested_title(ticket)
            return Outcome(
                reply=(
                    f'خبر خوب! «{name}» آماده شد و همین حالا در روایتو قابل تماشاست:\n'
                    f'{_watch_url(ctype, obj.slug)}\n\nتماشای خوبی داشته باشی!'
                ),
                status=SupportTicket.Status.RESOLVED,
                note=f'catalog_ready:{ctype}:{obj.slug}',
                action='catalog_ready',
            )
        return None

    # A ticket mirrored from a player report is judged on that report — never on a
    # title guess. The report knows the exact movie/series/episode; the ticket's
    # ``related_title`` ("Çukur — قسمت 27") does not resolve to a catalog row, and a
    # series-level check would call the show playable while this episode is still
    # a bare .mkv.
    report = ticket.content_issue_reports.order_by('-created_at').first()
    if report is not None:
        try:
            from apps.catalog.content_remediation import recheck_report

            recheck_report(report)  # DB-only; resolves the report if the target now plays
        except Exception as exc:  # noqa: BLE001
            logger.info('report recheck failed for %s: %s', ticket.tracking_code, exc)
        if str(report.status).lower() == 'resolved':
            return Outcome(
                reply=(
                    'مشکلی که گزارش کردی برطرف شد ✅ منبع/زیرنویس تازه‌ای جایگزین شد. '
                    'اگر باز هم تکرار شد، همین‌جا بنویس.'
                ),
                status=SupportTicket.Status.RESOLVED,
                note=f'cir:{report.pk}:resolved',
                action='report_resolved',
            )
        if _dead_end_unannounced(ticket, report):
            # Automatic fixing has honestly run out of road. Say it once: a viewer
            # left on "در صف قرار گرفت" forever assumes nobody looked. The free
            # sweep keeps watching, so a mirror landing later still closes this.
            return Outcome(
                reply=(
                    'یک به‌روزرسانی دربارهٔ گزارشت: منابع را چند بار بررسی کردیم و فعلاً '
                    'نسخه‌ای که مرورگر بتواند پخش کند برای این مورد وجود ندارد. '
                    'پیگیری را باز نگه می‌داریم و به‌محض رسیدن نسخهٔ سازگار، همین‌جا خبرت می‌کنیم. '
                    f'{_PLAYBACK_WORKAROUND}'
                ),
                status=SupportTicket.Status.IN_PROGRESS,
                note=f'cir:{report.pk}:{_DEAD_END_MARK}',
                action='report_unavailable',
            )
        return None  # still broken (or a non-playback type left to its own remediation)

    # A hand-written bug ticket with no report: resolve once the title plays again.
    target = _resolve_ticket_target(ticket)
    if target is None:
        return None
    obj, ctype = target
    if not bool(getattr(obj, 'is_published', False)):
        return None
    try:
        from apps.catalog import playback_sources

        still_unplayable = playback_sources.browser_unplayable(obj)  # DB-only diagnosis
    except Exception as exc:  # noqa: BLE001
        logger.info('recheck diagnose failed for %s: %s', ticket.tracking_code, exc)
        return None
    if still_unplayable:
        return None
    name = getattr(obj, 'title', '')
    return Outcome(
        reply=(
            f'مشکل پخش «{name}» برطرف شد ✅ حالا یک منبع سازگار با مرورگر در دسترس است. '
            f'می‌توانی از اینجا تماشا کنی:\n{_watch_url(ctype, obj.slug)}'
        ),
        status=SupportTicket.Status.RESOLVED,
        note='playback_now_safe',
        action='playback_recovered',
    )


def retry_ticket(ticket: SupportTicket, *, dry_run: bool = False) -> tuple[Outcome, bool]:
    """Re-attempt a parked ``in_progress`` ticket — crawl-free.

    Uses :func:`_recheck_resolved` (a cheap DB check) rather than re-running the
    full remediation, so the dedicated playback-crawler owns all the actual
    re-crawling and the beat never piles crawl load on the box. The user is
    messaged again *only* when the ticket now genuinely resolves; otherwise the
    retry counter is bumped silently so the backoff advances without spamming the
    thread. Returns ``(outcome, resolved_now)``.
    """
    resolved_outcome = _recheck_resolved(ticket)
    if resolved_outcome is not None:
        outcome = resolved_outcome
    else:
        outcome = Outcome(
            reply='', status=SupportTicket.Status.IN_PROGRESS,
            note='still_pending', action='recheck',
        )
    attempts = _retry_count(ticket) + 1

    if outcome.status == SupportTicket.Status.RESOLVED:
        if not dry_run:
            bot = get_bot_user()
            services.reply_support_ticket(
                ticket=ticket, author=bot, body=outcome.reply, is_staff_reply=True,
            )
            services.set_support_ticket_status(
                ticket=ticket,
                status=SupportTicket.Status.RESOLVED,
                staff_note=(f'[auto:{outcome.action}] {outcome.note} · retries={attempts} · resolved')[:2000],
            )
        return outcome, True

    # Still unresolved. Post a reply only when the recheck produced a genuine
    # update to give (today: "there is no browser-safe source yet"), which its
    # note marks so it is said once; otherwise bump the counter silently. Either
    # way updated_at moves, so the backoff window advances.
    if not dry_run:
        if outcome.reply:
            services.reply_support_ticket(
                ticket=ticket, author=get_bot_user(), body=outcome.reply, is_staff_reply=True,
            )
        services.set_support_ticket_status(
            ticket=ticket,
            status=SupportTicket.Status.IN_PROGRESS,
            staff_note=(f'[auto:{outcome.action}] {outcome.note} · retries={attempts}')[:2000],
        )
    return outcome, False


def _needs_first_response(ticket: SupportTicket) -> bool:
    """Same rule as :func:`_first_response_tickets`, for a single (fresh) ticket."""
    if ticket.status != SupportTicket.Status.OPEN:
        return False
    if ticket.unread_by_staff:
        return True
    return not ticket.messages.filter(is_staff_reply=True).exists()


def process_ticket(ticket_id: int) -> Outcome | None:
    """Answer one ticket *now* (event path) — safe to race with the beat sweep.

    Takes the per-ticket lock and re-reads the row, so a ticket the sweep (or a
    duplicate task) already answered is skipped instead of getting a second reply.
    Returns ``None`` when there was nothing to do.
    """
    with _ticket_lock(ticket_id) as acquired:
        if not acquired:
            return None
        ticket = SupportTicket.objects.filter(pk=ticket_id).first()
        if ticket is None or not _needs_first_response(ticket):
            return None
        return resolve_ticket(ticket)


def close_tickets_for_reports(report_ids) -> int:
    """After reports were resolved by a sweep, tell their tickets' owners now.

    Without this a fixed ticket would wait for its next retry window (up to hours)
    before the user hears the good news.
    """
    from apps.catalog.models import ContentIssueReport

    ticket_ids = set(
        ContentIssueReport.objects.filter(pk__in=list(report_ids), support_ticket__isnull=False)
        .values_list('support_ticket_id', flat=True)
    )
    closed = 0
    for ticket_id in ticket_ids:
        with _ticket_lock(ticket_id) as acquired:
            if not acquired:
                continue
            ticket = SupportTicket.objects.filter(pk=ticket_id).first()
            if ticket is None or ticket.status != SupportTicket.Status.IN_PROGRESS:
                continue
            _outcome, resolved_now = retry_ticket(ticket)
            closed += int(resolved_now)
    return closed


def _first_response_tickets(limit: int, category: str | None) -> list[SupportTicket]:
    """OPEN tickets that still need an automated first reply.

    Status-based, *not* ``unread_by_staff``-based: a human merely opening the
    inbox clears that flag (``mark_ticket_read_by_staff``) without resolving
    anything, which used to make the engine abandon the ticket. A ticket qualifies
    when it is OPEN and either has no staff reply yet (brand-new, including every
    player «گزارش خطا» mirrored in) or the user has just written back
    (``unread_by_staff`` set again by their reply). A ticket a human has already
    replied to by hand is left alone.
    """
    base = SupportTicket.objects.filter(status=SupportTicket.Status.OPEN)
    if category:
        base = base.filter(category=category)

    never_answered = base.exclude(messages__is_staff_reply=True)
    user_wrote_back = base.filter(unread_by_staff=True)
    ids = set(never_answered.values_list('id', flat=True))
    ids |= set(user_wrote_back.values_list('id', flat=True))
    return list(
        SupportTicket.objects.filter(id__in=ids).order_by('created_at')[: max(1, limit)]
    )


def _retry_interval_seconds(retries: int) -> int:
    return RETRY_BACKOFF_SECONDS[min(max(retries, 0), len(RETRY_BACKOFF_SECONDS) - 1)]


def _retry_tickets(limit: int, category: str | None) -> list[SupportTicket]:
    """Parked ``in_progress`` tickets due for a background recheck.

    Only auto-parked, self-healable tickets. Each is rechecked on a widening
    backoff (``RETRY_BACKOFF_SECONDS``) for as long as it is younger than
    ``RETRY_MAX_AGE_DAYS`` — the recheck is a DB read, so patience is cheap, and a
    mirror the crawler lands on day two still closes the loop with the user.
    """
    now = timezone.now()
    qs = SupportTicket.objects.filter(
        status=SupportTicket.Status.IN_PROGRESS,
        category__in=_RETRYABLE_CATEGORIES,
        staff_note__startswith='[auto:',
        updated_at__lt=now - timedelta(seconds=RETRY_BACKOFF_SECONDS[0]),
        created_at__gt=now - timedelta(days=RETRY_MAX_AGE_DAYS),
    )
    if category:
        qs = qs.filter(category=category)
    due = []
    for ticket in qs.order_by('updated_at'):
        waited = (now - ticket.updated_at).total_seconds()
        if waited < _retry_interval_seconds(_retry_count(ticket)):
            continue
        due.append(ticket)
        if len(due) >= max(1, limit):
            break
    return due


def _tally(stats: dict[str, Any], ticket: SupportTicket, outcome: Outcome, *, phase: str) -> None:
    stats['processed'] += 1
    if not outcome.handled:
        stats['errors'] += 1
    if outcome.status == SupportTicket.Status.RESOLVED:
        stats['resolved'] += 1
    elif outcome.status == SupportTicket.Status.IN_PROGRESS:
        stats['in_progress'] += 1
    elif outcome.status == SupportTicket.Status.WAITING_USER:
        stats['waiting_user'] += 1
    stats['outcomes'].append({
        'tracking_code': ticket.tracking_code,
        'category': ticket.category,
        'status': outcome.status,
        'action': outcome.action,
        'note': outcome.note,
        'phase': phase,
    })


def resolve_open_tickets(
    *,
    limit: int = 50,
    dry_run: bool = False,
    category: str | None = None,
    ticket_code: str | None = None,
    retry: bool = True,
) -> dict[str, Any]:
    """Drive the support inbox to resolution.

    Two phases per run:
      1. **first response** — every OPEN ticket still needing an automated reply
         (status-based, robust to a human clearing the unread flag).
      2. **retry** — parked ``in_progress`` tickets re-attempted on a backoff so a
         title that finished importing, a source the crawler later fixed, or a
         subtitle that has since landed auto-resolves and notifies the user.

    Returns stats including a ``retried``/``retry_resolved`` breakdown.
    """
    stats: dict[str, Any] = {
        'processed': 0, 'resolved': 0, 'in_progress': 0, 'waiting_user': 0, 'errors': 0,
        'retried': 0, 'retry_resolved': 0, 'outcomes': [],
    }

    if ticket_code:
        # Operator-targeted: re-answer exactly this ticket regardless of state.
        for ticket in SupportTicket.objects.filter(tracking_code=ticket_code):
            outcome = resolve_ticket(ticket, dry_run=dry_run)
            _tally(stats, ticket, outcome, phase='targeted')
        return stats

    budget = max(1, limit)
    for ticket in _first_response_tickets(budget, category):
        if dry_run:
            _tally(stats, ticket, resolve_ticket(ticket, dry_run=True), phase='first_response')
            continue
        outcome = process_ticket(ticket.pk)
        if outcome is not None:  # None: another worker got there first
            _tally(stats, ticket, outcome, phase='first_response')

    remaining = budget - stats['processed']
    if retry and remaining > 0:
        for ticket in _retry_tickets(remaining, category):
            if dry_run:
                outcome, resolved_now = retry_ticket(ticket, dry_run=True)
            else:
                with _ticket_lock(ticket.pk) as acquired:
                    if not acquired:
                        continue
                    ticket.refresh_from_db()
                    if ticket.status != SupportTicket.Status.IN_PROGRESS:
                        continue
                    outcome, resolved_now = retry_ticket(ticket)
            stats['retried'] += 1
            if resolved_now:
                stats['retry_resolved'] += 1
            _tally(stats, ticket, outcome, phase='retry')

    return stats
