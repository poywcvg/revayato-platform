import hashlib
import json

from django.core.cache import cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.catalog.cache import catalog_cache_version
from apps.catalog.serializers import MovieListSerializer, SeriesListSerializer

from . import services


def _preferences_from_request(request):
    raw = {
        'favorite_genres': request.GET.get('favorite_genres'),
        'disliked_genres': request.GET.get('disliked_genres'),
        'preferred_countries': request.GET.get('preferred_countries'),
        'preferred_languages': request.GET.get('preferred_languages'),
        'preferred_age_ratings': request.GET.get('preferred_age_ratings'),
        'playback_preference': request.GET.get('playback_preference'),
        'content_sensitivity': request.GET.get('content_sensitivity'),
    }
    # JSON body (optional) wins for richer clients.
    if hasattr(request, 'data') and isinstance(getattr(request, 'data', None), dict):
        body_prefs = request.data.get('preferences')
        if isinstance(body_prefs, dict):
            raw.update(body_prefs)
        else:
            for key in raw:
                if key in request.data:
                    raw[key] = request.data.get(key)
    return services.normalize_preferences(raw)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def recommendations(request):
    try:
        limit = max(1, min(50, int(request.GET.get('limit', 20))))
    except (TypeError, ValueError):
        limit = 20
    preferences = _preferences_from_request(request)
    preference_digest = hashlib.sha256(
        json.dumps(preferences, ensure_ascii=False, sort_keys=True).encode(),
    ).hexdigest()[:16]
    cache_key = (
        f'recommendations:v3:catalog-{catalog_cache_version()}:'
        f'user-{request.user.pk}:limit-{limit}:{preference_digest}'
    )
    cached = cache.get(cache_key)
    if cached is not None:
        response = Response(cached)
        response['Cache-Control'] = 'private, max-age=60'
        response['X-Recommendation-Cache'] = 'HIT'
        return response

    data = services.get_recommendations_for_user(
        request.user,
        limit=limit,
        preferences=preferences,
    )

    ranked = []
    for entry in data['ranked']:
        serializer_class = MovieListSerializer if entry['content_type'] == 'movie' else SeriesListSerializer
        ranked.append({
            'content_type': entry['content_type'],
            'score': entry['score'],
            'reason': entry['reason'],
            'item': serializer_class(entry['item'], context={'request': request}).data,
        })
    payload = {
        'personalized': data['personalized'],
        'confidence': data['confidence'],
        'signals_used': data['signals_used'],
        'taste_summary': data.get('taste_summary') or {},
        'recommendations': ranked,
        # Reuse the already serialized ranked entries rather than serializing
        # every selected object a second time for compatibility collections.
        'movies': [entry['item'] for entry in ranked if entry['content_type'] == 'movie'],
        'series': [entry['item'] for entry in ranked if entry['content_type'] == 'series'],
    }
    cache.set(cache_key, payload, timeout=180)
    response = Response(payload)
    response['Cache-Control'] = 'private, max-age=60'
    response['X-Recommendation-Cache'] = 'MISS'
    return response
