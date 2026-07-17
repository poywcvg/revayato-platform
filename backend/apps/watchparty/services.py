from django.db import transaction
from django.utils import timezone

from config.public_urls import media_url, signed_download_url

from .models import WatchRoom, WatchRoomMember, WatchRoomPlaybackState


def expire_room_if_needed(room):
    if room.status == WatchRoom.Status.ACTIVE and room.is_expired:
        room.status = WatchRoom.Status.EXPIRED
        room.save(update_fields=['status'])
        room.members.filter(is_online=True).update(is_online=False, last_seen_at=timezone.now())
    return room


def user_can_access_room_content(user, room):
    """Current entitlement boundary; replace publication checks when subscriptions land."""
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if room.movie_id:
        return bool(room.movie and room.movie.is_published)
    episode = room.episode
    return bool(
        episode
        and episode.is_published
        and episode.season.is_published
        and episode.season.series.is_published
    )


def public_user_payload(user):
    display_name = user.get_short_name() or user.username or f'کاربر {user.pk}'
    avatar = None
    try:
        profile = user.profile
        display_name = profile.display_name or display_name
    except Exception:
        pass
    try:
        if user.avatar:
            avatar = media_url(user.avatar)
    except (ValueError, AttributeError):
        avatar = None
    return {'id': user.pk, 'display_name': display_name, 'avatar': avatar}


def member_payload(member):
    return {
        'user': public_user_payload(member.user),
        'role': member.role,
        'joined_at': member.joined_at.isoformat(),
        'last_seen_at': member.last_seen_at.isoformat(),
        'is_online': member.is_online,
    }


def playback_payload(state):
    return {
        'is_playing': state.is_playing,
        'position_seconds': state.position_seconds,
        'duration_seconds': state.duration_seconds,
        'playback_rate': state.playback_rate,
        'updated_by': public_user_payload(state.updated_by) if state.updated_by else None,
        'updated_at': state.updated_at.isoformat(),
    }


def content_payload(room):
    if room.movie_id:
        movie = room.movie
        return {
            'type': 'movie',
            'id': movie.pk,
            'slug': movie.slug,
            'title': movie.title,
            'description': movie.description,
            'duration_seconds': (movie.duration_minutes or 0) * 60,
            'video_url': media_url(movie.video_url) or None,
            'download_url': signed_download_url(movie.download_key) or None,
            'poster_url': media_url(movie.poster) or None,
            'backdrop_url': media_url(movie.backdrop) or None,
            'age_rating': movie.age_rating,
            'is_uncensored': movie.is_uncensored,
        }
    episode = room.episode
    series = episode.season.series
    return {
        'type': 'episode',
        'id': episode.pk,
        'slug': series.slug,
        'title': f'{series.title} · {episode.title}',
        'description': episode.description,
        'duration_seconds': (episode.duration_minutes or 0) * 60,
        'video_url': media_url(episode.video_url) or None,
        'download_url': signed_download_url(episode.download_key) or None,
        'poster_url': media_url(episode.poster) or None,
        'backdrop_url': media_url(series.backdrop) or None,
        'age_rating': series.age_rating,
        'is_uncensored': series.is_uncensored,
        'series': {
            'id': series.pk,
            'slug': series.slug,
            'title': series.title,
            'season_number': episode.season.season_number,
            'episode_number': episode.episode_number,
        },
    }


def room_queryset():
    return WatchRoom.objects.select_related(
        'host_user', 'movie', 'episode__season__series', 'playback_state',
    ).prefetch_related('members__user')


def room_payload(room, user=None):
    membership = None
    if user and user.is_authenticated:
        membership = next((member for member in room.members.all() if member.user_id == user.pk), None)
    return {
        'invite_code': room.invite_code,
        'status': room.status,
        'host': public_user_payload(room.host_user),
        'content': content_payload(room),
        'created_at': room.created_at.isoformat(),
        'expires_at': room.expires_at.isoformat(),
        'member_count': len(room.members.all()),
        'is_host': bool(user and user.is_authenticated and room.host_user_id == user.pk),
        'is_member': membership is not None,
        'my_role': membership.role if membership else None,
    }


@transaction.atomic
def update_playback_state(room_id, user, *, is_playing, position_seconds, duration_seconds, playback_rate):
    state, _created = WatchRoomPlaybackState.objects.select_for_update().get_or_create(room_id=room_id)
    state.is_playing = is_playing
    state.position_seconds = position_seconds
    state.duration_seconds = duration_seconds
    state.playback_rate = playback_rate
    state.updated_by = user
    state.save()
    return state
