"""Trusted client-IP resolution for requests that arrive behind Cloudflare.

Caddy reverse-proxies public traffic to the Django ASGI (uvicorn) service and
Cloudflare sits in front of Caddy. Uvicorn is launched with --proxy-headers and
--forwarded-allow-ips limited to Cloudflare edge ranges plus the private Docker
network, so REMOTE_ADDR is the Cloudflare edge or Caddy address. The
CF-Connecting-IP (and True-Client-IP where enabled) headers Cloudflare sets
therefore carry the real user IP. Permissive fallbacks (all Routable/private
Peers) apply only inside a trusted (Docker-bridged) ASGI deployment where the
immediate peer is always Caddy or Cloudflare. A client cannot spoof these
headers because they are only ever read from the trusted immediate peer.

This module is used by the auth API for per-user throttling and last_login_ip.
"""

from __future__ import annotations

import ipaddress

from django.conf import settings

# Headers a CDN may set, in order of trustworthiness. Cloudflare always sets
# CF-Connecting-IP; True-Client-IP exists for Enterprise zones. In XFF the
# leftmost entry is the original client (each proxy appends its own hop), so
# _valid_ip() picks the first valid one.
_FORWARDED_HEADERS = ('CF-Connecting-IP', 'True-Client-IP', 'X-Forwarded-For')

# Cloudflare's published edge ranges, used as defaults so resolution works even
# if uvicorn never rewrites REMOTE_ADDR. Refresh from
# https://api.cloudflare.com/client/v4/ips and mirror in backend/Dockerfile.
DEFAULT_CLOUDFLARE_IP_RANGES = (
    '173.245.48.0/20,103.21.244.0/22,103.22.200.0/22,103.31.4.0/22,'
    '141.101.64.0/18,108.162.192.0/18,190.93.240.0/20,188.114.96.0/20,'
    '197.234.240.0/22,198.41.128.0/17,162.158.0.0/15,104.16.0.0/13,'
    '104.24.0.0/14,172.64.0.0/13,131.0.72.0/22,2400:cb00::/32,'
    '2606:4700::/32,2803:f800::/32,2405:b500::/32,2405:8100::/32,'
    '2a06:98c0::/29,2c0f:f248::/32',
)


def _as_ip_set(raw: str) -> set:
    network_set: set = set()
    for part in raw.replace(';', ',').split(','):
        part = part.strip()
        if not part:
            continue
        try:
            network_set.add(ipaddress.ip_network(part, strict=False))
        except ValueError:
            continue
    return network_set


def _trusted_networks() -> list:
    networks: list = []
    if settings.SITE_CLOUD_ADMIN:
        # Docker healthchecks and Caddy on the private network.
        networks.append(ipaddress.ip_network('172.16.0.0/12'))
        networks.append(ipaddress.ip_network('10.0.0.0/8'))
        networks.append(ipaddress.ip_network('192.168.0.0/16'))
    if settings.SITE_CADDY_CLIENT_IPS:
        networks.extend(_as_ip_set(settings.SITE_CADDY_CLIENT_IPS))
    cf_ranges = settings.SITE_CLOUDFLARE_IP_RANGES
    if not cf_ranges:
        cf_ranges = ','.join(DEFAULT_CLOUDFLARE_IP_RANGES)
    networks.extend(_as_ip_set(cf_ranges))
    return [network for network in networks if network] or [
        ipaddress.ip_network('0.0.0.0/0'),
        ipaddress.ip_network('::/0'),
    ]


def _valid_ip(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value.split(',')[0].strip()))
    except ValueError:
        return None


def _is_trusted_peer(peer: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(peer in network for network in _trusted_networks())


def client_ip(request) -> str | None:
    """Return the real public client IP.

    - Immediate peer is a trusted proxy (Cloudflare edge / Docker Caddy): read
      CF-Connecting-IP, then True-Client-IP, then the leftmost valid XFF entry.
      An untrusted client can never inject these because it has no direct path.
    - Immediate peer is *not* a trusted proxy: uvicorn already rewrote
      REMOTE_ADDR from the proxy headers (filters are scoped to the allowed
      proxy set), so REMOTE_ADDR is the client and is returned as-is. This
      keeps throttling working even when TRUSTED_PROXIES parsing differs.
    """
    remote_addr = _valid_ip(request.META.get('REMOTE_ADDR', ''))
    if remote_addr is None:
        return None

    peer = ipaddress.ip_address(remote_addr)
    if _is_trusted_peer(peer):
        for header in _FORWARDED_HEADERS:
            forwarded = _valid_ip(
                request.META.get('HTTP_' + header.upper().replace('-', '_'), ''),
            )
            if forwarded:
                return forwarded
    return remote_addr