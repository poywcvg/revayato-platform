"""Where the viewer is, and whether online playback can work from there.

The video files this catalogue points at live on Iranian CDNs that answer only
to Iranian addresses. From anywhere else the connection is dropped rather than
refused, so the player is told nothing at all — it just sits on a ``<video>``
that never starts, until its own startup watchdog gives up and reports "this
source did not start in time". That message is true and useless: the file is
fine, the link is fine, the viewer is abroad.

This endpoint exists so the page can say the real reason. Cloudflare already
resolves a country for every request it forwards to us, in ``CF-IPCountry``, so
the answer costs nothing here: no database, no geo table, no third party, and
no user data leaving the origin.

Unknown is never reported as blocked. A request whose country we cannot read is
far more likely to be an Iranian viewer behind something that strips the header
than a viewer abroad, and telling a local user they are abroad is worse than
saying nothing at all.
"""

from __future__ import annotations

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# Cloudflare's own placeholders. ``XX`` is "no country for this address" and
# ``T1`` is a Tor exit — neither says the viewer is abroad, so neither blocks.
UNKNOWN_COUNTRY_CODES = frozenset({'', 'XX', 'T1'})

# In trust order. Cloudflare sets the first on every request; the others let the
# same answer work behind a different edge without a code change.
_COUNTRY_HEADERS = ('CF-IPCountry', 'CloudFront-Viewer-Country', 'X-Geo-Country')


def _allowed_regions() -> frozenset:
    """Country codes online playback is expected to work from."""
    raw = getattr(settings, 'SITE_PLAYBACK_REGIONS', '') or 'IR'
    codes = {part.strip().upper() for part in raw.replace(';', ',').split(',')}
    return frozenset(code for code in codes if code) or frozenset({'IR'})


def viewer_country(request) -> str:
    """The viewer's ISO-3166 country, or ``''`` when no edge resolved one.

    Only read from headers the immediate peer set. Behind Cloudflare that peer
    is the edge and the value is authoritative; served directly it is absent,
    which resolves to unknown and therefore to no claim about the viewer.
    """
    for header in _COUNTRY_HEADERS:
        value = request.META.get('HTTP_' + header.upper().replace('-', '_'), '')
        code = str(value or '').strip().upper()[:2]
        if code and code not in UNKNOWN_COUNTRY_CODES:
            return code
    return ''


def playback_allowed_from(request) -> bool:
    """False only when the viewer's country is known *and* outside the set."""
    country = viewer_country(request)
    return not country or country in _allowed_regions()


@api_view(['GET'])
@permission_classes([AllowAny])
def playback_region(request):
    """Report the viewer's country and whether playback should work from it.

    Per-viewer by definition, so it must never be stored in a shared cache —
    one cached answer would tell every later viewer they are in the country of
    whoever happened to ask first.
    """
    country = viewer_country(request)
    response = Response({
        'country': country,
        'known': bool(country),
        'allowed': not country or country in _allowed_regions(),
        'regions': sorted(_allowed_regions()),
    })
    response['Cache-Control'] = 'no-store, private'
    response['Vary'] = 'CF-IPCountry'
    return response
