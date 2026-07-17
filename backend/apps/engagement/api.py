from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from . import selectors, services
from .serializers import (
    LikeToggleInputSerializer, RateContentInputSerializer, RatingSerializer,
    PrivacySafeEventInputSerializer, UserActivityEventSerializer, WatchlistItemSerializer,
    WatchlistToggleInputSerializer,
)


@api_view(['POST'])
@permission_classes([AllowAny])
def create_event(request):
    serializer = UserActivityEventSerializer(data=request.data)
    if serializer.is_valid():
        event = serializer.save(
            user=request.user if request.user.is_authenticated else None,
        )
        return Response(
            UserActivityEventSerializer(event).data,
            status=status.HTTP_201_CREATED,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def create_privacy_safe_event(request):
    """Accept only consented first-party signals; never derive device/network identity."""
    if request.headers.get('X-Personalization-Consent') != 'granted':
        return Response(
            {'detail': 'Explicit personalization consent is required.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    serializer = PrivacySafeEventInputSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    event = serializer.save(
        user=request.user if request.user.is_authenticated else None,
    )
    return Response({
        'id': event.id,
        'event_type': serializer.validated_data['event_type'],
        'accepted': True,
        'created_at': event.created_at,
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
def rating_summary(request):
    content_type = request.GET.get('content_type')
    object_id = request.GET.get('object_id')
    if not content_type or not object_id:
        return Response({'detail': 'content_type and object_id are required'}, status=status.HTTP_400_BAD_REQUEST)

    summary = selectors.get_rating_summary(content_type, object_id)
    my_rating = selectors.get_user_rating(request.user, content_type, object_id)
    summary['my_rating'] = RatingSerializer(my_rating).data if my_rating else None
    return Response(summary)


@api_view(['POST', 'DELETE'])
@permission_classes([IsAuthenticated])
def rate_content(request):
    if request.method == 'DELETE':
        input_serializer = LikeToggleInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data
        services.remove_rating(request.user, data['content_type'], data['object_id'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    input_serializer = RateContentInputSerializer(data=request.data)
    input_serializer.is_valid(raise_exception=True)
    data = input_serializer.validated_data
    rating = services.rate_content(
        user=request.user,
        content_type=data['content_type'],
        object_id=data['object_id'],
        score=data['score'],
        review=data.get('review', ''),
        is_spoiler=data.get('is_spoiler', False),
    )
    return Response(RatingSerializer(rating).data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def watchlist_list(request):
    list_type = request.GET.get('list_type')
    queryset = selectors.get_user_watchlist(request.user, list_type=list_type)
    return Response(WatchlistItemSerializer(queryset, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def watchlist_toggle(request):
    input_serializer = WatchlistToggleInputSerializer(data=request.data)
    input_serializer.is_valid(raise_exception=True)
    data = input_serializer.validated_data
    added = services.toggle_watchlist(
        user=request.user,
        content_type=data['content_type'],
        object_id=data['object_id'],
        list_type=data['list_type'],
    )
    return Response({'added': added})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def like_toggle(request):
    input_serializer = LikeToggleInputSerializer(data=request.data)
    input_serializer.is_valid(raise_exception=True)
    data = input_serializer.validated_data
    liked = services.toggle_like(
        user=request.user,
        content_type=data['content_type'],
        object_id=data['object_id'],
    )
    return Response({'liked': liked})
