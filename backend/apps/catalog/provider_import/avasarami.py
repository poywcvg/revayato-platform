"""Avasarami licensed provider connector.

CAPTCHA-aware: never solves or bypasses CAPTCHA/MFA. Prefer official API token,
authorized cookie/session, or feed. Listing/download contracts remain explicit
until the provider documents a server-to-server API.
"""

from __future__ import annotations

import ssl
import time
import urllib.error
import urllib.request
from html import unescape
from typing import Iterator

from django.conf import settings

from .base import (
    BaseProviderConnector,
    ProviderAuthResult,
    ProviderDownloadCandidate,
    ProviderMovie,
    ProviderSeries,
    sanitize_payload,
)
from .exceptions import (
    ProviderCaptchaRequired,
    ProviderContractUnknown,
    ProviderNotConfigured,
    ProviderRateLimited,
)

CAPTCHA_MARKERS = (
    'captcha',
    'g-recaptcha',
    'hcaptcha',
    'h-captcha',
    'turnstile',
    'cf-turnstile',
    'data-sitekey',
    'recaptcha',
)

CAPTCHA_MESSAGE = (
    'Avasarami requires CAPTCHA/interactive verification. Request official API, '
    'server token, IP whitelist, export feed, or authorized long-lived session.'
)


class AvasaramiConnector(BaseProviderConnector):
    slug = 'avasarami'

    def __init__(self, provider_source):
        super().__init__(provider_source)
        cfg = provider_source.config or {}
        self.base_url = (
            cfg.get('base_url')
            or getattr(settings, 'AVASARAMI_BASE_URL', 'https://avasarami.top')
        ).rstrip('/')
        self.login_url = cfg.get('login_url') or getattr(
            settings, 'AVASARAMI_LOGIN_URL', f'{self.base_url}/sign-in/',
        )
        self.movies_url = cfg.get('movies_url') or getattr(
            settings, 'AVASARAMI_MOVIES_URL', f'{self.base_url}/movies/',
        )
        self.series_url = cfg.get('series_url') or getattr(
            settings, 'AVASARAMI_SERIES_URL', f'{self.base_url}/series/',
        )
        self.auth_type = (
            (provider_source.auth_type or getattr(settings, 'AVASARAMI_AUTH_TYPE', '') or 'none')
            .strip()
            .lower()
        )
        self.timeout = int(
            provider_source.timeout_seconds
            or getattr(settings, 'AVASARAMI_TIMEOUT_SECONDS', 30)
        )
        self.rate_limit = max(
            1,
            int(
                provider_source.rate_limit_per_minute
                or getattr(settings, 'AVASARAMI_RATE_LIMIT_PER_MINUTE', 30)
            ),
        )
        self.verify_ssl = bool(
            provider_source.verify_ssl
            if provider_source.verify_ssl is not None
            else getattr(settings, 'AVASARAMI_VERIFY_SSL', True)
        )
        self._last_request_at = 0.0

    def _env(self, name: str) -> str:
        return getattr(settings, f'AVASARAMI_{name}', '') or ''

    def _secret_status(self) -> dict:
        return {
            'auth_type': self.auth_type or 'none',
            'api_token_configured': bool(self._env('API_TOKEN')),
            'cookie_configured': bool(self._env('COOKIE')),
            'username_configured': bool(self._env('USERNAME')),
            'password_configured': bool(self._env('PASSWORD')),
        }

    def _throttle(self):
        min_interval = 60.0 / self.rate_limit
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_at = time.monotonic()

    def _ssl_context(self):
        if self.verify_ssl:
            return ssl.create_default_context()
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _request(self, url: str, *, method='GET', headers=None, data=None) -> tuple[int, str, dict]:
        self._throttle()
        req_headers = {
            'User-Agent': 'RevayatoProviderImporter/1.0 (+authorized-integration)',
            'Accept': 'text/html,application/json;q=0.9,*/*;q=0.8',
        }
        if headers:
            req_headers.update(headers)
        request = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout, context=self._ssl_context(),
            ) as response:
                body = response.read().decode('utf-8', errors='replace')
                return response.getcode(), body, dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace') if exc.fp else ''
            if exc.code == 429:
                raise ProviderRateLimited('Avasarami rate limit exceeded.') from exc
            return exc.code, body, dict(exc.headers.items()) if exc.headers else {}
        except urllib.error.URLError as exc:
            raise ProviderNotConfigured(f'Avasarami endpoint unreachable: {exc.reason}') from exc

    def detect_captcha(self, html: str) -> bool:
        text = unescape(html or '').lower()
        return any(marker in text for marker in CAPTCHA_MARKERS)

    def validate_credentials(self) -> ProviderAuthResult:
        secrets = self._secret_status()
        auth_type = self.auth_type
        if not auth_type or auth_type == 'none':
            # Infer from configured secrets.
            if secrets['api_token_configured']:
                auth_type = 'bearer_token'
            elif secrets['cookie_configured']:
                auth_type = 'cookie_session'
            elif secrets['username_configured'] or secrets['password_configured']:
                auth_type = 'username_password'
            else:
                return ProviderAuthResult(
                    ok=False,
                    message=(
                        'No Avasarami credentials configured. Set AVASARAMI_API_TOKEN, '
                        'AVASARAMI_COOKIE, or an authorized feed.'
                    ),
                    auth_type='none',
                    sanitized_details=secrets,
                )

        if auth_type in {'bearer_token', 'api_key'}:
            return self._validate_token(auth_type, secrets)
        if auth_type == 'cookie_session':
            return self._validate_cookie(secrets)
        if auth_type == 'feed':
            return ProviderAuthResult(
                ok=False,
                message='Avasarami feed URLs are not configured yet.',
                auth_type='feed',
                sanitized_details=secrets,
            )
        if auth_type == 'username_password':
            return self._validate_username_password(secrets)
        return ProviderAuthResult(
            ok=False,
            message=f'Unsupported Avasarami auth type: {auth_type}',
            auth_type=auth_type,
            sanitized_details=secrets,
        )

    def _validate_token(self, auth_type: str, secrets: dict) -> ProviderAuthResult:
        token = self._env('API_TOKEN')
        if not token:
            return ProviderAuthResult(
                ok=False,
                message='AVASARAMI_API_TOKEN is not set.',
                auth_type=auth_type,
                sanitized_details=secrets,
            )
        headers = {'Authorization': f'Bearer {token}'} if auth_type == 'bearer_token' else {
            'X-API-Key': token,
        }
        status, body, _ = self._request(self.movies_url, headers=headers)
        if status in {401, 403}:
            return ProviderAuthResult(
                ok=False,
                message='Avasarami rejected the configured API token.',
                auth_type=auth_type,
                sanitized_details={**secrets, 'http_status': status},
            )
        if status >= 500:
            return ProviderAuthResult(
                ok=False,
                message='Avasarami is temporarily unavailable.',
                auth_type=auth_type,
                sanitized_details={**secrets, 'http_status': status},
            )
        return ProviderAuthResult(
            ok=True,
            message='Avasarami API token accepted for authorized requests.',
            auth_type=auth_type,
            sanitized_details={**secrets, 'http_status': status, 'body_bytes': len(body)},
        )

    def _validate_cookie(self, secrets: dict) -> ProviderAuthResult:
        cookie = self._env('COOKIE')
        if not cookie:
            return ProviderAuthResult(
                ok=False,
                message='AVASARAMI_COOKIE is not set.',
                auth_type='cookie_session',
                sanitized_details=secrets,
            )
        status, body, _ = self._request(self.movies_url, headers={'Cookie': cookie})
        if status in {401, 403} or 'sign-in' in body.lower():
            return ProviderAuthResult(
                ok=False,
                message='Avasarami rejected the authorized session cookie.',
                auth_type='cookie_session',
                sanitized_details={**secrets, 'http_status': status},
            )
        return ProviderAuthResult(
            ok=True,
            message='Avasarami authorized cookie/session accepted.',
            auth_type='cookie_session',
            sanitized_details={**secrets, 'http_status': status},
        )

    def _validate_username_password(self, secrets: dict) -> ProviderAuthResult:
        status, body, _ = self._request(self.login_url)
        if self.detect_captcha(body):
            return ProviderAuthResult(
                ok=False,
                message=CAPTCHA_MESSAGE,
                requires_interactive_verification=True,
                auth_type='username_password',
                sanitized_details={**secrets, 'http_status': status, 'captcha_detected': True},
            )
        if not secrets['username_configured'] or not secrets['password_configured']:
            return ProviderAuthResult(
                ok=False,
                message='AVASARAMI_USERNAME / AVASARAMI_PASSWORD are incomplete.',
                auth_type='username_password',
                sanitized_details=secrets,
            )
        # CAPTCHA-free form login is rare; still refuse MFA-style pages.
        lower = body.lower()
        if any(token in lower for token in ('one-time', 'otp', '2fa', 'two-factor', 'mfa')):
            return ProviderAuthResult(
                ok=False,
                message=(
                    'Avasarami login requires MFA/OTP. Configure API token, authorized '
                    'cookie/session, or provider feed instead.'
                ),
                requires_interactive_verification=True,
                auth_type='username_password',
                sanitized_details={**secrets, 'mfa_detected': True},
            )
        return ProviderAuthResult(
            ok=False,
            message=(
                'Avasarami interactive username/password login is not enabled for automated '
                'imports. Prefer AVASARAMI_API_TOKEN or AVASARAMI_COOKIE.'
            ),
            requires_interactive_verification=True,
            auth_type='username_password',
            sanitized_details=secrets,
        )

    def authenticate(self) -> ProviderAuthResult:
        result = self.validate_credentials()
        if result.requires_interactive_verification:
            raise ProviderCaptchaRequired(result.message)
        if not result.ok:
            raise ProviderNotConfigured(result.message)
        return result

    def _auth_headers(self) -> dict:
        result = self.validate_credentials()
        if not result.ok:
            if result.requires_interactive_verification:
                raise ProviderCaptchaRequired(result.message)
            raise ProviderNotConfigured(result.message)
        headers = {}
        if result.auth_type == 'bearer_token':
            headers['Authorization'] = f'Bearer {self._env("API_TOKEN")}'
        elif result.auth_type == 'api_key':
            headers['X-API-Key'] = self._env('API_TOKEN')
        elif result.auth_type == 'cookie_session':
            headers['Cookie'] = self._env('COOKIE')
        return headers

    def list_movies(self, *, page: int = 1, since=None):
        self._auth_headers()
        raise ProviderContractUnknown(
            'Avasarami listing structure/API is not configured yet. '
            'Provide an official movies API/feed contract before discovery.'
        )

    def list_series(self, *, page: int = 1, since=None):
        self._auth_headers()
        raise ProviderContractUnknown(
            'Avasarami series listing structure/API is not configured yet. '
            'Provide an official series API/feed contract before discovery.'
        )

    def get_movie_detail(self, provider_item_id: str) -> ProviderMovie:
        raise ProviderContractUnknown('Avasarami movie detail API is not configured yet.')

    def get_series_detail(self, provider_item_id: str) -> ProviderSeries:
        raise ProviderContractUnknown('Avasarami series detail API is not configured yet.')

    def get_download_candidates(self, provider_item_id: str, content_type: str):
        raise ProviderContractUnknown('Avasarami download candidate API is not configured yet.')

    def open_download_stream(self, candidate: ProviderDownloadCandidate) -> Iterator[bytes]:
        if not candidate.url_or_reference:
            raise ProviderContractUnknown('Download reference missing.')
        headers = self._auth_headers()
        self._throttle()
        request = urllib.request.Request(
            candidate.url_or_reference,
            headers={
                'User-Agent': 'RevayatoProviderImporter/1.0 (+authorized-integration)',
                **headers,
            },
        )
        with urllib.request.urlopen(
            request, timeout=self.timeout, context=self._ssl_context(),
        ) as response:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk
