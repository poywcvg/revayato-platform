import re

from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.catalog.serializers import MovieListSerializer, SeriesListSerializer

from . import services


@api_view(['GET'])
def recommendations(request):
    try:
        limit = max(1, min(50, int(request.GET.get('limit', 20))))
    except (TypeError, ValueError):
        limit = 20
    user = request.user if request.user.is_authenticated else None
    session_key = request.headers.get('X-Anonymous-Session-ID', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}', session_key):
        session_key = ''
    data = services.get_recommendations_for_user(user, limit=limit, session_key=session_key)

    ranked = []
    for entry in data['ranked']:
        serializer_class = MovieListSerializer if entry['content_type'] == 'movie' else SeriesListSerializer
        ranked.append({
            'content_type': entry['content_type'],
            'score': entry['score'],
            'reason': entry['reason'],
            'item': serializer_class(entry['item'], context={'request': request}).data,
        })
    return Response({
        'personalized': data['personalized'],
        'confidence': data['confidence'],
        'signals_used': data['signals_used'],
        'recommendations': ranked,
        'movies': MovieListSerializer(data['movies'], many=True, context={'request': request}).data,
        'series': SeriesListSerializer(data['series'], many=True, context={'request': request}).data,
    })
