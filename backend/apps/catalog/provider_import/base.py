"""Base connector interface and shared data structures."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterator

from .sanitizers import sanitize_payload

__all__ = [
    'sanitize_payload',
    'ProviderAuthResult',
    'ProviderMovie',
    'ProviderSeries',
    'ProviderEpisode',
    'ProviderDownloadCandidate',
    'BaseProviderConnector',
]


@dataclass
class ProviderAuthResult:
    ok: bool
    message: str
    requires_interactive_verification: bool = False
    auth_type: str = ''
    sanitized_details: dict = field(default_factory=dict)

    def to_dict(self):
        data = asdict(self)
        data['sanitized_details'] = sanitize_payload(self.sanitized_details)
        data['message'] = sanitize_payload(self.message)
        return data


@dataclass
class ProviderMovie:
    provider_item_id: str
    title: str = ''
    original_title: str = ''
    year: int | None = None
    tmdb_id: int | None = None
    imdb_id: str = ''
    raw_payload: dict = field(default_factory=dict)

    def to_dict(self):
        data = asdict(self)
        data['raw_payload'] = sanitize_payload(self.raw_payload)
        return data


@dataclass
class ProviderSeries:
    provider_item_id: str
    title: str = ''
    original_title: str = ''
    year: int | None = None
    tmdb_id: int | None = None
    imdb_id: str = ''
    raw_payload: dict = field(default_factory=dict)

    def to_dict(self):
        data = asdict(self)
        data['raw_payload'] = sanitize_payload(self.raw_payload)
        return data


@dataclass
class ProviderEpisode:
    provider_item_id: str
    series_provider_id: str
    title: str = ''
    season_number: int | None = None
    episode_number: int | None = None
    tmdb_id: int | None = None
    imdb_id: str = ''
    raw_payload: dict = field(default_factory=dict)

    def to_dict(self):
        data = asdict(self)
        data['raw_payload'] = sanitize_payload(self.raw_payload)
        return data


@dataclass
class ProviderDownloadCandidate:
    provider_item_id: str
    content_type: str
    quality: str = ''
    format: str = ''
    size_bytes: int | None = None
    filename: str = ''
    content_type_header: str = ''
    url_or_reference: str = ''  # internal only — never serialize
    checksum: str = ''
    raw_payload: dict = field(default_factory=dict)

    def public_dict(self):
        return {
            'provider_item_id': self.provider_item_id,
            'content_type': self.content_type,
            'quality': self.quality,
            'format': self.format,
            'size_bytes': self.size_bytes,
            'filename': self.filename,
            'content_type_header': self.content_type_header,
            'checksum': self.checksum,
            'raw_payload': sanitize_payload(self.raw_payload),
        }


class BaseProviderConnector:
    slug = 'base'

    def __init__(self, provider_source):
        self.provider = provider_source

    def validate_credentials(self) -> ProviderAuthResult:
        raise NotImplementedError

    def validate_access(self) -> ProviderAuthResult:
        return self.validate_credentials()

    def authenticate(self) -> ProviderAuthResult:
        return self.validate_credentials()

    def list_movies(self, *, page: int = 1, since=None) -> list[ProviderMovie]:
        raise NotImplementedError

    def list_series(self, *, page: int = 1, since=None) -> list[ProviderSeries]:
        raise NotImplementedError

    def get_movie_detail(self, provider_item_id: str) -> ProviderMovie:
        raise NotImplementedError

    def get_series_detail(self, provider_item_id: str) -> ProviderSeries:
        raise NotImplementedError

    def get_download_candidates(self, provider_item_id: str, content_type: str) -> list[ProviderDownloadCandidate]:
        raise NotImplementedError

    def open_download_stream(self, candidate: ProviderDownloadCandidate) -> Iterator[bytes]:
        raise NotImplementedError
