"""The call a player makes right before it starts: "give me a URL that works."

Everything the client had before this endpoint was a URL captured whenever the
catalog page was last rendered. For most of this catalog that URL carries a
provider token that lapses in about thirteen hours, so the page could be fresh
and the link already dead — and the viewer discovered it as a silent failure
in a black <video>.

So the client asks once, at the moment of play, and gets back the URL that is
good *now*: normally the stored one, unchanged, for the cost of a string parse;
and when the token has lapsed, a re-signed one from a live provider crawl
(:mod:`playback_resolve`).

It is a POST because it can crawl, and it is throttled for the same reason.
"""

from __future__ import annotations

import logging

from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from apps.catalog.models import Episode, Movie, Series

logger = logging.getLogger(__name__)


class PlaybackResolveThrottle(AnonRateThrottle):
    """A refresh can cost a provider crawl; a viewer only needs one per play."""

    scope = 'playback_resolve'


def resolve_target(kind: str, obj_id: int):
    """``(owner, episode)`` for a published title, or ``(None, None)``.

    ``owner`` is whoever holds ``download_links`` — for an episode that is its
    series, not the episode itself.
    """
    kind = (kind or '').strip().lower()
    if not obj_id:
        return None, None
    if kind == 'movie':
        return Movie.objects.filter(pk=obj_id, is_published=True).first(), None
    if kind == 'series':
        return Series.objects.filter(pk=obj_id, is_published=True).first(), None
    if kind == 'episode':
        episode = (
            Episode.objects
            .filter(pk=obj_id, is_published=True)
            .select_related('season__series')
            .first()
        )
        if episode is None:
            return None, None
        return episode.season.series, episode
    return None, None


@api_view(['POST'])
@throttle_classes([PlaybackResolveThrottle])
def playback_resolve(request):
    """Return the playback URL for a title, re-signing it if it has lapsed."""
    from apps.catalog.playback_resolve import resolve_playback

    data = request.data if isinstance(request.data, dict) else {}
    kind = str(data.get('kind') or '').strip().lower()
    try:
        obj_id = int(data.get('id') or 0)
    except (TypeError, ValueError):
        obj_id = 0

    if kind not in {'movie', 'series', 'episode'} or not obj_id:
        return Response(
            {'ok': False, 'code': 'bad_request', 'detail': 'A title is required.'},
            status=400,
        )

    owner, episode = resolve_target(kind, obj_id)
    if owner is None:
        return Response(
            {'ok': False, 'code': 'not_found', 'detail': 'No such title.'}, status=404,
        )

    # ``allow_refresh`` lets the caller ask the cheap question on its own — the
    # detail page uses it to find out whether a link has lapsed without paying
    # for a crawl nobody asked for.
    allow_refresh = str(data.get('refresh', '1')).lower() not in {'0', 'false', 'no'}
    result = resolve_playback(owner, episode, allow_refresh=allow_refresh)

    payload = {'ok': bool(result.url), **result.as_dict()}
    if not result.url:
        payload['code'] = 'no_source'
    return Response(payload)
