import re
import time

from django.db import transaction
from django.utils import timezone

from config.public_urls import (
    download_quality_rank,
    media_url,
    public_download_links,
    resolve_download_href,
    signed_download_url,
)

from .models import WatchRoom, WatchRoomMember, WatchRoomPlaybackState

_SIDECAR_SUBTITLE_RE = re.compile(r'\.(vtt|webvtt|srt|ass|ssa)(?:$|\?)', re.I)


def _public_stream_url(value):
    """Preserve absolute CDN URLs; only rewrite relative object keys via media CDN."""
    raw = str(value or '').strip()
    if not raw:
        return ''
    if raw.startswith(('http://', 'https://', '//')):
        return raw
    return media_url(raw) or ''


def _link_row(url, *, label='', quality='', size_label='', kind='', subtitle_type=''):
    row = {
        'label': label or quality or 'پخش آنلاین',
        'quality': quality or '',
        'size_label': size_label or '',
        'url': url,
    }
    if kind:
        row['kind'] = kind
    if subtitle_type:
        row['subtitle_type'] = subtitle_type
    return row


def _dedupe_stream_links(rows):
    seen = set()
    unique = []
    for row in rows:
        url = str(row.get('url') or '').strip()
        if not url or url in seen or _SIDECAR_SUBTITLE_RE.search(url):
            continue
        seen.add(url)
        unique.append(row)
    return unique


def _episode_stream_links(episode):
    """Series download_links are scoped per episode; Episode itself has no download_links field."""
    series = episode.season.series
    season_no = getattr(episode.season, 'season_number', 1) or 1
    episode_no = episode.episode_number
    rows = []
    for item in public_download_links(series) or []:
        if not isinstance(item, dict):
            continue
        item_season = item.get('season_number')
        item_episode = item.get('episode_number')
        try:
            item_season = int(item_season) if item_season is not None and str(item_season).strip() != '' else None
            item_episode = int(item_episode) if item_episode is not None and str(item_episode).strip() != '' else None
        except (TypeError, ValueError):
            continue
        if item_season != season_no or item_episode != episode_no:
            continue
        url = str(item.get('url') or '').strip()
        if not url:
            continue
        rows.append(_link_row(
            url,
            label=item.get('label') or '',
            quality=item.get('quality') or '',
            size_label=item.get('size_label') or '',
            kind=item.get('kind') or '',
            subtitle_type=item.get('subtitle_type') or '',
        ))
    rows.sort(
        key=lambda row: (
            download_quality_rank(row.get('quality')),
            row.get('quality') or '',
            row.get('label') or '',
        ),
        reverse=True,
    )
    video = _public_stream_url(getattr(episode, 'video_url', None) or '')
    download = resolve_download_href(getattr(episode, 'download_key', None) or '') or ''
    extras = []
    if video:
        extras.append(_link_row(video, label='پخش آنلاین'))
    if download and download != video:
        extras.append(_link_row(download, label='دانلود'))
    return _dedupe_stream_links([*rows, *extras])


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


def playback_payload(state, *, stream_url=None, server_time_ms=None):
    payload = {
        'is_playing': state.is_playing,
        'position_seconds': state.position_seconds,
        'duration_seconds': state.duration_seconds,
        'playback_rate': state.playback_rate,
        'updated_by': public_user_payload(state.updated_by) if state.updated_by else None,
        'updated_at': state.updated_at.isoformat(),
        'server_time_ms': int(server_time_ms if server_time_ms is not None else time.time() * 1000),
    }
    if stream_url:
        payload['stream_url'] = stream_url
    return payload


def ephemeral_playback_payload(
    *,
    user,
    is_playing,
    position_seconds,
    duration_seconds,
    playback_rate,
    stream_url=None,
):
    """Broadcast host position without forcing a DB write on every heartbeat."""
    return {
        'is_playing': bool(is_playing),
        'position_seconds': float(position_seconds),
        'duration_seconds': float(duration_seconds),
        'playback_rate': float(playback_rate),
        'updated_by': public_user_payload(user) if user else None,
        'updated_at': timezone.now().isoformat(),
        'server_time_ms': int(time.time() * 1000),
        **({'stream_url': stream_url} if stream_url else {}),
    }


def resolve_stream_links(obj):
    """Prefer external download_links, then native video_url / download_key.

    Episodes store playable mirrors on the parent Series.download_links rows
    (scoped by season/episode). Absolute http(s) video URLs must stay intact —
    media_url() would strip the CDN host and 404 on the local media prefix.
    """
    from apps.catalog.models import Episode

    if isinstance(obj, Episode):
        return _episode_stream_links(obj)

    if hasattr(obj, 'download_links'):
        links = [
            row for row in (public_download_links(obj) or [])
            if isinstance(row, dict) and row.get('url') and not _SIDECAR_SUBTITLE_RE.search(str(row.get('url') or ''))
        ]
        if links:
            return links

    rows = []
    video = _public_stream_url(getattr(obj, 'video_url', None) or '')
    download = resolve_download_href(getattr(obj, 'download_key', None) or '') or ''
    quality = getattr(obj, 'quality', '') or ''
    if video:
        rows.append(_link_row(video, label=quality or 'پخش آنلاین', quality=quality))
    if download and download != video:
        rows.append(_link_row(download, label=quality or 'دانلود', quality=quality))
    return _dedupe_stream_links(rows)


def allowed_stream_urls(room):
    content = room.movie or room.episode
    if not content:
        return set()
    return {str(item.get('url') or '').strip() for item in resolve_stream_links(content) if item.get('url')}


def content_payload(room):
    if room.movie_id:
        movie = room.movie
        stream_links = resolve_stream_links(movie)
        primary = stream_links[0]['url'] if stream_links else None
        title = (movie.original_title or '').strip() or movie.title
        secondary = movie.title if title != movie.title else ''
        subtitle_tracks = []
        for track in (movie.subtitle_tracks or []):
            if not isinstance(track, dict):
                continue
            src = media_url(track.get('key') or track.get('src') or '')
            if not src:
                continue
            subtitle_tracks.append({
                'id': track.get('id') or track.get('language') or 'fa',
                'label': track.get('label') or 'فارسی',
                'language': track.get('language') or 'fa',
                'src': src,
                'default': bool(track.get('default', True)),
                **({'source_url': track['source_url']} if track.get('source_url') else {}),
            })
        return {
            'type': 'movie',
            'id': movie.pk,
            'slug': movie.slug,
            'title': title,
            'secondary_title': secondary,
            'description': movie.description,
            'duration_seconds': (movie.duration_minutes or 0) * 60,
            'video_url': primary,
            'stream_links': stream_links,
            'subtitle_tracks': subtitle_tracks,
            'download_url': signed_download_url(movie.download_key) or None,
            'poster_url': media_url(movie.poster) or None,
            'backdrop_url': media_url(movie.backdrop) or None,
            'age_rating': movie.age_rating,
            'is_uncensored': movie.is_uncensored,
        }
    episode = room.episode
    series = episode.season.series
    stream_links = resolve_stream_links(episode)
    primary = stream_links[0]['url'] if stream_links else None
    series_title = (series.original_title or '').strip() or series.title
    subtitle_tracks = []
    for track in (episode.subtitle_tracks or []):
        if not isinstance(track, dict):
            continue
        src = media_url(track.get('key') or track.get('src') or '')
        if not src:
            continue
        subtitle_tracks.append({
            'id': track.get('id') or track.get('language') or 'fa',
            'label': track.get('label') or 'فارسی',
            'language': track.get('language') or 'fa',
            'src': src,
            'default': bool(track.get('default', True)),
            **({'source_url': track['source_url']} if track.get('source_url') else {}),
        })
    return {
        'type': 'episode',
        'id': episode.pk,
        'slug': series.slug,
        'title': f'{series_title} · {episode.title}',
        'secondary_title': series.title if series_title != series.title else '',
        'description': episode.description,
        'duration_seconds': (episode.duration_minutes or 0) * 60,
        'video_url': primary,
        'stream_links': stream_links,
        'subtitle_tracks': subtitle_tracks,
        'download_url': signed_download_url(episode.download_key) or None,
        'poster_url': media_url(episode.poster) or None,
        'backdrop_url': media_url(series.backdrop) or None,
        'age_rating': series.age_rating,
        'is_uncensored': series.is_uncensored,
        'series': {
            'id': series.pk,
            'slug': series.slug,
            'title': series_title,
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
