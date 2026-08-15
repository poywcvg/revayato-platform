"""Provider import exceptions."""


class ProviderImportError(Exception):
    code = 'provider_import_error'

    def __init__(self, message, *, code=None):
        super().__init__(message)
        if code:
            self.code = code


class ProviderAuthError(ProviderImportError):
    code = 'provider_auth_error'


class ProviderCaptchaRequired(ProviderAuthError):
    code = 'provider_captcha_required'


class InteractiveVerificationRequired(ProviderCaptchaRequired):
    """CAPTCHA, Cloudflare interactive challenge, or MFA/OTP required."""

    code = 'interactive_verification_required'


class ProviderAccessDenied(ProviderAuthError):
    code = 'provider_access_denied'


class ProviderContractUnknown(ProviderImportError):
    code = 'provider_contract_unknown'


class ProviderRateLimited(ProviderImportError):
    code = 'provider_rate_limited'


class ProviderNotConfigured(ProviderImportError):
    code = 'provider_not_configured'


class UntrustedHostError(ProviderImportError):
    code = 'untrusted_host'


class JobCancelled(ProviderImportError):
    code = 'job_cancelled'
