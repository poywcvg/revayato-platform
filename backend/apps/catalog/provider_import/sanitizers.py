"""Centralized redaction for provider import logs and API payloads.

Never log or serialize passwords, tokens, cookies, CSRF values, session IDs,
source download URLs, presigned URLs, or object-storage credentials.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

SENSITIVE_KEY_FRAGMENTS = (
    'password', 'passwd', 'secret', 'token', 'api_token', 'access_token',
    'authorization', 'cookie', 'cookies', 'set-cookie', 'csrf', 'nonce',
    'session', 'download_url', 'stream_url', 'file_url', 'signed_url',
    'presigned', 'source_reference', 'source_page', 'url_or_reference',
    'aws_secret', 'access_key', 'credential',
)

# Keys allowed even if they contain a fragment above (boolean flags only).
ALLOWLIST_KEYS = {
    'password_configured',
    'username_configured',
    'api_token_configured',
    'cookie_configured',
    'credentials_configured',
    'secret_configured',
}

SECRET_VALUE_PATTERNS = (
    re.compile(r'(?i)(authorization\s*[:=]\s*)(\S+)'),
    re.compile(r'(?i)(cookie\s*[:=]\s*)([^\s;]+)'),
    re.compile(r'(?i)(bearer\s+)([A-Za-z0-9\-._~+/]+=*)'),
    re.compile(r'(?i)(X-Amz-Signature=)([^&\s]+)'),
    re.compile(r'(?i)(AWSAccessKeyId=)([^&\s]+)'),
)

REDACTED = '[REDACTED]'


def looks_like_url(value: str) -> bool:
    try:
        parts = urlsplit(str(value))
    except Exception:
        return False
    return parts.scheme in {'http', 'https'} and bool(parts.netloc)


def redact_text(value: str, *, max_length=500) -> str:
    text = str(value or '')
    for pattern in SECRET_VALUE_PATTERNS:
        text = pattern.sub(rf'\1{REDACTED}', text)
    if looks_like_url(text) and any(
        token in text.lower()
        for token in ('download', 'stream', 'cdn', 'presign', 'signature', 'aws')
    ):
        return REDACTED
    return text[:max_length]


def sanitize_payload(value: Any, *, depth=0) -> Any:
    """Recursively drop or redact secrets and provider/media URLs."""
    if depth > 8:
        return None
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            key_s = str(key)
            key_l = key_s.lower()
            if key_l in ALLOWLIST_KEYS:
                cleaned[key_s] = bool(item) if not isinstance(item, bool) else item
                continue
            if any(fragment in key_l for fragment in SENSITIVE_KEY_FRAGMENTS):
                continue
            if key_l in {'url', 'href', 'link', 'src'} and isinstance(item, str) and looks_like_url(item):
                continue
            cleaned[key_s] = sanitize_payload(item, depth=depth + 1)
        return cleaned
    if isinstance(value, list):
        return [sanitize_payload(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact_text(str(value))


def secret_flags_from_settings(*, prefix: str) -> dict:
    """Return configured/missing booleans only — never secret values."""
    from django.conf import settings

    def present(name: str) -> bool:
        return bool(getattr(settings, f'{prefix}_{name}', '') or '')

    return {
        'api_token_configured': present('API_TOKEN'),
        'cookie_configured': present('COOKIE'),
        'username_configured': present('USERNAME'),
        'password_configured': present('PASSWORD'),
        'credentials_configured': present('API_TOKEN') or present('COOKIE') or (
            present('USERNAME') and present('PASSWORD')
        ),
    }
