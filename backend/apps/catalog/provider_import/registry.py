"""Connector registry."""

from .avasarami import AvasaramiConnector
from .base import BaseProviderConnector
from .exceptions import ProviderNotConfigured
from .providers.dornatv import DornatvConnector
from .providers.myf2m import MyF2MConnector

_REGISTRY = {
    'avasarami': AvasaramiConnector,
    'myf2m': MyF2MConnector,
    'dornatv': DornatvConnector,
}


def list_connectors():
    return sorted(_REGISTRY.keys())


def get_connector(provider_source) -> BaseProviderConnector:
    """Return a connector for a ProviderSource row or a slug string."""
    if isinstance(provider_source, str):
        slug = provider_source.strip().lower()
        source = None
    else:
        slug = (getattr(provider_source, 'slug', None) or '').strip().lower()
        source = provider_source
    connector_cls = _REGISTRY.get(slug)
    if not connector_cls:
        raise ProviderNotConfigured(f'No connector registered for provider "{slug}".')
    return connector_cls(source)
