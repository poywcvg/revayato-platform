"""AI behavior-analysis assistant endpoints.

Both endpoints are strictly read-only on the catalog: they read the user's
behavior signals (UserActivityEvent / Rating / Like / WatchlistItem) and the
existing recommendation engine, then optionally ask the LLM to turn that into
natural-language Persian analysis. No Movie/Series rows are created or removed.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.catalog.serializers import MovieListSerializer, SeriesListSerializer
from apps.engagement.models import UserActivityEvent
from apps.recommendations import services

from . import llm

ACTION_LABELS = {
    'view_movie': 'تماشای فیلم',
    'view_series': 'تماشای سریال',
    'view_episode': 'تماشای قسمت',
    'play': 'پخش',
    'pause': 'توقف موقت',
    'watch_progress': 'پیشرفت تماشا',
    'complete_watch': 'تمام کردن اثر',
    'like': 'پسندیدن',
    'remove_like': 'لغو پسندیدن',
    'dislike': 'عدم علاقه',
    'rate': 'امتیازدهی',
    'add_to_watchlist': 'افزودن به لیست تماشا',
    'remove_from_watchlist': 'حذف از لیست تماشا',
    'search': 'جستجو',
    'click_search_result': 'کلیک روی نتیجه جستجو',
    'filter_genre': 'فیلتر ژانر',
    'filter_year': 'فیلتر سال',
    'filter_country': 'فیلتر کشور',
    'open_actor_page': 'باز کردن صفحه بازیگر',
    'open_director_page': 'باز کردن صفحه کارگردان',
    'share': 'اشتراک‌گذاری',
    'comment': 'نظر',
    'download_click': 'کلیک دانلود',
    'trailer_watch': 'تماشای تریلر',
}


def _recent_event_labels(user, limit=12):
    """Short Persian descriptions of the user's latest activity (no PII)."""
    qs = UserActivityEvent.objects.filter(user=user).order_by('-created_at')[:limit]
    labels = []
    for ev in qs:
        label = ACTION_LABELS.get(ev.action, ev.action)
        if ev.query:
            label = f'{label}: «{ev.query}»'
        elif ev.content_type in ('movie', 'series', 'episode') and ev.object_id:
            label = f'{label} (شناسه {ev.object_id})'
        labels.append(label)
    return labels


def _recommendation_payload(request, data):
    ranked = []
    for entry in data['ranked']:
        serializer_class = (
            MovieListSerializer if entry['content_type'] == 'movie' else SeriesListSerializer
        )
        ranked.append({
            'content_type': entry['content_type'],
            'score': entry['score'],
            'reason': entry['reason'],
            'item': serializer_class(entry['item'], context={'request': request}).data,
        })
    return ranked


def _build_assistant_response(request, user, limit, optional_message=None):
    """Run the recommender, ask the LLM (with fallback), return the payload."""
    data = services.get_recommendations_for_user(user, limit=limit)
    picks = []
    for entry in data['ranked']:
        item = entry['item']
        picks.append({
            'content_type': entry['content_type'],
            'title': getattr(item, 'title', None),
            'reason': entry['reason'],
        })

    taste_summary = data.get('taste_summary') or {}
    recent = _recent_event_labels(user)

    used_ai = True
    message = optional_message
    try:
        if not message:
            message = llm.analyze_behavior(
                profile=None,
                taste_summary=taste_summary,
                recent_events=recent,
                picks=picks,
            )
    except RuntimeError as exc:
        used_ai = False
        message = _fallback_message(taste_summary, recent, picks, reason=str(exc))

    return {
        'message': message,
        'recommendations': _recommendation_payload(request, data),
        'taste_summary': taste_summary,
        'personalized': data.get('personalized', False),
        'confidence': data.get('confidence', 0),
        'signals_used': data.get('signals_used', 0),
        'model': (llm._config()['model'] if used_ai else None),
        'ai_available': used_ai,
    }


def _fallback_message(taste_summary, recent, picks, reason=None):
    """Deterministic Persian summary when the LLM is unavailable."""
    top_genres = [g.get('title') for g in taste_summary.get('top_genres', [])]
    playback = taste_summary.get('inferred_playback', 'any')
    completed = taste_summary.get('completed_count', 0)

    parts = ['سلام! بر اساس فعالیت‌های تماشای شما، سلیقه‌تان را این‌طور تشخیص دادم:']
    if top_genres:
        parts.append(f'ژانرهای مورد علاقه: {", ".join(top_genres)}.')
    else:
        parts.append('هنوز فعالیت کافی برای تشخیص ژانرهای مورد علاقه ثبت نشده است.')
    parts.append(f'نحوه تماشای ترجیحی: {playback}.')
    parts.append(f'تعداد آثار تمام‌شده: {completed}.')

    if picks:
        names = [
            p.get('title') or '?' for p in picks[:5]
            if p.get('content_type') in ('movie', 'series')
        ]
        if names:
            parts.append('پیشنهادهای برگزیده: ' + '، '.join(names) + '.')

    if reason:
        parts.append('(تحلیل هوشمند موقتاً در دسترس نیست؛ پیشنهادها بر اساس سلیقه‌ی شناخته‌شده نمایش داده می‌شوند.)')
    return ' '.join(parts)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def assistant_chat(request):
    try:
        limit = max(1, min(20, int(request.data.get('limit', 6))))
    except (TypeError, ValueError):
        limit = 6
    user_message = request.data.get('message') or None

    payload = _build_assistant_response(
        request, request.user, limit, optional_message=user_message
    )
    return Response(payload)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def assistant_insight(request):
    try:
        limit = max(1, min(20, int(request.GET.get('limit', 6))))
    except (TypeError, ValueError):
        limit = 6
    payload = _build_assistant_response(request, request.user, limit)
    return Response(payload)
